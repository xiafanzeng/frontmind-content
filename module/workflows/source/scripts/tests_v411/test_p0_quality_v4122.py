"""New P0 evidence gate and immutable legacy resources; no production calls.

These tests prove contracts and source delivery, not literary quality.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared import editorial_contracts as contracts, p0_style
from shared.host_tools import HostTools, ToolError


class P0QualityContractTests(unittest.TestCase):
    body = "本企业先核对项目合同与需求，再据此确定测试内容。\n\n测试方案说明功能与性能分别需要检查的事项。"

    def result(self, **changes):
        value = {"outcome": "accepted", "article_markdown": self.body, "editorial_notes": [], "reason": "",
                 "quality_review": contracts.fixture_quality_review(self.body)}
        value.update(changes)
        return value

    def validate(self, value):
        return contracts.validate_finalize_result(value, self.body, require_quality_review=True)

    def test_marker_distinguishes_new_old_and_question_jobs(self):
        for marker, enabled, deep in ((p0_style.P0_STYLE_CONTRACT_VERSION, True, True),
                                      (p0_style.LEGACY_STYLE_CONTRACT_VERSION, True, False), (None, False, False)):
            state = {"job_kind": "p0", "metadata": {"p0_style_contract": marker}}
            self.assertEqual(p0_style.is_enabled(state), enabled)
            self.assertEqual(p0_style.is_deep(state), deep)
            self.assertFalse(p0_style.is_deep({**state, "job_kind": "article"}))
        with self.assertRaises(contracts.EditorialContractError):
            p0_style.is_deep({"metadata": {"p0_style_contract": "unrecognized"}})

    def test_new_pass_requires_separate_review_legacy_does_not(self):
        value = self.result()
        self.assertEqual(self.validate(value), value)
        del value["quality_review"]
        self.assertEqual(contracts.validate_finalize_result(value, self.body), value)
        with self.assertRaisesRegex(contracts.EditorialContractError, "quality_review"):
            self.validate(value)

    def test_editorial_action_cannot_override_quality_failure(self):
        for part in ("fact_check", "article_quality", "example_comparison", "unresolved_issues"):
            with self.subTest(part=part):
                value = self.result()
                review = value["quality_review"]
                if part == "article_quality":
                    review[part]["passed"] = False
                    review[part]["checks"][1]["passed"] = False
                elif part == "example_comparison":
                    review[part][0]["passed"] = False
                elif part == "unresolved_issues":
                    review[part] = ["重点仍停留在服务名称罗列，需返回初稿展开。"]
                else:
                    review[part]["passed"] = False
                with self.assertRaises(contracts.EditorialContractError):
                    self.validate(value)

    def test_incomplete_returns_normally_with_actual_rejected_candidate_evidence(self):
        value = self.result(outcome="incomplete", article_markdown="", reason="返回蓝图补足章节任务")
        value["quality_review"]["article_quality"]["passed"] = False
        value["quality_review"]["article_quality"]["checks"][1]["passed"] = False
        value["quality_review"]["unresolved_issues"] = ["关系未展开，应返回蓝图/写作补足重点。"]
        self.assertEqual(self.validate(value), value)
        value["quality_review"]["unresolved_issues"] = []
        with self.assertRaises(contracts.EditorialContractError):
            self.validate(value)

    def test_review_quotes_must_belong_to_returned_final_not_only_candidate(self):
        revised = "本企业按项目资料界定检查对象。客户提供的合同和需求共同说明测试依据。"
        value = self.result(outcome="revised", article_markdown=revised, editorial_notes=["调整工作关系的解释。"])
        with self.assertRaisesRegex(contracts.EditorialContractError, "连续引用"):
            self.validate(value)
        value["quality_review"] = contracts.fixture_quality_review(revised)
        self.assertEqual(self.validate(value), value)
        value["quality_review"]["example_comparison"][0]["article_quote"] = "这是一段完全不在任何输入稿件里的虚构证据。"
        with self.assertRaises(contracts.EditorialContractError):
            self.validate(value)

    def test_dimension_and_example_evidence_must_be_complete_and_typed(self):
        mutations = [
            lambda q: q["article_quality"]["checks"].pop(),
            lambda q: q["article_quality"]["checks"][0].update(dimension="ending"),
            lambda q: q["example_comparison"][0].update(example_id="gangjun"),
            lambda q: q["fact_check"].update(passed="true"),
            lambda q: q["article_quality"]["checks"][0].update(passed=1),
            lambda q: q["fact_check"]["evidence"][0].update(assessment=""),
            lambda q: q["example_comparison"][0].update(reference_feature=""),
        ]
        for change in mutations:
            value = self.result()
            change(value["quality_review"])
            with self.assertRaises(contracts.EditorialContractError):
                self.validate(value)

    def test_schema_and_prompt_describe_all_enforced_fields(self):
        schema = p0_style.quality_review_schema()
        self.assertEqual(set(schema["required"]), set(self.result()["quality_review"]))
        guidance = p0_style.quality_review_guidance()
        for field in ("incomplete", "article_quote", "unresolved_issues", *contracts.QUALITY_DIMENSIONS, *contracts.QUALITY_EXAMPLES):
            self.assertIn(field, guidance)
        self.assertIn("不要把减少字数", p0_style.style_guidance(deep=True))
        self.assertNotEqual(p0_style.style_guidance(), p0_style.style_guidance(deep=True))


class P0SnapshotAndReadsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package, self.job = self.root / "package", self.root / "job"
        self.package.mkdir()
        self.job.mkdir()

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def resources(self, folder, version, label):
        root = self.package / "resources" / folder
        records = []
        for ident in p0_style.EXAMPLE_IDS:
            body = "完整模拟例文用于结构检查，末段亦须保留。" + ident
            self.put(root / (ident + ".md"), body)
            self.put(root / (ident + "_guide.md"), label + "段落拆解")
            records.append({"id": ident, "title": ident, "body_path": ident + ".md", "content_sha256": p0_style.sha256(body), "guide_path": ident + "_guide.md"})
        self.put(root / "manifest.json", {"contract_version": version, "examples": records})
        return root

    def test_old_snapshot_remains_exact_when_new_guides_and_manifest_change(self):
        old = self.resources("p0_style_legacy_v4121", p0_style.LEGACY_STYLE_CONTRACT_VERSION, "旧版")
        new = self.resources("p0_style", p0_style.P0_STYLE_CONTRACT_VERSION, "新版")
        self.put(self.job / "job_state.json", {"job_kind": "p0", "metadata": {"p0_style_contract": p0_style.LEGACY_STYLE_CONTRACT_VERSION}})
        before = p0_style.freeze_examples(self.package, self.job)
        self.put(new / "xingyuanzhi_guide.md", "新版改进后的详细拆解")
        self.assertEqual(p0_style.job_examples(self.package, self.job), before)
        self.assertTrue(all(item["guide"] == "旧版段落拆解" for item in before))
        # Altering frozen bytes plus their declared hash still cannot defeat
        # the approved legacy manifest and guide check.
        snapshot_path = self.job / p0_style.SNAPSHOT_RELATIVE
        snapshot = json.loads(snapshot_path.read_text())
        self.put(snapshot_path.parent / "gangjun_guide.md", "偷偷替换旧说明")
        snapshot["examples"][1]["guide_sha256"] = p0_style.sha256("偷偷替换旧说明")
        self.put(snapshot_path, snapshot)
        with self.assertRaises(contracts.EditorialContractError):
            p0_style.job_examples(self.package, self.job)

    def tools(self, version):
        self.put(self.job / "job_state.json", {"job_kind": "p0", "metadata": {"p0_style_contract": version}})
        blueprint = {"opening": "开篇任务", "sections": [{"heading": "章节", "task": "阐明关系与前后分工"}],
                     "ending": "收束任务", "writing_material_markdown": "充分的原始事实、必要条件与工作关系。"}
        self.put(self.job / "blueprints/p0_blueprint.json", blueprint)
        examples = []
        for ident in p0_style.EXAMPLE_IDS:
            path = self.job / "inputs/p0_style_examples" / (ident + ".md")
            self.put(path, ident + "例文完整内容")
            self.put(path.parent / (ident + "_guide.md"), ident + "写法拆解完整内容")
            examples.append({"id": ident, "path": str(path), "title": ident, "guide_path": ident + "_guide.md"})
        with patch.object(p0_style, "job_examples", return_value=examples):
            return HostTools(self.package, self.job, "p0_finalize")

    def test_new_finalizer_reads_complete_blueprint_material_and_guides(self):
        tools = self.tools(p0_style.P0_STYLE_CONTRACT_VERSION)
        required = {row["path"] for row in tools.artifacts.values() if row["required"]}
        self.assertIn("blueprints/p0_blueprint.json", required)
        self.assertTrue(all("inputs/p0_style_examples/" + ident + "_guide.md" in required for ident in p0_style.EXAMPLE_IDS))
        for ident in tools._required:
            if tools.artifacts[ident]["path"] != "blueprints/p0_blueprint.json":
                tools.execute("read_material", {"artifact_id": ident})
        with self.assertRaises(ToolError):
            tools.validate_complete_reads()
        tools.execute("read_material", {"artifact_id": "blueprints/p0_blueprint.json"})
        self.assertTrue(tools.validate_complete_reads())

    def test_legacy_finalizer_does_not_add_blueprint_or_guide_read_gates(self):
        tools = self.tools(p0_style.LEGACY_STYLE_CONTRACT_VERSION)
        required = {row["path"] for row in tools.artifacts.values() if row["required"]}
        self.assertNotIn("blueprints/p0_blueprint.json", required)
        self.assertFalse(any(path.endswith("_guide.md") for path in required))


if __name__ == "__main__":
    unittest.main()
