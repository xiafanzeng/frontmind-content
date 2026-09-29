"""Offline streamed-EOF regressions through the actual completion wrapper.

The SDK, HTTP client, stream chunks, and model output are local fakes. Real
OpenAI value types only exercise the adapter's normal completion conversion.
"""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

import openai

from shared import agents_runtime as ar, model_runtime as rt
from scripts.tests_v411.agents_sdk_fake import bundle
from scripts.tests_v411.test_model_runtime import FakeTools, valid


def streamed_bundle(modes=None):
    modes = modes or {}
    sdk, engine = bundle()
    base_model = sdk[0].OpenAIChatCompletionsModel
    observed = []
    finish_reasons = []

    class Client:
        def __init__(self, **kwargs):
            self.chat = NS(completions=NS(create=self.create))
            self.fixture = None

        async def close(self):
            pass

        async def create(self, **kwargs):
            assert kwargs["stream"] is True
            model = kwargs["model"]
            mode = modes.get(model)
            if mode == "408":
                raise RuntimeError("Error code: 408 - stream disconnected before completion")
            output = self.fixture.output
            if mode in {"missing_finish", "partial_tool"}:
                delta = ({"reasoning_content": "offline synthetic reasoning"} if mode == "missing_finish"
                         else {"tool_calls": [{"index": 0, "id": "unfinished", "type": "function",
                               "function": {"name": "read_material", "arguments": '{"artifact_id":'}}]})
                finish = None
            elif mode in {"length", "content_filter"}:
                delta, finish = {"content": "incomplete offline output"}, mode
            elif output and output[0].get("type") == "function_call":
                call = output[0]
                delta = {"tool_calls": [{"index": 0, "id": call["call_id"], "type": "function",
                         "function": {"name": call["name"], "arguments": call["arguments"]}}]}
                finish = "tool_calls"
            else:
                delta, finish = {"content": "offline final text"}, "stop"
            finish_reasons.append(finish)

            async def chunks():
                if mode == "empty_stream":
                    return
                if mode == "missing_choices":
                    yield {"id": "offline-stream", "model": model, "choices": []}
                    return
                yield {"id": "offline-stream", "model": model, "choices": [
                    {"index": 0, "delta": delta, "finish_reason": None}]}
                if finish is not None:
                    yield {"id": "offline-stream", "model": model, "choices": [
                        {"index": 0, "delta": {}, "finish_reason": finish}]}
            return chunks()

    class Model(base_model):
        def __init__(self, model, openai_client):
            super().__init__(model=model, openai_client=openai_client)
            self.client = openai_client

        async def get_response(self, **kwargs):
            observed.append(self.model)
            if modes.get(self.model) == "plain":
                response = NS(output=[{"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "offline text, not a tool submission"}]}],
                    response_id="offline-plain")
            else:
                response = await super().get_response(**kwargs)
            self.client.fixture = response
            # execute_sdk replaces this create method with checked_completion;
            # the fake chunks therefore traverse the real merge and guards.
            await self.client.chat.completions.create(model=self.model)
            return response

    sdk[0].OpenAIChatCompletionsModel = Model
    sdk[1].AsyncOpenAI = Client
    sdk[1].types = openai.types
    return sdk, observed, finish_reasons


class StreamCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.pkg = Path(self.temp.name) / "pkg"
        (self.pkg / "config").mkdir(parents=True)
        self.job = Path(self.temp.name) / "job"
        self.job.mkdir()
        self.config = {"api_key": "offline-test-token", "base_url": "https://example.test/v1",
                       "model": "host-primary", "completion_transport": "stream_merged"}
        self.save_config()

    def save_config(self):
        (self.pkg / "config/xty.json").write_text(json.dumps(self.config))

    def runit(self, sdk, *, retry=False, job=None, prompt="unchanged task"):
        return rt.run_action(self.pkg, job or self.job, "p0_blueprint", prompt, valid,
                             host_tools=FakeTools(), transport=sdk, offline=True, retry=retry)

    def records(self, job=None):
        paths = ((job or self.job) / "provider/p0_blueprint/runtime/attempts").glob("*/execution.json")
        return [(p.parent, rt._read_json(p)) for p in sorted(paths)]

    def test_stream_eof_without_finish_is_transport_failure(self):
        sdk, observed, _ = streamed_bundle({"host-primary": "missing_finish"})
        with self.assertRaises(rt.ProviderActionError) as raised:
            self.runit(sdk)
        self.assertEqual(raised.exception.code, "stream_response_incomplete")
        self.assertTrue(getattr(raised.exception, "transport_failure", False))
        path, record = self.records()[0]
        self.assertEqual(record["error"]["code"], "stream_response_incomplete")
        self.assertIs(record["error"]["transport"], True)
        self.assertEqual(observed, ["host-primary"])
        self.assertFalse((path / "submission.json").exists())
        self.assertFalse(list(path.glob("tool_*.json")))

    def test_partial_tool_arguments_at_eof_are_never_executed(self):
        sdk, _, _ = streamed_bundle({"host-primary": "partial_tool"})
        with self.assertRaises(rt.ProviderActionError) as raised:
            self.runit(sdk)
        self.assertEqual(raised.exception.code, "stream_response_incomplete")
        path, _ = self.records()[0]
        self.assertFalse(list(path.glob("tool_*.json")))

    def test_empty_stream_is_incomplete_transport(self):
        sdk, _, _ = streamed_bundle({"host-primary": "empty_stream"})
        with self.assertRaises(rt.ProviderActionError) as raised:
            self.runit(sdk)
        self.assertEqual(raised.exception.code, "stream_response_incomplete")
        self.assertIs(self.records()[0][1]["error"]["transport"], True)

    def test_stream_without_choices_is_incomplete_transport(self):
        sdk, _, _ = streamed_bundle({"host-primary": "missing_choices"})
        with self.assertRaises(rt.ProviderActionError) as raised:
            self.runit(sdk)
        self.assertEqual(raised.exception.code, "stream_response_incomplete")
        self.assertIs(self.records()[0][1]["error"]["transport"], True)

    def test_valid_tool_calls_and_stop_complete_normally_without_usage(self):
        sdk, _, finishes = streamed_bundle()
        self.assertEqual(self.runit(sdk), {"ok": True})
        self.assertIn("tool_calls", finishes)
        self.assertIn("stop", finishes)
        self.assertEqual(self.records()[0][1]["status"], "succeeded")

    def test_length_and_content_filter_keep_existing_nontransport_error(self):
        for mode in ("length", "content_filter"):
            with self.subTest(mode=mode):
                job = self.job / mode
                job.mkdir()
                sdk, _, _ = streamed_bundle({"host-primary": mode})
                with self.assertRaises(rt.ProviderActionError) as raised:
                    self.runit(sdk, job=job)
                self.assertEqual(raised.exception.code, "model_output_incomplete")
                self.assertIs(self.records(job)[0][1]["error"]["transport"], False)

    def test_complete_plain_text_without_submit_remains_protocol_failure(self):
        self.config["backup_model"] = "host-backup"
        self.save_config()
        sdk, observed, finishes = streamed_bundle({"host-primary": "plain"})
        with self.assertRaises(rt.ProviderActionError) as raised:
            self.runit(sdk)
        self.assertEqual(raised.exception.code, "missing_submit_result")
        self.assertEqual(finishes, ["stop"])
        self.assertEqual(observed, ["host-primary"])
        self.assertEqual(len(self.records()), 1)
        self.assertIs(self.records()[0][1]["error"]["transport"], False)

    def test_stream_eof_can_fail_over_without_accepting_partial_response(self):
        self.config["backup_model"] = "host-backup"
        self.save_config()
        sdk, observed, _ = streamed_bundle({"host-primary": "missing_finish"})
        self.assertEqual(self.runit(sdk), {"ok": True})
        self.assertEqual(observed.count("host-primary"), 1)
        records = {r["requested_configuration"]["model"]: r for _, r in self.records()}
        self.assertEqual(records["host-primary"]["error"]["code"], "stream_response_incomplete")
        self.assertEqual(records["host-backup"]["status"], "succeeded")
        self.assertEqual(records["host-backup"]["fallback_for"], records["host-primary"]["attempt_id"])

    def test_explicit_retry_resumes_current_backup_without_recalling_primary(self):
        self.config["backup_model"] = "host-backup"
        self.save_config()
        # The old missing_submit_result must remain a protocol error. Explicit
        # retry may still resume its saved backup, using the existing contract.
        for mode in ("missing_finish", "plain"):
            with self.subTest(mode=mode):
                job = self.job / mode
                job.mkdir()
                sdk, _, _ = streamed_bundle({"host-primary": "408", "host-backup": mode})
                with self.assertRaises(rt.ProviderActionError):
                    self.runit(sdk, job=job)
                original = {r["requested_configuration"]["model"]: (p, r) for p, r in self.records(job)}
                self.assertEqual(set(original), {"host-primary", "host-backup"})
                primary_path, primary = original["host-primary"]
                backup_path, backup = original["host-backup"]
                before = (primary_path / "execution.json").read_bytes()
                sdk2, observed, _ = streamed_bundle()
                self.assertEqual(self.runit(sdk2, retry=True, job=job), {"ok": True})
                self.assertEqual(set(observed), {"host-backup"})
                self.assertEqual(len(self.records(job)), 2)
                self.assertEqual((primary_path / "execution.json").read_bytes(), before)
                resumed = rt._read_json(backup_path / "execution.json")
                self.assertEqual(resumed["attempt_id"], backup["attempt_id"])
                self.assertEqual(resumed["fingerprint"], backup["fingerprint"])
                self.assertEqual(resumed["resume_count"], 1)
                self.assertEqual(resumed["status"], "succeeded")

    def test_explicit_backup_retry_rejects_changed_input_before_any_model_call(self):
        self.config["backup_model"] = "host-backup"
        self.save_config()
        sdk, _, _ = streamed_bundle({"host-primary": "408", "host-backup": "missing_finish"})
        with self.assertRaises(rt.ProviderActionError):
            self.runit(sdk)
        old = {path: (path / "execution.json").read_bytes() for path, _ in self.records()}
        sdk2, observed, _ = streamed_bundle()
        with self.assertRaises(rt.ProviderActionError) as raised:
            self.runit(sdk2, retry=True, prompt="changed task cannot reuse old checkpoint")
        self.assertEqual(raised.exception.code, "agents_input_changed")
        self.assertEqual(observed, [])
        self.assertEqual(len(self.records()), 2)
        for path, before in old.items():
            self.assertEqual((path / "execution.json").read_bytes(), before)

    def test_plain_continue_does_not_retry_an_already_failed_backup(self):
        self.config["backup_model"] = "host-backup"
        self.save_config()
        sdk, _, _ = streamed_bundle({"host-primary": "408", "host-backup": "missing_finish"})
        with self.assertRaises(rt.ProviderActionError):
            self.runit(sdk)
        old = {path: (path / "execution.json").read_bytes() for path, _ in self.records()}
        sdk2, observed, _ = streamed_bundle()
        with self.assertRaises(rt.ProviderActionError) as raised:
            self.runit(sdk2)
        self.assertEqual(raised.exception.code, "agents_explicit_retry_required")
        self.assertEqual(observed, [])
        self.assertEqual(len(self.records()), 2)
        for path, before in old.items():
            self.assertEqual((path / "execution.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
