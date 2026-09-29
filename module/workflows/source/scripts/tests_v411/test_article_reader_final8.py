"""Actual question-prose payload/identity tests; no model-quality claims or API calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as controller
from shared import article_reader as reader, model_runtime as rt, writing_context as wc, manuscript_revision as mr

ROOT = Path(__file__).resolve().parents[2]
BUILDERS = {"blueprint": wc.prompt_blueprint, "draft": wc.prompt_article,
            "edit": wc.prompt_edit, "finalize": wc.prompt_finalize}


def fixture_profile(action):
    """Exercise real wire-plan builders without loading credential config."""
    if action in rt.HOST_ACTIONS:
        return {"provider": "xty", "wire_api": "openai_agents_sdk", "model": "fixture-host",
                "base_url": "https://example.test/v1", "max_tokens": 131072,
                "max_turns": 100, "max_tool_calls": 1000, "timeout_seconds": 1800}
    return {"provider": "deepseek", "model": "deepseek-v4-pro", "thinking": {"type": "enabled"},
            "reasoning_effort": "max", "max_tokens": 65536, "stream": True,
            "response_format": {"type": "json_object"}, "timeout_seconds": 300}


class ArticleReaderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.job = Path(temp.name)
        self.state = {"job_kind": "article", "metadata": {"article_reader_contract": reader.CONTRACT},
                      "revision": 7, "reference_pack": {"brand": "合成服务"},
                      "selected_pattern_id": "P01", "selected_example_route": "A",
                      "question": {"question_text": "怎样选择本题服务？"},
                      "decisions": {"response_brief": "CURRENT_USER：完整名称，无表格无emoji。",
                                    "blueprint_edits": "HISTORY_STRATEGY：保留主推荐和一条替代路径。"}}
        self.example = "EXAMPLE_BEGIN\n原例文完整中段✅\n|原样式|不直接继承|\nEXAMPLE_END"
        self.answers = ["ANSWER_A_BEGIN\n全文中段\nANSWER_A_END", "ANSWER_B_BEGIN\n全文中段\nANSWER_B_END"]
        self.body = "# 合成标题\n\n## 服务安排\n\n合成甲服务中心提供远程答疑，合成乙服务中心提供现场讲解，预约需提前两日。"
        self.blueprint = {
            "kind": "article", "question": self.state["question"]["question_text"], "pattern_id": "P01",
            "article_brief": "BRIEF：重点介绍合成甲，简要交代现场服务路径。",
            "example_use": "EXAMPLE_USE：借鉴原例文如何展开具体内容。",
            "answer_use": "ANSWER_USE：保留正式回答。", "brand_positioning_use": "POSITIONING_STRATEGY",
            "estimated_length": "重点充分展开", "candidate_order": ["合成甲", "合成乙"],
            "opening": "PRIVATE_OPENING", "ending": "PRIVATE_ENDING",
            "sections": [{"heading": "服务安排", "task": "PRIVATE_SECTION_TASK"}],
            "writing_material_markdown": "FACT_BEGIN\n合成甲服务中心提供远程答疑。合成乙服务中心提供现场讲解，预约需提前两日。\nFACT_END",
            "writing_material_sources": [{"source_ref": "inputs/source.md", "use": "服务与预约条件"}],
            "material_adjustments": ["BACKSTAGE：不要把预约条件扩大成服务保证。"]}
        self.put("examples/current.md", self.example)
        self.put("inputs/source.md", "RAW_SOURCE_NOT_IN_AUTHOR")
        self.put("question_positioning/question_positioning.json", {"natural_analysis": "FULL_QUESTION_POSITIONING"})
        for prefix in ("article", "p0"):
            self.put(f"blueprints/{prefix}_blueprint.json", {**self.blueprint, "kind": prefix})
            self.put(f"production/{prefix}_draft.json", {"article_markdown": self.body,
                     "requires_blueprint_reconfirmation": False, "reconfirmation_reason": ""})
            self.put(f"production/{prefix}_edited.json", {"article_markdown": self.body,
                     "edit_status": "accepted", "editorial_notes": [],
                     "requires_blueprint_reconfirmation": False, "reconfirmation_reason": ""})
        self.wf = SimpleNamespace(load_state=lambda _: self.state,
            load_examples=lambda *_: [{"title": "完整例文", "path": "examples/current.md"}],
            answer_texts=lambda _: self.answers,
            brand_content_context=lambda _: {"p0": "FULL_P0_BEGIN\n背景全文\nFULL_P0_END", "core_positioning": "BRAND_POSITION"},
            user_material_text=lambda *_: "", read_json=lambda p: json.loads(Path(p).read_text()))
        profile_patch = patch.object(rt, "profile_for", side_effect=fixture_profile)
        profile_patch.start()
        self.addCleanup(profile_patch.stop)

    def put(self, relative, value):
        path = self.job / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def prompt(self, stage, *, p0=False):
        return BUILDERS[stage](self.wf, self.job, p0=p0)

    def digest(self, stage, *, p0=False):
        prompt = self.prompt(stage, p0=p0)
        action = ("p0_" if p0 else "article_") + stage
        return hashlib.sha256(prompt.encode()).hexdigest(), rt.request_fingerprint(action, prompt, offline=True)

    def test_new_article_opt_in_only_and_old_state_is_not_upgraded(self):
        new = controller.make_state("new", "article")
        self.assertTrue(reader.enabled(new))
        self.assertFalse(reader.enabled(controller.make_state("p0", "p0")))
        self.assertNotIn("article_reader_contract", controller.make_state("pack", "reference_pack")["metadata"])
        schema = json.loads((ROOT / "shared/job_state.schema.json").read_text())
        self.assertIn(reader.CONTRACT, schema["properties"]["metadata"]["properties"]["article_reader_contract"]["enum"])
        self.state["metadata"] = {}
        self.put("provider/article_edit/request.json", {"prompt": "immutable old request"})
        self.put("provider/article_edit/checkpoint.json", {"fingerprint": "immutable old checkpoint"})
        self.put("production/article_finalized.json", {"article_markdown": "immutable completed body"})
        before = {p.relative_to(self.job): p.read_bytes() for p in self.job.rglob("*") if p.is_file()}
        for stage in BUILDERS:
            self.assertFalse(self.prompt(stage).startswith(reader.MARKER))
        after = {p.relative_to(self.job): p.read_bytes() for p in self.job.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.state["metadata"], {})

    def test_reader_principles_reach_effective_writer_and_sdk_payload_once(self):
        for stage in BUILDERS:
            action = "article_" + stage
            prompt = self.prompt(stage)
            payload = rt.build_payload(action, prompt)
            system = payload["instructions"] if action in rt.HOST_ACTIONS else payload["messages"][0]["content"]
            user = payload["input"][0]["content"] if action in rt.HOST_ACTIONS else payload["messages"][1]["content"]
            self.assertTrue(prompt.startswith(reader.MARKER + "\n"))
            self.assertEqual(system.count(reader.COMMON), 1)
            self.assertIn({"blueprint": reader.SELECTION, "draft": reader.DRAFT,
                           "edit": reader.EDIT, "finalize": reader.FINALIZE}[stage], system)
            self.assertNotIn(reader.COMMON, user)
            self.assertEqual(user, prompt)
            self.assertIn(self.example, user)  # Complete original example, no lexical deletion.
            self.assertIn("只有当前用户明确要求", system)
            self.assertIn("共同提醒", system)
            self.assertIn("具体对象独有的限制", system)
            self.assertIn("不是禁词表", system)
            if action in rt.HOST_ACTIONS:
                self.assertEqual(payload["profile"], fixture_profile(action))
                self.assertEqual(payload["stop_at_tool_names"], ["submit_result"])
            else:
                self.assertEqual(payload["model"], "deepseek-v4-pro")
                self.assertEqual(payload["reasoning_effort"], "max")
                self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_material_scope_matches_each_pattern_and_never_leaks_p0_rule(self):
        for pattern in ("P01", "P02", "P03", "P04", "P05", "P06"):
            self.state["selected_pattern_id"] = pattern
            prompt = self.prompt("blueprint")
            self.assertIn(reader.material_scope(pattern), prompt)
            self.assertNotIn("P0 只选企业自身及真实业务关系", prompt)
            self.assertIn("完整例文用于参考写法，不移植例文事实", prompt)

    def test_author_keeps_context_but_not_precomposed_blueprint_or_source_log(self):
        for stage in ("draft", "edit", "finalize"):
            prompt = self.prompt(stage)
            for text in (self.blueprint["writing_material_markdown"], self.blueprint["article_brief"],
                         self.blueprint["example_use"], self.blueprint["answer_use"], self.example,
                         *self.answers, "FULL_QUESTION_POSITIONING", "HISTORY_STRATEGY", "FULL_P0_END"):
                self.assertIn(text, prompt)
            self.assertIn("后台选择依据，完整保留", prompt)
            for text in ("PRIVATE_OPENING", "PRIVATE_ENDING", "PRIVATE_SECTION_TASK", "RAW_SOURCE_NOT_IN_AUTHOR"):
                self.assertNotIn(text, prompt)
            self.assertEqual("BACKSTAGE" in prompt, stage == "finalize")
            self.assertIn('"合成甲",\n    "合成乙"', prompt)

    def test_host_preserves_natural_prose_and_keeps_existing_once_only_contract(self):
        prompt = self.prompt("finalize")
        payload = rt.build_payload("article_finalize", prompt)
        self.assertIn(reader.FINALIZE, payload["instructions"])
        self.assertNotIn(rt.MANUSCRIPT_EDITOR_ROLE, payload["instructions"])
        self.assertNotIn(wc.focused_editorial_guidance(), prompt)
        self.assertIn("自然准确的段落原样保留", prompt)
        self.assertIn("若必须大幅重写才能成立，返回incomplete", prompt)
        self.assertIn("最多自动修正一次", prompt)
        self.assertIn(self.body, prompt)
        result_schema = payload["tools"][-1]["function"]["parameters"]["properties"]["result"]
        self.assertEqual(result_schema["required"], ["outcome", "article_markdown", "editorial_notes", "reason"])
        self.assertEqual(result_schema["properties"]["outcome"]["enum"],
                         ["accepted", "revised", "requires_blueprint_reconfirmation", "incomplete"])
        self.assertNotIn("article_style", rt.DEEPSEEK_ACTIONS | rt.HOST_ACTIONS)

    def install_revision(self, edits):
        value = {"contract": mr.CONTRACT_VERSION, "prefix": "article", "revision_id": "synthetic-revision",
                 "base_markdown": self.body, "base_sha256": mr.text_hash(self.body),
                 "edits_markdown": edits, "edits_sha256": mr.text_hash(edits),
                 "source": {"draft_sha256": mr.file_hash(self.job / "production/article_draft.json"),
                            "blueprint_sha256": mr.file_hash(self.job / "blueprints/article_blueprint.json")}}
        self.put("revisions/article.json", value)
        self.state["metadata"]["article_manuscript_revision"] = {
            "path": "revisions/article.json", "sha256": mr.file_hash(self.job / "revisions/article.json")}

    def test_current_revision_overrides_historical_expression_but_keeps_complete_content(self):
        edits = "CURRENT_REVISION：原句‘用资源组合建立比较基础’很生硬。介绍具体服务，处理全文同类结构。保留合成甲先于合成乙。"
        self.install_revision(edits)
        for stage in ("edit", "finalize"):
            prompt = self.prompt(stage)
            self.assertEqual(prompt.count(edits), 1)
            self.assertIn("本轮唯一当前正文修改委托", prompt)
            self.assertIn("历史蓝图阶段修订（完整原文）", prompt)
            self.assertIn(self.state["decisions"]["blueprint_edits"], prompt)
            self.assertIn("上游表达方案完整原文", prompt)
            self.assertIn("写法、重点展开方式、段落模板与公共提醒位置服从当前正文修改意见", prompt)
            self.assertNotIn("决定重心与详略", prompt)
            for text in (self.body, self.example, self.blueprint["writing_material_markdown"],
                         self.blueprint["article_brief"], self.blueprint["example_use"],
                         self.blueprint["answer_use"], *self.answers):
                self.assertIn(text, prompt)
            self.assertIn("保留用户明确指定的内容、对象先后与主题顺序", prompt)
            self.assertIn('"合成甲",\n    "合成乙"', prompt)

    def test_current_blueprint_feedback_is_not_downgraded_without_a_manuscript_revision(self):
        prompt = self.prompt("edit")
        self.assertIn("本次用户对蓝图与文章的修订", prompt)
        self.assertIn(self.state["decisions"]["blueprint_edits"], prompt)
        self.assertNotIn("历史蓝图阶段修订（完整原文）", prompt)
        self.assertIn("上游表达方案完整原文", prompt)
        self.assertIn(self.blueprint["article_brief"], prompt)

    def test_new_e8_uses_one_editorial_role_without_legacy_rewrite_prohibition(self):
        prompt = self.prompt("edit")
        system = rt.build_payload("article_edit", prompt)["messages"][0]["content"]
        self.assertNotIn(rt.MANUSCRIPT_EDITOR_ROLE, system)
        self.assertEqual(system.count(reader.COMMON), 1)
        self.assertIn(reader.EDIT, system)
        self.assertNotIn(wc.focused_editorial_guidance(), prompt)
        self.assertNotIn(wc.editorial_authority_guidance(), prompt)
        self.assertNotIn("不再从素材开始重新成篇", prompt)
        self.assertNotIn("不要从头重写", prompt)
        self.assertIn("具体编辑职责见系统指令", prompt)
        self.assertIn("旧稿措辞与表达框架不是必须保留的内容", prompt)
        self.assertIn("可重写有问题的整段、整节及全文同类结构", prompt)
        self.assertIn("用户已指出的问题表达及全文同类结构可直接重写", prompt)

    def test_real_rule_change_invalidates_new_requests_without_touching_old_or_p0(self):
        new = {stage: self.digest(stage) for stage in BUILDERS}
        prompts = {stage: self.prompt(stage) for stage in BUILDERS}
        self.state["metadata"] = {}
        old = {stage: self.digest(stage) for stage in BUILDERS}
        p0 = {stage: self.digest(stage, p0=True) for stage in BUILDERS}
        with patch.object(reader, "COMMON", reader.COMMON + "\nCHANGED_READER_RULE"):
            for stage in BUILDERS:
                self.assertNotEqual(rt.request_fingerprint("article_" + stage, prompts[stage], offline=True), new[stage][1])
                self.assertEqual(self.digest(stage), old[stage])
                self.assertEqual(self.digest(stage, p0=True), p0[stage])
        self.assertTrue(all(new[stage] != old[stage] for stage in BUILDERS))

    def test_legacy_prompt_and_request_match_frozen_final7_baseline(self):
        # Populated from the immutable Final_v7 ZIP using this same synthetic
        # input and fixture profile. Guards against silent old-Job migration.
        self.state["metadata"] = {}
        expected = LEGACY_FINAL7_HASHES
        for prefix in ("article", "p0"):
            for stage in BUILDERS:
                self.assertEqual(self.digest(stage, p0=prefix == "p0"), tuple(expected[prefix + "_" + stage]))


LEGACY_FINAL7_HASHES = {
    "article_blueprint": [
        "f1057198cb3e70431b67e23da3aa77d88e2c610b64fd242a966003f2ee82bbd5",
        "0e2f83003c44d027cfeda4aa40f9ab5001b96ff9e625473281639901661cd08d"
    ],
    "article_draft": [
        "6e8c34f78c4af38d7395e53b6845632e45d9f00451a198ceaa98a62fc2e56f9a",
        "ee9971b5fae6010b2d147162b69c65532ae782c96fbbb9447edbf55be4fdc1d3"
    ],
    "article_edit": [
        "c49566a88b86a5fa650641a73711f888297df10da36251440c74ef6fa1bbdd23",
        "6134bc054abf02b821ec486913291a067864d14a116b8ae0a0208e970dcc1565"
    ],
    "article_finalize": [
        "5276aab43eb673372aeb68d0e8f8ad2feea30d2f3f1668cb36da9bdd3d912cfe",
        "415ff22e6ce0285e2a99da369a91deca7af8420354d142cfba45496198660011"
    ],
    "p0_blueprint": [
        "88f8a5ef356dbd04cf1345a57b418ad923f07806bc59cad3114a755c23f43fcb",
        "233684ac2b50d5459a5e2c736ce01493dcc52401014c7bea588ac73e7e9186e0"
    ],
    "p0_draft": [
        "3629b83f6aec61f8a6f69653a99a6bc95104aa2537754fb2dfcc79d0d0b6b87f",
        "4176b4ce20d8c32cf854a75ab719da54ff4308a8f859eaa1d7e0a3f114d31118"
    ],
    "p0_edit": [
        "1452adca503dd44be157d5e366a76165715b74183a1ebf762dcde294cdb8cfa0",
        "8a918abfdb94179d5aba369e05c49a73d976bb4192d36a9820ef581063d0c5b6"
    ],
    "p0_finalize": [
        "c4fe812ca8cd3a062bd6d59e1952fcfd249c812f47ca8af003c606a4f9315f79",
        "76f49937d49d0a82a3c03d312c9932021a705944b6841390aaad1447dce10ff4"
    ]
}


if __name__ == "__main__":
    unittest.main()
