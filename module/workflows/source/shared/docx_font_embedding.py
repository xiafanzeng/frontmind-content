#!/usr/bin/env python3
"""Portable Noto font embedding for FrontMind DOCX deliveries.

Word stores embedded OpenType fonts as obfuscated ``.odttf`` parts.  This
module subsets the two bundled OFL Noto faces to the characters used by the
finished document, writes deterministic font keys, and can independently
reverse-check the resulting package. It deliberately does not discover host
fonts: the two fixed release files and their OFL text are the only authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping
import unicodedata
import uuid
import zipfile


try:
    from lxml import etree
except ImportError as exc:  # pragma: no cover - preflight reports the missing runtime
    raise RuntimeError("lxml is required for portable DOCX font embedding") from exc

from shared.portable_fonttools import load_vendored_fonttools, runtime_report as fonttools_runtime_report


FONT_FAMILY = "Noto Sans CJK SC"
FONT_UPSTREAM_VERSION = "2.004"
FONT_LICENSE_FILE = "OFL-Noto-CJK.txt"
FONT_FILES = (
    {
        "file": "NotoSansCJKsc-Regular.otf", "style": "Regular",
        "postscript_name": "NotoSansCJKsc-Regular", "minimum_codepoint_count": 40000,
    },
    {
        "file": "NotoSansCJKsc-Bold.otf", "style": "Bold",
        "postscript_name": "NotoSansCJKsc-Bold", "minimum_codepoint_count": 40000,
    },
)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
FONT_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"
ODTTF_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.obfuscatedFont"

FONT_TABLE_PATH = "word/fontTable.xml"
FONT_TABLE_RELS_PATH = "word/_rels/fontTable.xml.rels"
REGULAR_PART_PATH = "word/fonts/NotoSansCJKsc-Regular.odttf"
BOLD_PART_PATH = "word/fonts/NotoSansCJKsc-Bold.odttf"

# ECMA-376 requires a GUID for each obfuscated font stream.  The keys are
# stable release constants and are not derived from a document or font file.
FONT_KEYS = {
    "Regular": "{A96249BD-0456-5EF1-9B5E-1162072B8AB2}",
    "Bold": "{7B6AF24B-21D4-5BE3-B592-EB0F6FC4E421}",
}

# The exact finished text is authoritative.  Basic Latin is retained as a
# small editing/field safety margin without turning the subset back into a
# 16-MB full font.
BASELINE_CODEPOINTS = frozenset(range(0x20, 0x7F)) | {
    0x00A0,  # no-break space
    0x3000,  # ideographic space
}


class FontEmbeddingError(RuntimeError):
    """Raised when the release font or the embedded DOCX contract is invalid."""


@dataclass(frozen=True)
class EmbeddedFace:
    style: str
    source_file: str
    part_path: str
    relationship_id: str
    font_key: str
    subset_size: int
    glyph_count: int
    codepoint_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "style": self.style,
            "source_file": self.source_file,
            "part_path": self.part_path,
            "relationship_id": self.relationship_id,
            "font_key": self.font_key,
            "subset_size": self.subset_size,
            "glyph_count": self.glyph_count,
            "codepoint_count": self.codepoint_count,
        }


def _fonttools() -> tuple[Any, Any]:
    try:
        load_vendored_fonttools()
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except (ImportError, RuntimeError) as exc:
        raise FontEmbeddingError(
            "the release-vendored FontTools runtime is required to subset and validate portable DOCX fonts"
        ) from exc
    return subset, TTFont


def load_release_fonts(font_asset_root: Path) -> list[dict[str, Any]]:
    """Resolve and parse the two release-controlled Noto faces.

    File identity receipts are deliberately not part of the publication
    workflow.  The stronger runtime invariant is that each bundled file is a
    readable OpenType face with the declared family/style, editable embedding
    rights and the expected broad CJK glyph coverage.
    """
    # v3.7 uses fixed release paths.  A manifest would reintroduce a runtime
    # ledger and is unnecessary for these two bundled, licensed assets.
    license_path = font_asset_root / FONT_LICENSE_FILE
    if not license_path.is_file() or license_path.stat().st_size <= 0:
        raise FontEmbeddingError("bundled Noto license file is missing or empty")
    try:
        license_text = license_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FontEmbeddingError("bundled Noto license file is unreadable") from exc
    if "SIL OPEN FONT LICENSE Version 1.1" not in license_text:
        raise FontEmbeddingError("bundled Noto license file is not the declared OFL 1.1 text")

    _, TTFont = _fonttools()
    by_style: dict[str, dict[str, Any]] = {}
    for record in FONT_FILES:
        if not isinstance(record, dict):
            continue
        style = str(record.get("style") or "")
        path = font_asset_root / str(record.get("file") or "")
        if style not in {"Regular", "Bold"} or style in by_style:
            continue
        if not path.is_file() or path.stat().st_size <= 0:
            raise FontEmbeddingError(f"bundled font is missing or empty: {path.name}")
        try:
            font = TTFont(str(path), recalcTimestamp=False, lazy=False)
            family = font["name"].getDebugName(1)
            subfamily = font["name"].getDebugName(2)
            postscript_name = font["name"].getDebugName(6)
            version = font["name"].getDebugName(5) or ""
            fs_type = int(font["OS/2"].fsType)
            cmap = font.getBestCmap() or {}
            glyph_count = len(font.getGlyphOrder())
        except Exception as exc:
            raise FontEmbeddingError(f"bundled font is not readable OpenType: {path.name}") from exc
        minimum_codepoints = int(record.get("minimum_codepoint_count") or 1)
        expected_postscript = str(record.get("postscript_name") or "")
        missing_baseline = sorted(set(BASELINE_CODEPOINTS) - set(cmap))
        if family != FONT_FAMILY or subfamily != style:
            raise FontEmbeddingError(
                f"bundled font metadata mismatch: {path.name} ({family!r}, {subfamily!r})"
            )
        if expected_postscript and postscript_name != expected_postscript:
            raise FontEmbeddingError(f"bundled font PostScript name mismatch: {path.name}")
        if FONT_UPSTREAM_VERSION not in version:
            raise FontEmbeddingError(f"bundled font version mismatch: {path.name}")
        if fs_type != 0:
            raise FontEmbeddingError(
                f"bundled font is not installable/editable for embedding: {path.name}"
            )
        if missing_baseline or len(cmap) < minimum_codepoints or glyph_count <= len(cmap):
            raise FontEmbeddingError(f"bundled font glyph coverage is incomplete: {path.name}")
        by_style[style] = {
            **record,
            "path": path,
            "family": family,
            "subfamily": subfamily,
            "postscript_name": postscript_name,
            "fs_type": fs_type,
            "glyph_count": glyph_count,
            "codepoint_count": len(cmap),
        }
    if set(by_style) != {"Regular", "Bold"}:
        raise FontEmbeddingError("bundled Noto Regular/Bold faces are incomplete")
    return [by_style["Regular"], by_style["Bold"]]


def document_codepoints(parts: Mapping[str, bytes]) -> set[int]:
    """Collect characters that can be reader-visible in Word XML parts."""
    values: list[str] = []
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    for name, data in parts.items():
        if not name.startswith("word/") or not name.endswith(".xml"):
            continue
        try:
            root = etree.fromstring(data, parser)
        except Exception as exc:
            raise FontEmbeddingError(f"cannot parse DOCX XML while collecting glyphs: {name}") from exc
        for node in root.xpath(".//w:t | .//w:instrText | .//w:delText", namespaces={"w": W_NS}):
            if node.text:
                values.append(node.text)
        # Accessible image descriptions are not typeset in the article, but
        # retaining their glyphs keeps Word's accessibility panes portable.
        for node in root.xpath(".//*[local-name()='docPr']"):
            for attribute in ("name", "title", "descr"):
                value = node.get(attribute)
                if value:
                    values.append(value)
    # Unicode format controls such as WORD JOINER affect line breaking but do
    # not require a drawable font glyph.  Asking FontTools to retain them as
    # cmap entries makes a valid embedded subset fail when the source font
    # intentionally has no visible glyph for the control.
    return set(BASELINE_CODEPOINTS) | {
        ord(character)
        for value in values
        for character in value
        if unicodedata.category(character) != "Cf"
    }


def subset_font_bytes(font_path: Path, codepoints: Iterable[int]) -> tuple[bytes, dict[str, Any]]:
    """Create a deterministic OpenType subset and enforce editable embedding rights."""
    subset, TTFont = _fonttools()
    # Preserve the release font's global bounding box. Some Word-compatible
    # renderers consult ``head.yMin/yMax`` when resolving line boxes; recomputing
    # those bounds from a small Chinese subset can otherwise move page breaks
    # even though hhea/OS/2 metrics are unchanged.
    font = TTFont(
        str(font_path), recalcTimestamp=False, recalcBBoxes=False, lazy=False,
    )
    fs_type = int(font["OS/2"].fsType)
    if fs_type != 0:
        raise FontEmbeddingError(
            f"font {font_path.name} is not installable/editable for embedding (OS/2 fsType={fs_type})"
        )
    options = subset.Options()
    options.recalc_timestamp = False
    options.recalc_bounds = False
    options.name_IDs = ["*"]
    options.name_languages = ["*"]
    options.name_legacy = True
    options.layout_features = ["*"]
    options.notdef_glyph = True
    options.notdef_outline = True
    options.recommended_glyphs = True
    subsetter = subset.Subsetter(options=options)
    requested = set(int(value) for value in codepoints)
    subsetter.populate(unicodes=sorted(requested))
    subsetter.subset(font)
    output = BytesIO()
    font.save(output, reorderTables=True)
    data = output.getvalue()
    check = TTFont(BytesIO(data), recalcTimestamp=False, lazy=False)
    cmap = check.getBestCmap() or {}
    missing = sorted(requested - set(cmap))
    if missing:
        preview = ", ".join(f"U+{value:04X}" for value in missing[:12])
        raise FontEmbeddingError(f"font subset lacks required document characters: {preview}")
    return data, {
        "fs_type": fs_type,
        "family": check["name"].getDebugName(1),
        "subfamily": check["name"].getDebugName(2),
        "postscript_name": check["name"].getDebugName(6),
        "glyph_count": len(check.getGlyphOrder()),
        "codepoint_count": len(cmap),
    }


def deterministic_font_key(*, style: str) -> str:
    """Return the fixed legal OOXML key for a release font style."""
    try:
        return FONT_KEYS[style]
    except KeyError as exc:
        raise FontEmbeddingError(f"unsupported embedded font style: {style!r}") from exc


def _font_key_bytes(font_key: str) -> bytes:
    try:
        raw = uuid.UUID(font_key.strip("{}"))
    except (ValueError, AttributeError) as exc:
        raise FontEmbeddingError(f"invalid embedded font key: {font_key!r}") from exc
    # ECMA-376 describes the GUID as hexadecimal bytes and reverses their
    # order before XORing the first 32 bytes of the font stream.
    return raw.bytes[::-1]


def obfuscate_font(data: bytes, font_key: str) -> bytes:
    if len(data) < 32:
        raise FontEmbeddingError("OpenType font is too short to obfuscate")
    result = bytearray(data)
    key = _font_key_bytes(font_key)
    for index in range(32):
        result[index] ^= key[index % 16]
    return bytes(result)


def deobfuscate_font(data: bytes, font_key: str) -> bytes:
    # XOR is its own inverse.
    return obfuscate_font(data, font_key)


def _parse_xml(data: bytes, label: str) -> Any:
    try:
        return etree.fromstring(
            data, etree.XMLParser(remove_blank_text=False, resolve_entities=False),
        )
    except Exception as exc:
        raise FontEmbeddingError(f"cannot parse required DOCX part: {label}") from exc


def _serialize_xml(root: Any) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _relationship_ids(root: Any) -> set[str]:
    return {
        str(node.get("Id"))
        for node in root.findall(f"{{{PKG_REL_NS}}}Relationship")
        if node.get("Id")
    }


def _available_relationship_id(root: Any, preferred: str) -> str:
    used = _relationship_ids(root)
    if preferred not in used:
        return preferred
    suffix = 2
    while f"{preferred}{suffix}" in used:
        suffix += 1
    return f"{preferred}{suffix}"


def inject_embedded_fonts(
    parts: dict[str, bytes], *, font_asset_root: Path,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    """Return package parts with valid Regular/Bold ODTTF embeddings."""
    if FONT_TABLE_PATH not in parts or "[Content_Types].xml" not in parts:
        raise FontEmbeddingError("DOCX is missing its font table or content-types part")
    codepoints = document_codepoints(parts)
    faces = load_release_fonts(font_asset_root)

    if FONT_TABLE_RELS_PATH in parts:
        rels = _parse_xml(parts[FONT_TABLE_RELS_PATH], FONT_TABLE_RELS_PATH)
    else:
        rels = etree.Element(f"{{{PKG_REL_NS}}}Relationships", nsmap={None: PKG_REL_NS})
    # Replace a prior FrontMind embedding without disturbing unrelated font
    # relationships in a legacy document.
    for node in list(rels.findall(f"{{{PKG_REL_NS}}}Relationship")):
        target = str(node.get("Target") or "")
        if target in {
            "fonts/NotoSansCJKsc-Regular.odttf",
            "fonts/NotoSansCJKsc-Bold.odttf",
        }:
            rels.remove(node)

    relationship_ids = {
        "Regular": _available_relationship_id(rels, "rIdFrontMindNotoRegular"),
        "Bold": _available_relationship_id(rels, "rIdFrontMindNotoBold"),
    }
    table = _parse_xml(parts[FONT_TABLE_PATH], FONT_TABLE_PATH)
    for node in list(table.findall(f"{{{W_NS}}}font")):
        if node.get(f"{{{W_NS}}}name") == FONT_FAMILY:
            table.remove(node)
    font_node = etree.SubElement(table, f"{{{W_NS}}}font")
    font_node.set(f"{{{W_NS}}}name", FONT_FAMILY)
    alt_name = etree.SubElement(font_node, f"{{{W_NS}}}altName")
    alt_name.set(f"{{{W_NS}}}val", FONT_FAMILY)
    family = etree.SubElement(font_node, f"{{{W_NS}}}family")
    family.set(f"{{{W_NS}}}val", "swiss")
    pitch = etree.SubElement(font_node, f"{{{W_NS}}}pitch")
    pitch.set(f"{{{W_NS}}}val", "variable")

    records: list[EmbeddedFace] = []
    for face in faces:
        style = str(face["style"])
        subset_bytes, metadata = subset_font_bytes(Path(face["path"]), codepoints)
        font_key = deterministic_font_key(style=style)
        relationship_id = relationship_ids[style]
        part_path = REGULAR_PART_PATH if style == "Regular" else BOLD_PART_PATH
        target = part_path.removeprefix("word/")
        relationship = etree.SubElement(rels, f"{{{PKG_REL_NS}}}Relationship")
        relationship.set("Id", relationship_id)
        relationship.set("Type", FONT_REL_TYPE)
        relationship.set("Target", target)
        embed = etree.SubElement(
            font_node,
            f"{{{W_NS}}}{'embedRegular' if style == 'Regular' else 'embedBold'}",
        )
        embed.set(f"{{{R_NS}}}id", relationship_id)
        embed.set(f"{{{W_NS}}}fontKey", font_key)
        embed.set(f"{{{W_NS}}}subsetted", "true")
        parts[part_path] = obfuscate_font(subset_bytes, font_key)
        records.append(EmbeddedFace(
            style=style,
            source_file=Path(face["path"]).name,
            part_path=part_path,
            relationship_id=relationship_id,
            font_key=font_key,
            subset_size=len(subset_bytes),
            glyph_count=int(metadata["glyph_count"]),
            codepoint_count=int(metadata["codepoint_count"]),
        ))

    content_types = _parse_xml(parts["[Content_Types].xml"], "[Content_Types].xml")
    default_nodes = content_types.findall(f"{{{CONTENT_TYPES_NS}}}Default")
    odttf = [node for node in default_nodes if str(node.get("Extension") or "").casefold() == "odttf"]
    if odttf:
        odttf[0].set("ContentType", ODTTF_CONTENT_TYPE)
        for duplicate in odttf[1:]:
            content_types.remove(duplicate)
    else:
        node = etree.SubElement(content_types, f"{{{CONTENT_TYPES_NS}}}Default")
        node.set("Extension", "odttf")
        node.set("ContentType", ODTTF_CONTENT_TYPE)

    parts[FONT_TABLE_PATH] = _serialize_xml(table)
    parts[FONT_TABLE_RELS_PATH] = _serialize_xml(rels)
    parts["[Content_Types].xml"] = _serialize_xml(content_types)
    return parts, {
        "family": FONT_FAMILY,
        "subsetted": True,
        "document_codepoint_count": len(codepoints),
        "fonttools_runtime": fonttools_runtime_report(),
        "faces": [record.as_dict() for record in records],
    }


def _font_table_embeddings(parts: Mapping[str, bytes]) -> list[dict[str, str]]:
    if FONT_TABLE_PATH not in parts or FONT_TABLE_RELS_PATH not in parts:
        raise FontEmbeddingError("DOCX has no embedded-font table relationships")
    table = _parse_xml(parts[FONT_TABLE_PATH], FONT_TABLE_PATH)
    rels = _parse_xml(parts[FONT_TABLE_RELS_PATH], FONT_TABLE_RELS_PATH)
    relation_map = {
        str(node.get("Id")): node
        for node in rels.findall(f"{{{PKG_REL_NS}}}Relationship")
        if node.get("Id")
    }
    font_nodes = [
        node for node in table.findall(f"{{{W_NS}}}font")
        if node.get(f"{{{W_NS}}}name") == FONT_FAMILY
    ]
    if len(font_nodes) != 1:
        raise FontEmbeddingError("DOCX must contain exactly one Noto font-table entry")
    output: list[dict[str, str]] = []
    for style, tag in (("Regular", "embedRegular"), ("Bold", "embedBold")):
        embed = font_nodes[0].find(f"{{{W_NS}}}{tag}")
        if embed is None:
            raise FontEmbeddingError(f"DOCX is missing the embedded Noto {style} face")
        relation_id = str(embed.get(f"{{{R_NS}}}id") or "")
        relation = relation_map.get(relation_id)
        if relation is None or relation.get("Type") != FONT_REL_TYPE:
            raise FontEmbeddingError(f"DOCX has an invalid Noto {style} font relationship")
        target = str(relation.get("Target") or "")
        if relation.get("TargetMode") == "External" or target.startswith(("/", "http:", "https:")):
            raise FontEmbeddingError(f"DOCX Noto {style} font is not an internal package part")
        normalized = "word/" + target.lstrip("./")
        expected_part = REGULAR_PART_PATH if style == "Regular" else BOLD_PART_PATH
        if normalized != expected_part:
            raise FontEmbeddingError(
                f"DOCX Noto {style} relationship targets {normalized!r}, not {expected_part!r}"
            )
        font_key = str(embed.get(f"{{{W_NS}}}fontKey") or "")
        if not valid_guid(font_key):
            raise FontEmbeddingError(f"DOCX Noto {style} fontKey is not a canonical GUID")
        output.append({
            "style": style,
            "relationship_id": relation_id,
            "font_key": font_key,
            "subsetted": str(embed.get(f"{{{W_NS}}}subsetted") or "").casefold(),
            "part_path": normalized,
        })
    return output


def audit_embedded_fonts(parts: Mapping[str, bytes]) -> dict[str, Any]:
    """Independently deobfuscate and validate the portable font package."""
    _, TTFont = _fonttools()
    issues: list[str] = []
    face_reports: list[dict[str, Any]] = []
    required = document_codepoints(parts)
    try:
        embeddings = _font_table_embeddings(parts)
    except Exception as exc:
        return {
            "family": FONT_FAMILY,
            "document_codepoint_count": len(required),
            "faces": [],
            "issues": [str(exc)],
            "passed": False,
            "external_font_dependency": True,
        }
    for embedding in embeddings:
        part_path = embedding["part_path"]
        if part_path not in parts:
            issues.append(f"embedded font part is missing: {part_path}")
            continue
        if embedding["subsetted"] not in {"1", "true", "on"}:
            issues.append(f"embedded Noto {embedding['style']} is not marked subsetted")
        try:
            raw = deobfuscate_font(parts[part_path], embedding["font_key"])
            font = TTFont(BytesIO(raw), recalcTimestamp=False, lazy=False)
            cmap = font.getBestCmap() or {}
            missing = sorted(required - set(cmap))
            fs_type = int(font["OS/2"].fsType)
            family = font["name"].getDebugName(1)
            subfamily = font["name"].getDebugName(2)
            if family != FONT_FAMILY:
                issues.append(f"embedded {embedding['style']} family is {family!r}, not {FONT_FAMILY!r}")
            if subfamily != embedding["style"]:
                issues.append(
                    f"embedded {embedding['style']} subfamily is {subfamily!r}, not {embedding['style']!r}"
                )
            if fs_type != 0:
                issues.append(f"embedded {embedding['style']} OS/2 fsType is not installable: {fs_type}")
            if missing:
                preview = ", ".join(f"U+{value:04X}" for value in missing[:12])
                issues.append(f"embedded {embedding['style']} lacks document glyphs: {preview}")
            face_reports.append({
                **embedding,
                "size": len(raw),
                "family": family,
                "subfamily": subfamily,
                "postscript_name": font["name"].getDebugName(6),
                "fs_type": fs_type,
                "glyph_count": len(font.getGlyphOrder()),
                "codepoint_count": len(cmap),
                "missing_document_codepoints": len(missing),
            })
        except Exception as exc:
            issues.append(f"embedded Noto {embedding['style']} cannot be decoded as OpenType: {exc}")

    content_types = parts.get("[Content_Types].xml")
    if content_types:
        root = _parse_xml(content_types, "[Content_Types].xml")
        declarations = [
            node for node in root.findall(f"{{{CONTENT_TYPES_NS}}}Default")
            if str(node.get("Extension") or "").casefold() == "odttf"
        ]
        if len(declarations) != 1 or declarations[0].get("ContentType") != ODTTF_CONTENT_TYPE:
            issues.append("DOCX has no valid unique ODTTF content-type declaration")
    else:
        issues.append("DOCX content-types part is missing")
    if {face.get("style") for face in face_reports} != {"Regular", "Bold"}:
        issues.append("DOCX does not contain independently valid Regular and Bold embedded faces")
    return {
        "family": FONT_FAMILY,
        "document_codepoint_count": len(required),
        "faces": face_reports,
        "issues": list(dict.fromkeys(issues)),
        "passed": not issues,
        # When both font streams are internal, parseable and cover every
        # finished-document character, display does not depend on a host font.
        "external_font_dependency": bool(issues),
    }


def _ensure_xml_properties(run_properties: Any, family: str = FONT_FAMILY) -> None:
    fonts = run_properties.find(f"{{{W_NS}}}rFonts")
    if fonts is None:
        fonts = etree.Element(f"{{{W_NS}}}rFonts")
        run_properties.insert(0, fonts)
    for name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(f"{{{W_NS}}}{name}", family)
    fonts.set(f"{{{W_NS}}}hint", "eastAsia")
    for name in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(f"{{{W_NS}}}{name}", None)
    language = run_properties.find(f"{{{W_NS}}}lang")
    if language is None:
        language = etree.Element(f"{{{W_NS}}}lang")
        run_properties.append(language)
    language.set(f"{{{W_NS}}}val", "zh-CN")
    language.set(f"{{{W_NS}}}eastAsia", "zh-CN")


def _patch_word_xml(name: str, data: bytes, family: str = FONT_FAMILY) -> bytes:
    """Apply one explicit Chinese font contract to every visible Word run."""
    root = _parse_xml(data, name)
    if name.startswith("word/") and name.endswith(".xml"):
        for run in root.xpath(".//w:r", namespaces={"w": W_NS}):
            run_properties = run.find(f"{{{W_NS}}}rPr")
            if run_properties is None:
                run_properties = etree.Element(f"{{{W_NS}}}rPr")
                run.insert(0, run_properties)
            _ensure_xml_properties(run_properties, family)
        for run_properties in root.xpath(".//w:rPr", namespaces={"w": W_NS}):
            _ensure_xml_properties(run_properties, family)
        if name == "word/styles.xml":
            defaults = root.find(f"{{{W_NS}}}docDefaults")
            if defaults is None:
                defaults = etree.Element(f"{{{W_NS}}}docDefaults")
                root.insert(0, defaults)
            default_properties = defaults.find(f"{{{W_NS}}}rPrDefault")
            if default_properties is None:
                default_properties = etree.SubElement(defaults, f"{{{W_NS}}}rPrDefault")
            run_properties = default_properties.find(f"{{{W_NS}}}rPr")
            if run_properties is None:
                run_properties = etree.SubElement(default_properties, f"{{{W_NS}}}rPr")
            _ensure_xml_properties(run_properties, family)
        if name == "word/settings.xml":
            language = root.find(f"{{{W_NS}}}themeFontLang")
            if language is None:
                language = etree.SubElement(root, f"{{{W_NS}}}themeFontLang")
            language.set(f"{{{W_NS}}}val", "zh-CN")
            language.set(f"{{{W_NS}}}eastAsia", "zh-CN")
            language.set(f"{{{W_NS}}}bidi", "zh-CN")
            for tag in ("embedTrueTypeFonts", "saveSubsetFonts"):
                prior = root.find(f"{{{W_NS}}}{tag}")
                if prior is not None:
                    root.remove(prior)
            insertion = 0
            for index, child in enumerate(root):
                if etree.QName(child).localname in {
                    "writeProtection", "view", "zoom", "removePersonalInformation",
                    "removeDateAndTime", "doNotDisplayPageBoundaries", "displayBackgroundShape",
                    "printPostScriptOverText", "printFractionalCharacterWidth", "printFormsData",
                }:
                    insertion = index + 1
            for tag in ("embedTrueTypeFonts", "saveSubsetFonts"):
                root.insert(insertion, etree.Element(f"{{{W_NS}}}{tag}"))
                insertion += 1
    if name == "word/theme/theme1.xml":
        namespaces = {"a": A_NS}
        for xpath in (
            ".//a:majorFont/a:latin", ".//a:majorFont/a:ea",
            ".//a:minorFont/a:latin", ".//a:minorFont/a:ea",
        ):
            for node in root.xpath(xpath, namespaces=namespaces):
                node.set("typeface", family)
    return _serialize_xml(root)


def _new_zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def enforce_docx_font_contract(
    path: Path | str, *, font_asset_root: Path | None = None,
) -> dict[str, Any]:
    """Patch, subset, embed and verify the release-controlled CJK fonts."""
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise FontEmbeddingError(f"DOCX is missing or unsafe: {source}")
    assets = font_asset_root or Path(__file__).resolve().parent / "assets" / "fonts"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{source.name}.fonts-", suffix=".docx", dir=source.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with zipfile.ZipFile(source, "r") as incoming:
            original_infos = {item.filename: item for item in incoming.infolist()}
            original_order = [item.filename for item in incoming.infolist()]
            parts = {name: incoming.read(name) for name in original_order}
        for name in list(parts):
            if name.startswith("word/") and name.endswith(".xml"):
                parts[name] = _patch_word_xml(name, parts[name])
        parts, embedding_report = inject_embedded_fonts(parts, font_asset_root=assets)
        replaced_or_new = {FONT_TABLE_RELS_PATH, REGULAR_PART_PATH, BOLD_PART_PATH}
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9,
        ) as outgoing:
            for name in original_order:
                if name in replaced_or_new:
                    continue
                outgoing.writestr(original_infos[name], parts[name])
            for name in (FONT_TABLE_RELS_PATH, REGULAR_PART_PATH, BOLD_PART_PATH):
                outgoing.writestr(_new_zip_info(name), parts[name])
        with zipfile.ZipFile(temporary, "r") as packaged:
            audit = audit_embedded_fonts({name: packaged.read(name) for name in packaged.namelist()})
        if not audit["passed"]:
            raise FontEmbeddingError("embedded DOCX font audit failed: " + "; ".join(audit["issues"]))
        os.replace(temporary, source)
        return {**embedding_report, "audit": audit}
    finally:
        temporary.unlink(missing_ok=True)


def audit_docx_embedded_fonts(path: Path | str) -> dict[str, Any]:
    source = Path(path)
    with zipfile.ZipFile(source, "r") as packaged:
        return audit_embedded_fonts({name: packaged.read(name) for name in packaged.namelist()})


def strip_embedded_font_parts(parts: Mapping[str, bytes]) -> dict[str, bytes]:
    """Test helper: return a copy with portable font parts removed."""
    return {
        name: data for name, data in parts.items()
        if not name.startswith("word/fonts/") and name != FONT_TABLE_RELS_PATH
    }


def valid_guid(value: str) -> bool:
    return bool(re.fullmatch(
        r"\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}",
        value,
    ))
