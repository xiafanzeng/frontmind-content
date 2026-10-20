"""Frozen 5+5 publication policy, real controller gates and legacy requests.

All inputs are synthetic; these tests make no network or model calls.
"""
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as wf
from scripts.tests_v411 import test_title_input_scope_final13 as scope
from scripts.tests_v411 import test_category_title_host_reads_v162 as host_reads
from shared import manuscript_revision, model_runtime, title_strategy, writing_context
from shared import title_publication as publication, writing_context_v14 as context


def titles(*, grouped=True, count=10, canonical="title_08"):
    rows = [{"title": f"合成品类推荐与需求参考{i}", "angle": "同主题表达"}
            for i in range(1, count + 1)]
    if grouped:
        for index, row in enumerate(rows):
            row["style"] = "formal" if index < 5 else "scenario"
    return {"candidates": rows, "canonical_title_id": canonical}


def review(raw):
    return {"outcome": "accepted", **copy.deepcopy(raw), "title_notes": [], "reason": ""}


class GroupedTitleContractTests(unittest.TestCase):
    def test_style_and_any_canonical_choice_survive_artifact_and_review_round_trips(self):
        for selected in ("title_01", "title_05", "title_06", "title_10"):
            raw = titles(canonical=selected)
            normalized = publication.validate_title_map(raw, expected_policy=title_strategy.DEFAULT)
            self.assertEqual(normalized["title_strategy"], title_strategy.DEFAULT)
            self.assertEqual([row["style"] for row in normalized["options"]], list(title_strategy.STYLE_SEQUENCE))
            self.assertEqual(normalized["families"]["article"]["options"], normalized["options"])
            self.assertEqual(normalized["recommended_title_id"], selected)
            self.assertEqual(publication.validate_title_map(normalized, expected_policy=title_strategy.DEFAULT), normalized)
            self.assertEqual(publication.validate_title_map(normalized), normalized)
            self.assertEqual(publication.title_review_input(normalized, p0=False), raw)
            self.assertEqual(publication.validate_title_review_result(review(raw), normalized, p0=False,
                                                                       expected_policy=title_strategy.DEFAULT), review(raw))

    def test_frozen_policy_rejects_missing_style_four_six_six_four_and_reordering(self):
        invalid = []
        missing_all = titles(grouped=False)
        missing_one = titles(); del missing_one["candidates"][7]["style"]
        four_six = titles(); four_six["candidates"][4]["style"] = "scenario"
        six_four = titles(); six_four["candidates"][5]["style"] = "formal"
        reordered = titles(); reordered["candidates"][0], reordered["candidates"][9] = reordered["candidates"][9], reordered["candidates"][0]
        unknown = titles(); unknown["candidates"][7]["style"] = "lively"
        invalid.extend([missing_all, missing_one, four_six, six_four, reordered, unknown,
                        titles(count=9), titles(count=11), titles(grouped=False, count=20)])
        for index, raw in enumerate(invalid):
            with self.subTest(case=index):
                with self.assertRaises(ValueError):
                    publication.validate_title_map(raw, expected_policy=title_strategy.DEFAULT)
                with self.assertRaises(ValueError):
                    publication.publication("# 内部标题\n正文", raw, p0=False,
                                            expected_policy=title_strategy.DEFAULT)
                with self.assertRaises(ValueError):
                    publication.validate_title_review_result(review(raw), titles(), p0=False,
                                                              expected_policy=title_strategy.DEFAULT)

    def test_expected_policy_is_not_guessed_from_the_result(self):
        with self.assertRaises(ValueError):
            publication.validate_title_map(titles(grouped=False), expected_count=10,
                                           expected_policy=title_strategy.DEFAULT)
        with self.assertRaises(ValueError):
            publication.validate_title_map(titles(), expected_count=20, expected_policy=title_strategy.DEFAULT)
        with self.assertRaises(ValueError):
            publication.validate_title_map(titles(), expected_policy=title_strategy.LEGACY_POLICY)
        with self.assertRaises(ValueError):
            publication.validate_title_map(titles(), p0=True, expected_policy=title_strategy.DEFAULT)
        publication.validate_title_map(titles(grouped=False), expected_policy=title_strategy.LEGACY_POLICY)
        publication.validate_title_map(titles(grouped=False, count=20), expected_count=20)

    def test_normalized_artifact_cannot_lose_or_disagree_about_its_styles(self):
        original = publication.validate_title_map(titles(), expected_policy=title_strategy.DEFAULT)
        mutations = (
            lambda item: item["options"][1].update(style="scenario"),
            lambda item: item["families"]["article"]["options"][1].update(style="scenario"),
            lambda item: item.pop("title_strategy"),
            lambda item: item.update(title_strategy=title_strategy.LEGACY_POLICY),
        )
        for change in mutations:
            value = copy.deepcopy(original)
            value["families"]["article"]["options"] = copy.deepcopy(value["options"])
            change(value)
            with self.assertRaises(ValueError):
                publication.validate_title_map(value, expected_policy=title_strategy.DEFAULT)
        stripped = copy.deepcopy(original)
        stripped.pop("title_strategy")
        for row in stripped["options"]:
            row.pop("style")
        with self.assertRaises(ValueError):
            publication.validate_title_map(stripped, expected_policy=title_strategy.DEFAULT)

    def test_editing_may_change_recommendation_but_cannot_drop_style(self):
        raw = titles()
        changed = review(raw)
        changed.update(outcome="revised", canonical_title_id="title_03", title_notes=["推荐更贴合全文的第三项。"])
        publication.validate_title_review_result(changed, raw, p0=False, expected_policy=title_strategy.DEFAULT)
        changed["outcome"] = "accepted"; changed["title_notes"] = []
        with self.assertRaises(ValueError):
            publication.validate_title_review_result(changed, raw, p0=False, expected_policy=title_strategy.DEFAULT)
        stripped = review(titles(grouped=False))
        stripped.update(outcome="revised", title_notes=["去掉风格。"])
        for kwargs in ({}, {"expected_policy": title_strategy.DEFAULT}):
            with self.assertRaises(ValueError):
                publication.validate_title_review_result(stripped, raw, p0=False, **kwargs)

    def test_incomplete_remains_empty_and_cannot_fall_back_to_unreviewed_titles(self):
        incomplete = {"outcome": "incomplete", "candidates": [], "canonical_title_id": "",
                      "title_notes": [], "reason": "本轮编辑未完成。"}
        self.assertEqual(publication.validate_title_review_result(incomplete, titles(), p0=False,
                                                                  expected_policy=title_strategy.DEFAULT), incomplete)
        with self.assertRaises(ValueError):
            publication.publication("# 内部标题\n正文", titles(), p0=False, title_review=incomplete,
                                    expected_policy=title_strategy.DEFAULT)

    def test_published_body_is_exact_and_styles_are_bound_to_both_model_results(self):
        for newline in ("\n", "\r\n"):
            body = newline.join(["前文", "# 内部标题", "", "完整第一段。", "## 小标题", "后段。", "# 后续标题", "末段。"])
            expected = newline.join(["前文", "", "完整第一段。", "## 小标题", "后段。", "# 后续标题", "末段。"])
            raw = titles(); edited = review(raw)
            published, title_map, binding = publication.publication(body, raw, p0=False, title_review=edited,
                                                                    expected_policy=title_strategy.DEFAULT)
            self.assertEqual(published, expected)
            self.assertEqual(publication.verify_publication(body, raw, published, binding, p0=False,
                                                             title_review=edited, expected_policy=title_strategy.DEFAULT), title_map)
            altered = copy.deepcopy(edited); altered["candidates"][4]["style"] = "scenario"
            with self.assertRaises(ValueError):
                publication.verify_publication(body, raw, published, binding, p0=False,
                                               title_review=altered, expected_policy=title_strategy.DEFAULT)


