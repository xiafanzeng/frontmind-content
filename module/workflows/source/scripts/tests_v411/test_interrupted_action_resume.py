"""Controller regressions; real-provider acceptance runs separately."""
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/frontmind_workflow.py"
spec = importlib.util.spec_from_file_location("resume_controller", SCRIPT)
controller = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = controller
spec.loader.exec_module(controller)


class InterruptedActionResume(unittest.TestCase):
    def test_rejected_attachment_stops_before_research_and_keeps_intake_receipt(self):
        root = Path(tempfile.mkdtemp(prefix="frontmind-partial-intake-"))
        job = root / "job"
        controller.ensure_new_job(job, "reference_pack", job_id="partial-intake-job")
        valid = root / "企业资料.md"
        valid.write_text("# 企业资料\n合成企业提供测试服务。", encoding="utf-8")
        invalid = root / "损坏介绍.pptx"
        invalid.write_bytes(b"invalid pptx")
        with self.assertRaisesRegex(controller.WorkflowError, "材料接收未完成.*损坏介绍.pptx"):
            controller._create_material_pack_for_job(job, "合成企业", [valid, invalid])
        receipt = json.loads((job / "inputs/material_intake_report.json").read_text())
        self.assertEqual(receipt["accepted_count"], 1)
        self.assertEqual(receipt["rejected_count"], 1)
        self.assertEqual(receipt["input_items"][1]["status"], "rejected")
        self.assertFalse(controller.load_state(job)["metadata"].get("created_material_pack_in_job"))
        self.assertFalse((job / "provider").exists())

    def test_real_cli_starts_brand_without_materials_and_requires_original_revision(self):
        job = Path(tempfile.mkdtemp(prefix="frontmind-intake-")) / "job"
        started = subprocess.run([sys.executable, "-B", str(SCRIPT), "reference-pack", "create",
            "--brand", "流程回归企业", "--job-dir", str(job)], text=True, capture_output=True)
        self.assertEqual(started.returncode, 0, started.stderr)
        original = json.loads((job / "job_state.json").read_text())
        self.assertEqual(original["status"], "awaiting_reference_pack_input")
        self.assertFalse(original["flags"]["offline_fixture"])
        self.assertFalse((job / "provider").exists())
        stale = subprocess.run([sys.executable, "-B", str(SCRIPT), "continue", "--job-dir", str(job),
            "--revision", str(original["revision"] + 1), "--retry-current-action"], text=True, capture_output=True)
        self.assertEqual(stale.returncode, 2)
        self.assertEqual(json.loads((job / "job_state.json").read_text()), original)

    def test_interrupted_pending_action_resumes_without_inventing_error_or_new_job(self):
        job = Path(tempfile.mkdtemp(prefix="frontmind-resume-")) / "job"
        controller.ensure_new_job(job, "reference_pack", job_id="original-job")
        state = controller.load_state(job)
        state.update(status="running_positioning_market_research", stage="positioning_research", revision=4,
            pending_action={"action": "positioning_market_research", "requires_provider_action": True})
        controller.save_state(job, state)
        args = controller.parser().parse_args(["continue", "--job-dir", str(job), "--revision", "4", "--retry-current-action"])
        with controller.job_execution_lock(job), patch.object(controller, "drive", return_value=0) as drive:
            self.assertEqual(controller.continue_workflow(args), 0)
            drive.assert_called_once_with(job.resolve())
        resumed = controller.load_state(job)
        self.assertEqual(resumed["job_id"], "original-job")
        self.assertEqual(resumed["revision"], 4)
        self.assertEqual(resumed["pending_action"], state["pending_action"])
        self.assertEqual(resumed["flags"]["retry_current_action"], "positioning_market_research")

    def test_stop_between_provider_actions_continues_the_saved_stage(self):
        job = Path(tempfile.mkdtemp(prefix="frontmind-stage-resume-")) / "job"
        controller.ensure_new_job(job, "reference_pack", job_id="original-stage-job")
        state = controller.load_state(job)
        state.update(status="running_reference_pack_assembly", stage="reference_pack_assembly", revision=5)
        controller.save_state(job, state)
        args = controller.parser().parse_args(["continue", "--job-dir", str(job), "--revision", "5", "--retry-current-action"])
        with controller.job_execution_lock(job), patch.object(controller, "drive", return_value=0) as drive:
            self.assertEqual(controller.continue_workflow(args), 0)
            drive.assert_called_once_with(job.resolve())
        self.assertEqual(controller.load_state(job), state)


if __name__ == "__main__":
    unittest.main()
