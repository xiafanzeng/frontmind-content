"""P0 deep composition survives projection and revision; legacy inputs stay exact."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared import writing_context as context


# Captured from the released v4.12.1 writing_context with the fixture below.
# These are prompt-byte regressions, not claims about editorial quality.
LEGACY_HASHES = {
    "p0/legacy/0/blueprint": "bf024621a497b3221cbffaca155ee7b346074ea31f72ec409f3948bad15047ff",
    "p0/legacy/0/article": "b4fc6e9fa4c47de3f30a9f1f94ae2a5759589aa867779b6429bfee40c793491d",
    "p0/legacy/0/edit": "f9c41e4256ed6dd5e239925d10eff8e1364035c0084cbb4fbff754341e169040",
    "p0/legacy/0/finalize": "f0379d702b6a220da4420738ea1dd76d3ec53894e8a954e7d73e4b95b58dc68f",
    "p0/frontmind-p0-style/4.12.1/0/blueprint": "93ba1b78a0d69d79f171765aa364127161d4367b231485edc0690a62fe340209",
    "p0/frontmind-p0-style/4.12.1/0/article": "24ca9da989f31b0c7fd412e4b428c42a82623d2930e0eac0aa40b3b6457d107c",
    "p0/frontmind-p0-style/4.12.1/0/edit": "d5ea9f41b3469e0d7220426e101b0931cddbdea327e14fc226858c83e1c3d90d",
    "p0/frontmind-p0-style/4.12.1/0/finalize": "61608483c44b6960cc8c3df609f7d42a86f83e008283513b97d3e4a8511f4ac8",
    "p0/frontmind-p0-style/4.12.1/0/style": "b98ab851e297ab07861e8e8304614f076e376572ed14ee9ac4a00fe64c1c8ec3",
    "P01/0/blueprint": "222ee6c0d68e387a6746987d0587597fcfe4d2f79b64bcd10e03eff0463192a3",
    "P01/0/article": "21d79cd99a80cab2ca230c7777d09826f08af37f5db0846dd3b8dd7c7ac2acd5",
    "P01/0/edit": "83ea76f34c9783b578386acbe75dac451219126ca28e01da18f95dd5aa1e92d3",
    "P01/0/finalize": "6e9ccdb499b89f0862374098fb9d8d2c7ec5c7921162e9a99d4392e10a6ba44e",
    "P02/0/blueprint": "1aca929a3d620e2dd0f478390e2be08ca7e989a4f2ce202ab32ecf328b602a9e",
    "P02/0/article": "c2ad1acc3a302bd08f04ebf0d5d5d0215101075e42c61843fad6dde59eea7169",
    "P02/0/edit": "efb54911cdfdd6dafc488675c900d0b457c55b2061a2c46fd967a0da30fddf77",
    "P02/0/finalize": "6a036c5cf4f5715f9a004206cb8003089a574bbe1f47a6522c9086c61da871c1",
    "P03/0/blueprint": "601303ab66b15c872719910f7558322ffd796b5b3caced28a7d791820e2f3511",
    "P03/0/article": "7cb1ed5b20720585f33255f649caac1c91ff4bdcbe7d8b984adcc3ce018ed03f",
    "P03/0/edit": "896d6199d96267ce45eabae408d1f5dc6608def7eb5807508a643f71a5c52c6a",
    "P03/0/finalize": "af60980ab2fdf1890c0542de1f1bc61d5b7058ef09adef523ae1296dbef996fa",
    "P04/0/blueprint": "8fdc7fd7cda2d7db02c6f44f269a0a4c4eea4868a516660a2ef4a2262c8deb60",
    "P04/0/article": "02595f3c5f9a19e7e8dedb9eeec6ab411fe3a05d27c6699acc045141574e128f",
    "P04/0/edit": "7835a14a023c92fc59be79c6ef00bc0fc44047594a3c7133eb2f661263d6b763",
    "P04/0/finalize": "09cba8159a275e2d508609acf8e504e98f992066606169feb17dcad64f6a2c4e",
    "P05/0/blueprint": "5c965084562a9c3b24bc65fe88ac9aa1f53b186b2c90405c0d5451b3c5f3cd0e",
    "P05/0/article": "a66a43b4cba2e4c2b0d0656bdaf8277b247f8d4601fd41081690f39c09a1644c",
    "P05/0/edit": "ca0a90ef5e88f96c23cb27e6b680d8c8093c9a0670609443efa68a80104540d0",
    "P05/0/finalize": "4dc5c46b441c45ce2a9c3f8047f84f357d4194c4cb56eba4edac5ff9f7698ec4",
    "P06/0/blueprint": "c095cfa58c621dd5ee8fda69afb0fb7c73c730606cf5a303dc475c304a09663a",
    "P06/0/article": "6b1c37580c64005fb6e8afd820c18eb62888de3c60aa493f13f095de4946001d",
    "P06/0/edit": "a4c46ad028815837631a35dadbe696079978552acfe1600a2bbfd7bfa5e9bd93",
    "P06/0/finalize": "a84a94e46420df2a953e9325a596cbffd4be9882391283dd91d68dfcc3419f9e",
    "p0/legacy/1/blueprint": "bf024621a497b3221cbffaca155ee7b346074ea31f72ec409f3948bad15047ff",
    "p0/legacy/1/article": "b4fc6e9fa4c47de3f30a9f1f94ae2a5759589aa867779b6429bfee40c793491d",
    "p0/legacy/1/edit": "2b2fa126563644e44832505f54e6b7b2c27581c4a72175b0418096200771fa4d",
    "p0/legacy/1/finalize": "c2c5516cb54b2174e9eef4c981a0982f732c012296e10f503da229ad9fca3efb",
    "p0/frontmind-p0-style/4.12.1/1/blueprint": "93ba1b78a0d69d79f171765aa364127161d4367b231485edc0690a62fe340209",
    "p0/frontmind-p0-style/4.12.1/1/article": "24ca9da989f31b0c7fd412e4b428c42a82623d2930e0eac0aa40b3b6457d107c",
    "p0/frontmind-p0-style/4.12.1/1/edit": "368037bc9799fe81883a377d4c6838d0644cc8acb530c8a51955ab42f8a78715",
    "p0/frontmind-p0-style/4.12.1/1/finalize": "7fae7733bfdeaca70b717504d1628b4e4e6b7456f4c44098f959aeaaba6b391d",
    "p0/frontmind-p0-style/4.12.1/1/style": "6153a001d093eaec669df1efcb8701570edda07f0ba5626bfe3dab625791ba08",
    "P01/1/blueprint": "222ee6c0d68e387a6746987d0587597fcfe4d2f79b64bcd10e03eff0463192a3",
    "P01/1/article": "21d79cd99a80cab2ca230c7777d09826f08af37f5db0846dd3b8dd7c7ac2acd5",
    "P01/1/edit": "19c6f02cad36eec74db5423d164fdee5f4d2c29e2dedd565d66c6c38d751144c",
    "P01/1/finalize": "2cb9fc1c9c8d5ce539b5b3a769603e67dec9985fecb3c950f1cfc8f541cffe91",
    "P02/1/blueprint": "1aca929a3d620e2dd0f478390e2be08ca7e989a4f2ce202ab32ecf328b602a9e",
    "P02/1/article": "c2ad1acc3a302bd08f04ebf0d5d5d0215101075e42c61843fad6dde59eea7169",
    "P02/1/edit": "b2e13f413f17d0185d3ebc447616306eb0e513ae129c0384698355db74edebf0",
    "P02/1/finalize": "2fe7f9833831ece4cbe69fe6e9c5bb4727ca6035d92b1787155ed783237d2e5f",
    "P03/1/blueprint": "601303ab66b15c872719910f7558322ffd796b5b3caced28a7d791820e2f3511",
    "P03/1/article": "7cb1ed5b20720585f33255f649caac1c91ff4bdcbe7d8b984adcc3ce018ed03f",
    "P03/1/edit": "e73058744104ef33518ce7cb2bfb6e120ee675462c7a0467d31e4fb31c536098",
    "P03/1/finalize": "7632c0013b929eb35978d7ec09799a60aa0b695f8417817d98e4ea61cc431a0c",
    "P04/1/blueprint": "8fdc7fd7cda2d7db02c6f44f269a0a4c4eea4868a516660a2ef4a2262c8deb60",
    "P04/1/article": "02595f3c5f9a19e7e8dedb9eeec6ab411fe3a05d27c6699acc045141574e128f",
    "P04/1/edit": "b48180fbf56be14ba7888f35b3e3fe81254a8e94995443c7f16fb9810ca2c22f",
    "P04/1/finalize": "8540195792f83c1b262ccdccb830cef50c08c041de2124817bb611ea48094810",
    "P05/1/blueprint": "5c965084562a9c3b24bc65fe88ac9aa1f53b186b2c90405c0d5451b3c5f3cd0e",
    "P05/1/article": "a66a43b4cba2e4c2b0d0656bdaf8277b247f8d4601fd41081690f39c09a1644c",
    "P05/1/edit": "83307aafd6d6618a13e565512861336336ca6b1c6890a56b76299ec9e32d098e",
    "P05/1/finalize": "0ce46c5e741e9550f690b0e13c4ee9d92b59cb812b9346ac6558f38b21b525fa",
    "P06/1/blueprint": "c095cfa58c621dd5ee8fda69afb0fb7c73c730606cf5a303dc475c304a09663a",
    "P06/1/article": "6b1c37580c64005fb6e8afd820c18eb62888de3c60aa493f13f095de4946001d",
    "P06/1/edit": "2f59a8e8ed5664131525838b932dc89f310cb5c383228077666972de31071fd7",
    "P06/1/finalize": "6c66becb99e4eeb517a8927395d4f856d38a158a648e7ec72ce46facb3878828"
}


class DeepContextTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.job = Path(temporary.name)
        self.state = {"job_kind": "p0", "revision": 9,
                      "metadata": {"p0_style_contract": "frontmind-p0-style/4.12.2"},
                      "reference_pack": {"brand": "示例检测", "path": "/unused/pack"},
                      "selected_example_route": "top20", "selected_pattern_id": "P03",
                      "question": {"question_text": "如何测试应用？"},
                      "decisions": {"response_brief": "为项目负责人写深度介绍，解释业务与方法。",
                                    "blueprint_edits": "重新选材、建立蓝图；重点内容展开，正文约2200字。"}}
        self.examples = "港隽固定全文开始\n事实与作用的完整段落。\n港隽全文结束\n星源智固定全文开始\n机制到验证的完整段落。\n星源智全文结束"
        self.blueprint = {
            "kind": "p0", "article_brief": "读者应理解三类业务为何面向不同任务。",
            "opening": "从项目交付所需确认事项进入。", "ending": "在理解工作方法后自然收束。",
            "sections": [{"heading": "业务用途", "task": "用产品确认与项目验收的事实解释不同用途。"},
                         {"heading": "工作方法", "task": "说明合同需求、项目资料与测试方案的直接关系。"}],
            "estimated_length": "2000—2600字", "example_use": "港隽的关系解释；星源智的专业推进。",
            "writing_material_markdown": "## 可用事实\n服务分别面向产品确认和项目验收。\n## 相关原文节选\n“客户如有需要进行项目知识培训。”\n实际节选末尾。",
            "writing_material_sources": [{"source_ref": "inputs/source.md", "use": "业务用途及培训主体"}],
            "material_adjustments": ["培训主体是客户，不能改成测评机构。"],
            "research_markdown": "WHOLE_RESEARCH_MUST_NOT_LEAK",
        }
        self.body = "# 示范标题\n\n## 业务用途\n\n服务面向不同任务，正文应当充分解释它们的关系。\n\n## 工作方法\n\n委托内容与相关资料共同构成测试工作的依据。"
        draft = {"article_markdown": self.body, "requires_blueprint_reconfirmation": False, "reconfirmation_reason": ""}
        edited = {**draft, "edit_status": "accepted", "editorial_notes": []}
        styled = {**edited, "editorial_plan": "保留展开内容并检查关系。",
                  "style_audit": {key: "SELF_AUDIT_MUST_NOT_REPLACE_JUDGMENT" for key in
                                  ("opening", "progression", "brand_specificity", "pacing", "precise_language", "ending", "fact_check")}}
        for prefix in ("p0", "article"):
            self.put(f"blueprints/{prefix}_blueprint.json", {**self.blueprint, "kind": "p0" if prefix == "p0" else "article"})
            self.put(f"production/{prefix}_draft.json", draft)
            self.put(f"production/{prefix}_edited.json", edited)
        self.put("production/p0_styled.json", styled)
        self.put("examples/additional.md", "补充例文完整正文。")
        self.put("question_positioning/question_positioning.json", {"natural_analysis": "本题已确认比较理由。"})
        self.wf = SimpleNamespace(
            load_state=lambda job: self.state,
            load_examples=lambda job, scope: [{"title": "补充例文", "path": str(self.job / "examples/additional.md")}],
            answer_texts=lambda job: ["完整答案一。", "完整答案二。"],
            brand_content_context=lambda job: {"p0": "已确认P0背景。", "core_positioning": "核心定位。"},
            read_json=lambda path: json.loads(Path(path).read_text()),
        )
        self.revision = None
        self.addCleanup(patch.stopall)
        patch("shared.p0_style.examples_markdown", return_value=self.examples).start()
        patch("shared.manuscript_revision.current_revision", side_effect=lambda *args, **kwargs: self.revision).start()

    def put(self, path, value):
        target = self.job / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def enable_revision(self):
        self.revision = {"edits_markdown": "只调整开篇，删除末段的重复句。", "base_markdown": self.body,
                         "base_source": "previous_published_final"}

    def prompts(self, module=context, *, p0=True):
        values = {name: getattr(module, "prompt_" + name)(self.wf, self.job, p0=p0)
                  for name in ("blueprint", "article", "edit", "finalize")}
        if p0 and self.state.get("metadata", {}).get("p0_style_contract"):
            values["style"] = module.prompt_p0_style(self.wf, self.job)
        return values

    def test_new_marker_and_complete_composition_reach_every_manuscript_stage(self):
        projected = context.writer_blueprint(self.blueprint, deep=True)
        self.assertEqual(projected["composition_notes"]["sections"], self.blueprint["sections"])
        for stage, prompt in self.prompts().items():
            with self.subTest(stage=stage):
                self.assertTrue(prompt.startswith(context.DEEP_P0_PROMPT_PREFIX))
                self.assertIn(self.examples, prompt)
                if stage != "blueprint":
                    for key in ("article_brief", "opening", "ending", "example_use", "estimated_length"):
                        self.assertIn(self.blueprint[key], prompt)
                    for section in self.blueprint["sections"]:
                        self.assertIn(section["task"], prompt)
                    self.assertIn(self.blueprint["writing_material_markdown"], prompt)
                    self.assertIn(self.blueprint["material_adjustments"][0], prompt)
                    self.assertNotIn("WHOLE_RESEARCH_MUST_NOT_LEAK", prompt)

    def test_material_preparation_retains_source_details_without_precompressing(self):
        prompt = self.prompts()["blueprint"]
        self.assertIn("附与重点解释有关的原文节选", prompt)
        self.assertIn("先阅读与文章重心相关的原件", prompt)
        self.assertIn("素材够不够，按能否支撑本节解释判断", prompt)
        self.assertNotIn("用几段精练、连续的自然语言总结", prompt)
        self.assertNotIn("选材在这里完成，不留备用资料库", prompt)

    def test_local_refinement_preserves_durable_targets_and_full_plan(self):
        self.enable_revision()
        for stage, prompt in self.prompts().items():
            if stage in {"blueprint", "article"}:
                continue
            with self.subTest(stage=stage):
                self.assertIn(self.revision["edits_markdown"], prompt)
                self.assertIn(self.blueprint["article_brief"], prompt)
                self.assertIn(self.blueprint["example_use"], prompt)
                self.assertIn(self.blueprint["estimated_length"], prompt)
                self.assertIn(self.blueprint["sections"][1]["task"], prompt)
                self.assertIn("阶段动作已经完成", prompt)
                self.assertNotIn("旧篇幅目标和旧详略命令也不自动恢复", prompt)
                self.assertNotIn("不再扩写其他已自然准确的段落", prompt)

    def test_stage_responsibilities_and_independent_final_gate(self):
        prompts = self.prompts()
        self.assertIn("E8职责：检查事实关系、内容缺口与章节逻辑", prompts["edit"])
        self.assertIn("第三遍职责：专门改善段落展开", prompts["style"])
        final = prompts["finalize"]
        self.assertIn("quality_review", final)
        self.assertIn("重新选材、改变构思或补写多个重点", final)
        self.assertIn("返回 incomplete", final)
        self.assertIn("未解决则停止，不生成标题或正式交付", final)
        self.assertNotIn("SELF_AUDIT_MUST_NOT_REPLACE_JUDGMENT", final)
        for stage in ("article", "edit", "style", "finalize"):
            self.assertIn("模型拟定", prompts[stage])
            self.assertNotIn("保留核心定位含义、正式回答、对象范围、章节主题及其确认顺序", prompts[stage])

    def legacy_prompt_hashes(self, module=context):
        hashes = {}
        for refining in (False, True):
            self.revision = None
            if refining:
                self.enable_revision()
            for contract in (None, "frontmind-p0-style/4.12.1"):
                self.state["job_kind"] = "p0"
                self.state["metadata"] = {"p0_style_contract": contract} if contract else {}
                for name, text in self.prompts(module).items():
                    key = f"p0/{contract or 'legacy'}/{int(refining)}/{name}"
                    hashes[key] = hashlib.sha256(text.encode()).hexdigest()
            self.state["job_kind"] = "article"
            self.state["metadata"] = {}
            for pattern in ("P01", "P02", "P03", "P04", "P05", "P06"):
                self.state["selected_pattern_id"] = pattern
                for name, text in self.prompts(module, p0=False).items():
                    hashes[f"{pattern}/{int(refining)}/{name}"] = hashlib.sha256(text.encode()).hexdigest()
        return hashes

    def test_legacy_p0_and_all_question_prompts_remain_byte_identical(self):
        self.assertEqual(self.legacy_prompt_hashes(), LEGACY_HASHES)


if __name__ == "__main__":
    unittest.main()
