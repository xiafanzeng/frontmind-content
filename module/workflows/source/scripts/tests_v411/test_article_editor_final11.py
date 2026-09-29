"""Versioned editorial composition and historical request compatibility.

The frozen hashes were obtained from the unchanged v10 source, before adding
v11. Payload tests exercise the actual system/user wire builders, never paid
models; passing them does not establish the quality of a generated article.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts import frontmind_workflow as controller
from scripts.tests_v411 import test_article_reader_final8 as fixtures
from shared import article_positioning as positioning, article_reader as reader
from shared import model_runtime as runtime

ROOT = Path(__file__).resolve().parents[2]
EDITS = "REVISION_V11_COMPATIBILITY: 保留事实、选择理由和条件，重组重复段落。"


class ArticleEditorFinal11Tests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.ArticleReaderTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def contract(self, value):
        if value is None:
            self.case.state["metadata"].pop("article_reader_contract", None)
        else:
            self.case.state["metadata"]["article_reader_contract"] = value

    def test_prior_v9_legacy_and_p0_prompts_and_request_fingerprints_are_unchanged(self):
        for contract, name in ((None, "legacy"), (positioning.CONTRACT, "v9")):
            self.contract(contract)
            for stage in fixtures.BUILDERS:
                with self.subTest(contract=name, stage=stage):
                    self.assertEqual(self.case.digest(stage), tuple(HISTORICAL[name][stage]))
        for stage in fixtures.BUILDERS:
            self.assertEqual(self.case.digest(stage, p0=True), tuple(HISTORICAL["p0"][stage]))
        self.case.install_revision(EDITS)
        for contract, name in ((None, "legacy_revision"), (positioning.CONTRACT, "v9_revision")):
            self.contract(contract)
            for stage in ("edit", "finalize"):
                with self.subTest(contract=name, stage=stage):
                    self.assertEqual(self.case.digest(stage), tuple(HISTORICAL[name][stage]))

    def test_real_revision_payload_contains_choice_and_concrete_editing_rules_once(self):
        self.contract(positioning.LEGACY_EDITOR_CONTRACT)
        self.case.install_revision(EDITS)
        for stage in ("edit", "finalize"):
            with self.subTest(stage=stage):
                action = "article_" + stage
                prompt = self.case.prompt(stage)
                payload = runtime.build_payload(action, prompt)
                if stage == "edit":
                    system, user = (m["content"] for m in payload["messages"][:2])
                    self.assertEqual(payload["model"], "deepseek-v4-pro")
                    self.assertEqual(payload["reasoning_effort"], "max")
                else:
                    system, user = payload["instructions"], payload["input"][0]["content"]
                    self.assertEqual(payload["stop_at_tool_names"], ["submit_result"])
                    self.assertEqual(system.count(positioning.CURRENT_FINAL_TASK), 1)
                    self.assertIn("选择理由完整不单独代表通过", system)
                    self.assertIn("文体与内容要求时返回incomplete", system)
                self.assertEqual(user, prompt)
                self.assertTrue(user.startswith(positioning.LEGACY_EDITOR_MARKER + "\n"))
                self.assertEqual(user.count(EDITS), 1)
                self.assertEqual(system.count(positioning.CHOICE_LOGIC), 1)
                self.assertEqual(system.count(positioning.EDITORIAL), 1)
                for requirement in ("不是词语黑名单", "用户点名的句子连同上下文处理",
                                    "改措辞后仍相同的提醒也属于重复", "不能为求自然删除这些条件",
                                    "不复述给作者的写法指令", "不得凭对象类别"):
                    self.assertIn(requirement, system)
                for value in (self.case.body, self.case.example, *self.case.answers,
                              self.case.blueprint["writing_material_markdown"],
                              self.case.blueprint["article_brief"], "FULL_QUESTION_POSITIONING"):
                    self.assertIn(value, user)
                self.assertNotIn("不要从头重写", user)
                self.assertNotIn("本轮基于已完成终稿局部精修", user)

    def test_v11_rules_change_only_current_request_identity_not_v9_v8_or_p0(self):
        originals = {}
        for value in (None, reader.CONTRACT, positioning.CONTRACT, positioning.LEGACY_EDITOR_CONTRACT):
            self.contract(value)
            originals[value] = {stage: self.case.digest(stage) for stage in fixtures.BUILDERS}
        p0 = {stage: self.case.digest(stage, p0=True) for stage in fixtures.BUILDERS}
        with patch.object(positioning, "EDITORIAL", positioning.EDITORIAL + "\nTEST_ONLY_EDITOR_CHANGE"):
            for value in (None, reader.CONTRACT, positioning.CONTRACT, positioning.LEGACY_EDITOR_CONTRACT):
                self.contract(value)
                for stage in fixtures.BUILDERS:
                    actual = self.case.digest(stage)
                    if value == positioning.LEGACY_EDITOR_CONTRACT:
                        # Only system content changed, not the user prompt.
                        self.assertEqual(actual[0], originals[value][stage][0])
                        self.assertNotEqual(actual[1], originals[value][stage][1])
                    else:
                        self.assertEqual(actual, originals[value][stage])
                    self.assertEqual(self.case.digest(stage, p0=True), p0[stage])

    def test_current_route_retains_existing_actions_schema_and_p0_contract(self):
        self.contract(positioning.CONTRACT)
        original = {stage: runtime.submit_tool_for("article_" + stage, prompt=self.case.prompt(stage))
                    for stage in ("blueprint", "finalize")}
        self.contract(positioning.LEGACY_EDITOR_CONTRACT)
        for stage in ("blueprint", "finalize"):
            self.assertEqual(runtime.submit_tool_for("article_" + stage, prompt=self.case.prompt(stage)),
                             original[stage])
        self.assertNotIn("article_style", runtime.HOST_ACTIONS | runtime.DEEPSEEK_ACTIONS)
        self.assertNotIn("article_editor_review", runtime.HOST_ACTIONS | runtime.DEEPSEEK_ACTIONS)
        for stage in fixtures.BUILDERS:
            self.assertEqual(self.case.digest(stage, p0=True), tuple(HISTORICAL["p0"][stage]))
        self.case.state["job_kind"] = "p0"
        self.assertFalse(positioning.is_current(self.case.state))
        self.assertFalse(positioning.enabled(self.case.state))

    def test_new_article_defaults_to_current_and_historical_v9_still_selects_v9(self):
        new = controller.make_state("new", "article")
        self.assertEqual(new["metadata"]["article_reader_contract"], positioning.CURRENT_CONTRACT)
        self.assertEqual(positioning.marker(new), positioning.CURRENT_MARKER)
        self.assertEqual(positioning.final_task(new), positioning.NATURAL_ROLES["finalize"])
        self.contract(positioning.CONTRACT)
        self.assertTrue(positioning.enabled(self.case.state))
        self.assertFalse(positioning.is_current(self.case.state))
        self.assertEqual(positioning.marker(self.case.state), positioning.MARKER)
        self.assertEqual(positioning.final_task(self.case.state), positioning.FINAL_TASK)
        for stage in fixtures.BUILDERS:
            self.assertTrue(self.case.prompt(stage).startswith(positioning.MARKER + "\n"))
        for kind in ("p0", "reference_pack"):
            self.assertNotIn("article_reader_contract", controller.make_state("other", kind)["metadata"])
        allowed = json.loads((ROOT / "shared/job_state.schema.json").read_text())["properties"]["metadata"]["properties"]["article_reader_contract"]["enum"]
        self.assertTrue({reader.CONTRACT, positioning.CONTRACT, positioning.CURRENT_CONTRACT}.issubset(allowed))

    def test_explicit_v9_upgrade_freezes_old_source_and_records_v11_target(self):
        # Delay the dynamic controller fixture until unittest discovery ends.
        from scripts.tests_v411.test_article_editor_upgrade_final10 import ArticleEditorUpgradeTests
        integration = ArticleEditorUpgradeTests()
        integration.setUp()
        self.addCleanup(integration.doCleanups)
        integration.assert_upgrade_preserves_source(positioning.CONTRACT)


# Independent v10 baseline: (prompt SHA256, request fingerprint), using the
# existing deterministic reader fixture and the exact EDITS string above.
HISTORICAL = {
    "legacy": {
        "blueprint": ["f1057198cb3e70431b67e23da3aa77d88e2c610b64fd242a966003f2ee82bbd5", "0e2f83003c44d027cfeda4aa40f9ab5001b96ff9e625473281639901661cd08d"],
        "draft": ["6e8c34f78c4af38d7395e53b6845632e45d9f00451a198ceaa98a62fc2e56f9a", "ee9971b5fae6010b2d147162b69c65532ae782c96fbbb9447edbf55be4fdc1d3"],
        "edit": ["c49566a88b86a5fa650641a73711f888297df10da36251440c74ef6fa1bbdd23", "6134bc054abf02b821ec486913291a067864d14a116b8ae0a0208e970dcc1565"],
        "finalize": ["5276aab43eb673372aeb68d0e8f8ad2feea30d2f3f1668cb36da9bdd3d912cfe", "415ff22e6ce0285e2a99da369a91deca7af8420354d142cfba45496198660011"]},
    "v9": {
        "blueprint": ["10f6ececcd090223988cb53160b01114e023a9ad393e099d2f99dad88be0704b", "004beea800937d9859762bea684cead805a3d38017ee89c643a0a545a31ba3a8"],
        "draft": ["cb4b420495ca660ab51ce3b9bbcf93dc23f55bb9f7942a389a1868d1fc3c4c2e", "f37a1c429a5b2769a3ee059fcb26e02dd7d9f0bfc0f6c7e4b8341fc003b8e6ed"],
        "edit": ["439e66197fc61832bec669ac77a822d4b29cefaf5cc8dbca53f39fced21900f0", "6965a758625aa7ca1ab0c783dff975d8376b041e652a79a95f10e026711517cd"],
        "finalize": ["5a1babc63e2c585dd06a4799e06e7d930770c72fde564f7e9f838d5f939d96b3", "f353ce9faacfc4f42a6467f9dace33530e376a0b97748357daa7580f8c24a17b"]},
    "p0": {
        "blueprint": ["88f8a5ef356dbd04cf1345a57b418ad923f07806bc59cad3114a755c23f43fcb", "233684ac2b50d5459a5e2c736ce01493dcc52401014c7bea588ac73e7e9186e0"],
        "draft": ["3629b83f6aec61f8a6f69653a99a6bc95104aa2537754fb2dfcc79d0d0b6b87f", "4176b4ce20d8c32cf854a75ab719da54ff4308a8f859eaa1d7e0a3f114d31118"],
        "edit": ["1452adca503dd44be157d5e366a76165715b74183a1ebf762dcde294cdb8cfa0", "8a918abfdb94179d5aba369e05c49a73d976bb4192d36a9820ef581063d0c5b6"],
        "finalize": ["c4fe812ca8cd3a062bd6d59e1952fcfd249c812f47ca8af003c606a4f9315f79", "76f49937d49d0a82a3c03d312c9932021a705944b6841390aaad1447dce10ff4"]},
    "legacy_revision": {
        "edit": ["720d116371b55b6288f495efdf82c179aa73a3f9456f02782ba323c2574b3aed", "c83c01d937a96144ec4be59e29b1d4c54305349bdb8de96574c7845a9a238f5f"],
        "finalize": ["6c9164c107a38d1df370404f7331b170a716b6e6efb4a571e74ee71d29827922", "2591302ccc51d7530b86c8a0038bcb3461ee7d7d510d70fb77d4e1569c344bac"]},
    "v9_revision": {
        "edit": ["c136ee7abbf07becad248c926d58b75b8518052602e8805aa4c12448adade14e", "4501d9c11d82429c13d629b8be731158c5e9d40343a331ed061d54d813124766"],
        "finalize": ["1a375411fad087c087f24e5672ef37891b7fbf3137f5305c2c8d83ca0b273557", "37dd547e83a321f12746b976930d5e5b17d6c0b5507b12025a6cea7cfc6dacb7"]}}


if __name__ == "__main__":
    unittest.main()
