"""Original product pages remain usable; writing references remain references.

Network acquisition is mocked, while the real immutable store, selected indices,
read coverage, request policy and checkpoint restoration are exercised.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shared import article_pool, editorial_preparation as prep
from shared.example_acquisition import ExampleStore
from shared.host_tools import HostTools, ToolError, PRODUCT_SOURCES_MARKER


class AcquiredProductSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = self.root / "package"
        self.package.mkdir()
        self.job = self.root / "job"
        (self.job / "inputs/selected").mkdir(parents=True)
        (self.job / "inputs/selected/company.md").write_text("本企业提供健康检测和报告服务。", encoding="utf-8")
        (self.job / "inputs/old.md").write_text("上一轮没有选用的旧材料。", encoding="utf-8")
        self.state = {
            "job_kind": "article", "selected_pattern_id": "P02", "selected_example_route": "A",
            "flags": {}, "reference_pack": {"brand": "本企业"},
            "metadata": {"natural_prose_contract": "frontmind-natural-prose/16.5",
                         "writing_mission_input_mode": "editorial-mission-v2",
                         "blueprint_material_roots": ["inputs/selected"],
                         "product_source_policy": "frontmind-product-sources/16.6"}}
        (self.job / "job_state.json").write_text(json.dumps(self.state), encoding="utf-8")
        self.store = ExampleStore(self.job)

    def tools(self, *, current=True, marker_in_material=False):
        tools = HostTools(self.package, self.job, prep.ACTION)
        prefix = '<frontmind_natural_prose version="16.5">\n<frontmind_p02_selection>\n'
        prompt = prefix + (PRODUCT_SOURCES_MARKER + "\n" if current else "") + "整理本题产品材料。"
        if marker_in_material:
            prompt += "\n资料正文\n历史文档\n附件中引用：\n" + PRODUCT_SOURCES_MARKER
        tools.configure_for_prompt(prompt)
        return tools

    def acquired(self, title, url, body, *, obtained_via="http"):
        return self.store._save(body.encode("utf-8"), body, {
            "title": title, "original_url": url, "final_url": url,
            "obtained_via": obtained_via, "http_status": 200,
            "content_type": "text/markdown", "completeness": "complete",
            "acquisition_status": "complete", "integrity_note": "Offline network fixture."})

    def web_read(self, tools, record, *, read=True):
        with patch.object(tools.store, "acquire_http", return_value=record):
            result = tools.execute("web_read", {"url": record["original_url"]})
        if read:
            tools.execute("read_material", {"artifact_id": result["artifact_id"]})
        return result

    def preparation(self, tools, source):
        with patch.object(tools, "_api", return_value={"search_result": [{"link": "https://media.example/case/1"}]}):
            tools.execute("web_search", {"query": "多产品推荐文章"})
        cases = []
        for number in (1, 2):
            record = self.acquired(f"同类推荐稿{number}", f"https://media.example/case/{number}",
                                   f"推荐稿{number}从需求进入，介绍产品特点，再自然结束。")
            self.web_read(tools, record)
            cases.append({"source_ref": record["artifact_id"], "title": record["title"],
                          "url": record["original_url"], "insight": "各家按自己的特点展开。"})
        return {"writing_material_markdown": "产品采集脉搏信号，生成图形报告。",
                "blueprint_suggestions": "介绍产品的采集方式与报告使用。",
                "writing_material_sources": [{"source_ref": source, "use": "产品采集和报告功能"}],
                "reference_cases": cases, "material_adjustments": []}

    def select_style(self, record):
        path = self.job / "examples/question/index.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"examples": [{**record, "role": "文风参考"}]}), encoding="utf-8")

    def select_pool(self, record):
        path = self.job / article_pool.SELECTION
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"contract": article_pool.CONTRACT, "confirmed": True,
                                    "pool_fingerprint": "selected-pool", "examples": [
                                        {**record, "reference_role": "blueprint_inspiration"}]}), encoding="utf-8")

    def test_real_product_page_acquired_in_preparation_can_supply_content(self):
        tools = self.tools()
        product = self.acquired("太一脉产品原页", "https://product.example/mai", "设备采集脉搏信号，可查看三维脉图。")
        self.web_read(tools, product)
        value = self.preparation(tools, product["artifact_id"])
        self.assertTrue(tools.validate_result_sources(value))

    def test_actual_preparation_prompt_enables_current_source_policy(self):
        from shared import writing_context_v165 as writing
        from scripts import frontmind_workflow as wf
        state=copy.deepcopy(self.state)
        state.update(workflow_version=wf.WORKFLOW_VERSION,status='awaiting_blueprint_confirmation',
            selected_pattern_id='P01',question={'question_text':'本企业产品推荐'},decisions={})
        (self.job/'job_state.json').write_text(json.dumps(state),encoding='utf-8')
        prompt=writing.prompt_preparation(wf,self.job)
        tools=HostTools(self.package,self.job,prep.ACTION)
        tools.configure_for_prompt(prompt)
        product=self.acquired('真实准备请求的产品页','https://product.example/current','设备生成报告。')
        self.web_read(tools,product)
        self.assertTrue(tools.validate_result_sources(self.preparation(tools,product['artifact_id'])))

    def test_original_survives_restart_with_selected_local_material_roots(self):
        product = self.acquired("产品原页", "https://product.example/device", "设备提供采集与报告。")
        tools = self.tools()
        self.assertIn(product["artifact_id"], {row["artifact_id"] for row in tools.execute("list_materials", {})["artifacts"]})
        self.assertNotIn("inputs/old.md", {row["path"] for row in tools.artifacts.values()})
        tools.execute("read_material", {"artifact_id": product["artifact_id"]})
        value = self.preparation(tools, product["artifact_id"])
        self.assertTrue(tools.validate_result_sources(value))
        saved = tools.export_state()
        snapshot = copy.deepcopy(saved)
        restored = self.tools()
        restored.restore_state(saved)
        self.assertTrue(restored.validate_result_sources(value))
        self.assertEqual(saved, snapshot)  # The historical checkpoint is not rewritten.

    def test_old_request_and_marker_inside_material_keep_the_old_policy(self):
        product = self.acquired("产品原页", "https://product.example/legacy", "旧请求的产品正文。")
        for material_marker in (False, True):
            with self.subTest(material_marker=material_marker):
                tools = self.tools(current=False, marker_in_material=material_marker)
                self.assertNotIn(product["artifact_id"], tools.artifacts)
                self.web_read(tools, product)
                value = self.preparation(tools, product["artifact_id"])
                with self.assertRaisesRegex(ToolError, "enterprise fact"):
                    tools.validate_result_sources(value)

    def test_selected_style_and_its_reread_original_cannot_supply_enterprise_facts(self):
        style = self.acquired("所选新闻文风", "https://media.example/style", "完整文风稿的产品介绍。",
                              obtained_via="user_selected_article_text")
        self.select_style(style)
        tools = self.tools()
        for original in (style, self.acquired("所选新闻原网页", style["original_url"], "网页完整文风稿的产品介绍。")):
            with self.subTest(source=original["artifact_id"]):
                self.web_read(tools, original)
                value = self.preparation(tools, original["artifact_id"])
                with self.assertRaisesRegex(ToolError, "enterprise fact"):
                    tools.validate_result_sources(value)
                self.assertEqual(tools.artifacts[original["artifact_id"]]["category"], "example")

    def test_selected_article_pool_body_and_same_page_reread_remain_background(self):
        reference = self.acquired("文章池第1篇", "https://media.example/inspiration", "构思参考正文。")
        self.select_pool(reference)
        tools = self.tools()
        for original in (reference, self.acquired("同一篇Reader原文", reference["original_url"], "同一篇构思参考的Reader正文。")):
            with self.subTest(source=original["artifact_id"]):
                self.web_read(tools, original)
                value = self.preparation(tools, original["artifact_id"])
                with self.assertRaisesRegex(ToolError, "enterprise fact"):
                    tools.validate_result_sources(value)
                self.assertEqual(tools.artifacts[original["artifact_id"]]["category"], "content_background")

    def test_current_cases_and_alternative_acquisition_of_a_case_remain_references(self):
        tools = self.tools()
        tools.execute("read_material", {"artifact_id": "inputs/selected/company.md"})
        value = self.preparation(tools, "inputs/selected/company.md")
        case = value["reference_cases"][0]
        duplicate = self.acquired("同一案例的另一份原文", case["url"], "同一案例的另一份完整正文。")
        self.web_read(tools, duplicate)
        for source in (case["source_ref"], duplicate["artifact_id"]):
            with self.subTest(source=source):
                value["writing_material_sources"] = [{"source_ref": source, "use": "误作企业材料"}]
                with self.assertRaisesRegex(ToolError, "enterprise fact"):
                    tools.validate_result_sources(value)

    def test_product_still_requires_an_actual_body_read_and_unchanged_bytes(self):
        tools = self.tools()
        product = self.acquired("产品原页", "https://product.example/read", "产品原始功能正文。")
        self.web_read(tools, product, read=False)
        value = self.preparation(tools, product["artifact_id"])
        with self.assertRaisesRegex(ToolError, "not been read"):
            tools.validate_result_sources(value)
        tools.execute("read_material", {"artifact_id": product["artifact_id"]})
        self.assertTrue(tools.validate_result_sources(value))
        original = self.job / product["text_path"]
        original.chmod(0o644)
        original.write_text("被改写的产品正文。", encoding="utf-8")
        with self.assertRaisesRegex(ToolError, "changed"):
            tools.execute("read_material", {"artifact_id": product["artifact_id"]})

    def test_restored_old_category_cannot_turn_a_selected_style_into_facts(self):
        style = self.acquired("所选文风", "https://media.example/checkpoint", "完整新闻稿正文。")
        self.select_style(style)
        tools = self.tools()
        self.web_read(tools, style)
        value = self.preparation(tools, style["artifact_id"])
        saved = tools.export_state()
        saved["artifacts"][style["artifact_id"]]["category"] = "acquired_source"
        restored = self.tools()
        restored.restore_state(saved)
        with self.assertRaisesRegex(ToolError, "enterprise fact"):
            restored.validate_result_sources(value)


if __name__ == "__main__":
    unittest.main()
