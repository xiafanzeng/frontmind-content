"""Offline regressions for 408/stream failover and pre-fix saved failures.

Use the public OpenAI exception types but an explicit fake SDK for all model
responses. These tests make no network calls and never open a real Job.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openai

from shared import agents_runtime as ar, model_runtime as rt
from scripts.tests_v411.agents_sdk_fake import bundle
from scripts.tests_v411.test_model_runtime import FakeTools, valid


STREAM_ERROR = "stream disconnected before completion"
SAVED_408 = "Error code: 408 - {'error': {'message': 'stream disconnected before completion'}}"


def status_error(status, message="Request failed"):
    response = SimpleNamespace(request=SimpleNamespace(), status_code=status, headers={})
    return openai.APIStatusError(message, response=response, body={"message": message})


def model_bundle(errors=None, *, after_read=False):
    """Inject a genuine exception at the fake model boundary, preserving logs."""
    sdk, engine = bundle()
    base = sdk[0].OpenAIChatCompletionsModel
    observed = []
    errors = errors or {}

    class Model(base):
        async def get_response(self, **kwargs):
            observed.append(self.model)
            read = any(item.get("type") == "function_call_output" for item in kwargs["input"])
            if self.model in errors and (read or not after_read):
                engine.calls += 1
                raise errors[self.model]()
            return await super().get_response(**kwargs)

    sdk[0].OpenAIChatCompletionsModel = Model
    return sdk, observed


class HostBackup408Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pkg = Path(self.temp.name) / "pkg"
        (self.pkg / "config").mkdir(parents=True)
        self.job = Path(self.temp.name) / "job"
        self.job.mkdir()
        (self.pkg / "config/xty.json").write_text(json.dumps({
            "api_key": "offline-test-token", "base_url": "https://example.test/v1",
            "model": "host-primary", "backup_model": "host-backup", "backup_reasoning_effort": "max",
        }))

    def runit(self, sdk, *, job=None):
        return rt.run_action(self.pkg, job or self.job, "p0_blueprint", "unchanged current task", valid,
                             host_tools=FakeTools(), transport=sdk, offline=True)

    def records(self, job=None):
        root = (job or self.job) / "provider/p0_blueprint/runtime/attempts"
        return [(path.parent, rt._read_json(path)) for path in sorted(root.glob("*/execution.json"))]

    def make_old_failure(self, message=SAVED_408, *, job=None, code=None):
        sdk, observed = model_bundle({"host-primary": lambda: RuntimeError(message)}, after_read=True)
        # Reproduce the original classifier, not an invented successful result.
        with patch.object(ar, "_transport_failure", return_value=False):
            with self.assertRaises(rt.ProviderActionError):
                self.runit(sdk, job=job)
        rows = self.records(job)
        self.assertEqual(len(rows), 1)
        path, record = rows[0]
        self.assertEqual(observed, ["host-primary", "host-primary"])
        self.assertIs(record["error"]["transport"], False)
        if code:
            record["error"]["code"] = code
            (path / "execution.json").write_text(json.dumps(record))
        return path, copy.deepcopy(record)

    def assert_old_failure_recovers(self, message, *, move_latest=False):
        path, old = self.make_old_failure(message)
        unchanged = {name: (path / name).read_bytes() for name in
                     ("request_plan.json", "prompt.md", "checkpoint.json", "tool_read_material_1.json")
                     if (path / name).exists()}
        config_before = (self.pkg / "config/xty.json").read_bytes()
        if move_latest:
            other = path.parent / "unrelated-attempt"
            other.mkdir()
            (other / "execution.json").write_text(json.dumps({
                "attempt_id": other.name, "status": "failed", "fingerprint": "unrelated",
                "error": {"code": "invalid_result_contract", "message": SAVED_408, "transport": False},
            }))
            (path.parent.parent / "latest.json").write_text(json.dumps({"attempt_id": other.name}))
        sdk, observed = model_bundle()
        self.assertEqual(self.runit(sdk), {"ok": True})
        self.assertTrue(observed)
        self.assertEqual(set(observed), {"host-backup"})
        current = rt._read_json(path / "execution.json")
        self.assertEqual(current["error"], old["error"])
        self.assertEqual(current["model_calls"], old["model_calls"])
        self.assertEqual(current["fingerprint"], old["fingerprint"])
        self.assertEqual(current.get("resume_count"), old.get("resume_count"))
        self.assertTrue(current["failed_over_to_backup"])
        for name, before in unchanged.items():
            self.assertEqual((path / name).read_bytes(), before)
        self.assertEqual((self.pkg / "config/xty.json").read_bytes(), config_before)
        backup = next(record for _, record in self.records()
                      if record.get("requested_configuration", {}).get("model") == "host-backup")
        self.assertEqual(backup["status"], "succeeded")
        self.assertEqual(backup["fallback_for"], old["attempt_id"])
        self.assertNotEqual(backup["fingerprint"], old["fingerprint"])
        # A later plain continue restores the successful backup without billing
        # either model again, even though the original error stays unmodified.
        sdk2, observed2 = model_bundle()
        self.assertEqual(self.runit(sdk2), {"ok": True})
        self.assertEqual(observed2, [])

    def test_api_status_408_is_transport_without_message_hint(self):
        self.assertTrue(ar._transport_failure(status_error(408)))

    def test_explicit_stream_failures_are_transport(self):
        for message in (STREAM_ERROR, "Stream disconnected before completion",
                        "Stream closed before response.completed"):
            with self.subTest(message=message):
                self.assertTrue(ar._transport_failure(RuntimeError(message)))
        self.assertTrue(ar._transport_failure(
            openai.APIError(STREAM_ERROR, request=SimpleNamespace(), body=None)))

    def test_exception_cause_and_context_retain_transport_identity(self):
        for attribute in ("__cause__", "__context__"):
            outer = RuntimeError("SDK wrapper")
            setattr(outer, attribute, status_error(408))
            with self.subTest(attribute=attribute):
                self.assertTrue(ar._transport_failure(outer))

    def test_existing_connection_timeout_and_5xx_remain_transport(self):
        errors = [openai.APIConnectionError(request=SimpleNamespace()),
                  openai.APITimeoutError(request=SimpleNamespace()),
                  status_error(500), status_error(524), RuntimeError("Connection error."),
                  RuntimeError("Error code: 524 - origin timeout")]
        for error in errors:
            with self.subTest(error=type(error).__name__, text=str(error)):
                self.assertTrue(ar._transport_failure(error))

    def test_nontransport_http_status_overrides_incidental_stream_wording(self):
        for status in (400, 401, 403, 404, 409, 422, 429):
            for error in (status_error(status, STREAM_ERROR),
                          RuntimeError(f"Error code: {status} - {STREAM_ERROR}")):
                with self.subTest(status=status, error=type(error).__name__):
                    self.assertFalse(ar._transport_failure(error))

    def test_contract_tool_and_budget_errors_do_not_qualify_with_408_text(self):
        for code in ("invalid_result_contract", "tool_protocol_error", "model_turn_limit"):
            error = rt.ProviderActionError(code, SAVED_408)
            wrapped = RuntimeError("SDK wrapper")
            wrapped.__cause__ = error
            with self.subTest(code=code):
                self.assertFalse(ar._transport_failure(error))
                self.assertFalse(ar._transport_failure(wrapped))

    def test_408_failure_immediately_runs_backup_and_links_attempts(self):
        sdk, observed = model_bundle({"host-primary": lambda: status_error(408)})
        self.assertEqual(self.runit(sdk), {"ok": True})
        self.assertEqual(observed.count("host-primary"), 1)
        rows = {r["requested_configuration"]["model"]: r for _, r in self.records()}
        self.assertEqual(set(rows), {"host-primary", "host-backup"})
        self.assertTrue(rows["host-primary"]["error"]["transport"])
        self.assertTrue(rows["host-primary"]["failed_over_to_backup"])
        self.assertEqual(rows["host-backup"]["fallback_for"], rows["host-primary"]["attempt_id"])
        self.assertEqual(rows["host-backup"]["status"], "succeeded")

    def test_stream_failure_after_a_read_runs_backup(self):
        sdk, observed = model_bundle({"host-primary": lambda: RuntimeError(STREAM_ERROR)}, after_read=True)
        self.assertEqual(self.runit(sdk), {"ok": True})
        self.assertEqual(observed[:2], ["host-primary", "host-primary"])
        self.assertEqual(set(observed[2:]), {"host-backup"})

    def test_historical_408_plain_continue_skips_primary_and_preserves_error(self):
        self.assert_old_failure_recovers(SAVED_408)

    def test_historical_stream_plain_continue_skips_primary_and_preserves_error(self):
        self.assert_old_failure_recovers(STREAM_ERROR)

    def test_recovery_uses_matching_attempt_instead_of_unrelated_latest(self):
        self.assert_old_failure_recovers(SAVED_408, move_latest=True)

    def test_historical_contract_tool_and_budget_408_text_never_runs_backup(self):
        for code in ("invalid_result_contract", "tool_protocol_error", "model_turn_limit"):
            with self.subTest(code=code):
                job = self.job / code
                job.mkdir()
                path, old = self.make_old_failure(code=code, job=job)
                sdk, observed = model_bundle()
                with self.assertRaises(rt.ProviderActionError):
                    self.runit(sdk, job=job)
                self.assertEqual(observed, [])
                self.assertEqual(len(self.records(job)), 1)
                self.assertEqual(rt._read_json(path / "execution.json"), old)

    def test_nontransport_http_never_runs_backup(self):
        for status in (401, 403, 404, 429):
            with self.subTest(status=status):
                job = self.job / str(status)
                job.mkdir()
                sdk, observed = model_bundle({"host-primary": lambda: status_error(status, STREAM_ERROR)})
                with self.assertRaises(rt.ProviderActionError):
                    self.runit(sdk, job=job)
                self.assertEqual(observed, ["host-primary"])
                self.assertEqual(len(self.records(job)), 1)
                self.assertIs(self.records(job)[0][1]["error"]["transport"], False)

    def test_both_transport_failures_preserve_separate_attempts(self):
        sdk, observed = model_bundle({"host-primary": lambda: status_error(408),
                                      "host-backup": lambda: RuntimeError(STREAM_ERROR)})
        with self.assertRaises(rt.ProviderActionError) as result:
            self.runit(sdk)
        self.assertIn("主宿主与备用宿主", str(result.exception))
        self.assertEqual(observed, ["host-primary", "host-backup"])
        records = [record for _, record in self.records()]
        self.assertEqual(len(records), 2)
        self.assertTrue(all(record["status"] == "failed" for record in records))
        self.assertTrue(all(record["error"]["transport"] is True for record in records))
        primary = next(r for r in records if r["requested_configuration"]["model"] == "host-primary")
        backup = next(r for r in records if r["requested_configuration"]["model"] == "host-backup")
        self.assertEqual(backup["fallback_for"], primary["attempt_id"])
        self.assertTrue(primary["failed_over_to_backup"])

    def test_backup_contract_failure_is_not_mislabeled_as_transport(self):
        sdk, observed = model_bundle({"host-primary": lambda: status_error(408),
            "host-backup": lambda: rt.ProviderActionError("invalid_result_contract", SAVED_408)})
        with self.assertRaises(rt.ProviderActionError) as result:
            self.runit(sdk)
        self.assertEqual(observed, ["host-primary", "host-backup"])
        self.assertEqual(result.exception.code, "invalid_result_contract")
        self.assertNotIn("均在传输层失败", str(result.exception))
        backup = next(r for _, r in self.records() if r["requested_configuration"]["model"] == "host-backup")
        self.assertEqual(backup["error"]["code"], "invalid_result_contract")
        self.assertIs(backup["error"]["transport"], False)


if __name__ == "__main__":
    unittest.main()
