from unittest.mock import patch
from scripts.tests_v411.historical_profiles import historical_profile
"""Offline title-review source isolation, read gates and original file hashes.

All manuscripts, candidates and Responses events here are synthetic fixtures;
these checks do not evaluate real provider headline quality.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from shared.host_tools import HostTools, ToolError
from shared import model_runtime as runtime
from scripts.tests_v411.test_responses_runtime_v4116 import native


class HostTitleReviewTests(unittest.TestCase):
    def setUp(self):
        archived=patch.object(runtime, "profile_for", side_effect=historical_profile)
        archived.start(); self.addCleanup(archived.stop)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.package = root / "package"
        self.package.mkdir()
        self.job = root / "job"
        self.job.mkdir()
        self.body = "# 合成内部稿标识\n\n完整首段。\n\n## 章节\n完整正文，末句保留项目适用条件。\n"
        self.titles = {
            "candidates": [{"title": f"合成候选{index}", "angle": f"合成角度{index}"}
                           for index in range(1, 21)],
            "canonical_title_id": "title_03",
        }

    def save(self, relative, value):
        path = self.job / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def inputs(self, prefix="p0"):
        manuscript = self.save(f"production/{prefix}_finalized.json",
                               {"outcome": "accepted", "article_markdown": self.body})
        titles = self.save(f"production/{prefix}_titles.json", self.titles)
        return manuscript, titles

    def tools(self, prefix="p0", **kwargs):
        return HostTools(self.package, self.job, prefix + "_title_review", **kwargs)

    def complete_prompt(self):
        return ("完整正文，内部H1仅作来源标识：\n" + self.body + "\n原始候选完整JSON：\n" +
                json.dumps(self.titles, ensure_ascii=False, sort_keys=True, indent=2))

    def test_both_actions_register_only_two_required_inputs_and_local_read_tools(self):
        # Deliberately invalid upstream data would fail if title review tried
        # to reconstruct a Pack, selected examples or a manuscript rerun.
        self.save("answers/first_answer.json", {"answer": "unrelated upstream answer"})
        self.save("examples/p0/index.json", {"examples": [{"artifact_id": "not-an-example"}]})
        self.save("examples/question/index.json", {"examples": [{"artifact_id": "not-an-example"}]})
        self.save("job_state.json", {"selected_example_route": "top20"})
        pack = self.job / "00_input/reference_pack.zip"
        pack.parent.mkdir()
        pack.write_bytes(b"not-a-pack")
        for prefix in ("p0", "article"):
            with self.subTest(prefix=prefix):
                paths = self.inputs(prefix)
                tools = self.tools(prefix)
                inventory = tools.execute("list_materials", {})
                self.assertEqual(inventory["total"], 2)
                self.assertEqual(len(inventory["required_artifacts"]), 2)
                self.assertEqual({row["path"] for row in inventory["artifacts"]},
                                 {path.relative_to(self.job).as_posix() for path in paths})
                self.assertEqual({item["function"]["name"] for item in tools.definitions},
                                 {"list_materials", "read_material", "search_materials"})
                for name in ("web_search", "web_read", "ocr", "extract_document"):
                    with self.assertRaisesRegex(ToolError, "not permitted"):
                        tools.execute(name, {})
                with self.assertRaises(ToolError):
                    tools.register_file(self.job / "answers/first_answer.json")
                self.assertEqual(tools.execute("search_materials", {"query": "unrelated upstream"})["total_matches"], 0)
                self.assertEqual({row["path"]: row["sha256"] for row in tools.cache_dependencies()},
                                 {path.relative_to(self.job).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in paths})

    def test_complete_inline_sources_allow_submit_with_raw_or_canonical_json(self):
        for prefix in ("p0", "article"):
            _, path = self.inputs(prefix)
            for raw in (path.read_text(encoding="utf-8"),
                        json.dumps(self.titles, ensure_ascii=False, sort_keys=True, indent=2)):
                with self.subTest(prefix=prefix, representation=raw[:30]):
                    tools = self.tools(prefix)
                    tools.record_inline_inputs([{"role": "user", "content": self.body + "\n" + raw}])
                    self.assertTrue(tools.assert_required_reads_complete())
                    self.assertEqual(len(tools.inline_reads), 2)
                    self.assertEqual(tools.read_ranges, {})
                    for row in tools.cache_dependencies():
                        self.assertEqual(row["sha256"], hashlib.sha256((self.job / row["path"]).read_bytes()).hexdigest())

    def test_missing_or_partial_inline_body_or_original_candidates_cannot_submit(self):
        self.inputs()
        serialized = json.dumps(self.titles, ensure_ascii=False, sort_keys=True, indent=2)
        only_candidates = json.dumps(self.titles["candidates"], ensure_ascii=False, sort_keys=True, indent=2)
        for prompt in (self.body, serialized, self.body[:-12] + "\n" + serialized,
                       self.body + "\n" + only_candidates,
                       self.body + "\n" + "\n".join(row["title"] for row in self.titles["candidates"])):
            with self.subTest(prompt=prompt[:20]):
                tools = self.tools()
                tools.record_inline_inputs([{"role": "user", "content": prompt}])
                with self.assertRaisesRegex(ToolError, "not been completely read"):
                    tools.assert_required_reads_complete()

    def test_search_and_partial_pages_do_not_replace_full_reads(self):
        self.inputs()
        tools = self.tools()
        tools.execute("search_materials", {"query": "合成"})
        for row in tools.artifacts.values():
            tools.execute("read_material", {"artifact_id": row["artifact_id"], "limit": 10})
        with self.assertRaises(ToolError):
            tools.assert_required_reads_complete()
        for row in tools.artifacts.values():
            offset = 0
            while True:
                page = tools.execute("read_material", {"artifact_id": row["artifact_id"], "offset": offset, "limit": 100})
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
        self.assertTrue(tools.assert_required_reads_complete())

    def test_missing_and_malformed_input_errors_identify_the_required_file(self):
        for prefix in ("p0", "article"):
            paths = self.inputs(prefix)
            for path in paths:
                original = path.read_bytes()
                path.unlink()
                with self.subTest(prefix=prefix, file=path.name), self.assertRaisesRegex(ToolError, path.name):
                    self.tools(prefix)
                path.write_bytes(original)
        manuscript, titles = self.inputs()
        for path, value in ((manuscript, {}), (manuscript, {"article_markdown": " "}),
                            (manuscript, "JSON scalar is not article_markdown"),
                            (titles, []), (titles, {})):
            original = path.read_bytes()
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(value=value), self.assertRaisesRegex(ToolError, path.name):
                self.tools()
            path.write_bytes(original)
        titles.write_text("{malformed JSON", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "original title candidates.*valid.*p0_titles.json"):
            self.tools()

    def test_supplied_inputs_need_no_manufactured_production_history(self):
        manuscript = self.job / "inputs/supplied_manuscript.md"
        manuscript.parent.mkdir()
        manuscript.write_text(self.body, encoding="utf-8")
        titles = self.save("inputs/original_deepseek_titles.json", self.titles)
        for prefix in ("p0", "article"):
            with self.subTest(prefix=prefix):
                tools = self.tools(prefix, title_review_inputs=(manuscript, titles))
                tools.record_inline_inputs([{"role": "user", "content": self.complete_prompt()}])
                self.assertTrue(tools.assert_required_reads_complete())
                self.assertEqual({row["path"] for row in tools.cache_dependencies()},
                                 {"inputs/supplied_manuscript.md", "inputs/original_deepseek_titles.json"})
        self.assertFalse((self.job / "production").exists())
        with self.assertRaisesRegex(ToolError, "only supported"):
            HostTools(self.package, self.job, "p0_finalize", title_review_inputs=(manuscript, titles))
        outside = self.package / "outside.md"
        outside.write_text(self.body, encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "safe final manuscript"):
            self.tools(title_review_inputs=(outside, titles))
        linked = self.job / "inputs/linked.md"
        linked.symlink_to(outside)
        with self.assertRaisesRegex(ToolError, "safe final manuscript"):
            self.tools(title_review_inputs=(linked, titles))

    def test_changed_sources_invalidate_inline_reads_and_saved_dependencies(self):
        for index in (0, 1):
            with self.subTest(input_index=index):
                paths = self.inputs()
                tools = self.tools()
                tools.record_inline_inputs([{"role": "user", "content": self.complete_prompt()}])
                saved = tools.export_state()
                path = paths[index]
                path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                with self.assertRaises(ToolError):
                    tools.assert_required_reads_complete()
                with self.assertRaisesRegex(ToolError, "dependency changed"):
                    self.tools().restore_state(saved)

    def test_native_offline_submission_needs_both_complete_sources(self):
        # Exercise the actual single-action submit gate using synthetic native
        # Responses events, with no network and no upstream production claims.
        manuscript = self.job / "inputs/supplied_manuscript.md"
        manuscript.parent.mkdir()
        manuscript.write_text(self.body, encoding="utf-8")
        titles = self.save("inputs/original_deepseek_titles.json", self.titles)
        serialized = json.dumps(self.titles, ensure_ascii=False, sort_keys=True, indent=2)
        for prefix, prompt, succeeds in (("p0", self.body, False), ("article", serialized, False),
                                         ("p0", self.complete_prompt(), True)):
            calls = []
            def transport(*args):
                calls.append(args)
                return native(name="submit_result", arguments={"result": self.titles})
            tools = self.tools(prefix, title_review_inputs=(manuscript, titles))
            def run():
                return runtime.run_action(self.package, self.job, prefix + "_title_review", prompt,
                                          lambda value: value, host_tools=tools, transport=transport, offline=True)
            with self.subTest(prefix=prefix, succeeds=succeeds):
                if succeeds:
                    result = run()
                    self.assertEqual(result, self.titles)
                else:
                    with self.assertRaises(runtime.ProviderActionError) as error:
                        run()
                    self.assertEqual(error.exception.code, "invalid_result_contract")
                    self.assertIn("not been completely read", str(error.exception))
                self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
