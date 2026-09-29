#!/usr/bin/env python3
"""Validate the self-contained FrontMind v4.11 release projection."""
from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
RELEASE_VERSION = "4.13.2"
WORKFLOW_VERSION = "4.11"

REQUIRED_FILES = (
    "scripts/upgrade_to_v4132.py", "UPGRADE_v4.13.2.json",
    "CHANGELOG_v4.13.2.md", "FrontMind_执行手册_v4.13.2.md", "VALIDATION_v4.13.2.md",
    "shared/question_bank_import.py", "shared/p0_titles.py", "resources/p0_titles/SKILL.md",
    "scripts/upgrade_to_v4131.py", "UPGRADE_v4.13.1.json",
    "FrontMind_执行手册_v4.13.1.md", "CHANGELOG_v4.13.1.md", "VALIDATION_v4.13.1.md",
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
    "shared/p0_style.py",
    "shared/managed_runtime.py",
    "shared/agents_runtime.py",
    "scripts/probe_agents_gateway.py",
    "scripts/agents_sessions.py",
    "config/xty.json",
    "FrontMind_执行手册_v4.13.0.md",
    "HOST_RUNTIME_COMPARISON.md",
    "CHANGELOG_v4.13.0.md",
    "VALIDATION_v4.13.0.md",
    "shared/brand_stage.py",
    "shared/prose_only.py",
    "shared/reader_editing.py",
    "shared/p0_prose_editor.py",
    "resources/p0_prose_editor/SKILL.md",
    "resources/p0_prose_editor/manifest.json",
    "resources/p0_prose_editor/ADAPTATION.md",
    "resources/p0_prose_editor/PROVENANCE.json",
    "acceptance_fixtures/p0_prose_editor_v4128/cases.json",
    "acceptance_fixtures/p0_prose_editor_v4128/README.md",
    "shared/p0_rework.py",
    "scripts/tests_v411/test_prose_only_v4126.py",
    "shared/brand_references.py",
    "scripts/rewrite_p0_live.py",
    "scripts/tests_v411/test_brand_stage_v414.py",
    "shared/brand_prose.py",
    "shared/docx_system_fonts.py",
    "scripts/probe_live_apis.py", "resources/p0_style/manifest.json",
    "resources/p0_style/gangjun.md", "resources/p0_style/gangjun_guide.md",
    "resources/p0_style/xingyuanzhi_guide.md",
    "shared/manuscript_revision.py",
    "shared/title_publication.py",
    "shared/model_runtime.py", "shared/responses_runtime.py", "shared/host_tools.py",
    "shared/example_acquisition.py", "shared/writing_context.py", "shared/editorial_contracts.py",
    "shared/writing_context_v13.py", "shared/writing_requirements.py", "shared/recommendation_references.py",
    "FIX_v4.13.2_Final_v13.md", "resources/p01_recommendation/manifest.json",
    "shared/natural_editor.py", "FIX_v4.13.2_Final_v12.md", "shared/article_reader.py", "scripts/tests_v411/test_article_reader_final8.py",
    "shared/article_positioning.py", "scripts/tests_v411/test_article_positioning_final9.py",
    "scripts/tests_v411/test_article_editor_upgrade_final10.py", "FIX_v4.13.2_Final_v10.md",
    "scripts/tests_v411/test_article_editor_final11.py", "FIX_v4.13.2_Final_v11.md",
    "config/deepseek.json", "config/zhipu.json",
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
    "FrontMind_执行手册_v4.12.3.md",
    "CHANGELOG_v4.12.3.md",
    "CHANGELOG_v4.12.5.md",
    "CHANGELOG_v4.12.6.md",
    "CHANGELOG_v4.12.7.md",
    "CHANGELOG_v4.12.8.md",
    "CHANGELOG_v4.12.4.md",
    "FrontMind_执行手册_v4.12.5.md",
    "FrontMind_执行手册_v4.12.6.md",
    "FrontMind_执行手册_v4.12.7.md",
    "FrontMind_执行手册_v4.12.8.md",
    "FrontMind_执行手册_v4.12.4.md",
    "resources/p0_brand_stage/manifest.json",
    "v4.12.3_深度品宣全链路重整与验收执行手册.md",
    "RUNBOOK.md",
    "CHANGELOG_v4.11.0.md",
    "REFERENCE_PACK_4.1_ARCHITECTURE.md",
)
JSON_FILES = (
    "resources/p0_prose_editor/manifest.json",
    "resources/p0_prose_editor/PROVENANCE.json",
    "acceptance_fixtures/p0_prose_editor_v4128/cases.json",
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
    "FrontMind_执行手册_v4.12.3.md",
    "CHANGELOG_v4.12.3.md",
    "CHANGELOG_v4.12.5.md",
    "CHANGELOG_v4.12.6.md",
    "CHANGELOG_v4.12.7.md",
    "CHANGELOG_v4.12.8.md",
    "CHANGELOG_v4.12.4.md",
    "FrontMind_执行手册_v4.12.5.md",
    "FrontMind_执行手册_v4.12.6.md",
    "FrontMind_执行手册_v4.12.7.md",
    "FrontMind_执行手册_v4.12.8.md",
    "FrontMind_执行手册_v4.12.4.md",
    "resources/p0_brand_stage/manifest.json",
    "v4.12.3_深度品宣全链路重整与验收执行手册.md",
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


def _sdk_suite_result(returncode: int, xml_path: Path, output: str) -> dict[str, object]:
    """A skipped/missing official SDK test is never a passing release gate."""
    try:
        cases=list(ET.parse(xml_path).getroot().iter("testcase"))
        skipped=sum(case.find("skipped") is not None for case in cases)
        failures=sum(case.find("failure") is not None or case.find("error") is not None for case in cases)
    except (OSError, ET.ParseError):
        cases=[];skipped=0;failures=0
    return {"status":"pass" if returncode==0 and len(cases)>=4 and skipped==0 and failures==0 else "fail",
            "test_count":len(cases), "skipped":skipped, "failures":failures,
            "returncode":returncode, "official_sdk_required":True,
            "model_transport":"patched_offline", "paid_api_called":False,
            "output_tail":"\n".join(output.splitlines()[-30:])}


def run_sdk_tests() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="frontmind-sdk-gate-") as work:
        xml_path=Path(work)/"sdk-results.xml"
        completed=subprocess.run(
            [sys.executable,"-B","-m","pytest","scripts/tests_v411/test_agents_real_sdk_v4130.py",
             "-q","-rs","-p","no:cacheprovider","--junitxml",str(xml_path)],
            cwd=ROOT,text=True,capture_output=True,
            env={**os.environ,"PYTHONDONTWRITEBYTECODE":"1"},check=False)
        return _sdk_suite_result(completed.returncode,xml_path,completed.stdout+completed.stderr)


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
    sdk_tests = run_sdk_tests()
    return {
        "status": "pass" if completed.returncode == 0 and sdk_tests["status"] == "pass" else "fail",
        "test_count": count,
        "official_sdk_tests": sdk_tests,
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
        if 'RELEASE_VERSION = "4.13.2"' not in version_source:
            errors.append("release version is not " + RELEASE_VERSION)
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

    if not errors:
        try:
            from shared import p0_prose_editor
            p0_prose_editor.skill_body()
        except (ImportError, ValueError, OSError) as exc:
            errors.append("P0 prose editor resource unavailable: " + str(exc))

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
