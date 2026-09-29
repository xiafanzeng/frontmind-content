"""Explicit editor migration through the real controller; no paid model calls.

Completed source fixtures and simulated transports test provenance and dispatch,
not model writing quality. No production Job or credential file is accessed.
"""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.tests_v411.test_article_reader_final8 import fixture_profile
from shared import article_positioning as positioning, article_reader as reader
from shared import manuscript_revision as revisions, model_runtime as runtime, natural_editor

OPTION = "--upgrade-article-editor"


class ArticleEditorUpgradeTests(unittest.TestCase):
    def setUp(self):
        # Delay this integration fixture until discovery has finished. Its
        # historical dynamic module name is also loaded by existing suites.
        from scripts.tests_v411 import test_manuscript_revision as fixtures
        global wf
        wf = fixtures.wf
        self.case = fixtures.ManuscriptRevisionTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.transport = self.case.fixture
        self.request = self.case.request
        self.request.write_text("CURRENT_REVISION：重组全文同类问题，保留合成企业的事实及选择条件。", encoding="utf-8")
        # The controller's credential-leak guard and runtime read no real config.
        guard = patch.object(runtime, "load_configuration", return_value={})
        guard.start()
        self.addCleanup(guard.stop)

    @staticmethod
    def inventory(root):
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in root.rglob("*") if p.is_file()}

    def start(self, job, *, upgrade=True):
        extra = ["--manuscript-edits", str(self.request)]
        if upgrade:
            extra.append(OPTION)
        args = self.case.args(job, *extra)
        with patch.object(wf, "drive", return_value=0):
            self.assertEqual(args.func(args), 0)

    def assert_upgrade_preserves_source(self, old_contract):
        job = self.case.completed("article")
        state = wf.load_state(job)
        if old_contract is not None:
            state["metadata"]["article_reader_contract"] = old_contract
        state["decisions"]["blueprint_edits"] = "HISTORICAL_REQUEST：保留原业务主题。"
        wf.save_state(job, state)
        evidence = job / "provider/article_draft/runtime/attempts/historical/request.json"
        wf.atomic_json(evidence, {"fixture": "immutable original request"})
        before = self.inventory(job)
        old_state = wf.load_state(job)
        original_validate = revisions.validate_completed_manuscript
        original_snapshot = wf.snapshot_completed_job_for_writing
        events = []

        def validate(*args, **kwargs):
            self.assertEqual(self.inventory(job), before)
            result = original_validate(*args, **kwargs)
            events.append("validated")
            return result

        def snapshot(*args, **kwargs):
            self.assertEqual(events, ["validated"])
            self.assertEqual(self.inventory(job), before)
            result = original_snapshot(*args, **kwargs)
            events.append("snapshotted")
            return result

        with patch.object(revisions, "validate_completed_manuscript", side_effect=validate), \
                patch.object(wf, "snapshot_completed_job_for_writing", side_effect=snapshot):
            self.start(job)
        state = wf.load_state(job)
        frozen = revisions.current_revision(wf, job, p0=False)
        archive = Path(frozen["source_snapshot"])
        self.assertEqual(events, ["validated", "snapshotted"])
        self.assertEqual(self.inventory(archive), before)
        self.assertEqual(wf.load_state(archive), old_state)
        self.assertEqual(state["metadata"]["article_reader_contract"], positioning.CURRENT_CONTRACT)
        self.assertEqual(frozen["editor_contract_change"], {
            "from": old_contract, "to": positioning.CURRENT_CONTRACT, "explicit_option": OPTION})
        self.assertEqual(frozen["base_markdown"], self.transport.final)
        self.assertEqual(frozen["edits_markdown"], self.request.read_text())
        self.assertEqual(state["revision"], old_state["revision"] + 1)
        self.assertEqual(state["flags"]["article_production_step"], "edit")
        self.assertEqual(state["reference_pack"], old_state["reference_pack"])
        self.assertEqual(state["decisions"], old_state["decisions"])
        for name in ("production/article_draft.json", "blueprints/article_blueprint.json",
                     evidence.relative_to(job).as_posix()):
            self.assertEqual((job / name).read_bytes(), before[name])
        self.assertEqual(self.transport.payloads, [])

    def test_legacy_upgrade_validates_then_snapshots_before_setting_contract(self):
        self.assert_upgrade_preserves_source(None)

    def test_v8_upgrade_preserves_the_exact_prior_contract_and_request(self):
        self.assert_upgrade_preserves_source(reader.CONTRACT)

    def assert_rejected_unchanged(self, job, args):
        before = self.inventory(job)
        siblings = set(job.parent.iterdir())
        with patch.object(wf, "snapshot_completed_job_for_writing") as snapshot, \
                patch.object(wf, "drive") as drive:
            with self.assertRaises(wf.WorkflowError):
                args.func(args)
            snapshot.assert_not_called()
            drive.assert_not_called()
        self.assertEqual(self.inventory(job), before)
        self.assertEqual(set(job.parent.iterdir()), siblings)
        self.assertEqual(self.transport.payloads, [])

    def test_invalid_options_and_stale_revision_fail_without_snapshots_or_mutation(self):
        job = self.case.completed("article")
        common = ["--manuscript-edits", str(self.request), OPTION]
        invalid = [self.case.args(job, OPTION),
                   self.case.args(job, OPTION, "--title-edits", str(self.request))]
        for extra in (["--accept-blueprint"], ["--blueprint-edits", "rewrite"],
                      ["--retry-current-action"], ["--title-edits", str(self.request)],
                      ["--p0-rework", "edit"], ["--question-positioning-edits", "change"]):
            invalid.append(self.case.args(job, *common, *extra))
        stale = self.case.args(job, *common)
        stale.revision -= 1
        invalid.append(stale)
        for args in invalid:
            with self.subTest(options={k: v for k, v in vars(args).items() if v and k != "func"}):
                self.assert_rejected_unchanged(job, args)

    def test_incomplete_article_cannot_opt_in(self):
        job = self.case.completed("article")
        state = wf.load_state(job)
        state["status"] = "running_article_production"
        wf.save_state(job, state)
        self.assert_rejected_unchanged(job, self.case.args(
            job, "--manuscript-edits", str(self.request), OPTION))

    def test_completed_p0_can_explicitly_opt_in_to_current_shared_editor(self):
        job = self.case.completed("p0")
        self.start(job)
        state = wf.load_state(job)
        self.assertEqual(state["metadata"]["writing_editor_contract"], natural_editor.CONTRACT)
        self.assertNotIn("article_reader_contract", state["metadata"])
        self.assertEqual(state["flags"]["p0_production_step"], "edit")

    def test_unverified_or_changed_publication_cannot_trigger_upgrade(self):
        job = self.case.completed("article")
        state = wf.load_state(job)
        state["flags"]["offline_fixture"] = False
        wf.save_state(job, state)
        self.assert_rejected_unchanged(job, self.case.args(
            job, "--manuscript-edits", str(self.request), OPTION))
        state["flags"]["offline_fixture"] = True
        wf.save_state(job, state)
        Path(state["metadata"]["delivery"]["markdown"]).write_text("tampered delivery")
        self.assert_rejected_unchanged(job, self.case.args(
            job, "--manuscript-edits", str(self.request), OPTION))

    def test_snapshot_failure_never_changes_editor_contract(self):
        job = self.case.completed("article")
        before = self.inventory(job)
        siblings = set(job.parent.iterdir())
        with patch.object(wf, "snapshot_completed_job_for_writing", side_effect=wf.WorkflowError("snapshot failed")), \
                patch.object(wf, "drive") as drive:
            with self.assertRaisesRegex(wf.WorkflowError, "snapshot failed"):
                wf.continue_workflow(self.case.args(job, "--manuscript-edits", str(self.request), OPTION))
            drive.assert_not_called()
        self.assertEqual(self.inventory(job), before)
        self.assertEqual(set(job.parent.iterdir()), siblings)

    def test_without_flag_legacy_and_p0_keep_their_original_editor_route(self):
        for prefix in ("article", "p0"):
            with self.subTest(prefix=prefix):
                job = self.case.completed(prefix)
                self.start(job, upgrade=False)
                state = wf.load_state(job)
                frozen = revisions.current_revision(wf, job, p0=prefix == "p0")
                self.assertNotIn("article_reader_contract", state["metadata"])
                self.assertNotIn("editor_contract_change", frozen)
                prompt = wf.prompt_edit(job, p0=prefix == "p0")
                self.assertNotIn(positioning.MARKER, prompt)
                self.assertNotIn(positioning.CURRENT_MARKER, prompt)
                self.assertNotIn(reader.MARKER, prompt)
                self.assertIn("不要从头重写", prompt)
        self.assertEqual(wf.make_state("new", "article")["metadata"]["article_reader_contract"], positioning.CURRENT_CONTRACT)
        self.assertNotIn("article_reader_contract", wf.make_state("new-p0", "p0")["metadata"])

    def test_without_flag_v8_contract_is_not_silently_migrated(self):
        job = self.case.completed("article")
        state = wf.load_state(job)
        state["metadata"]["article_reader_contract"] = reader.CONTRACT
        wf.save_state(job, state)
        self.start(job, upgrade=False)
        self.assertEqual(wf.load_state(job)["metadata"]["article_reader_contract"], reader.CONTRACT)
        self.assertNotIn("editor_contract_change", revisions.current_revision(wf, job, p0=False))
        self.assertTrue(wf.prompt_edit(job, p0=False).startswith(reader.MARKER + "\n"))

    def test_upgraded_controller_dispatches_current_payloads_without_rewriting_draft(self):
        job = self.case.completed("article")
        original = {name: (job / name).read_bytes() for name in (
            "production/article_draft.json", "blueprints/article_blueprint.json")}
        self.start(job)
        state = wf.load_state(job)
        state["flags"]["offline_fixture"] = False
        wf.save_state(job, state)
        self.transport.edit_payload = {
            "edit_status": "accepted", "article_markdown": self.transport.final,
            "editorial_notes": [], "requires_blueprint_reconfirmation": False,
            "reconfirmation_reason": ""}
        self.transport.expected_candidate = self.transport.final
        self.transport.final_outcome = "accepted"
        with patch.object(wf, "prompt_article", side_effect=AssertionError("must not restart draft")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(wf.drive(job), 0)
        self.assertEqual(wf.load_state(job)["status"], "completed")
        self.assertEqual(set(self.transport.counts), {
            "article_edit", "article_finalize", "article_titles", "article_title_review"})
        self.assertEqual(self.transport.counts["article_edit"], 1)
        for action in ("article_edit", "article_finalize"):
            prompt = (job / "provider" / action / "prompt.md").read_text()
            self.assertTrue(natural_editor.matches(prompt))
            self.assertEqual(prompt.count(self.request.read_text()), 1)
            self.assertNotIn("不要从头重写", prompt)
            self.assertNotIn("本轮基于已完成终稿局部精修", prompt)
            # Also exercise the current SDK wire-plan builder with precisely
            # the prompt that the real production controller dispatched.
            with patch.object(runtime, "profile_for", side_effect=fixture_profile):
                payload = runtime.build_payload(action, prompt)
            if action == "article_edit":
                system = payload["messages"][0]["content"]
                self.assertEqual(payload["messages"][1]["content"], prompt)
                actual = next(v for a, v in self.transport.payloads if a == action)
                self.assertEqual(actual["messages"][0]["content"], system)
                self.assertEqual(actual["messages"][1]["content"], prompt.rstrip())
            else:
                system = payload["instructions"]
                self.assertEqual(payload["input"][0]["content"], prompt)
                self.assertEqual(payload["stop_at_tool_names"], ["submit_result"])
            self.assertTrue(system.startswith(natural_editor.system(action, prompt)))
            self.assertNotIn(positioning.CHOICE_LOGIC, system)
        for name, data in original.items():
            self.assertEqual((job / name).read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
