"""Synthetic, offline regressions for raw model evidence and derived validation."""
import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from shared import agents_runtime as agents, model_runtime as runtime
from scripts.tests_v411.test_model_runtime import FakeTools
from scripts.tests_v411.test_positioning_contracts import C, RESEARCH, BRAND


class SubmissionImmutabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.attempt = Path(temporary.name)
        self.arguments = {"result": {"candidates": [{"name": "Synthetic candidate"}]}}
        self.original = copy.deepcopy(self.arguments)
        self.call_id = "synthetic-submit"
        self.response = self.attempt / "model_0001_response.json"
        runtime._atomic(self.response, {"output": [{
            "type": "function_call", "call_id": self.call_id, "name": "submit_result",
            "arguments": json.dumps(self.arguments),
        }]})
        self.model_bytes = self.response.read_bytes()
        self.tools = FakeTools()
        self.tools.read = True
        self.record = {"requested_configuration": {"max_tool_calls": 10}, "dependencies": []}
        runtime._atomic(self.attempt / "request_plan.json", {
            "profile": self.record["requested_configuration"], "instructions": "Synthetic input", "input": [],
        })
        (self.attempt / "prompt.md").write_text("Synthetic input")

    def receipt(self):
        filename = "tool_" + hashlib.sha256(self.call_id.encode()).hexdigest() + ".json"
        return runtime._read_json(self.attempt / filename)

    @staticmethod
    def normalize(value):
        value["candidates"][0]["id"] = "c001"
        return value

    def invoke(self, validator):
        journal = agents.ToolJournal(self.attempt, self.record, self.tools, validator, [])
        return json.loads(asyncio.run(journal.invoke("submit_result", self.call_id, json.dumps(self.arguments))))

    def test_market_research_normalization_leaves_nested_input_unchanged(self):
        for wrapped in (False, True):
            with self.subTest(wrapped=wrapped):
                raw = copy.deepcopy(RESEARCH)
                raw["competitor_candidates"][0]["source_urls"] = [None, "https://example.com/source"]
                value = {"choice_map": raw} if wrapped else raw
                before = copy.deepcopy(value)
                normalized = C.normalize_research_result(value, BRAND)
                self.assertEqual(value, before)
                self.assertEqual(normalized["competitor_candidates"][0]["id"], "c001")
                self.assertEqual(normalized["competitor_candidates"][0]["source_urls"], ["https://example.com/source"])
                self.assertIsNot(normalized["competitor_candidates"][0], raw["competitor_candidates"][0])

    def test_completed_journal_preserves_raw_arguments_and_restores_derived_result(self):
        self.assertEqual(self.invoke(self.normalize), {"submitted": True})
        self.assertEqual(self.receipt()["arguments"], self.original)
        self.assertEqual(runtime._read_json(self.attempt / "parsed_result.json"), self.original["result"])
        checked = runtime._read_json(self.attempt / "validated_result.json")
        self.assertEqual(checked["candidates"][0]["id"], "c001")
        runtime._atomic(self.attempt / "completion.json", {"status": "submitted"})
        self.record.update(agents_evidence_sha256=agents.evidence_manifest(self.attempt), result_sha256=agents.digest(checked))
        self.assertEqual(agents.restore_result(self.attempt, self.record, FakeTools(), self.normalize,
                                              verify_current_inputs=False), checked)
        # Both first submission and cached replay keep the immutable source bytes.
        self.assertEqual(self.invoke(self.normalize), {"submitted": True})
        self.assertEqual(self.receipt()["arguments"], self.original)
        self.assertEqual(self.response.read_bytes(), self.model_bytes)

    def test_rejected_validation_cannot_change_durable_feedback_arguments(self):
        def rejected(value):
            self.normalize(value)
            raise ValueError("Synthetic contract failure")
        first = self.invoke(rejected)
        self.assertEqual(first["error"], "invalid_result_contract")
        self.assertEqual(self.receipt()["arguments"], self.original)
        self.assertEqual(self.invoke(rejected), first)
        self.assertFalse((self.attempt / "submission.json").exists())
        self.assertEqual(self.response.read_bytes(), self.model_bytes)

    def test_validator_returning_none_keeps_normalization_separate(self):
        original = copy.deepcopy(self.original["result"])
        def mutate_without_return(value):
            self.normalize(value)
        checked = runtime._checked(mutate_without_return, original)
        self.assertEqual(original, self.original["result"])
        self.assertEqual(checked["candidates"][0]["id"], "c001")

    def test_mismatched_tool_arguments_and_name_still_fail_closed(self):
        for name, arguments in (("submit_result", {"result": {"forged": True}}),
                                ("read_material", self.arguments)):
            with self.subTest(name=name), self.assertRaises(runtime.ProviderActionError) as error:
                agents._source_call(self.attempt, self.call_id, name, arguments)
            self.assertEqual(error.exception.code, "tool_call_source_mismatch")
        self.assertEqual(self.response.read_bytes(), self.model_bytes)


if __name__ == "__main__":
    unittest.main()
