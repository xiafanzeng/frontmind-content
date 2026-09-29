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
from shared.model_runtime import configuration_status


REQUIRED = {
    "openpyxl": "openpyxl",
    "openai-agents": "agents",
    "openai": "openai",
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
    # Font files are not distributed. Word resolves the declared family locally.
    return {"available": True, "mode": "system_fonts", "family": "Noto Sans CJK SC",
            "font_files_bundled": False, "embedded_fonts": False,
            "glyph_rendering_verified": False,
            "note": "依赖阅读设备的中文字体；实际排版需渲染检查，不宣称跨设备完全一致。"}


def main() -> int:
    models = configuration_status(ROOT)
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
        "embedded_host_configured": bool(models["xty"]["configured"]),
        "embedded_deepseek_configured": bool(models["deepseek"]["configured"]),
        "embedded_search_configured": bool(models["zhipu"]["configured"]),
    }
    package_checks["python_compatible"] = sys.version_info >= (3, 10)
    if required["openai-agents"]["available"]:
        from shared.agents_runtime import SDK_VERSION, OPENAI_VERSION
        import importlib.metadata
        package_checks["agents_sdk_version"] = importlib.metadata.version("openai-agents") == SDK_VERSION
        package_checks["openai_client_version"] = importlib.metadata.version("openai") == OPENAI_VERSION
    missing = [name for name, item in required.items() if not item["available"]]
    missing.extend(name for name, ok in package_checks.items() if not ok)
    payload = {
        "status": "pass" if not missing else "fail",
        "release_version": RELEASE_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "python": sys.version.split()[0],
        "required": required,
        "optional": optional,
        "docx_font_runtime": docx_font_runtime,
        "package": package_checks,
        "models": models,
        "missing": missing,
        "notes": [
            "Production host uses local OpenAI Agents SDK + explicit XTY Chat Completions; DeepSeek author is unchanged. Zhipu remains auxiliary/legacy only. Preflight does not verify live access or article quality.",
            "Preflight checks local configuration without displaying credentials or making API calls or user decisions.",
            "Reference Pack 4.1 is the only persistent content package in runtime 4.11.",
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