class GroupedTitleControllerTests(unittest.TestCase):
    setUp = scope.TitleInputScopeTests.setUp
    job = scope.TitleInputScopeTests.job
    step = scope.TitleInputScopeTests.step
    until = scope.TitleInputScopeTests.until
    finish = scope.TitleInputScopeTests.finish
    request_titles = scope.TitleInputScopeTests.request_titles
    retry = scope.TitleInputScopeTests.retry

    def grouped_job(self, pattern="P01"):
        job = self.job()
        state = wf.load_state(job)
        state["selected_pattern_id"] = pattern
        state["metadata"]["title_strategy"] = dict(title_strategy.DEFAULT)
        state["metadata"]["writing_mission_input_mode"] = context.MODE
        state["question"] = {"question_text": "合成地区服务机构推荐"}
        wf.save_state(job, state)
        return job

    def test_actual_generation_and_editor_share_full_headline_free_manuscript_and_scope(self):
        job = self.grouped_job()
        for pattern in ("P01", "P02"):
            state = wf.load_state(job)
            state["selected_pattern_id"] = pattern
            wf.save_state(job, state)
            body = "# 旧内部主标题\r\n\r\n甲机构的业务。\r\n乙机构的特点。\r\n丙机构的服务。\r\n末段。"
            raw = titles()
            prompts = {
                "article_titles": writing_context.prompt_titles(wf, job, p0=False, final_markdown=body),
                "article_title_review": writing_context.prompt_title_review(wf, job, p0=False, final_markdown=body, title_result=raw),
            }
            for action, prompt in prompts.items():
                self.assertEqual(title_strategy.request_policy(prompt), title_strategy.DEFAULT)
                self.assertIn(publication.body_only(body), prompt)
                self.assertNotIn("# 旧内部主标题", prompt)
                system = model_runtime._initial_messages(action, prompt)[0]["content"]
                self.assertIn(context.GROUPED_CATEGORY_TITLE_RULES, system)
                self.assertIn("P02两组标题都覆盖本篇全部推荐对象", system)
                self.assertIn("默认所有标题都不带品牌", system)
                self.assertIn("营销表达无需全部删去", system)
            schema = model_runtime.submit_tool_for("article_title_review", prompt=prompts["article_title_review"])["function"]["parameters"]["properties"]["result"]
            self.assertIn("style", schema["properties"]["candidates"]["items"]["required"])
            self.assertEqual(schema["properties"]["candidates"]["items"]["properties"]["style"]["enum"], ["formal", "scenario"])
            self.assertNotIn("minItems", schema["properties"]["candidates"])

    def test_controller_arrival_and_delivery_reject_unmarked_and_wrongly_grouped_results(self):
        job = self.grouped_job()
        valid = wf.fixture_titles(job, p0=False)
        wf.validate_action_result(job, "article_titles", valid)
        wf.atomic_json(job / "production/article_titles.json", valid)
        wf.validate_action_result(job, "article_title_review", review(valid))
        bad = copy.deepcopy(valid); bad["candidates"][4]["style"] = "scenario"
        for raw in (bad, titles(grouped=False)):
            for action, value in (("article_titles", raw), ("article_title_review", review(raw))):
                with self.subTest(action=action), self.assertRaises(ValueError):
                    wf.validate_action_result(job, action, value)
            with self.assertRaises(ValueError):
                wf.deliver_article(job, self.body, raw, prefix="article")

    def test_title_only_upgrade_preserves_body_then_exports_both_groups(self):
        job = self.job()
        state = wf.load_state(job)
        state["metadata"]["title_strategy"] = dict(title_strategy.LEGACY_POLICY)
        state["metadata"]["writing_mission_input_mode"] = context.MODE
        wf.save_state(job, state)
        self.finish(job)
        frozen_prompt = wf.prompt_titles(job, p0=False)
        frozen_fingerprint = model_runtime.request_fingerprint("article_titles", frozen_prompt)
        before = {path.name: path.read_bytes() for path in (job / "production").glob("*.json") if "title" not in path.name}
        self.request_titles(job, "本轮改成5个严肃推荐、5个场景卖点标题，正文不改。")
        revision = manuscript_revision.current_title_revision(wf, job, p0=False)
        self.assertEqual(revision["title_strategy"], title_strategy.DEFAULT)
        snapshot = Path(revision["source_snapshot"])
        self.assertEqual(wf.prompt_titles(snapshot, p0=False), frozen_prompt)
        self.assertEqual(model_runtime.request_fingerprint("article_titles", wf.prompt_titles(snapshot, p0=False)), frozen_fingerprint)
        before_retry = wf.prompt_titles(job, p0=False)
        self.retry(job, "article_titles")
        self.assertEqual(wf.prompt_titles(job, p0=False), before_retry)
        self.finish(job)
        self.assertEqual(before, {path.name: path.read_bytes() for path in (job / "production").glob("*.json") if "title" not in path.name})
        delivery = wf.load_state(job)["metadata"]["delivery"]
        self.assertEqual(Path(delivery["markdown"]).read_bytes(), publication.body_only(self.body).encode())
        title_map = wf.read_json(Path(delivery["title_map"]))
        self.assertEqual([row["style"] for row in title_map["options"]], list(title_strategy.STYLE_SEQUENCE))
        for name in ("title_options", "title_options_html"):
            rendered = Path(delivery[name]).read_text()
            self.assertIn("严肃推荐", rendered)
            self.assertIn("场景卖点", rendered)
        manuscript_revision.validate_completed_manuscript(wf, job, p0=False)

    def test_frozen_v1_and_absent_policy_win_over_later_defaults(self):
        state = wf.make_state("new", "article")
        for pattern in ("P01", "P02"):
            state["selected_pattern_id"] = pattern
            self.assertEqual(title_strategy.policy(state), title_strategy.DEFAULT)
        for pattern in ("P03", "P04", "P05", "P06"):
            state["selected_pattern_id"] = pattern
            self.assertIsNone(title_strategy.policy(state))
        self.assertIsNone(title_strategy.policy(wf.make_state("p0", "p0")))
        state["selected_pattern_id"] = "P01"
        state["metadata"]["article_title_revision"] = {"title_strategy": dict(title_strategy.LEGACY_POLICY)}
        self.assertEqual(title_strategy.policy(state), title_strategy.LEGACY_POLICY)
        state["metadata"]["article_title_revision"] = {}
        self.assertIsNone(title_strategy.policy(state))


