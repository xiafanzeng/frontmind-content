"""Offline regressions for freezing answers from distinct AI platforms."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts import frontmind_workflow as wf
from shared import question_bank_import as bank


class DistinctAIPlatformAnswersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name)

    def question(self, platforms, repeats=1):
        return {
            "question_uid": "q000001", "question_text": "合成选题",
            "period_id": "p000001", "observed_from": "2026-10-10",
            "observed_to": "2026-10-10",
            "answers": [
                {"platform": platform, "answer_text": f"{platform}原始完整答案{sample}。\n\n保留段落。",
                 "answer_id": f"a{n * repeats + sample + 1:06d}",
                 "period_id": "p000001", "sampled_at": "2026-10-10",
                 "source_record": {"sheet": "详细表格", "row": 2 + n * 20 + sample,
                                   "question_text": "合成选题", "date_raw": "2026-10-10"}}
                for n, platform in enumerate(platforms) for sample in range(repeats)
            ],
        }

    def test_known_web_and_mobile_clients_are_not_two_ai_platforms(self):
        for name in ("豆包", "元宝", "通义千问"):
            with self.subTest(platform=name):
                question = self.question([f"{name}-网页版", f"{name}-手机版"])
                with self.assertRaisesRegex(wf.WorkflowError, "两个不同 AI 平台"):
                    wf.freeze_question_inputs(self.job, question)
        self.assertFalse((self.job / "inputs/answer_01.md").exists())

    def test_selects_doubao_and_yuanbao_preserving_all_source_records(self):
        platforms = [f"{name}-{client}" for name in ("豆包", "元宝", "通义千问")
                     for client in ("网页版", "手机版")]
        question = self.question(platforms, repeats=5)
        original = copy.deepcopy(question)
        statistics = bank.known_platforms(question["answers"])
        frozen = wf.freeze_question_inputs(self.job, question)
        self.assertEqual(["豆包-网页版", "元宝-网页版"],
                         [a["platform"] for a in frozen["answers"]])
        self.assertEqual(["a000001", "a000011"], [a["answer_id"] for a in frozen["answers"]])
        self.assertEqual([original["answers"][0]["source_record"], original["answers"][10]["source_record"]],
                         [a["source_record"] for a in frozen["answers"]])
        self.assertEqual(original, question)
        self.assertEqual(original, json.loads((self.job / "inputs/question_observations.json").read_text()))
        self.assertEqual(30, len(question["answers"]))
        self.assertEqual(statistics, bank.known_platforms(question["answers"]))
        self.assertEqual(6, len(statistics))
        for selected, raw in zip(frozen["answers"], (original["answers"][0], original["answers"][10])):
            self.assertTrue(Path(selected["full_text_path"]).read_text().endswith(raw["answer_text"] + "\n"))

    def test_unknown_independent_names_are_not_fuzzily_merged(self):
        platforms = ["独立平台甲-网页版", "独立平台甲-手机版"]
        question = self.question(platforms)
        frozen = wf.freeze_question_inputs(self.job, question)
        self.assertEqual(platforms, [a["platform"] for a in frozen["answers"]])


if __name__ == "__main__":
    unittest.main()
