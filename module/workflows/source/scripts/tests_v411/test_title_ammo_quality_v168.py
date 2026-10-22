"""Context-preserving title hooks and advisory editing, without model calls."""
import copy
import unittest

from shared import title_ammo, title_quality


class TitleAmmoTests(unittest.TestCase):
    def test_empty_material_has_no_invented_hooks(self):
        ammo = title_ammo.extract("")
        self.assertEqual(ammo["items"], [])
        self.assertEqual(ammo["numbers"], [])
        self.assertIn("不补造", title_ammo.render(ammo))

    def test_numeric_identifiers_keep_product_context(self):
        text = "检测约2分钟完成，设备采用12通道采集。专利号为ZL202630024381.0，标准为GB/T 12345-2024。"
        ammo = title_ammo.extract(text)
        for token in ("2分钟", "12通道", "ZL202630024381.0", "GB/T 12345-2024"):
            self.assertIn(token, ammo["numbers"])
        self.assertTrue(all(row["body_covered"] for row in ammo["items"]))
        rendered = title_ammo.render(ammo)
        self.assertIn("检测约2分钟完成，设备采用12通道采集", rendered)

    def test_requirements_do_not_turn_author_counts_into_product_facts(self):
        ammo = title_ammo.extract("", "正文3000字，篇幅3600字符，生成10个标题，5个正式标题；检测约2分钟完成，设备采用12通道。")
        self.assertEqual(ammo["numbers"], ["2分钟", "12通道"])
        self.assertTrue(all(not row["body_covered"] for row in ammo["items"]))

    def test_events_are_original_relationships_not_isolated_actions(self):
        text = "仁南健康科技有限公司与香港中文大学（深圳）开展合作。美中发展贸易协会代表到访公司。合作；到访。"
        ammo = title_ammo.extract(text)
        self.assertIn("仁南健康科技有限公司与香港中文大学（深圳）开展合作", ammo["events"])
        self.assertIn("美中发展贸易协会代表到访公司", ammo["events"])
        self.assertNotIn("合作", ammo["events"])
        self.assertNotIn("到访", ammo["events"])
        self.assertIn("美中发展贸易协会代表到访公司", title_ammo.render(ammo))

    def test_chinese_organization_boundaries_exclude_relationship_prefixes(self):
        ammo = title_ammo.extract("该产品由仁南健康科技有限公司与香港中文大学（深圳）联合研发，美中发展贸易协会代表到访。")
        self.assertIn("仁南健康科技有限公司", ammo["orgs"])
        self.assertIn("香港中文大学（深圳）", ammo["orgs"])
        self.assertIn("美中发展贸易协会", ammo["orgs"])
        self.assertNotIn("该产品由仁南健康科技有限公司", ammo["orgs"])
        self.assertNotIn("与香港中文大学（深圳）", ammo["orgs"])

    def test_extra_preserves_origin_source_and_body_coverage_without_verification(self):
        extra = ["检测2分钟完成", {"text": "美中发展贸易协会代表到访", "source": "客户资料第3页"}]
        ammo = title_ammo.extract("这款设备放在药店。", extra=extra)
        event = next(row for row in ammo["items"] if row["kind"] == "event")
        self.assertEqual(event["origin"], "extra")
        self.assertEqual(event["source"], "客户资料第3页")
        self.assertFalse(event["body_covered"])
        self.assertIn("不等于独立核验", title_ammo.render(ammo))
        self.assertIn("正文未覆盖", title_ammo.render(ammo))
        self.assertIn("2分钟", ammo["numbers"])

    def test_reusing_a_number_does_not_claim_an_extra_relationship_is_in_body(self):
        ammo = title_ammo.extract("工作人员讨论了2分钟。", extra=["检测2分钟完成"])
        row = next(row for row in ammo["items"] if row["kind"] == "number" and row["origin"] == "extra")
        self.assertFalse(row["body_covered"])

    def test_decimal_and_standard_numbers_are_not_split_or_reassembled(self):
        ammo = title_ammo.extract("设备重1.5公斤，检测时间约2.5分钟。采用ISO 12345-2标准。")
        self.assertIn("1.5公斤", ammo["numbers"])
        self.assertIn("2.5分钟", ammo["numbers"])
        self.assertIn("ISO 12345-2", ammo["numbers"])
        self.assertIn("设备重1.5公斤，检测时间约2.5分钟", title_ammo.render(ammo))

    def test_invalid_extra_values_do_not_become_assertions(self):
        ammo = title_ammo.extract("", extra=[None, 25, {"source": "附件"}, {"text": "设备重1.5公斤", "source": "附件"}])
        self.assertEqual(ammo["extra"], ["设备重1.5公斤"])
        self.assertTrue(all(row.get("source") == "附件" for row in ammo["items"]))


