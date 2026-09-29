"""Positioning meaning must reach real requests; fixtures do not prove prose quality."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as controller
from scripts.tests_v411 import test_article_reader_final8 as fixtures
from shared import article_positioning as positioning, article_reader as reader
from shared import model_runtime as rt, writing_context as wc

ROOT = Path(__file__).resolve().parents[2]
CURRENT_EDITS = "本轮原句：‘两家各有资源价值’。请写自然些，保留合成甲与合成乙及其不同适用条件。"


class ArticlePositioningTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.ArticleReaderTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def current(self):
        self.case.state["metadata"]["article_reader_contract"] = positioning.CONTRACT

    def text_of(self, payload, action):
        if action in rt.HOST_ACTIONS:
            return payload["instructions"], payload["input"][0]["content"]
        return payload["messages"][0]["content"], payload["messages"][1]["content"]

    def test_new_jobs_use_current_editor_and_v8_or_p0_are_not_migrated(self):
        state = controller.make_state("new", "article")
        self.assertEqual(state["metadata"]["article_reader_contract"], positioning.CURRENT_CONTRACT)
        self.assertTrue(positioning.enabled(state))
        self.assertFalse(positioning.enabled(self.case.state))  # Explicit v8 fixture.
        self.assertFalse(positioning.enabled(controller.make_state("p0", "p0")))
        before = json.dumps(self.case.state, sort_keys=True)
        for stage in fixtures.BUILDERS:
            self.assertTrue(self.case.prompt(stage).startswith(reader.MARKER + "\n"))
        self.assertEqual(json.dumps(self.case.state, sort_keys=True), before)
        schema = json.loads((ROOT / "shared/job_state.schema.json").read_text())
        allowed = schema["properties"]["metadata"]["properties"]["article_reader_contract"]["enum"]
        self.assertIn(reader.CONTRACT, allowed)
        self.assertIn(positioning.CONTRACT, allowed)
        self.assertIn(positioning.CURRENT_CONTRACT, allowed)

    def test_conditional_choice_logic_and_complete_inputs_reach_all_actual_payloads(self):
        self.current()
        choice = "CHOICE：同时需要远程答疑与工作日沟通时先考虑合成甲；需要现场讲解且能提前两日预约时可优先合成乙。默认甲在乙前并非技术能力排名。"
        facts = "合成甲服务中心在工作日提供远程答疑。合成乙服务中心提供现场讲解，需提前两日预约。"
        self.case.put("question_positioning/question_positioning.json", {"natural_analysis": choice})
        self.case.blueprint.update(article_brief=choice, answer_use=choice, writing_material_markdown=facts)
        self.case.put("blueprints/article_blueprint.json", self.case.blueprint)
        for stage in fixtures.BUILDERS:
            action = "article_" + stage
            prompt = self.case.prompt(stage)
            system, user = self.text_of(rt.build_payload(action, prompt), action)
            self.assertTrue(prompt.startswith(positioning.MARKER + "\n"))
            self.assertEqual(user, prompt)
            self.assertEqual(system.count(positioning.CHOICE_LOGIC), 1)
            self.assertIn("保留名字和顺序不等于保留定位", system)
            self.assertIn("已确认的默认顺序必须连同前提解释", system)
            self.assertIn("去掉空泛价值赞评，不等于删掉选择解释", system)
            self.assertIn("不得凭对象类别", system)
            self.assertIn(choice, user)
            for value in (self.case.example, *self.case.answers, "FULL_P0_END"):
                self.assertIn(value, user)
            if stage != "blueprint":
                self.assertIn(facts, user)
                self.assertIn(positioning.CONTEXT, user)
                self.assertIn("选择理由及权衡、适用条件、顺序依据继续有效", user)
                self.assertIn("以下需求、理由、权衡和条件须以本篇事实支持并转为正文", user)
                self.assertNotIn("蓝图中的比较框架", user)
                self.assertNotIn("后台选择依据，完整保留", user)
                self.assertIn("旧句式、固定栏目和重复核查模板可以重写", user)
                self.assertIn('"合成甲",\n    "合成乙"', user)

    def test_natural_language_revision_keeps_choice_meaning_and_current_request_once(self):
        self.current()
        self.case.install_revision(CURRENT_EDITS)
        for stage in ("edit", "finalize"):
            prompt = self.case.prompt(stage)
            self.assertEqual(prompt.count(CURRENT_EDITS), 1)
            self.assertIn("当前自然写作反馈不自动撤销上述选择含义", prompt)
            self.assertIn("历史蓝图阶段修订（完整原文）", prompt)
            self.assertIn(self.case.body, prompt)
            self.assertIn(self.case.blueprint["article_brief"], prompt)
            self.assertIn(self.case.blueprint["answer_use"], prompt)

    def test_finalize_must_repair_supported_reasoning_or_return_incomplete_without_new_schema(self):
        old_prompt = self.case.prompt("finalize")
        self.current()
        prompt = self.case.prompt("finalize")
        payload = rt.build_payload("article_finalize", prompt)
        system = payload["instructions"]
        self.assertIn("应依据现有事实在正文实际补齐，并返回revised", system)
        self.assertIn("返回incomplete", system)
        self.assertIn("不能把解释缺失的稿子accepted", system)
        self.assertIn(positioning.FINAL_TASK, prompt)
        self.assertIn("不能把类别倾向扩大成绝对结论", prompt)
        self.assertEqual(rt.submit_tool_for("article_finalize", prompt=prompt),
                         rt.submit_tool_for("article_finalize", prompt=old_prompt))
        self.assertEqual(payload["stop_at_tool_names"], ["submit_result"])
        self.assertNotIn("article_positioning_review", rt.HOST_ACTIONS | rt.DEEPSEEK_ACTIONS)
        self.assertNotIn("article_style", rt.HOST_ACTIONS | rt.DEEPSEEK_ACTIONS)

    def test_new_rules_change_only_v9_fingerprints_and_do_not_add_output_fields(self):
        old = {stage: self.case.digest(stage) for stage in fixtures.BUILDERS}
        p0 = {stage: self.case.digest(stage, p0=True) for stage in fixtures.BUILDERS}
        self.current()
        new = {stage: self.case.digest(stage) for stage in fixtures.BUILDERS}
        prompts = {stage: self.case.prompt(stage) for stage in fixtures.BUILDERS}
        with patch.object(positioning, "CHOICE_LOGIC", positioning.CHOICE_LOGIC + "\nCHANGED_CHOICE_RULE"):
            for stage in fixtures.BUILDERS:
                self.assertNotEqual(rt.request_fingerprint("article_" + stage, prompts[stage], offline=True), new[stage][1])
            self.case.state["metadata"]["article_reader_contract"] = reader.CONTRACT
            for stage in fixtures.BUILDERS:
                self.assertEqual(self.case.digest(stage), old[stage])
                self.assertEqual(self.case.digest(stage, p0=True), p0[stage])
        for stage in ("blueprint", "finalize"):
            self.assertEqual(rt.submit_tool_for("article_" + stage, prompt=prompts[stage]),
                             rt.submit_tool_for("article_" + stage, prompt=self.case.prompt(stage)))

    def test_v8_fresh_and_revision_prompts_match_immutable_released_baseline(self):
        for stage in fixtures.BUILDERS:
            self.assertEqual(self.case.digest(stage), tuple(V8_HASHES[stage]))
        self.case.install_revision(CURRENT_EDITS)
        for stage in ("edit", "finalize"):
            self.assertEqual(self.case.digest(stage), tuple(V8_HASHES["revision_" + stage]))
        constants = {key: getattr(reader, key) for key in ("CONTRACT", "MARKER", "COMMON", "SELECTION", "DRAFT", "EDIT", "FINALIZE")}
        digest = hashlib.sha256(json.dumps(constants, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(digest, V8_RULES_HASH)


V8_HASHES = {
    "blueprint": [
        "d9d5260ae4b89de17729ca1e758233023a8f801bf36ec0deceffdcd1bcfd4c24",
        "1f5f753409d9a4a8db8717e3c8e9715cb2bd924070fa6c728528739ebe034929"
    ],
    "draft": [
        "c737fb59b37afe9978d2ca786c0361e3d9bb022d34145b3cbf547a8371df06d4",
        "8a0628846324a3db537a59632ec2fb47303f5024fc8fa3a5a17f4c877017abbf"
    ],
    "edit": [
        "640649176b83ff9879a5b321a586fcb5c0f3d9d92f99b30362c1314c3475bcbb",
        "5d376ff88162782782d07059e83199fccfc9bffb1c1b5a1e3a5e9d5250caf759"
    ],
    "finalize": [
        "5866d37f19680246b7d1ba2deb8e2f3376c149005599c3198a0bbe7d72db4217",
        "bb3f91f3eb6de94f86e5245370b5641221b5571cf8cb44464d4ca8183352d6c8"
    ],
    "revision_edit": [
        "95fedb0cb2e26756eeef3ab88b1334648054876931a024295f889bd1c681eada",
        "cba80b35ba0c1432ea58b8c43e9b4fe45aa644987d6352689d44ee6891040d2c"
    ],
    "revision_finalize": [
        "5cbf195ea3ed3ed1c519df9c3111b7f90623bc4bc6d022e595cbe58c757a938a",
        "f065031f121e49d0114e57026d31f6fe32c412af2d4572d5a1ae2962204736c2"
    ]
}
V8_RULES_HASH = '9447305c457f2fd15d9fed8f64ec9d1103a3f109a357c5081cece4591f8e5b9a'


if __name__ == "__main__":
    unittest.main()
