"""Preserve wide monitoring exports without treating answers as brand facts."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook
from shared import question_bank_import as bank
from Reference_Pack_Workflow.shared import reference_pack_builder as builder


class WideMonitoringImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def workbook(self, platforms=("元宝", "千问", "豆包")):
        book = Workbook()
        original = {}
        for index, platform in enumerate(platforms):
            sheet = book.active if index == 0 else book.create_sheet()
            sheet.title = platform
            sheet.append(["品牌名称", "监控问题", "监控日期"] +
                         [f"答案{slot}" for slot in (1, 2) for _ in range(4)])
            sheet.append([None, None, None] + ["内容", "截图链接", "排名", "监控词排名"] * 2)
            answers = [f"  # {platform}样本{slot}\n\n完整段落。\r\n[citation:{slot}]  " for slot in (1, 2)]
            original[platform] = answers
            sheet.append(["合成品牌", "怎样选择服务？", "2026-06-22"] +
                         [value for slot, text in enumerate(answers, 1) for value in
                          (text, f"https://example.com/{index}/{slot}.png", slot + 2, slot)])
        path = self.root / "monitoring.xlsx"
        book.save(path)
        book.close()
        return path, original

    def test_wide_import_preserves_every_sample_and_provenance(self):
        path, original = self.workbook()
        before = path.read_bytes()
        self.assertTrue(bank.looks_like_monitoring(path))
        artifacts, index, report = bank.build_artifacts(path, brand="合成品牌")
        self.assertEqual((1, 3, 6), (report["question_count"], report["row_count"], report["answer_count"]))
        self.assertEqual(["2026-06-22"], report["observed_dates"])
        record = index["slices"][0]
        self.assertEqual(3, record["platform_count"])
        answers = artifacts[record["monitoring_path"]]["answers"]
        for platform_index, platform in enumerate(original):
            actual = [answer for answer in answers if answer["platform"] == platform]
            self.assertEqual(original[platform], [answer["answer_text"] for answer in actual])
            for slot, answer in enumerate(actual, 1):
                self.assertEqual(str(slot), answer["sample_label"])
                self.assertEqual(str(slot + 2), answer["exported_rank"])
                self.assertEqual(str(slot), answer["monitor_keyword_rank"])
                self.assertEqual(f"https://example.com/{platform_index}/{slot}.png", answer["screenshot_url"])
                self.assertEqual(platform, answer["source_record"]["sheet"])
                self.assertEqual(3, answer["source_record"]["row"])
                self.assertEqual("sha256:" + hashlib.sha256(before).hexdigest(), answer["source_record"]["file_sha256"])
                self.assertEqual([], answer["citations"])
        self.assertEqual(before, path.read_bytes())
        self.assertEqual("not_supplied", artifacts[record["citation_path"]]["availability"])

    def test_mixed_intake_keeps_wide_answers_out_of_business_registry(self):
        path, _ = self.workbook()
        business = self.root / "business.md"
        business.write_text("合成品牌提供本地软件服务。", encoding="utf-8")
        result = builder.create_reference_pack(brand_name="合成品牌", knowledge_base=[business, path], output=self.root / "pack")
        self.assertTrue(result["readiness"]["question_ready"]["q000001"])
        registry = (self.root / "pack/registries/knowledge_registry.json").read_text()
        self.assertNotIn("monitoring.xlsx", registry)

    def test_generic_sheet_name_is_not_an_observed_platform(self):
        path, _ = self.workbook(("Sheet1",))
        self.assertFalse(bank.looks_like_monitoring(path))
        artifacts, index, _ = bank.build_artifacts(path, brand="合成品牌")
        self.assertFalse(bank.readiness_for(index, lambda member: artifacts[member])["q000001"])


if __name__ == "__main__":
    unittest.main()
