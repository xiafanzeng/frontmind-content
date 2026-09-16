#!/usr/bin/env python3
"""Load the release-vendored FontTools runtime without host packages.

Portable DOCX font embedding must remain reproducible from a freshly extracted
Workflow ZIP. This loader checks the pinned version, readable license files and
actual import, then places only that controlled directory at the front of
``sys.path``. A failure is a DOCX production error.
"""

from __future__ import annotations

from functools import lru_cache
import importlib
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


VENDORED_FONTTOOLS_VERSION = "4.63.0"
VENDOR_ROOT = Path(__file__).resolve().parent / "vendor" / "fonttools_4_63_0"
VENDOR_MANIFEST = VENDOR_ROOT / "VENDOR.json"


class PortableFontToolsError(RuntimeError):
    """Raised when the release-controlled FontTools runtime is incomplete."""


@lru_cache(maxsize=1)
def validate_vendored_fonttools() -> dict[str, Any]:
    if not VENDOR_MANIFEST.is_file():
        raise PortableFontToolsError(
            f"vendored FontTools manifest is missing: {VENDOR_MANIFEST}"
        )
    try:
        manifest = json.loads(VENDOR_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PortableFontToolsError("vendored FontTools manifest is unreadable") from exc
    if str(manifest.get("version") or "") != VENDORED_FONTTOOLS_VERSION:
        raise PortableFontToolsError("vendored FontTools version is not release-pinned")
    code_root = VENDOR_ROOT / "fontTools"
    if not code_root.is_dir() or not (code_root / "__init__.py").is_file():
        raise PortableFontToolsError("vendored FontTools Python package is incomplete")
    if str(manifest.get("license") or "").strip() != "MIT":
        raise PortableFontToolsError("vendored FontTools license metadata is missing")
    license_files: list[str] = []
    for record in manifest.get("licenses", []):
        if not isinstance(record, dict):
            raise PortableFontToolsError("vendored FontTools license manifest is malformed")
        path = VENDOR_ROOT / str(record.get("file") or "")
        if not path.is_file() or path.stat().st_size <= 0:
            raise PortableFontToolsError("vendored FontTools license is missing or unreadable")
        license_files.append(path.relative_to(VENDOR_ROOT).as_posix())
    if not license_files:
        raise PortableFontToolsError("vendored FontTools license files are missing")
    return {
        "version": VENDORED_FONTTOOLS_VERSION,
        "vendor_root": str(VENDOR_ROOT.resolve()),
        "license": "MIT",
        "license_files": license_files,
        "source_mode": "release_vendored_pure_python",
    }


@lru_cache(maxsize=1)
def load_vendored_fonttools() -> ModuleType:
    report = validate_vendored_fonttools()
    vendor_text = str(VENDOR_ROOT.resolve())
    if vendor_text in sys.path:
        sys.path.remove(vendor_text)
    sys.path.insert(0, vendor_text)
    module = importlib.import_module("fontTools")
    module_file = Path(str(getattr(module, "__file__", ""))).resolve()
    try:
        module_file.relative_to(VENDOR_ROOT.resolve())
    except ValueError as exc:
        raise PortableFontToolsError(
            f"FontTools resolved outside the release vendor tree: {module_file}"
        ) from exc
    if str(getattr(module, "__version__", "")) != VENDORED_FONTTOOLS_VERSION:
        raise PortableFontToolsError("loaded FontTools does not match the pinned release version")
    # Expose the validation result for machine-readable runtime checks without
    # changing FontTools behavior.
    setattr(module, "__frontmind_vendor_report__", report)
    return module


def runtime_report() -> dict[str, Any]:
    module = load_vendored_fonttools()
    report = dict(validate_vendored_fonttools())
    report["module_file"] = str(Path(str(module.__file__)).resolve())
    report["available"] = True
    report["error"] = None
    return report
