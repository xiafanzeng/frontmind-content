#!/usr/bin/env python3
"""Validate a canonical Reference Pack 4.1 for runtime 4.11."""
from __future__ import annotations

import argparse
import json
import re
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
from shared.question_research import (  # noqa: E402
    QUESTION_RESEARCH_INDEX_MEMBER,
    validate_question_research_index,
)
from shared.reference_pack import (  # noqa: E402
    BRAND_MARKET_MEMBERS,
    CANONICAL_PATHS,
    P0_MEMBERS,
    PROFILE,
    SCHEMA_VERSION,
    STRATEGY_MEMBERS,
    brand_name,
    material_index_member,
    registry_members,
)

MAX_FILES = 5_000
MAX_COMPRESSION_RATIO = 200


def safe_relative(value: str) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key!r}")
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise ValueError(f"non-standard JSON number is forbidden: {value}")


def decode_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_pairs,
            parse_constant=_reject_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"invalid JSON {label}: {exc}") from exc


class PackageView:
    def names(self) -> list[str]:
        raise NotImplementedError

    def read(self, name: str) -> bytes:
        raise NotImplementedError


class DirectoryView(PackageView):
    def __init__(self, root: Path):
        self.root = root
        if not root.is_dir():
            raise ValueError(f"not a package directory: {root}")
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError(f"directory package contains symlink: {relative}")
            if not (stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode)):
                raise ValueError(f"directory package contains special file: {relative}")

    def names(self) -> list[str]:
        names = sorted(path.relative_to(self.root).as_posix() for path in self.root.rglob("*") if path.is_file())
        if len(names) > MAX_FILES:
            raise ValueError(f"package contains more than {MAX_FILES} files")
        for name in names:
            if not safe_relative(name):
                raise ValueError(f"unsafe package path: {name}")
        return names

    def read(self, name: str) -> bytes:
        if not safe_relative(name):
            raise ValueError(f"unsafe package path: {name}")
        return (self.root / name).read_bytes()


class ZipView(PackageView):
    def __init__(self, path: Path):
        self.archive = zipfile.ZipFile(path)
        all_infos = self.archive.infolist()
        names = [item.filename for item in all_infos]
        if len(names) != len(set(names)):
            raise ValueError("ZIP contains duplicate paths")
        infos = [item for item in all_infos if not item.is_dir()]
        if len(infos) > MAX_FILES:
            raise ValueError(f"ZIP contains more than {MAX_FILES} files")
        for item in all_infos:
            checked = item.filename[:-1] if item.is_dir() and item.filename.endswith("/") else item.filename
            if not safe_relative(checked):
                raise ValueError(f"unsafe ZIP path: {item.filename}")
            if item.flag_bits & 0x1:
                raise ValueError(f"encrypted ZIP member is unsupported: {item.filename}")
            mode = item.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if kind == stat.S_IFLNK:
                raise ValueError(f"ZIP contains symlink: {item.filename}")
            if kind not in {0, stat.S_IFREG, stat.S_IFDIR}:
                raise ValueError(f"ZIP contains special file: {item.filename}")
            if item.is_dir():
                continue
            if item.file_size and not item.compress_size:
                raise ValueError(f"ZIP member exceeds compression-ratio limit: {item.filename}")
            if item.compress_size and item.file_size / item.compress_size > MAX_COMPRESSION_RATIO:
                raise ValueError(f"ZIP member exceeds compression-ratio limit: {item.filename}")

    def names(self) -> list[str]:
        return sorted(item.filename for item in self.archive.infolist() if not item.is_dir())

    def read(self, name: str) -> bytes:
        if not safe_relative(name):
            raise ValueError(f"unsafe ZIP path: {name}")
        return self.archive.read(name)


def _object(view: PackageView, name: str, errors: list[str]) -> dict[str, Any] | None:
    if not safe_relative(name):
        errors.append(f"unsafe declared path: {name!r}")
        return None
    try:
        value = decode_json(view.read(name), name)
    except (KeyError, OSError, ValueError) as exc:
        errors.append(str(exc))
        return None
    if not isinstance(value, dict):
        errors.append(f"JSON root must be an object: {name}")
        return None
    return value


