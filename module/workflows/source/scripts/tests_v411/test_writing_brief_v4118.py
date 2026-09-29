"""Expression-task delivery and editorial intent; no automatic prose scoring."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared import writing_context as wc
from shared.editorial_contracts import EditorialContractError
from shared.model_runtime import request_fingerprint, submit_tool_for, system_prompt_for


class WritingBriefTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)
        self.state = {"reference_pack": {"brand": "合成企业"}, "revision": 1,
                      "selected_example_route": "top20", "selected_pattern_id": "P02",
                      "question": {"question_text": "合成甲乙分别适合什么需求？"},
                      "decisions": {"response_brief": "本轮委托：重新组织全文，保留对象与事实。"}}
        self.example = "EXAMPLE_BEGIN\n完整首段\nEXAMPLE_MIDDLE\n完整中段\nEXAMPLE_END"
        self.answers = ["ANSWER_A_BEGIN\n第一篇完整答案中段\nANSWER_A_END",
                        "ANSWER_B_BEGIN\n第二篇完整答案中段\nANSWER_B_END"]
        self.blueprint = {"kind": "p0", "question": self.state["question"]["question_text"],
                          "pattern_id": "P02", "candidate_order": ["合成乙", "合成甲"],
                          "article_brief": "BRIEF_SENTINEL 让读者理解两种交付方式与需求的关系，重点解释配合条件，简要交代机构信息。",
                          "example_use": "EXAMPLE_USE_SENTINEL 参考例文如何用具体动作展开重点，其余信息简述。",
                          "estimated_length": "依内容详略安排", "answer_use": "ANSWER_USE 保留已确认的判断",
                          "opening": "PRIVATE_OPENING", "ending": "PRIVATE_ENDING",
                          "style_source": "PRIVATE_STYLE_SOURCE",
                          "sections": [{"heading": "业务与需求", "task": "PRIVATE_SECTION_PROSE"}],
                          "writing_material_markdown": "合成甲提供远程服务。合成乙提供现场服务，需提前两日预约。",
                          "writing_material_sources": [{"source_ref": "inputs/source.md", "use": "服务和预约条件"}],
                          "material_adjustments": ["PRIVATE_SOURCE_NOTE"], "research_markdown": "PRIVATE_RESEARCH"}
        self.put("examples/selected.md", self.example)
        self.put("inputs/source.md", "RAW_LIBRARY_MUST_STAY_OUT")
        self.put("question_positioning/question_positioning.json", {"natural_analysis": "CURRENT_P02_POSITIONING"})
        self.wf = SimpleNamespace(
            load_state=lambda job: self.state,
            load_examples=lambda job, scope: [{"path": "examples/selected.md", "title": "合成例文"}],
            answer_texts=lambda job: self.answers,
            brand_content_context=lambda job: {"p0": "FULL_P0_BEGIN\n完整背景中段\nFULL_P0_END", "core_positioning": "QUESTION_CORE"},
            user_material_text=lambda *args: "",
            read_json=lambda p: json.loads(Path(p).read_text()))
        self.save()

    def put(self, name, value):
        path = self.job / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def save(self):
        body = "# 合成文章\n\n## 业务与需求\n\n合成甲提供远程服务，合成乙的现场服务需提前两日预约。"
        for prefix in ("p0", "article"):
            self.put(f"blueprints/{prefix}_blueprint.json", {**self.blueprint, "kind": prefix})
            self.put(f"production/{prefix}_draft.json", {"article_markdown": body, "requires_blueprint_reconfirmation": False, "reconfirmation_reason": ""})
            self.put(f"production/{prefix}_edited.json", {"article_markdown": body, "edit_status": "accepted", "editorial_notes": [], "requires_blueprint_reconfirmation": False, "reconfirmation_reason": ""})

    def test_new_blueprint_requires_real_expression_and_example_use(self):
        self.assertIs(wc.validate_article_brief(self.blueprint), self.blueprint)
        for field, code in (("article_brief", "article_brief_missing"), ("example_use", "example_use_missing")):
            for value in (None, "", "  ", [], {}):
                with self.subTest(field=field, value=value):
                    candidate = {**self.blueprint, field: value}
                    with self.assertRaises(EditorialContractError) as caught:
                        wc.validate_article_brief(candidate)
                    self.assertEqual(caught.exception.code, code)

    def test_tool_schema_and_prompt_request_the_same_new_contract(self):
        for p0, action in ((True, "p0_blueprint"), (False, "article_blueprint")):
            schema = submit_tool_for(action)["function"]["parameters"]["properties"]["result"]
            prompt = wc.prompt_blueprint(self.wf, self.job, p0=p0)
            for field in ("article_brief", "example_use"):
                self.assertIn(field, schema["required"])
                self.assertEqual(schema["properties"][field]["minLength"], 1)
                self.assertIn(field, prompt)
            self.assertIn(self.example, prompt)
            self.assertIn("不按文章章节提前铺成底稿", prompt)
            self.assertIn("哪些信息只需简要交代", prompt)

    def test_old_blueprint_remains_readable_without_fabricating_a_brief(self):
        old = {k: v for k, v in self.blueprint.items() if k not in {"article_brief", "example_use"}}
        self.assertIs(wc.validate_writing_material(old), old)
        self.assertNotIn("article_brief", wc.writer_blueprint(old)["composition_notes"])
        self.put("blueprints/p0_blueprint.json", old)
        self.assertIn(old["writing_material_markdown"], wc.prompt_article(self.wf, self.job, p0=True))
        self.assertNotIn("article_brief", json.loads((self.job / "blueprints/p0_blueprint.json").read_text()))

    def test_all_manuscript_stages_receive_brief_examples_and_only_selected_facts(self):
        before = copy.deepcopy(self.state)
        for p0 in (True, False):
            for builder in (wc.prompt_article, wc.prompt_edit, wc.prompt_finalize):
                with self.subTest(p0=p0, stage=builder.__name__):
                    prompt = builder(self.wf, self.job, p0=p0)
                    for value in (self.blueprint["article_brief"], self.blueprint["example_use"],
                                  self.blueprint["writing_material_markdown"], self.example):
                        self.assertIn(value, prompt)
                    for private in ("PRIVATE_OPENING", "PRIVATE_ENDING", "PRIVATE_SECTION_PROSE", "PRIVATE_STYLE_SOURCE", "PRIVATE_RESEARCH", "RAW_LIBRARY_MUST_STAY_OUT"):
                        self.assertNotIn(private, prompt)
                    self.assertEqual("PRIVATE_SOURCE_NOTE" in prompt, builder is wc.prompt_finalize)
                    if not p0:
                        for answer in self.answers:
                            self.assertIn(answer, prompt)
                        self.assertIn(self.wf.brand_content_context(self.job)["p0"], prompt)
        self.assertEqual(before, self.state)

    def test_p02_p05_keep_every_subject_and_order(self):
        for pattern in ("P02", "P05"):
            self.state["selected_pattern_id"] = pattern
            for builder in (wc.prompt_article, wc.prompt_edit, wc.prompt_finalize):
                prompt = builder(self.wf, self.job, p0=False)
                self.assertIn(self.blueprint["writing_material_markdown"], prompt)
                self.assertIn('"candidate_order": [\n    "合成乙",\n    "合成甲"', prompt)
                self.assertEqual("CURRENT_P02_POSITIONING" in prompt, pattern == "P02")
                self.assertNotIn("不写具名或类别竞品对照", prompt)

    def test_brief_and_example_use_changes_invalidate_relevant_requests(self):
        for field in ("article_brief", "example_use"):
            before = wc.prompt_article(self.wf, self.job, p0=True)
            changed = {**self.blueprint, field: self.blueprint[field] + " 更新本篇重点。"}
            self.put("blueprints/p0_blueprint.json", changed)
            after = wc.prompt_article(self.wf, self.job, p0=True)
            self.assertNotEqual(request_fingerprint("p0_draft", before, offline=True), request_fingerprint("p0_draft", after, offline=True))
            self.save()

    def test_edit_candidate_keeps_brief_but_does_not_promote_it_to_source(self):
        original = copy.deepcopy(self.blueprint)
        candidate = wc.blueprint_edit_candidate(self.blueprint, p0=True)
        self.assertEqual(candidate["article_brief"], self.blueprint["article_brief"])
        self.assertNotIn("research_markdown", candidate)
        self.assertEqual(candidate["writing_material_sources"], self.blueprint["writing_material_sources"])
        self.assertEqual(original, self.blueprint)

    def test_editors_evaluate_genre_then_paragraphs_then_facts(self):
        guidance = wc.focused_editorial_guidance()
        self.assertLess(guidance.index("一、整体阅读"), guidance.index("二、段落编辑"))
        self.assertLess(guidance.index("二、段落编辑"), guidance.index("三、句子与事实复核"))
        for builder in (wc.prompt_edit, wc.prompt_finalize):
            prompt = builder(self.wf, self.job, p0=True)
            self.assertIn(guidance, prompt)
            self.assertNotIn("执笔任务：", prompt)
            self.assertIn("仍像业务目录或材料汇编也不能判为通过", prompt)
            self.assertIn("本次新增句、标题及定义句", prompt)
        self.assertIn("最多自动修正一次", wc.prompt_finalize(self.wf, self.job, p0=True))

    def test_systems_assign_positive_writing_task_and_shared_editorial_checks(self):
        for prefix in ("p0", "article"):
            draft = system_prompt_for(prefix + "_draft")
            self.assertIn("值得连续阅读", draft)
            self.assertIn("安排主次与详略", draft)
            self.assertNotIn("全文编辑", draft)
            for suffix in ("edit", "finalize"):
                editor = system_prompt_for(prefix + "_" + suffix)
                self.assertIn("先整体阅读", editor)
                self.assertIn("再处理段落", editor)
                self.assertIn("最后复核句子", editor)
                self.assertIn("不重新从素材成篇", editor)

    def test_client_specific_commission_does_not_change_general_rules(self):
        source = wc.manuscript_composition_guidance("P00") + wc.focused_editorial_guidance() + wc.writing_material_contract_guidance()
        for private in ("一航", "港隽", "气体回收", "固定五节", "案例原件结论"):
            self.assertNotIn(private, source)
        self.state["decisions"]["blueprint_edits"] = "LOCAL_COMMISSION 仅本任务要求。"
        self.assertIn("LOCAL_COMMISSION", wc.prompt_article(self.wf, self.job, p0=True))
        self.state["decisions"].pop("blueprint_edits")
        self.assertNotIn("LOCAL_COMMISSION", wc.prompt_article(self.wf, self.job, p0=True))
        self.assertEqual(source, wc.manuscript_composition_guidance("P00") + wc.focused_editorial_guidance() + wc.writing_material_contract_guidance())

    def test_relation_checks_reach_both_editors_without_industry_specific_examples(self):
        for p0 in (True, False):
            prefix = "p0" if p0 else "article"
            for stage, builder in (("edit", wc.prompt_edit), ("finalize", wc.prompt_finalize)):
                with self.subTest(p0=p0, stage=stage):
                    prompt = builder(self.wf, self.job, p0=p0)
                    self.assertIn("材料明示的是并列、时间、条件还是状态", prompt)
                    self.assertIn("提交前再核对自己的连接句和新增限定", prompt)
                    self.assertIn("不用后台资料缺口说明", prompt)
                    self.assertIn(self.blueprint["writing_material_markdown"], prompt)
                    self.assertIn(self.example, prompt)
                    system = system_prompt_for(prefix + "_" + stage)
                    self.assertIn("不能为流畅而新增承诺、先后依赖或因果", system)
                    for forbidden in ("横向连接", "课程结束时", "复盘意见后", "制造业", "教育行业"):
                        self.assertNotIn(forbidden, wc.focused_editorial_guidance() + system)

    def test_editor_guidance_does_not_change_blueprint_or_author_input(self):
        for p0 in (True, False):
            before = {builder.__name__: builder(self.wf, self.job, p0=p0)
                      for builder in (wc.prompt_blueprint, wc.prompt_article, wc.prompt_edit, wc.prompt_finalize)}
            with patch.object(wc, "focused_editorial_guidance", return_value="EDITOR_RELATION_CHECK_ONLY"):
                for builder in (wc.prompt_blueprint, wc.prompt_article):
                    self.assertEqual(builder(self.wf, self.job, p0=p0), before[builder.__name__])
                for builder in (wc.prompt_edit, wc.prompt_finalize):
                    updated = builder(self.wf, self.job, p0=p0)
                    self.assertNotEqual(updated, before[builder.__name__])
                    self.assertIn("EDITOR_RELATION_CHECK_ONLY", updated)


if __name__ == "__main__":
    unittest.main()
