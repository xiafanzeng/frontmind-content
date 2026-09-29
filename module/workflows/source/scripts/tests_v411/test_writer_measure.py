"""Writer-local measurement, exact output preservation and paid-call recovery."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import model_runtime as rt, natural_editor, writer_measure
from shared import writing_context_v14 as current
from scripts.tests_v411.test_model_runtime import stream, tool_stream


def valid(value):
    if not isinstance(value.get("article_markdown"), str):
        raise ValueError("article_markdown required")
    return value


class WriterMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "package"
        self.job = Path(self.tmp.name) / "job"
        self.root.mkdir()
        self.job.mkdir()
        self.prompt = current.wrap(writer_measure.MARKER + "\n写成正文，目标3000字符。")
        self.body = "# 不统计主标题\n\n**机构名称** 正文 A1。\n\n## 小标题\n[业务](https://example.test)"
        self.result = {"article_markdown": self.body}

    def run_action(self, transport, *, action="article_repair", prompt=None, retry=False):
        return rt.run_action(self.root, self.job, action, self.prompt if prompt is None else prompt,
                             valid, retry=retry, transport=transport, offline=True)

    def latest(self):
        record = rt.action_record(self.job, "article_repair")
        return self.job / "provider/article_repair/runtime/attempts" / record["attempt_id"], record

    def count_stream(self):
        return tool_stream("count_article", {"article_markdown": self.body}, model="deepseek-v4-pro")

    def test_only_explicit_new_article_body_requests_have_counter(self):
        for action in rt.DEEPSEEK_ACTIONS:
            with self.subTest(action=action):
                new = rt.build_payload(action, self.prompt)
                self.assertEqual("tools" in new, action in writer_measure.ACTIONS)
                if action in writer_measure.ACTIONS:
                    self.assertEqual([x["function"]["name"] for x in new["tools"]], ["count_article"])
                    self.assertIn(writer_measure.GUIDANCE, new["messages"][0]["content"])
                old = rt.build_payload(action, current.wrap("写成正文。"))
                self.assertNotIn("tools", old)
                self.assertNotIn(writer_measure.GUIDANCE, old["messages"][0]["content"])
        # A pasted marker later in material cannot activate a tool session.
        self.assertFalse(writer_measure.matches("article_edit", current.wrap("素材\n" + writer_measure.MARKER)))

    def test_counter_is_read_only_and_returns_only_the_shared_count(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("no file access")):
            result = writer_measure.execute("count_article", {"article_markdown": self.body})
        self.assertEqual(result, {"body_characters": natural_editor.character_count(self.body)})
        for name, arguments in (("read_material", {}), ("count_article", {"path": "/etc/passwd"}),
                                ("count_article", {"article_markdown": self.body, "target": 3000})):
            with self.assertRaises(ValueError):
                writer_measure.execute(name, arguments)

    def test_count_round_preserves_reasoning_and_exact_final_json_without_length_gate(self):
        payloads = []
        def transport(profile, key, payload):
            payloads.append(payload)
            return self.count_stream() if len(payloads) == 1 else stream(content=json.dumps(self.result))
        self.assertEqual(self.run_action(transport), self.result)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(payloads[1]["messages"][2]["reasoning_content"], "preserved tool thought")
        self.assertEqual(payloads[1]["messages"][3], {
            "role": "tool", "tool_call_id": "call-1", "content": rt._json({"body_characters": natural_editor.character_count(self.body)})})
        _, record = self.latest()
        self.assertEqual(record["tool_calls"], 1)
        self.assertEqual(record["requested_configuration"]["reasoning_effort"], "high")
        self.assertEqual(self.run_action(lambda *args: self.fail("completed output must be cached")), self.result)

    def test_count_is_an_author_aid_not_a_new_required_result_gate(self):
        self.assertEqual(self.run_action(lambda *args: stream(content=json.dumps(self.result))), self.result)

    def test_interrupt_after_count_resumes_same_conversation_without_rewriting(self):
        calls = []
        def interrupted(profile, key, payload):
            calls.append(payload)
            if len(calls) == 1:
                return self.count_stream()
            raise rt.ProviderActionError("network_timeout", "simulated interruption")
        with self.assertRaises(rt.ProviderActionError):
            self.run_action(interrupted)
        old, old_record = self.latest()
        def resume(profile, key, payload):
            self.assertEqual(payload["messages"], calls[1]["messages"])
            return stream(content=json.dumps(self.result))
        self.assertEqual(self.run_action(resume, retry=True), self.result)
        new, record = self.latest()
        self.assertNotEqual(new, old)
        self.assertEqual(record["resumed_tools_from_attempt"], old_record["attempt_id"])
        self.assertEqual(self.run_action(lambda *args: self.fail("recovered output must be cached")), self.result)

    def test_complete_count_recovers_if_checkpoint_write_was_interrupted(self):
        real_checkpoint = rt._checkpoint
        def fail_after_count(attempt, messages, host_tools, tool_count, pending_submission=None):
            if tool_count:
                raise OSError("simulated checkpoint failure")
            return real_checkpoint(attempt, messages, host_tools, tool_count, pending_submission)
        with patch.object(rt, "_checkpoint", side_effect=fail_after_count):
            with self.assertRaises(rt.ProviderActionError):
                self.run_action(lambda *args: self.count_stream())
        def resume(profile, key, payload):
            self.assertEqual(payload["messages"][-1]["role"], "tool")
            self.assertEqual(json.loads(payload["messages"][-1]["content"])["body_characters"], natural_editor.character_count(self.body))
            return stream(content=json.dumps(self.result))
        self.assertEqual(self.run_action(resume, retry=True), self.result)

    def test_old_v14_request_stays_direct_and_zero_call_recoverable(self):
        old_prompt = current.wrap("旧任务正文请求。")
        self.assertEqual(self.run_action(lambda *args: stream(content=json.dumps(self.result)), prompt=old_prompt), self.result)
        self.assertEqual(self.run_action(lambda *args: self.fail("old completed writer called again"), prompt=old_prompt), self.result)

    def test_saved_counter_feedback_cannot_be_forged_for_recovery(self):
        calls = []
        def transport(profile, key, payload):
            calls.append(payload)
            return self.count_stream() if len(calls) == 1 else stream(content=json.dumps(self.result))
        self.run_action(transport)
        attempt, record = self.latest()
        path = attempt / "round_02_request.json"
        request = rt._read_json(path)
        request["messages"][3]["content"] = '{"body_characters":3000}'
        rt._atomic(path, request)
        with self.assertRaises(ValueError):
            rt._saved_result(attempt, record, None, valid, persist=False)


if __name__ == "__main__":
    unittest.main()
