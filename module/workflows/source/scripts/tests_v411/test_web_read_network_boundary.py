"""The fetch location determines whether local DNS belongs in URL validation."""
import sys
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.example_acquisition import AcquisitionError, ExampleStore, public_url
from shared.host_tools import HostTools
from shared import agents_runtime as ar


class WebReadNetworkBoundaryTests(unittest.TestCase):
    def test_reader_fetches_without_local_dns_and_preserves_the_actual_response(self):
        job = Path(tempfile.mkdtemp(prefix="reader-boundary-"))
        store = ExampleStore(job)
        response = {"reader_result": {"url": "https://example.org/article",
            "title": "Article", "content": "First paragraph.\nSecond paragraph."}}
        reader = Mock(return_value=response)
        with patch("shared.example_acquisition.socket.getaddrinfo", side_effect=AssertionError("Reader must resolve remotely")):
            result = store.acquire_reader("https://example.org/article", reader)
        self.assertEqual(reader.call_args.args[0], "reader")
        self.assertEqual(reader.call_args.args[1]["url"], "https://example.org/article")
        self.assertEqual(result["obtained_via"], "zhipu_reader")
        self.assertEqual((job / result["text_path"]).read_text(), response["reader_result"]["content"])
        self.assertEqual(store.resolve(result["artifact_id"])["completeness"], "complete")

    def test_direct_http_keeps_its_local_address_check(self):
        address = [(2, 1, 6, "", ("198.18.2.41", 443))]
        with patch("shared.example_acquisition.socket.getaddrinfo", return_value=address):
            with self.assertRaisesRegex(AcquisitionError, "non-public address"):
                public_url("https://example.org/article")

    def test_reader_validates_http_url_before_contacting_provider(self):
        store = ExampleStore(Path(tempfile.mkdtemp(prefix="reader-address-")))
        reader = Mock()
        for url in ("file:///etc/hosts", "https://user:password@example.org", "https://example.org:22"):
            with self.subTest(url=url), self.assertRaises(AcquisitionError):
                store.acquire_reader(url, reader)
        reader.assert_not_called()



    def test_web_read_address_failure_is_model_feedback(self):
        root = Path(tempfile.mkdtemp(prefix="reader-error-"))
        tools = HostTools(root / "package", root / "job", "positioning_market_research")
        with self.assertRaises(AcquisitionError):
            tools.execute("web_read", {"url": "file:///etc/hosts", "method": "reader"})

    def test_interrupted_web_read_replays_only_on_explicit_resume(self):
        root = Path(tempfile.mkdtemp(prefix="reader-resume-"))
        tools = Mock()
        tools.export_state.return_value = {}
        tools.execute.side_effect = OSError("interrupted")
        record = {"requested_configuration": {"max_tool_calls": 10}, "retry_explicit": False}
        journal = ar.ToolJournal(root, record, tools, lambda value: value, [])
        arguments = json.dumps({"url": "https://example.org", "method": "reader"})
        (root / "model_0001_response.json").write_text(json.dumps({"output": [{"type": "function_call", "name": "web_read", "call_id": "read-page", "arguments": arguments}]}))
        (root / "request_plan.json").write_text(json.dumps({"instructions": "test", "input": []}))
        with self.assertRaises(OSError):
            asyncio.run(journal.invoke("web_read", "read-page", arguments))
        with self.assertRaisesRegex(Exception, "tool_outcome_unknown"):
            asyncio.run(journal.invoke("web_read", "read-page", arguments))
        self.assertEqual(tools.execute.call_count, 1)
        record["retry_explicit"] = True
        tools.execute.side_effect = None
        tools.execute.return_value = {"completeness": "complete"}
        result = json.loads(asyncio.run(journal.invoke("web_read", "read-page", arguments)))
        self.assertEqual(result["completeness"], "complete")
        receipt = json.loads(next(root.glob("tool_*.json")).read_text())
        self.assertEqual(receipt["readonly_replay_count"], 1)
        self.assertEqual(receipt["status"], "completed")
        asyncio.run(journal.invoke("web_read", "read-page", arguments))
        self.assertEqual(tools.execute.call_count, 2)

if __name__ == "__main__":
    unittest.main()
