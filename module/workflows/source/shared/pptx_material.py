"""Read presentation text, notes and image parts in presentation order."""
from pathlib import PurePosixPath
import posixpath
import xml.etree.ElementTree as ET
import zipfile

NS = {
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"


def _relationships(archive, part):
    path = PurePosixPath(part)
    member = str(path.parent / "_rels" / (path.name + ".rels"))
    if member not in archive.namelist():
        return {}
    return {
        rel.attrib["Id"]: {
            "type": rel.attrib["Type"].rsplit("/", 1)[-1],
            "part": posixpath.normpath(posixpath.join(str(path.parent), rel.attrib["Target"])).lstrip("/"),
        }
        for rel in ET.fromstring(archive.read(member)).findall(REL)
        if rel.get("TargetMode") != "External"
    }


def _text_blocks(node):
    if node.tag == "{" + NS["a"] + "}p":
        return ["".join(
            child.text or "" if child.tag == "{" + NS["a"] + "}t" else
            "\n" if child.tag == "{" + NS["a"] + "}br" else
            "\t" if child.tag == "{" + NS["a"] + "}tab" else ""
            for child in node.iter()
        )]
    if node.tag == "{" + NS["a"] + "}tr":
        return ["\t".join(" / ".join(_text_blocks(cell)) for cell in node.findall("a:tc", NS))]
    return [text for child in node for text in _text_blocks(child) if text.strip()]


def read_pptx(path):
    """Read each slide's text and image paths. Do not fetch external links."""
    with zipfile.ZipFile(path) as archive:
        presentation = ET.fromstring(archive.read("ppt/presentation.xml"))
        relationships = _relationships(archive, "ppt/presentation.xml")
        slides = []
        for number, slide_id in enumerate(presentation.findall("p:sldIdLst/p:sldId", NS), 1):
            part = relationships[slide_id.attrib["{" + NS["r"] + "}id"]]["part"]
            slide = ET.fromstring(archive.read(part))
            rels = _relationships(archive, part)
            text = "\n".join(_text_blocks(slide))
            notes = []
            for rel in rels.values():
                if rel["type"] == "notesSlide":
                    note = ET.fromstring(archive.read(rel["part"]))
                    for shape in note.findall(".//p:sp", NS):
                        placeholder = shape.find("p:nvSpPr/p:nvPr/p:ph", NS)
                        if placeholder is None or placeholder.get("type") == "body":
                            notes.extend(_text_blocks(shape))
            image_parts = []
            for blip in slide.findall(".//a:blip", NS):
                embedded = blip.get("{" + NS["r"] + "}embed")
                if embedded:
                    image_parts.append(rels[embedded]["part"])
            slides.append({"number": number, "part": part, "text": text,
                           "notes": "\n".join(notes), "image_parts": list(dict.fromkeys(image_parts))})
        if not slides:
            raise ValueError("presentation has no slides")
        return slides


def presentation_text(slides):
    return "\n\n".join(
        f"# Slide {slide['number']}\n{slide['text']}" +
        (f"\n\n## Notes\n{slide['notes']}" if slide["notes"] else "")
        for slide in slides
    )