class TitleQualityTests(unittest.TestCase):
    def test_feedback_is_non_mutating_and_old_optional_fields_are_allowed(self):
        rows = [{"title": "一款让日常健康服务更方便的检测终端", "angle": "产品用途"}]
        before = copy.deepcopy(rows)
        self.assertEqual(title_quality.quality_feedback(rows), [])
        self.assertEqual(rows, before)

    def test_empty_or_sparse_ammo_never_adds_coverage_quotas(self):
        rows = [{"title": "一款让日常健康服务更方便的检测终端", "angle": "产品用途"}]
        for ammo in (None, title_ammo.extract(""), title_ammo.extract("检测2分钟完成。")):
            self.assertEqual(title_quality.quality_feedback(rows, ammo), [])

    def test_long_brand_is_not_mistaken_for_a_long_function_list(self):
        brand = "仁南医生蛋仔机器人健康管理终端"
        rows = [{"title": brand + "：放在药店的一份日常健康记录", "angle": "药店", "style": "formal"}]
        self.assertFalse(any("阅读长度" in item for item in title_quality.quality_feedback(rows, brand=brand)))

    def test_structure_feedback_points_to_titles_without_banning_literal_connectivity(self):
        rows = [
            {"title": "舌象、面象、脉象与问诊信息一起进入报告", "angle": "报告", "style": "formal"},
            {"title": "终端连接健康信息采集与服务场景", "angle": "采集", "style": "scenario"},
            {"title": "连接蓝牙耳机，戴着它就能听音乐", "angle": "听音乐"},
            {"title": "报告能回看、能打印，健康记录就在手边", "angle": "记录"},
        ]
        hints = title_quality.quality_feedback(rows)
        self.assertTrue(any("title_01" in item and "并列" in item for item in hints))
        self.assertTrue(any("title_02" in item and "内部机制" in item for item in hints))
        self.assertFalse(any("title_03" in item and "内部机制" in item for item in hints))
        self.assertTrue(any("title_04" in item and "罗列功能" in item for item in hints))

    def test_reordered_material_and_exact_angle_are_advisory_not_prefix_collisions(self):
        rows = [
            {"title": "终端让舌象面象脉象问诊信息进入健康报告", "angle": "报告：手机保存"},
            {"title": "终端让脉象舌象面象问诊信息进入健康报告", "angle": "报告：打印讲解"},
        ]
        hints = title_quality.quality_feedback(rows)
        self.assertTrue(any("换语序" in item for item in hints))
        self.assertFalse(any("angle 相同" in item for item in hints))
        rows[1]["angle"] = rows[0]["angle"]
        self.assertTrue(any("angle 相同" in item for item in title_quality.quality_feedback(rows)))

    def test_p01_p02_do_not_receive_an_organization_naming_quota(self):
        ammo = title_ammo.extract("北方大学与东方研究院开展合作。")
        rows = [{"title": "一款让日常健康服务更方便的检测终端", "angle": "产品用途"}]
        for pattern in ("P01", "P02"):
            self.assertEqual(title_quality.quality_feedback(rows, ammo, pattern=pattern), [])
        self.assertTrue(any("可挑选一个" in item for item in title_quality.quality_feedback(rows, ammo, pattern="P0")))

    def test_function_list_and_repeated_progression_suggestions_do_not_rewrite(self):
        rows = [
            {"title": "报告能回看，也能打印", "angle": "报告"},
            {"title": "从现场检测到手机记录", "angle": "留存"},
            {"title": "从一次沟通到长期健康记录", "angle": "持续服务"},
        ]
        before = copy.deepcopy(rows)
        hints = title_quality.quality_feedback(rows)
        self.assertTrue(any("罗列功能" in item for item in hints))
        self.assertTrue(any("重复使用“从" in item for item in hints))
        self.assertEqual(rows, before)


if __name__ == "__main__":
    unittest.main()
