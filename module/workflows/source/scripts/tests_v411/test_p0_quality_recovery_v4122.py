"""Quality rejection re-enters existing blueprint editing without a paid retry."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.tests_v411.test_controller_runtime_v4114 import wf
from shared import p0_style


class P0QualityRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.job = Path(self.temp.name).resolve() / "job"
        self.job.mkdir()
        state = wf.make_state("quality-recovery-fixture", "p0")
        state["metadata"]["p0_style_contract"] = "frontmind-p0-style/4.12.2"  # Historical quality schema fixture.
        state.update(status="running_p0_production", revision=7,
                     pending_action={"action": "p0_finalize", "error": {
                         "code": "host_incomplete", "message": "项目方法仍缺少充分展开，应返回蓝图。"}})
        state["flags"]["p0_production_step"] = "finalize"
        state["metadata"]["p0_production_bindings"] = {"style": "old-binding"}
        wf.save_state(self.job, state)
        self.rejected = {"outcome": "incomplete", "article_markdown": "", "editorial_notes": [],
                         "reason": "项目方法仍缺少充分展开，应返回蓝图。", "quality_review": {
                             "unresolved_issues": ["项目方法仍缺少充分展开。"]}}
        self.result_path = wf.action_paths(self.job, "p0_finalize")[2]
        wf.atomic_json(self.result_path, self.rejected)
        self.result_bytes = self.result_path.read_bytes()
        wf.atomic_json(self.job / "blueprints/p0_blueprint.json", {
            "kind": "p0", "article_brief": "保持深度目标。", "opening": "项目需求。",
            "sections": [{"heading": "方法", "task": "说明方法关系。"}], "ending": "完成解释。",
            "writing_material_markdown": "已有原件事实和项目细节。", "writing_material_sources": []})
        wf.atomic_json(self.job / "production/p0_styled.json", {"article_markdown": "未通过的候选正文。"})
        for stage in ("draft", "edit", "style", "titles", "title_review"):
            wf.atomic_json(wf.action_paths(self.job, "p0_" + stage)[2], {"old_stage": stage})

    def args(self, *extra, revision=7):
        return wf.parser().parse_args(["continue", "--job-dir", str(self.job),
                                       "--revision", str(revision), *extra])

    def test_explicit_blueprint_edits_archive_rejection_and_use_existing_handler(self):
        with patch.object(wf, "drive", return_value=41) as drive:
            result = wf.continue_workflow(self.args("--p0-blueprint-edits", "保留原委托，补足项目方法展开。"))
        self.assertEqual(result, 41)
        drive.assert_called_once_with(self.job)
        state = wf.load_state(self.job)
        self.assertEqual(state["status"], "running_p0_blueprint")
        self.assertEqual(state["revision"], 7)
        self.assertIsNone(state["pending_action"])
        self.assertEqual(state["decisions"]["blueprint_edits"], "保留原委托，补足项目方法展开。")
        self.assertNotIn("p0_blueprint_confirmation", state["decisions"])
        self.assertNotIn("retry_current_action", state["flags"])
        self.assertEqual(state["metadata"]["p0_production_bindings"], {})
        history = state["metadata"]["p0_quality_rework_history"]
        archived = self.job / history[0]["result_path"]
        self.assertEqual(archived.read_bytes(), self.result_bytes)
        self.assertEqual(history[0]["result_sha256"], wf.sha256_file(archived))
        self.assertEqual(history[0]["requested_route"], "blueprint_edits")
        self.assertTrue((self.job / "production/p0_styled.json").is_file())
        self.assertTrue((self.job / "inputs/p0_blueprint_edit_outline.json").is_file())
        for stage in ("draft", "edit", "style", "finalize", "titles", "title_review"):
            path = wf.action_paths(self.job, "p0_" + stage)[2]
            self.assertFalse(path.exists())
            self.assertTrue(list((path.parent / "invalidated").glob("*/result.json")))

    def test_supplement_is_saved_then_routes_to_blueprint_without_confirmation(self):
        with patch.object(wf, "drive", return_value=42):
            self.assertEqual(wf.continue_workflow(self.args("--p0-blueprint-supplement", "新增原件中的工作分工事实。")), 42)
        state = wf.load_state(self.job)
        self.assertEqual(state["status"], "running_p0_blueprint")
        self.assertNotIn("p0_blueprint_confirmation", state["decisions"])
        self.assertNotIn("blueprint_edits", state["decisions"])
        saved = list((self.job / "inputs/user_materials/p0").glob("*/user_text.md"))
        self.assertEqual(saved[0].read_text().strip(), "新增原件中的工作分工事实。")
        self.assertEqual(state["metadata"]["p0_quality_rework_history"][0]["requested_route"], "blueprint_supplement")

    def test_stale_or_ambiguous_request_does_not_mutate_rejection(self):
        requests = [self.args("--p0-blueprint-edits", "修改", revision=6),
                    self.args("--accept-p0-blueprint"),
                    self.args("--p0-blueprint-edits", "修改", "--retry-current-action"),
                    self.args("--p0-blueprint-edits", "修改", "--p0-blueprint-supplement", "材料")]
        before = (self.job / "job_state.json").read_bytes()
        for args in requests:
            with self.subTest(args=args), patch.object(wf, "drive") as drive:
                with self.assertRaises(wf.WorkflowError):
                    wf.continue_workflow(args)
                drive.assert_not_called()
                self.assertEqual((self.job / "job_state.json").read_bytes(), before)
                self.assertEqual(self.result_path.read_bytes(), self.result_bytes)

    def test_no_implicit_rework_and_legacy_contract_keeps_existing_routing(self):
        with patch.object(wf, "drive", return_value=43) as drive:
            self.assertEqual(wf.continue_workflow(self.args()), 43)
        drive.assert_called_once_with(self.job)
        self.assertNotIn("p0_quality_rework_history", wf.load_state(self.job)["metadata"])
        state = wf.load_state(self.job)
        state["metadata"]["p0_style_contract"] = p0_style.LEGACY_STYLE_CONTRACT_VERSION
        wf.save_state(self.job, state)
        with patch.object(wf, "drive", return_value=44):
            self.assertEqual(wf.continue_workflow(self.args("--p0-blueprint-edits", "旧任务请求")), 44)
        self.assertEqual(wf.load_state(self.job)["status"], "running_p0_production")
        self.assertNotIn("p0_quality_rework_history", wf.load_state(self.job)["metadata"])


if __name__ == "__main__":
    unittest.main()
