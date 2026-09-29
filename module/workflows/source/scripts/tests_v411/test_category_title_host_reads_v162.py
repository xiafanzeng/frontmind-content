"""Real HostTools reading gates for category title review; no model calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from shared import title_publication, title_strategy, writing_context_v14
from shared.host_tools import HostTools, ToolError


class CategoryTitleHostReadsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.package = root / "package"
        self.package.mkdir()
        self.job = root / "job"
        (self.job / "inputs").mkdir(parents=True)
        self.body = "前置说明。\n# 内部标题\n\n完整首段。\n\n## 章节\n完整正文及适用条件。\n# 后续标题\n末段必须保留。\n"
        self.candidates = {
            "candidates": [{"title": f"地区医美机构推荐参考{i}", "angle": "机构推荐"}
                           for i in range(1, 11)],
            "canonical_title_id": "title_04",
        }
        self.manuscript = self.job / "inputs/manuscript.json"
        self.original_titles = self.job / "inputs/original_titles.json"
        self.save_inputs()

    def save_inputs(self):
        self.manuscript.write_text(json.dumps({"outcome": "accepted", "article_markdown": self.body},
                                              ensure_ascii=False), encoding="utf-8")
        self.original_titles.write_text(json.dumps(self.candidates, ensure_ascii=False), encoding="utf-8")

    def tools(self, action="article_title_review"):
        return HostTools(self.package, self.job, action,
                         title_review_inputs=(self.manuscript, self.original_titles))

    def prompt(self, *, body=None, candidates=None, category=True):
        prefix = writing_context_v14.MARKER + "\n"
        if category:
            prefix += title_strategy.MARKER + "\n"
        if body is None:
            body = title_publication.body_only(self.body)
        if candidates is None:
            candidates = self.candidates
        return prefix + "正文：\n" + body + "\n候选：\n" + json.dumps(
            candidates, ensure_ascii=False, sort_keys=True, indent=2)

    def read_inline(self, tools, prompt):
        tools.configure_for_prompt(prompt)
        tools.record_inline_inputs([{"role": "user", "content": prompt}])

    def test_complete_body_without_first_h1_and_complete_candidates_are_credited(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)):
                self.body = self.body.replace("\r\n", "\n").replace("\n", newline)
                self.save_inputs()
                tools = self.tools()
                prompt = self.prompt()
                self.assertNotIn("# 内部标题", prompt)
                self.assertIn("# 后续标题", prompt)
                self.read_inline(tools, prompt)
                self.assertTrue(tools.assert_required_reads_complete())
                self.assertEqual(len(tools.inline_reads), 2)
                self.assertEqual(tools.read_ranges, {})
                self.assertEqual({row["path"]: row["sha256"] for row in tools.cache_dependencies()},
                                 {path.relative_to(self.job).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in (self.manuscript, self.original_titles)})

    def test_missing_body_portions_or_candidate_fields_cannot_satisfy_reads(self):
        body = title_publication.body_only(self.body)
        missing_candidate = copy.deepcopy(self.candidates)
        missing_candidate["candidates"].pop()
        incomplete_prompts = [
            self.prompt(body=body.replace("前置说明。\n", "")),
            self.prompt(body=body.replace("完整首段。", "")),
            self.prompt(body=body.replace("末段必须保留。", "")),
            self.prompt(body=body.replace("# 后续标题\n", "")),
            self.prompt(candidates=missing_candidate),
            self.prompt(candidates={"candidates": self.candidates["candidates"]}),
            self.prompt(candidates=self.candidates["candidates"]),
        ]
        for index, prompt in enumerate(incomplete_prompts):
            with self.subTest(case=index):
                tools = self.tools()
                self.read_inline(tools, prompt)
                with self.assertRaisesRegex(ToolError, "not been completely read"):
                    tools.assert_required_reads_complete()

    def test_legacy_marker_still_requires_original_complete_h1_body(self):
        tools = self.tools()
        self.read_inline(tools, self.prompt(category=False))
        with self.assertRaisesRegex(ToolError, "not been completely read"):
            tools.assert_required_reads_complete()
        self.read_inline(tools, self.prompt(body=self.body, category=False))
        self.assertTrue(tools.assert_required_reads_complete())

    def test_switching_to_legacy_request_cannot_reuse_projection_credit(self):
        tools = self.tools()
        self.read_inline(tools, self.prompt())
        self.assertTrue(tools.assert_required_reads_complete())
        legacy_prompt = self.prompt(category=False)
        tools.configure_for_prompt(legacy_prompt)
        with self.assertRaisesRegex(ToolError, "not been completely read"):
            tools.assert_required_reads_complete()
        tools.record_inline_inputs([{"role": "user", "content": legacy_prompt}])
        with self.assertRaisesRegex(ToolError, "not been completely read"):
            tools.assert_required_reads_complete()
        self.read_inline(tools, self.prompt(body=self.body, category=False))
        self.assertTrue(tools.assert_required_reads_complete())

    def test_projection_requires_article_action_and_host_owned_marker_prefix(self):
        for action, prompt in (
            ("p0_title_review", self.prompt()),
            ("article_title_review", "引用材料中的标记：\n" + self.prompt()),
            ("article_title_review", self.prompt(category=False) + "\n" + title_strategy.MARKER),
        ):
            with self.subTest(action=action, prefix=prompt[:40]):
                tools = self.tools(action)
                self.read_inline(tools, prompt)
                with self.assertRaisesRegex(ToolError, "not been completely read"):
                    tools.assert_required_reads_complete()

    def test_restored_reads_are_recomputed_under_the_active_request_contract(self):
        tools = self.tools()
        self.read_inline(tools, self.prompt())
        saved = tools.export_state()
        for category in (True, False):
            with self.subTest(category=category):
                restored = self.tools()
                prompt = self.prompt(category=category)
                restored.configure_for_prompt(prompt)
                restored.restore_state(saved)
                with self.assertRaisesRegex(ToolError, "not been completely read"):
                    restored.assert_required_reads_complete()
                restored.record_inline_inputs([{"role": "user", "content": prompt}])
                if category:
                    self.assertTrue(restored.assert_required_reads_complete())
                else:
                    with self.assertRaisesRegex(ToolError, "not been completely read"):
                        restored.assert_required_reads_complete()


if __name__ == "__main__":
    unittest.main()