def _registry_has_expected_type(
    view: PackageView,
    names: set[str],
    member: Any,
    expected_type: str,
    errors: list[str],
) -> bool:
    """Check a factual registry role without loading any editorial asset."""

    if not isinstance(member, str) or not safe_relative(member) or member not in names:
        return False
    registry = _object(view, member, errors)
    return bool(isinstance(registry, dict) and registry.get("registry_type") == expected_type)


def _question_ready_uids(view: PackageView, index: dict[str, Any], names: set[str]) -> list[str]:
    """Return questions with two complete platform answers.

    A citation slice remains structurally present, but its details may be
    empty when the user supplied two complete AI answers directly. This is a
    production-input readiness signal, not a factual-evidence threshold.
    """

    slices = {
        (str(item.get("question_uid")), str(item.get("period_id"))): item
        for item in index.get("slices", []) if isinstance(item, dict)
    }
    result: list[str] = []
    for question in index.get("questions", []):
        if not isinstance(question, dict) or question.get("lifecycle", {}).get("state") != "active":
            continue
        uid = str(question.get("question_uid") or "")
        period_id = str(question.get("latest_complete_period_id") or "")
        record = slices.get((uid, period_id))
        if not uid or not isinstance(record, dict):
            continue
        monitoring_path = record.get("monitoring_path")
        citation_path = record.get("citation_path")
        if monitoring_path not in names or citation_path not in names:
            continue
        local_errors: list[str] = []
        monitoring = _object(view, str(monitoring_path), local_errors)
        citation = _object(view, str(citation_path), local_errors)
        platforms = {
            str(answer.get("platform") or "").strip()
            for answer in (monitoring or {}).get("answers", [])
            if isinstance(answer, dict) and str(answer.get("answer_text") or "").strip()
        }
        if (
            not local_errors
            and len(platforms - {""}) >= 2
            and isinstance((citation or {}).get("details"), list)
        ):
            result.append(uid)
    return sorted(set(result))