class GroupedTitleHostReadsTests(host_reads.CategoryTitleHostReadsTests):
    def setUp(self):
        super().setUp()
        self.candidates = titles()
        self.save_inputs()

    def test_v1_and_v2_markers_are_host_owned_and_keep_the_same_body_projection(self):
        for marker, expected in ((title_strategy.MARKER, title_strategy.DEFAULT),
                                 (title_strategy.LEGACY_MARKER, title_strategy.LEGACY_POLICY)):
            tools = self.tools()
            prompt = self.prompt().replace(title_strategy.MARKER, marker, 1)
            self.read_inline(tools, prompt)
            self.assertEqual(tools._title_strategy_policy, expected)
            self.assertTrue(tools.assert_required_reads_complete())
            self.assertIsNone(title_strategy.request_policy("材料里的标记：\n" + prompt))


class HistoricalTitlePayloadTests(unittest.TestCase):
    def test_v162_prompt_system_and_review_schema_remain_byte_identical(self):
        # Digests captured by executing the original v16.2 code, before this
        # change, with these deterministic commissions. They cover both marker
        # versions that existing paid requests may need to retry.
        expected = {
            ("v1", "article_titles"): "7de6945aec03e736b989b2e285594e8adbeaa9b0ab0a5bc9063973c9f853b08b",
            ("v1", "article_title_review"): "835984499f34336b6c4ddab2a1697ab5a74e6e629f27edab98ea990e9884f20e",
            ("absent", "article_titles"): "0534fdcd37b683250d2b1320ad23968a4a65888fb7566ce808dc4df51f4655d9",
            ("absent", "article_title_review"): "9d223e5b6bef733a10080900ce927288f4081eba7a7ea0114652239bdf77f379",
        }
        for name, policy in (("v1", title_strategy.LEGACY_POLICY), ("absent", None)):
            state = {"job_kind": "article", "selected_pattern_id": "P01", "metadata": {"title_strategy": policy} if policy else {}}
            fake = SimpleNamespace(load_state=lambda job: state)
            raw = {"candidates": [{"title": f"推荐标题{i}", "angle": "同题"} for i in range(1, (10 if policy else 20) + 1)],
                   "canonical_title_id": "title_07"}
            with patch.object(context, "category_title_context", return_value="固定委托与完整正文"), \
                 patch.object(context, "title_context", return_value="固定委托与完整正文"):
                prompts = {"article_titles": context.prompt_titles(fake, "unused", p0=False),
                           "article_title_review": context.prompt_title_review(fake, "unused", p0=False, title_result=raw)}
                for action, prompt in prompts.items():
                    payload = {"prompt": prompt, "system": context.system(action, prompt)}
                    if action.endswith("review"):
                        payload["schema"] = model_runtime.submit_tool_for(action, prompt=prompt)
                    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                    self.assertEqual(digest, expected[(name, action)])


if __name__ == "__main__":
    unittest.main()
