#!/usr/bin/env python3
"""Read-only dependency and package contract check for FrontMind v4.11."""
from __future__ import annotations

import importlib
import json
import os
import stat
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from shared.workflow_versions import RELEASE_VERSION, WORKFLOW_VERSION  # noqa: E402


REQUIRED = {
    "openpyxl": "openpyxl",
    "python-docx": "docx",
    "lxml": "lxml",
    "pypdf": "pypdf",
}
OPTIONAL = {"xlrd": "xlrd", "Pillow": "PIL"}


def probe(module: str) -> dict[str, object]:
    try:
        loaded = importlib.import_module(module)
        return {"available": True, "version": getattr(loaded, "__version__", None), "error": None}
    except Exception as exc:
        return {"available": False, "version": None, "error": f"{type(exc).__name__}: {str(exc)[:240]}"}


def probe_docx_font_runtime() -> dict[str, object]:
    try:
        from shared.docx_font_embedding import load_release_fonts
        from shared.portable_fonttools import runtime_report

        report = runtime_report()
        faces = load_release_fonts(ROOT / "shared/assets/fonts")
        return {
            "available": True,
            "fonttools_version": report["version"],
            "faces": [str(item["file"]) for item in faces],
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "fonttools_version": None,
            "faces": [],
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def main() -> int:
    required = {name: probe(module) for name, module in REQUIRED.items()}
    optional = {name: probe(module) for name, module in OPTIONAL.items()}
    docx_font_runtime = probe_docx_font_runtime()
    launcher = ROOT / "scripts/frontmind"
    controller = ROOT / "scripts/frontmind_workflow.py"
    schemas = [
        ROOT / "shared/reference_pack.schema.json",
        ROOT / "shared/competitive_choice_map.schema.json",
        ROOT / "shared/core_positioning_directions.schema.json",
        ROOT / "shared/positioning_direction_review.schema.json",
        ROOT / "shared/core_positioning_decision.schema.json",
        ROOT / "shared/core_positioning.schema.json",
        ROOT / "shared/core_positioning_review.schema.json",
        ROOT / "shared/positioning_user_materials.schema.json",
        ROOT / "shared/p0_record.schema.json",
        ROOT / "shared/reference_pack_binding.schema.json",
        ROOT / "shared/question_positioning.schema.json",
        ROOT / "shared/job_state.schema.json",
    ]
    package_checks = {
        "launcher_exists": launcher.is_file() and not launcher.is_symlink(),
        "launcher_executable": launcher.is_file() and bool(launcher.stat().st_mode & stat.S_IXUSR),
        "controller_exists": controller.is_file() and not controller.is_symlink(),
        "schemas_exist": all(path.is_file() and not path.is_symlink() for path in schemas),
        "docx_font_runtime": bool(docx_font_runtime["available"]),
        "provider_callback_configured": bool(os.environ.get("FRONTMIND_CONTROLLER_PROVIDER", "").strip()),
    }
    missing = [name for name, item in required.items() if not item["available"]]
    missing.extend(name for name, ok in package_checks.items() if name != "provider_callback_configured" and not ok)
    payload = {
        "status": "pass" if not missing else "fail",
        "release_version": RELEASE_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "python": sys.version.split()[0],
        "required": required,
        "optional": optional,
        "docx_font_runtime": docx_font_runtime,
        "package": package_checks,
        "missing": missing,
        "notes": [
            "Provider callback is optional at preflight; without it the controller emits an internal action handoff.",
            "Preflight does not install packages, contact a model, read credentials or make a user decision.",
            "Reference Pack 4.1 is the only persistent content package in runtime 4.11.",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