def validate(view: PackageView, *, execution_compatible: bool = True) -> dict[str, Any]:
    del execution_compatible
    errors: list[str] = []
    warnings: list[str] = []
    try:
        names = set(view.names())
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return {"status": "fail", "errors": [str(exc)], "warnings": []}
    if "reference_pack.json" not in names:
        return {"status": "fail", "errors": ["reference_pack.json is missing"], "warnings": []}
    pack = _object(view, "reference_pack.json", errors)
    if pack is None:
        return {"status": "fail", "errors": errors, "warnings": warnings}
    if pack.get("schema_version") != SCHEMA_VERSION or pack.get("profile") != PROFILE:
        if pack.get("schema_version") == "4.0":
            errors.append("Reference Pack 4.0 不能直接用于 runtime 4.11；请运行 reference-pack refresh-market 升级并重新确认定位")
        elif pack.get("schema_version") in {"3.8", "3.7", "2.2.0", "2.1.0"}:
            errors.append("Reference Pack 3.x/2.x 不能用于 runtime 4.11；请使用原始材料重新构建 Reference Pack 4.1")
        else:
            errors.append(f"Reference Pack schema_version must be {SCHEMA_VERSION}")
        return {"status": "fail", "errors": errors, "warnings": warnings, "readiness": {}}
    if not brand_name(pack):
        errors.append("brand_name is required")
    if not isinstance(pack.get("pack_id"), str) or not re.fullmatch(r"rp_[a-f0-9]{16}", pack["pack_id"]):
        errors.append("pack_id is missing or invalid")
    if not isinstance(pack.get("pack_version"), int) or pack.get("pack_version", 0) < 1:
        errors.append("pack_version must be a positive integer")
    if pack.get("canonical_paths") != CANONICAL_PATHS:
        errors.append("canonical_paths do not match Reference Pack 4.1")
    declared = pack.get("readiness") if isinstance(pack.get("readiness"), dict) else {}
    if not declared:
        errors.append("readiness is required")

    registry_paths = registry_members(pack)
    required = list(registry_paths.values())
    material_member = material_index_member(pack)
    required.append(material_member)
    for member in required:
        if not isinstance(member, str) or not safe_relative(member):
            errors.append(f"required content path is missing or unsafe: {member!r}")
        elif member not in names:
            errors.append(f"required content file is absent: {member}")
        elif member.endswith(".json"):
            _object(view, member, errors)
    material = _object(view, material_member, errors) if isinstance(material_member, str) and material_member in names else None
    materials_ready = False
    question_ready_uids: list[str] = []
    if material is None:
        errors.append("materials index is unavailable")
    else:
        material_items = material.get("items")
        material_paths_valid = isinstance(material_items, list) and bool(material_items)
        if isinstance(material_items, list):
            for position, item in enumerate(material_items):
                member = item.get("path") if isinstance(item, dict) else None
                if not isinstance(member, str) or not safe_relative(member) or member not in names:
                    material_paths_valid = False
                    warnings.append(
                        f"materials index item {position} refers to an absent or unsafe material: {member!r}"
                    )
        registries_ready = all(
            _registry_has_expected_type(view, names, registry_paths.get(key), expected, errors)
            for key, expected in {
                "knowledge_registry_path": "knowledge_registry",
                "source_registry_path": "source_registry",
                "claim_registry_path": "claim_registry",
                "image_registry_path": "image_registry",
            }.items()
        )
        materials_ready = bool(material_paths_valid and registries_ready and brand_name(pack))
    if material is not None and material.get("question_research_index_path") is None:
        warnings.append("per-question research index is absent; canonical Pack question selection is unavailable")
    elif material is not None and material.get("question_research_index_path") != QUESTION_RESEARCH_INDEX_MEMBER:
        errors.append("question_research_index_path must use the canonical member")
    elif material is not None and QUESTION_RESEARCH_INDEX_MEMBER not in names:
        errors.append(f"required question research index is absent: {QUESTION_RESEARCH_INDEX_MEMBER}")
    elif material is not None:
        index = _object(view, QUESTION_RESEARCH_INDEX_MEMBER, errors)
        if index is not None:
            index_errors, index_warnings = validate_question_research_index(index, names)
            errors.extend(index_errors)
            warnings.extend(index_warnings)
            if not index_errors:
                question_ready_uids = _question_ready_uids(view, index, names)
    question_ready = {
        str(item.get("question_uid")): str(item.get("question_uid")) in question_ready_uids
        for item in (index or {}).get("questions", [])
        if isinstance(item, dict) and str(item.get("question_uid") or "")
    } if material is not None and 'index' in locals() and isinstance(index, dict) else {}

    def complete_members(group: dict[str, str]) -> bool:
        complete = True
        for member in group.values():
            if member not in names:
                complete = False
                continue
            if member.endswith(".json") and _object(view, member, errors) is None:
                complete = False
        return complete

    brand_market_ready = complete_members(BRAND_MARKET_MEMBERS)
    positioning_ready = bool(brand_market_ready and complete_members(STRATEGY_MEMBERS))
    p0_ready = bool(positioning_ready and complete_members(P0_MEMBERS))
    computed = {
        "materials_ready": bool(materials_ready and not errors),
        "brand_market_research_ready": bool(brand_market_ready and not errors),
        "positioning_ready": bool(positioning_ready and not errors),
        "p0_ready": bool(p0_ready and not errors),
        "question_ready": question_ready,
    }
    for key in ("materials_ready", "brand_market_research_ready", "positioning_ready", "p0_ready"):
        if declared.get(key) is not computed[key]:
            errors.append(f"declared readiness.{key} does not match package contents")
    if declared.get("question_ready") != question_ready:
        errors.append("declared readiness.question_ready does not match question research")
    if errors:
        computed = {
            **computed,
            "materials_ready": False if not materials_ready else computed["materials_ready"],
        }
    return {
        "status": "pass" if not errors else "fail",
        "validator": "v4.11_reference_pack_4.1",
        "errors": errors,
        "warnings": warnings,
        "readiness": computed,
        "pack_id": pack.get("pack_id"),
        "pack_version": pack.get("pack_version"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate one canonical Reference Pack 4.1")
    parser.add_argument("path", type=Path)
    parser.add_argument("--execution-compatible", action="store_true")
    args = parser.parse_args()
    source = args.path.resolve()
    view: PackageView = DirectoryView(source) if source.is_dir() else ZipView(source)
    try:
        report = validate(view, execution_compatible=True)
    finally:
        archive = getattr(view, "archive", None)
        if archive is not None:
            archive.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
