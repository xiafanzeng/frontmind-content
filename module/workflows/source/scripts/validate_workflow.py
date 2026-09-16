#!/usr/bin/env python3
"""Validate the self-contained FrontMind v4.11 release projection."""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = "4.11.0"
WORKFLOW_VERSION = "4.11"

REQUIRED_FILES = (
    "00.FrontMind内容制作总控.skill/SKILL.md",
    "AGENTS.md",
    "README.md",
    "START_HERE.md",
    "Master_Control/FrontMind_Content_Workflow_Master.md",
    "scripts/frontmind",
    "scripts/frontmind_workflow.py",
    "scripts/check_runtime_dependencies.py",
    "scripts/validate_workflow.py",
    "scripts/run_acceptance_v411.py",
    "scripts/tests_v411/test_workflow_v411.py",
    "shared/workflow_versions.py",
    "shared/reference_pack.schema.json",
    "shared/competitive_choice_map.schema.json",
    "shared/core_positioning_directions.schema.json",
    "shared/positioning_direction_review.schema.json",
    "shared/core_positioning_decision.schema.json",
    "shared/core_positioning.schema.json",
    "shared/core_positioning_review.schema.json",
    "shared/positioning_user_materials.schema.json",
    "shared/p0_record.schema.json",
    "shared/reference_pack_binding.schema.json",
    "shared/job_state.schema.json",
    "shared/question_positioning.schema.json",
    "shared/content-pattern-registry.json",
    "shared/content-pattern-guide.md",
    "shared/reference_pack.py",
    "shared/docx_font_embedding.py",
    "shared/portable_fonttools.py",
    "shared/assets/fonts/NotoSansCJKsc-Regular.otf",
    "shared/assets/fonts/NotoSansCJKsc-Bold.otf",
    "shared/assets/fonts/OFL-Noto-CJK.txt",
    "shared/vendor/fonttools_4_63_0/VENDOR.json",
    "Reference_Pack_Workflow/shared/reference_pack_builder.py",
    "Reference_Pack_Workflow/shared/intake_security.py",
    "Reference_Pack_Workflow/reference_pack_builder_result.schema.json",
    "Reference_Pack_Workflow/README.md",
    "acceptance_fixtures/v4.11_synthetic/manifest.json",
    "acceptance_fixtures/v4.11_synthetic/brand_material.md",
    "acceptance_fixtures/v4.11_synthetic/answer_01.md",
    "acceptance_fixtures/v4.11_synthetic/answer_02.md",
    "acceptance_fixtures/v4.11_cross_industry/b2b_software.md",
    "acceptance_fixtures/v4.11_cross_industry/manufacturing.md",
    "acceptance_fixtures/v4.11_cross_industry/education.md",
    "acceptance_fixtures/v4.11_cross_industry/professional_service.md",
    "acceptance_fixtures/v4.11_cross_industry/medical_aesthetics.md",
    "FrontMind_执行手册_v4.11.0.md",
    "RUNBOOK.md",
    "CHANGELOG_v4.11.0.md",
    "REFERENCE_PACK_4.1_ARCHITECTURE.md",
)
JSON_FILES = (
    "Reference_Pack_Workflow/reference_pack_builder_result.schema.json",
    "shared/reference_pack.schema.json",
    "shared/competitive_choice_map.schema.json",
    "shared/core_positioning_directions.schema.json",
    "shared/positioning_direction_review.schema.json",
    "shared/core_positioning_decision.schema.json",
    "shared/core_positioning.schema.json",
    "shared/core_positioning_review.schema.json",
    "shared/positioning_user_materials.schema.json",
    "shared/p0_record.schema.json",
    "shared/reference_pack_binding.schema.json",
    "shared/job_state.schema.json",
    "shared/question_positioning.schema.json",
    "shared/content-pattern-registry.json",
    "acceptance_fixtures/v4.11_synthetic/manifest.json",
)
RETIRED_RELEASE_FILES = (
    "shared/answer_semantic_ledger.py",
    "shared/answer_semantic_ledger.schema.json",
    "shared/evidence_overlay.py",
    "shared/evidence_overlay_manifest.schema.json",
    "shared/evidence_overlay_receipt.schema.json",
    "shared/featured_subject_positioning.py",
    "shared/featured_first_positioning.schema.json",
    "shared/brand_foundation_pack.schema.json",
    "shared/foundation_binding.schema.json",
    "scripts/run_acceptance_v49.py",
    "scripts/tests_v49/test_workflow_v49.py",
    "scripts/run_acceptance_v410.py",
    "scripts/tests_v410/test_workflow_v410.py",
    "shared/brand_market_context.schema.json",
    "FrontMind_执行手册_v4.10.0.md",
    "CHANGELOG_v4.10.0.md",
    "REFERENCE_PACK_4.0_ARCHITECTURE.md",
)
FORBIDDEN_CONTROLLER_TOKENS = (
    "answer_semantic_ledger",
    "awaiting_first_tier_evidence",
    "awaiting_positioning_supplement",
    "awaiting_positioning_evidence",
    "awaiting_foundation_route",
    "running_foundation_refresh",
    "foundation_ready",
    "--foundation-pack",
    "--foundation-route",
    "positioning-action",
    "positioning-choice",
)
PUBLIC_DOCS = (
    "README.md",
    "START_HERE.md",
    "RUNBOOK.md",
    "FrontMind_执行手册_v4.11.0.md",
    "CHANGELOG_v4.11.0.md",
    "REFERENCE_PACK_4.1_ARCHITECTURE.md",
    "AGENTS.md",
    "00.FrontMind内容制作总控.skill/SKILL.md",
    "Reference_Pack_Workflow/README.md",
    "Master_Control/FrontMind_Content_Workflow_Master.md",
)
FORBIDDEN_PUBLIC_PHRASES = (
    "Brand Foundation Pack",
    "--foundation-pack",
    "awaiting_foundation_route",
    "foundation_ready",
)


