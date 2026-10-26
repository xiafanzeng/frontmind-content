import base64
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.host_tools import HostTools, ToolError
from shared.pptx_material import read_pptx, presentation_text
from Reference_Pack_Workflow.shared.reference_pack_builder import _text_from_pptx


class PptxMaterialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.job = self.root / "job"
        (self.job / "inputs").mkdir(parents=True)
        self.path = self.job / "inputs/企业介绍.pptx"
        self.image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=")
        ns = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        def rels(items):
            return '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(
                f'<Relationship Id="{key}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{kind}" Target="{target}"/>'
                for key, kind, target in items) + '</Relationships>'
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("ppt/presentation.xml", f'<p:presentation {ns}><p:sldIdLst><p:sldId id="300" r:id="second"/><p:sldId id="301" r:id="first"/></p:sldIdLst></p:presentation>')
            archive.writestr("ppt/_rels/presentation.xml.rels", rels([("first", "slide", "slides/slide1.xml"), ("second", "slide", "slides/slide2.xml")]))
            archive.writestr("ppt/slides/slide2.xml", f'''<p:sld {ns}><p:cSld><p:spTree>
              <p:grpSp><p:sp><p:txBody><a:p><a:r><a:t>品牌</a:t></a:r><a:r><a:t>介绍 &amp; 服务</a:t></a:r><a:br/><a:r><a:t>第二行</a:t></a:r></a:p></p:txBody></p:sp></p:grpSp>
              <p:graphicFrame><a:graphic><a:graphicData><a:tbl><a:tr><a:tc><a:txBody><a:p><a:r><a:t>项目</a:t></a:r></a:p></a:txBody></a:tc><a:tc><a:txBody><a:p><a:r><a:t>设备</a:t></a:r></a:p></a:txBody></a:tc></a:tr></a:tbl></a:graphicData></a:graphic></p:graphicFrame>
              <p:pic><p:blipFill><a:blip r:embed="image"/></p:blipFill></p:pic>
              </p:spTree></p:cSld></p:sld>''')
            archive.writestr("ppt/slides/slide1.xml", f'<p:sld {ns}><p:cSld><p:spTree><p:pic><p:blipFill><a:blip r:embed="image"/></p:blipFill></p:pic></p:spTree></p:cSld></p:sld>')
            archive.writestr("ppt/slides/slide99.xml", f'<p:sld {ns}><a:p><a:r><a:t>不在播放序列中</a:t></a:r></a:p></p:sld>')
            archive.writestr("ppt/slides/_rels/slide2.xml.rels", rels([("note", "notesSlide", "../notesSlides/notesSlide8.xml"), ("image", "image", "../media/photo.png")]))
            archive.writestr("ppt/slides/_rels/slide1.xml.rels", rels([("image", "image", "../media/photo.png")]))
            archive.writestr("ppt/notesSlides/notesSlide8.xml", f'''<p:notes {ns}><p:cSld><p:spTree>
              <p:sp><p:nvSpPr><p:nvPr><p:ph type="body"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>仅在备注中的来源说明</a:t></a:r></a:p></p:txBody></p:sp>
              <p:sp><p:nvSpPr><p:nvPr><p:ph type="sldNum"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>99</a:t></a:r></a:p></p:txBody></p:sp>
              </p:spTree></p:cSld></p:notes>''')
            archive.writestr("ppt/media/photo.png", self.image)

    def tearDown(self):
        self.tmp.cleanup()

    def test_preserves_presentation_order_table_runs_groups_and_notes(self):
        slides = read_pptx(self.path)
        self.assertEqual([s["part"] for s in slides], ["ppt/slides/slide2.xml", "ppt/slides/slide1.xml"])
        self.assertEqual(slides[0]["text"], "品牌介绍 & 服务\n第二行\n项目\t设备")
        self.assertEqual(slides[0]["notes"], "仅在备注中的来源说明")
        self.assertEqual(slides[1]["text"], "")
        self.assertEqual(_text_from_pptx(self.path), presentation_text(slides))
        self.assertNotIn("不在播放序列中", presentation_text(slides))

    def test_agent_can_read_pptx_with_slide_images_ocr_and_source_provenance(self):
        tools = HostTools(self.root, self.job, "p0_blueprint")
        original = next(r["artifact_id"] for r in tools.artifacts.values() if r["path"].endswith(".pptx"))
        with patch.object(tools, "_api", side_effect=AssertionError("native text extraction should not call a provider")):
            result = tools.execute("extract_document", {"artifact_id": original})
        self.assertEqual(result["pages_requiring_ocr"], [2])
        self.assertFalse(result["complete"])
        self.assertTrue(result["native_text_complete"])
        self.assertEqual(result["image_text_status"], "not_extracted")
        self.assertEqual(result["slide_count"], 2)
        self.assertEqual(result["image_count"], 1)
        self.assertEqual(len(result["image_artifacts"]), 1)
        self.assertEqual(result["slides"][0]["image_artifacts"], result["slides"][1]["image_artifacts"])
        image_id = result["image_artifacts"][0]
        image_path = self.job / tools.artifacts[image_id]["path"]
        self.assertEqual(image_path.read_bytes(), self.image)
        source = {"writing_material_sources": [{"source_ref": original, "use": "企业事实"}]}
        with self.assertRaises(ToolError):
            tools.validate_result_sources(source)
        text = tools.execute("read_material", {"artifact_id": result["artifact_id"]})
        self.assertIn("# Slide 1\n品牌介绍", text["text"])
        self.assertIn(image_id, text["text"])
        self.assertTrue(tools.validate_result_sources(source))
        with patch.object(tools, "_api", return_value={"md_results": "图片中的合成文字"}) as api:
            ocr = tools.execute("ocr", {"artifact_id": image_id})
        self.assertEqual(api.call_args.args[0], "layout_parsing")
        self.assertEqual(ocr["total_chars"], len("图片中的合成文字"))
        self.assertIn("Read artifact_id with read_material", ocr["next_step"])
        self.assertEqual(tools.execute("read_material", {"artifact_id": ocr["artifact_id"]})["text"], "图片中的合成文字")
        restored = HostTools(self.root, self.job, "p0_blueprint")
        restored.restore_state(tools.export_state())
        self.assertTrue(restored.validate_result_sources(source))

    def test_slides_with_native_headings_still_have_unread_image_text(self):
        with zipfile.ZipFile(self.path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        members["ppt/slides/slide1.xml"] = members["ppt/slides/slide1.xml"].replace(
            b"<p:spTree>",
            '<p:spTree><p:sp><p:txBody><a:p><a:r><a:t>图片页标题</a:t></a:r></a:p></p:txBody></p:sp>'.encode(),
        )
        with zipfile.ZipFile(self.path, "w") as archive:
            for name, data in members.items():
                archive.writestr(name, data)
        tools = HostTools(self.root, self.job, "p0_blueprint")
        original = next(r["artifact_id"] for r in tools.artifacts.values() if r["path"].endswith(".pptx"))
        result = tools.execute("extract_document", {"artifact_id": original})
        self.assertEqual(result["pages_requiring_ocr"], [])
        self.assertTrue(result["native_text_complete"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["image_text_status"], "not_extracted")


if __name__ == "__main__":
    unittest.main()