def run_tests() -> dict[str, object]:
    completed = subprocess.run(
        [
            sys.executable, "-B", "-m", "unittest", "discover",
            "-s", "scripts/tests_v411", "-p", "test_*.py", "-v",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False,
    )
    combined = completed.stdout + completed.stderr
    count: int | None = None
    for line in combined.splitlines():
        if line.startswith("Ran ") and " tests" in line:
            try:
                count = int(line.split()[1])
            except (IndexError, ValueError):
                pass
    return {
        "status": "pass" if completed.returncode == 0 else "fail",
        "test_count": count,
        "returncode": completed.returncode,
        "output_tail": "\n".join(combined.splitlines()[-35:]),
    }


def validate(*, tests: bool, release_projection: bool) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"required regular file is missing: {relative}")
    for relative in JSON_FILES:
        path = ROOT / relative
        if not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors.append(f"invalid JSON: {relative}: {exc}")

    launcher = ROOT / "scripts/frontmind"
    if launcher.is_file() and stat.S_IMODE(launcher.stat().st_mode) != 0o755:
        errors.append("scripts/frontmind must have Unix mode 0755")

    versions = ROOT / "shared/workflow_versions.py"
    if versions.is_file():
        version_source = versions.read_text(encoding="utf-8")
        if 'RELEASE_VERSION = "4.11.0"' not in version_source:
            errors.append("release version is not 4.11.0")
        if 'WORKFLOW_VERSION = "4.11"' not in version_source:
            errors.append("workflow version is not 4.11")
        if 'REFERENCE_PACK_VERSION = "4.1"' not in version_source:
            errors.append("Reference Pack version is not 4.1")

    controller = ROOT / "scripts/frontmind_workflow.py"
    if controller.is_file():
        source = controller.read_text(encoding="utf-8")
        for token in FORBIDDEN_CONTROLLER_TOKENS:
            if token in source:
                errors.append(f"controller still contains retired token: {token}")

    for relative in PUBLIC_DOCS:
        path = ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for phrase in FORBIDDEN_PUBLIC_PHRASES:
            if phrase in text:
                errors.append(
                    f"public v4.11 document contains retired architecture phrase {phrase!r}: {relative}"
                )

    if release_projection:
        for relative in RETIRED_RELEASE_FILES:
            if (ROOT / relative).exists():
                errors.append(f"retired runtime file is present in release projection: {relative}")
        for path in ROOT.rglob("*"):
            if path.is_dir() and path.name in {
                "__pycache__", ".pytest_cache", "work", "jobs", "logs", "cache",
            }:
                errors.append(f"runtime/cache directory is present: {path.relative_to(ROOT)}")
            elif path.is_file() and path.suffix in {".pyc", ".log", ".tmp", ".bak"}:
                errors.append(f"runtime/cache file is present: {path.relative_to(ROOT)}")

    test_result = run_tests() if tests and not errors else None
    if test_result and test_result["status"] != "pass":
        errors.append("v4.11 test suite failed")
    return {
        "status": "pass" if not errors else "fail",
        "release_version": RELEASE_VERSION,
        "workflow_version": WORKFLOW_VERSION,
        "reference_pack_version": "4.1",
        "release_projection": release_projection,
        "errors": errors,
        "warnings": warnings,
        "tests": test_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate FrontMind Content Workflow v4.11")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--release-projection", action="store_true")
    arguments = parser.parse_args()
    report = validate(tests=arguments.run_tests, release_projection=arguments.release_projection)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
