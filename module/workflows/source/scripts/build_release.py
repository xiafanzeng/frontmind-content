#!/usr/bin/env python3
"""Build the self-contained FrontMind Content Workflow v4.13.2 release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


RELEASE_VERSION = "4.13.2"
WORKFLOW_VERSION = "4.11"
RELEASE_ROOT_NAME = "FrontMind_Content_Workflow_v4.13.2"
FINAL_ZIP_NAME = "FrontMind_Content_Workflow_v4.13.2_Final_v16_2_Category_Titles.zip"
CANDIDATE_ZIP_NAME = "FrontMind_Content_Workflow_v4.13.2_Candidate.zip"
CHECKSUM_NAME = FINAL_ZIP_NAME + ".sha256"
REPORT_NAME = "acceptance-report-v4.13.2.md"
PROGRAM_REPORT_NAME = "program-validation-v4.13.2.json"
EXTERNAL_REPORT_STEM = "external-validation-report"
CREDENTIAL_FILES = frozenset({"config/deepseek.json", "config/zhipu.json", "config/xty.json"})
ZIP_TIME = (2026, 1, 1, 0, 0, 0)

# This is deliberately an allowlist. Historical source remains available to
# maintainers, while old package models, ledgers, scoring modules, tests and
# work output cannot enter the v4.11 release projection.
RELEASE_FILES = frozenset({
    "validation/title_logic_v16_2.json",
    "title_examples/v16_2/README.md", "title_examples/v16_2/manifest.json",
    "title_examples/v16_2/P01.json", "title_examples/v16_2/P02.json",
    "scripts/tests_v411/test_category_title_host_reads_v162.py",
    "shared/title_strategy.py", "FIX_v4.13.2_Final_v16_2.md",
    "scripts/tests_v411/test_title_count_v162.py", "scripts/tests_v411/test_category_titles_v162.py",
    "shared/writing_context_v16.py", "shared/editorial_preparation.py",
    "scripts/run_taixin_v16_case.py", "scripts/package_v16.py", "FIX_v4.13.2_Final_v16.md", "FIX_v4.13.2_Final_v16_1.md",
    "shared/writing_context_v15.py", "shared/language_editor_v15.py",
    "scripts/run_taixin_v15_case.py", "scripts/package_v15.py", "FIX_v4.13.2_Final_v15.md",
    "scripts/tests_v411/test_natural_prose_prompts_v15.py", "scripts/tests_v411/test_language_editor_v15.py",
    "scripts/upgrade_to_v4132.py", "UPGRADE_v4.13.2.json",
    "CHANGELOG_v4.13.2.md", "FrontMind_执行手册_v4.13.2.md", "VALIDATION_v4.13.2.md",
    "shared/question_bank_import.py", "shared/p0_titles.py",
    "scripts/upgrade_to_v4131.py", "UPGRADE_v4.13.1.json",
    "FrontMind_执行手册_v4.13.1.md", "CHANGELOG_v4.13.1.md", "VALIDATION_v4.13.1.md",
    ".codex/config.toml",
    "00.FrontMind内容制作总控.skill/SKILL.md",
    "AGENTS.md",
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
    "CHANGELOG_v4.11.8.md",
    "CHANGELOG_v4.11.0.md",
    "MODEL_RUNTIME.md",
    "REFERENCE_PACK_4.1_ARCHITECTURE.md",
    "Master_Control/FrontMind_Content_Workflow_Master.md",
    "requirements.txt",
    "requirements-optional.txt",
    "scripts/frontmind",
    "scripts/frontmind_workflow.py",
    "scripts/check_runtime_dependencies.py",
    "scripts/validate_workflow.py",
    "scripts/run_acceptance_v411.py",
    "scripts/build_release.py",
    "scripts/tests_v411/__init__.py",
    "scripts/tests_v411/test_workflow_v411.py",
    "scripts/tests_v411/test_positioning_contracts.py",
    "scripts/tests_v411/test_competitor_selection.py",
    "scripts/tests_v411/positioning_provider_samples.py",
    "shared/README.md",
    "shared/workflow_versions.py",
    "shared/manuscript_revision.py", "shared/title_publication.py",
    "shared/model_runtime.py", "shared/responses_runtime.py", "shared/host_tools.py", "shared/material_inventory.py",
    "shared/example_acquisition.py", "shared/writing_context.py", "shared/editorial_contracts.py",
    "shared/writing_context_v14.py", "shared/writer_measure.py", "shared/p01_writing_v2.py", "FIX_v4.13.2_Final_v14.md",
    "shared/writing_context_v13.py", "shared/writing_requirements.py", "shared/recommendation_references.py",
    "shared/writing_materials.py",
    "FIX_v4.13.2_Final_v13.md", "scripts/tests_v411/test_writing_requirements_final13.py",
    "resources/p01_recommendation/manifest.json",
    "resources/p01_recommendation/kingdee/source.json", "resources/p01_recommendation/kingdee/README.md", "resources/p01_recommendation/thinkpad/source.json", "resources/p01_recommendation/thinkpad/README.md",
    "resources/p01_recommendation/kingdee/body.md", "resources/p01_recommendation/kingdee/original.html",
    "resources/p01_recommendation/thinkpad/body.md", "resources/p01_recommendation/thinkpad/original.html",
    "shared/natural_editor.py", "FIX_v4.13.2_Final_v12.md", "shared/article_reader.py", "scripts/tests_v411/test_article_reader_final8.py",
    "shared/article_positioning.py", "scripts/tests_v411/test_article_positioning_final9.py",
    "scripts/tests_v411/test_article_editor_upgrade_final10.py", "FIX_v4.13.2_Final_v10.md",
    "scripts/tests_v411/test_article_editor_final11.py", "FIX_v4.13.2_Final_v11.md",
    "shared/p0_style.py",
    "shared/managed_runtime.py",
    "shared/agents_runtime.py",
    "scripts/probe_agents_gateway.py",
    "scripts/agents_sessions.py",
    "config/xty.json",
    "CHANGELOG_v4.13.0.md",
    "FrontMind_执行手册_v4.13.0.md",
    "HOST_RUNTIME_COMPARISON.md",
    "VALIDATION_v4.13.0.md",
    "shared/brand_stage.py",
    "shared/prose_only.py",
    "shared/reader_editing.py",
    "shared/p0_prose_editor.py",
    "shared/p0_rework.py",
    "scripts/tests_v411/test_prose_only_v4126.py",
    "shared/brand_references.py",
    "scripts/rewrite_p0_live.py",
    "scripts/tests_v411/test_brand_stage_v414.py",
    "shared/brand_prose.py",
    "shared/docx_system_fonts.py",
    "scripts/probe_live_apis.py",
    "config/deepseek.json", "config/zhipu.json",
    "shared/content-pattern-guide.md",
    "shared/content-pattern-registry.json",
    "shared/reference_pack.schema.json",
    "shared/competitive_choice_map.schema.json",
    "shared/job_state.schema.json",
    "shared/core_positioning_directions.schema.json",
    "shared/positioning_direction_review.schema.json",
    "shared/core_positioning_decision.schema.json",
    "shared/core_positioning.schema.json",
    "shared/core_positioning_review.schema.json",
    "shared/positioning_user_materials.schema.json",
    "shared/p0_record.schema.json",
    "shared/reference_pack_binding.schema.json",
    "shared/question_positioning.schema.json",
    "shared/question_research.py",
    "shared/question_semantics.py",
    "shared/reference_pack.py",
    "shared/research_ingestion.py",
    "shared/docx_font_embedding.py",
    "shared/portable_fonttools.py",
    "shared/scripts/validate_execution_reference_pack.py",
    "shared/scripts/validate_json_instance.py",
    "Reference_Pack_Workflow/README.md",
    "Reference_Pack_Workflow/reference_pack_builder_result.schema.json",
    "Reference_Pack_Workflow/shared/intake_security.py",
    "Reference_Pack_Workflow/shared/reference_pack_builder.py",
    "acceptance_fixtures/v4.11_synthetic/manifest.json",
    "acceptance_fixtures/v4.11_synthetic/brand_material.md",
    "acceptance_fixtures/v4.11_synthetic/answer_01.md",
    "acceptance_fixtures/v4.11_synthetic/answer_02.md",
    "acceptance_fixtures/v4.11_cross_industry/b2b_software.md",
    "acceptance_fixtures/v4.11_cross_industry/manufacturing.md",
    "acceptance_fixtures/v4.11_cross_industry/education.md",
    "acceptance_fixtures/v4.11_cross_industry/professional_service.md",
    "acceptance_fixtures/v4.11_cross_industry/medical_aesthetics.md",
})
RELEASE_TREE_ROOTS = (
    "docs/history",
    "resources/p0_titles", "customer_inputs/taixin/v16",
    "acceptance_fixtures/v4.11.7_generalization",
    "scripts/tests_v411",
    "shared/assets/fonts",
    "resources/p0_style",
    "resources/p0_brand_stage",
    "resources/p0_prose_editor",
    "customer_inputs/yihang",
    "resources/p0_style_legacy_v4121",
    "resources/p0_style_legacy_v4122",
    "acceptance_fixtures/p0_prose_offline",
    "acceptance_fixtures/p0_reader_editing_v4127",
    "acceptance_fixtures/p0_prose_editor_v4128",
    "shared/vendor/fonttools_4_63_0",
)
ROOT_DOCUMENTS = (
    "FrontMind_执行手册_v4.13.2.md", "CHANGELOG_v4.13.2.md",
    "FrontMind_执行手册_v4.13.1.md", "CHANGELOG_v4.13.1.md",
    "START_HERE.md",
    "FrontMind_执行手册_v4.12.3.md",
    "RUNBOOK.md",
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
    "v4.12.3_深度品宣全链路重整与验收执行手册.md",
    "REFERENCE_PACK_4.1_ARCHITECTURE.md",
    "MODEL_RUNTIME.md",
)
FORBIDDEN_RELEASE_PATH_PARTS = {
    "work", "jobs", "logs", "cache", "__pycache__", ".pytest_cache",
    "provider", "provider-output", "provider-outputs",
}
FORBIDDEN_RELEASE_BASENAMES = {
    "answer_semantic_ledger.py",
    "answer_semantic_ledger.schema.json",
    "evidence_overlay.py",
    "evidence_overlay_manifest.schema.json",
    "evidence_overlay_receipt.schema.json",
    "featured_subject_positioning.py",
    "featured_first_positioning.schema.json",
    "brand_foundation_pack.schema.json",
    "foundation_binding.schema.json",
    "positioning_confirmation.schema.json",
    "brand_market_context.schema.json",
    "FrontMind_执行手册_v4.10.0.md",
    "CHANGELOG_v4.10.0.md",
    "REFERENCE_PACK_4.0_ARCHITECTURE.md",
    "run_acceptance_v410.py",
    "test_workflow_v410.py",
}
PRIVATE_MARKERS = (
    ("/" + "Users" + "/").encode("utf-8"),
    ("/" + "home" + "/").encode("utf-8"),
)


class ReleaseError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def regular_directory(path: Path, label: str) -> Path:
    requested = path.expanduser()
    if requested.is_symlink() or not requested.is_dir():
        raise ReleaseError(f"{label} must be a regular directory: {requested}")
    return requested.resolve()


def ensure_new_output(path: Path, source: Path) -> Path:
    requested = path.expanduser()
    if requested.exists() or requested.is_symlink():
        raise ReleaseError("output directory must not already exist")
    resolved = requested.parent.resolve() / requested.name
    try:
        resolved.relative_to(source)
    except ValueError:
        return resolved
    raise ReleaseError("output directory must be outside the source tree")


def runtime_available(executable: str) -> bool:
    try:
        completed = subprocess.run(
            [executable, "-B", "-c", "import openpyxl, docx, lxml, pypdf"],
            text=True, capture_output=True, check=False, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def choose_python() -> str:
    candidates: list[str] = []
    if os.environ.get("FRONTMIND_PYTHON"):
        candidates.append(os.environ["FRONTMIND_PYTHON"])
    candidates.extend((
        str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"),
        sys.executable,
        "python3",
        "python",
    ))
    for candidate in dict.fromkeys(candidates):
        if runtime_available(candidate):
            return candidate
    raise ReleaseError("no Python runtime provides openpyxl, python-docx and pypdf")


def run_json(command: list[str], cwd: Path, label: str, *, timeout: int = 900) -> dict[str, Any]:
    completed = subprocess.run(
        command, cwd=cwd, text=True, capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        check=False, timeout=timeout,
    )
    if completed.returncode != 0:
        raise ReleaseError(
            f"{label} failed ({completed.returncode})\n"
            f"stdout:\n{completed.stdout[-5000:]}\n"
            f"stderr:\n{completed.stderr[-5000:]}"
        )
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"{label} did not return JSON") from exc
    if not isinstance(value, dict) or value.get("status") != "pass":
        raise ReleaseError(f"{label} did not pass")
    return value


def validate_source(source: Path, python: str) -> dict[str, Any]:
    preflight = run_json([str(source / "scripts/frontmind"), "preflight"], source, "source preflight")
    validation = run_json(
        [python, "-B", "scripts/validate_workflow.py", "--run-tests"],
        source, "source validation and tests",
    )
    return {"preflight": preflight, "validation": validation}


def release_file_set(source: Path) -> frozenset[str]:
    """Resolve the exact runtime projection, including pinned asset trees."""
    files = set(RELEASE_FILES)
    for relative_root in RELEASE_TREE_ROOTS:
        root = source / relative_root
        if root.is_symlink() or not root.is_dir():
            raise ReleaseError(f"allowlisted runtime tree is missing or unsafe: {relative_root}")
        for path in root.rglob("*"):
            relative_parts = path.relative_to(root).parts
            if set(relative_parts) & {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} or path.suffix.casefold() in {".pyc", ".pyo"}:
                continue
            if path.is_symlink():
                raise ReleaseError(f"symlink in allowlisted runtime tree: {path.relative_to(source)}")
            if path.is_file():
                files.add(path.relative_to(source).as_posix())
            elif not path.is_dir():
                raise ReleaseError(f"special file in allowlisted runtime tree: {path.relative_to(source)}")
    return frozenset(files)


def copy_projection(source: Path, destination: Path) -> list[str]:
    destination.mkdir(parents=True)
    copied: list[str] = []
    normalized: set[str] = set()
    for relative_text in sorted(release_file_set(source)):
        relative = PurePosixPath(relative_text)
        key = unicodedata.normalize("NFC", relative_text).casefold()
        if key in normalized:
            raise ReleaseError(f"duplicate normalized release path: {relative_text}")
        normalized.add(key)
        source_path = source.joinpath(*relative.parts)
        if source_path.is_symlink() or not source_path.is_file():
            raise ReleaseError(f"allowlisted source file is missing or unsafe: {relative_text}")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        os.chmod(target, 0o755 if relative_text == "scripts/frontmind" else 0o600 if relative_text in {"config/deepseek.json", "config/zhipu.json", "config/xty.json"} else 0o644)
        copied.append(relative_text)
    return copied


def audit_projection(root: Path, expected_files: Iterable[str] | None = None) -> dict[str, Any]:
    if any(path.is_symlink() for path in root.rglob("*")):
        raise ReleaseError("symlink entered release projection")
    files = [path for path in root.rglob("*") if path.is_file()]
    actual = {path.relative_to(root).as_posix() for path in files}
    expected = set(expected_files) if expected_files is not None else set(release_file_set(root))
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ReleaseError(f"release projection mismatch; missing={missing}, extra={extra}")
    secrets = []
    for relative in CREDENTIAL_FILES:
        config_path = root / relative
        if not config_path.is_file() or stat.S_IMODE(config_path.stat().st_mode) != 0o600:
            raise ReleaseError(f"packaged credential file mode must be 0600: {relative}")
        try:
            value = json.loads(config_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            raise ReleaseError(f"packaged credential configuration is unreadable: {relative}") from None
        secret = value.get("api_key") if isinstance(value, dict) else None
        if not isinstance(secret, str) or not secret.strip():
            raise ReleaseError(f"packaged credential configuration is missing its key: {relative}")
        secrets.append(secret.strip().encode("utf-8"))
    for path in files:
        relative = path.relative_to(root)
        lowered_parts = {part.casefold() for part in relative.parts}
        if lowered_parts & FORBIDDEN_RELEASE_PATH_PARTS:
            raise ReleaseError(f"runtime output path entered release: {relative}")
        if path.name in FORBIDDEN_RELEASE_BASENAMES:
            raise ReleaseError(f"retired runtime file entered release: {relative}")
        if path.suffix.casefold() in {".pyc", ".log", ".tmp", ".bak"}:
            raise ReleaseError(f"runtime/cache file entered release: {relative}")
        data = path.read_bytes()
        # Public SPA fragment routes are part of preserved source HTML, not
        # workstation paths. Keep the original bytes and secret checks intact.
        fragment_pattern = rb'https?://[^\s<>"\x27]+#' + re.escape(PRIVATE_MARKERS[1]) + rb'[^\s<>"\x27]*'
        path_scan = re.sub(fragment_pattern, b'public-web-fragment', data)
        endpoint_pattern = rb'\$\.(?:get|post)\(\s*["\x27]' + re.escape(PRIVATE_MARKERS[1]) + rb'[^\s<>"\x27]*["\x27]'
        path_scan = re.sub(endpoint_pattern, b'public-http-endpoint', path_scan)
        for marker in PRIVATE_MARKERS:
            if marker in path_scan:
                raise ReleaseError(f"private/client marker entered release: {relative}")
        if relative.as_posix() not in CREDENTIAL_FILES and any(secret in data for secret in secrets):
            raise ReleaseError(f"credential appeared outside its configuration file: {relative}")
    launcher_mode = stat.S_IMODE((root / "scripts/frontmind").stat().st_mode)
    if launcher_mode != 0o755:
        raise ReleaseError("projected scripts/frontmind mode is not 0755")
    return {"file_count": len(files), "launcher_mode": "0755", "credential_modes": {name: "0600" for name in sorted(CREDENTIAL_FILES)}}


def write_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            name = f"{RELEASE_ROOT_NAME}/{relative}"
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if relative == "scripts/frontmind" else 0o600 if relative in {"config/deepseek.json", "config/zhipu.json", "config/xty.json"} else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.flag_bits |= 0x800
            with path.open("rb") as incoming, archive.open(info, "w", force_zip64=True) as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)


def inspect_release_zip(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(unicodedata.normalize("NFC", name).casefold() for name in names)):
            raise ReleaseError("final ZIP contains duplicate normalized paths")
        launcher_name = f"{RELEASE_ROOT_NAME}/scripts/frontmind"
        launcher = next((item for item in infos if item.filename == launcher_name), None)
        if launcher is None:
            raise ReleaseError("final ZIP does not contain scripts/frontmind")
        mode = stat.S_IMODE(launcher.external_attr >> 16)
        if mode != 0o755:
            raise ReleaseError("final ZIP scripts/frontmind mode is not 0755")
        for relative in CREDENTIAL_FILES:
            entry = next((item for item in infos if item.filename == f"{RELEASE_ROOT_NAME}/{relative}"), None)
            if entry is None or stat.S_IMODE(entry.external_attr >> 16) != 0o600:
                raise ReleaseError(f"ZIP credential mode must be 0600: {relative}")
        for entry in infos:
            member = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (member.is_absolute() or ".." in member.parts or not member.parts
                    or member.parts[0] != RELEASE_ROOT_NAME or "\\" in entry.filename
                    or not stat.S_ISREG(mode) or entry.flag_bits & 1):
                raise ReleaseError(f"unsafe release ZIP member: {entry.filename}")
        return {"member_count": len(infos), "launcher_mode": "0755", "credential_modes": {name: "0600" for name in sorted(CREDENTIAL_FILES)}}


def extract_zip(path: Path, destination: Path) -> Path:
    inspect_release_zip(path)
    destination.mkdir(parents=True)
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            member = PurePosixPath(item.filename)
            if member.is_absolute() or ".." in member.parts:
                raise ReleaseError(f"unsafe release ZIP member: {item.filename}")
            target = destination.joinpath(*member.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(item) as incoming, target.open("wb") as outgoing:
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            os.chmod(target, stat.S_IMODE(item.external_attr >> 16) or 0o644)
    return destination / RELEASE_ROOT_NAME


def validate_clean_extraction(root: Path, python: str) -> dict[str, Any]:
    preflight = run_json([str(root / "scripts/frontmind"), "preflight"], root, "clean preflight")
    validation = run_json(
        [python, "-B", "scripts/validate_workflow.py", "--release-projection", "--run-tests"],
        root, "clean projection and complete test validation",
    )
    return {"preflight": preflight, "validation": validation, "runtime": validate_model_runtime(root, python), "tests_repeated": True}


def validate_model_runtime(root: Path, python: str) -> dict[str, Any]:
    """Check the actual packaged routes/configuration without paid API calls."""
    code = """import json
from shared import model_runtime as runtime
assert len(runtime.HOST_ACTIONS) == 13
assert 'article_editorial_preparation' in runtime.HOST_ACTIONS
assert runtime.profile_for('article_polish') == runtime.profile_for('article_finalize')
assert runtime.DEEPSEEK_ACTIONS >= {'article_repair', 'p0_repair'}
assert len(runtime.DEEPSEEK_ACTIONS - {'article_repair', 'p0_repair'}) == 7
draft_profile = runtime.profile_for('article_draft')
assert not (runtime.HOST_ACTIONS & runtime.DEEPSEEK_ACTIONS)
for action in runtime.HOST_ACTIONS | runtime.DEEPSEEK_ACTIONS:
    profile = runtime.profile_for(action)
    host = action in runtime.HOST_ACTIONS
    assert isinstance(profile['model'],str) and profile['model'] if host else profile['model'] == 'deepseek-v4-pro'
    if host:
        assert profile['provider'] == 'xty' and profile['wire_api'] == 'openai_agents_sdk'
        assert profile['automatic_retries'] == 0 and profile['tracing_disabled'] is True
        assert not any(key in profile for key in ('thinking', 'reasoning_effort'))
    else:
        assert profile['reasoning_effort'] == draft_profile['reasoning_effort']
        assert profile['thinking']['type'] == 'enabled'
    assert not any(key in profile for key in ('speed', 'service_tier', 'temperature'))
configuration = runtime.configuration_status('.')
assert all(configuration[name]['configured'] for name in ('xty', 'deepseek'))
print(json.dumps({'status':'pass','host_action_count':len(runtime.HOST_ACTIONS), 'deepseek_action_count':len(runtime.DEEPSEEK_ACTIONS),'configuration':configuration,'paid_api_called':False}, ensure_ascii=False))
"""
    return run_json([python, "-B", "-c", code], root, "packaged model runtime sanity", timeout=60)


def verify_file_hashes(reference: Path, actual: Path, relative_files: Iterable[str]) -> dict[str, Any]:
    files = sorted(relative_files)
    for relative in files:
        target = actual / relative
        if target.is_symlink() or not target.is_file() or sha256(reference / relative) != sha256(target):
            raise ReleaseError(f"release file content changed: {relative}")
    return {"status": "pass", "file_count": len(files)}


def safe_acceptance_member(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ReleaseError(f"invalid acceptance path for {label}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReleaseError(f"unsafe acceptance path for {label}")
    path = root.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ReleaseError(f"missing acceptance file for {label}: {value}")
    try:
        path.resolve().relative_to(root)
    except ValueError as exc:
        raise ReleaseError(f"acceptance path escapes root for {label}") from exc
    return path


def validate_acceptance(root: Path) -> dict[str, Any]:
    manifest_path = root / "acceptance_manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ReleaseError("acceptance_manifest.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_counts = {
        "p0": 1, "question_articles": 7, "markdown": 8,
        "html": 8, "docx": 8, "title_maps": 8, "titles": 160,
    }
    if manifest.get("status") != "pass" or manifest.get("fixture_only") is not True:
        raise ReleaseError("acceptance run is not a passing anonymous fixture run")
    if manifest.get("schema_version") != WORKFLOW_VERSION:
        raise ReleaseError("acceptance run does not use the v4.11 contract")
    if manifest.get("counts") != expected_counts:
        raise ReleaseError(f"acceptance counts do not match: {manifest.get('counts')}")
    versions = manifest.get("pack_versions")
    if versions != list(range(1, 10)):
        raise ReleaseError(f"acceptance Reference Pack versions are not sequential: {versions}")
    if not isinstance(manifest.get("pack_id"), str) or not manifest["pack_id"].startswith("rp_"):
        raise ReleaseError("acceptance run does not identify one Reference Pack series")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != 8:
        raise ReleaseError("acceptance run must contain P0 plus seven questions")
    expected_case_ids = {"p0", "q01", "q02", "q03", "q04", "q05", "q06", "q07"}
    if {item.get("case_id") for item in cases if isinstance(item, dict)} != expected_case_ids:
        raise ReleaseError("acceptance case IDs are incomplete")
    forbidden_page_tokens = (
        "candidate_", "Fact ID", "answer_span", "dimension_first", "first_tier",
        "同分窗口", "evidence overlay", "supported", "blocked", "coverage",
    )
    docx_paths: set[str] = set()
    title_count = 0
    for case in cases:
        if not isinstance(case, dict):
            raise ReleaseError("acceptance case must be an object")
        deliverables = case.get("deliverables")
        if not isinstance(deliverables, dict) or set(deliverables) != {"markdown", "html", "docx", "title_map"}:
            raise ReleaseError(f"acceptance deliverables are incomplete: {case.get('case_id')}")
        markdown = safe_acceptance_member(root, deliverables["markdown"], f"{case['case_id']} Markdown")
        safe_acceptance_member(root, deliverables["html"], f"{case['case_id']} HTML")
        docx = safe_acceptance_member(root, deliverables["docx"], f"{case['case_id']} DOCX")
        title_map = safe_acceptance_member(root, deliverables["title_map"], f"{case['case_id']} Title Map")
        text = markdown.read_text(encoding="utf-8")
        for token in forbidden_page_tokens:
            if token.casefold() in text.casefold():
                raise ReleaseError(f"acceptance article contains internal token {token}: {case['case_id']}")
        with zipfile.ZipFile(docx) as archive:
            if "word/document.xml" not in archive.namelist():
                raise ReleaseError(f"invalid acceptance DOCX: {case['case_id']}")
        title_payload = json.loads(title_map.read_text(encoding="utf-8"))
        expected_count = case.get("title_count", 20)
        if expected_count not in {10, 20} or title_payload.get("total_count") != expected_count or len(title_payload.get("options") or []) != expected_count:
            raise ReleaseError(f"acceptance Title Map is incomplete: {case['case_id']}")
        title_count += expected_count
        docx_paths.add(deliverables["docx"])
    qpos = {item["case_id"]: item.get("question_positioning") for item in cases}
    expected_qpos = {"p0": False, "q01": True, "q02": False, "q03": True, "q04": False, "q05": False, "q06": True, "q07": True}
    if qpos != expected_qpos:
        raise ReleaseError("acceptance question-positioning routes do not match seven-case contract")
    qa_path = root / "docx_visual_qa.json"
    if qa_path.is_symlink() or not qa_path.is_file():
        raise ReleaseError("docx_visual_qa.json is required after rendering and visual review")
    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    qa_documents = qa.get("documents") if isinstance(qa.get("documents"), list) else []
    qa_paths = {item.get("path") for item in qa_documents if isinstance(item, dict) and item.get("status") == "pass"}
    if qa.get("status") != "pass" or qa_paths != docx_paths:
        raise ReleaseError("DOCX visual QA does not cover all eight acceptance documents")
    if any(not isinstance(item.get("page_count"), int) or item["page_count"] < 1 for item in qa_documents):
        raise ReleaseError("DOCX visual QA contains an invalid page count")
    return {
        "status": "pass", "counts": expected_counts,
        "case_count": len(cases), "title_count": title_count,
        "docx_visual_qa": {"status": "pass", "document_count": len(qa_documents)},
    }


def test_summary(report: dict[str, Any]) -> str:
    tests = report.get("validation", {}).get("tests") or {}
    if not tests:
        return "未在此目录重复运行测试"
    return f"{tests.get('test_count', 'unknown')} tests, {tests.get('status', 'unknown')}"


def report_markdown(report: dict[str, Any]) -> str:
    """Report only checks performed by this builder; never infer prose quality."""
    candidate = report.get("candidate", False)
    artifact_label = "候选程序包，内容尚未验收" if candidate else "程序发行包，业务与内容验收另列"
    acceptance = report.get("acceptance", {})
    legacy_note = "未要求运行或导入旧版八稿匿名验收；它不是本次构建前提。"
    if acceptance.get("status") == "pass":
        legacy_note = ("已校验显式提交的旧匿名夹具结果："
            f"{acceptance.get('case_count')} 个案例、{acceptance.get('title_count')} 个标题。"
            "该结果仅证明提交的夹具结构，不证明真实模型调用或客户文章质量。")
    external = report.get("external_validation_report")
    evidence_note = "本次未附外部业务验收报告。"
    if external:
        evidence_note = (f"原样附送 [{external['filename']}]({external['filename']})，"
            f"SHA-256：`{external['sha256']}`。构建器未判定其中的结论，也未将其状态转写为通过。")
    return f"""# FrontMind v{RELEASE_VERSION} 程序构建验证报告

- 类型：**{artifact_label}**
- 发行版本：`{RELEASE_VERSION}`；Runtime：`{WORKFLOW_VERSION}`；Reference Pack：`4.1`
- 生成时间：`{report['created_at']}`
- 本报告范围：程序、封装和解压验证；**不表示业务文章、模型调用、文字质量或 Word 排版已通过验收**。

## 实际程序验证

| 检查 | 结果 |
|---|---|
| 源码预检 | {report['source']['preflight']['status']} |
| 源码测试 | {test_summary(report['source'])} |
| 精确发行投射 | {report['projection']['file_count']} 个文件 |
| 投射与源码逐文件哈希 | {report['source_projection_hashes']['status']} |
| 全新解压预检 | {report['clean']['preflight']['status']} |
| 全新解压静态验证 | {report['clean']['validation']['status']} |
| 解压与投射逐文件哈希 | {report['clean']['file_hashes']['status']} |
| 固定模型路由 | OpenAI Agents SDK {report['clean']['runtime']['host_action_count']} 个宿主动作；DeepSeek {report['clean']['runtime']['deepseek_action_count']} 个动作 |
| ZIP 成员数 | {report['zip']['member_count']} |
| 启动器 ZIP / 解压权限 | 0755 / 0755 |
| 三份包内凭据 ZIP / 解压权限 | 0600 / 0600 |

解压验证没有重复运行整套源码测试。模型检查只读取包内固定 Profile 和配置可用性，不发起付费 API 调用，不显示密钥。新宿主路由为本地OpenAI Agents SDK + config/xty.json；DeepSeek-V4-Pro/max作者不变。

## 独立验收证据

{legacy_note}

{evidence_note}

| 验收维度 | 本构建器的结论 |
|---|---|
| 程序行为 | 以上实际检查通过 |
| 真实模型调用 | 不由打包过程验证；需具体业务请求与响应记录 |
| 内容通读 | 不由打包过程验证；需独立全文验读记录 |
| Word 全页渲染 | 不由打包过程验证；需实际文档及全部页面检查 |

## 发行边界与校验

发行ZIP包含白名单程序、执行文档、合成测试夹具、原包模型配置、原包例文资源及本版P0编辑Skill，沿用原包的一航输入样例。本轮上传的台心稿件、生成文章、星源智在线原文副本、Provider输出和运行日志不进入ZIP。外部验收报告仅放在发行目录。

- 文件：`{report['zip_filename']}`
- SHA-256：`{report['final_zip_sha256']}`
- 机器可读程序验证：[{PROGRAM_REPORT_NAME}]({PROGRAM_REPORT_NAME})
"""


def copy_validation_report(source: Path, destination_root: Path) -> dict[str, Any]:
    requested = source.expanduser()
    if requested.is_symlink() or not requested.is_file():
        raise ReleaseError("validation report must be one regular file")
    suffix = requested.suffix.lower() or ".txt"
    if suffix not in {".md", ".json", ".txt", ".html", ".pdf"}:
        raise ReleaseError("validation report must be Markdown, JSON, text, HTML or PDF")
    destination = destination_root / (EXTERNAL_REPORT_STEM + suffix)
    shutil.copyfile(requested, destination)
    os.chmod(destination, 0o644)
    return {"filename": destination.name, "sha256": sha256(destination),
            "bytes": destination.stat().st_size, "copied_verbatim": True,
            "semantic_validation_by_builder": False}


def build(source: Path, acceptance_source: Path | None = None, output_dir: Path | None = None,
          *, candidate: bool = False, validation_report: Path | None = None) -> dict[str, Any]:
    """Build a program package; legacy fixture evidence is explicitly optional.

    The original three-positional-argument API remains supported. Candidate mode
    changes the artifact label/name only; it does not bypass program checks.
    """
    source = regular_directory(source, "source")
    if output_dir is None:
        raise ReleaseError("output directory is required")
    output = ensure_new_output(output_dir, source)
    python = choose_python()
    source_result = validate_source(source, python)
    acceptance_result = {"status": "not_requested", "fixture_only": True}
    if acceptance_source is not None:
        acceptance_result = validate_acceptance(regular_directory(acceptance_source, "acceptance source"))
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        workflow = staging / RELEASE_ROOT_NAME
        copied = copy_projection(source, workflow)
        projection = audit_projection(workflow, copied)
        source_hashes = verify_file_hashes(source, workflow, copied)
        run_json([python, "-B", "scripts/validate_workflow.py", "--release-projection"],
                 workflow, "release projection validation")
        zip_name = CANDIDATE_ZIP_NAME if candidate else FINAL_ZIP_NAME
        final_zip = staging / zip_name
        write_zip(workflow, final_zip)
        zip_result = inspect_release_zip(final_zip)
        extraction_parent = staging / "clean-extraction"
        clean_root = extract_zip(final_zip, extraction_parent)
        clean_projection = audit_projection(clean_root, copied)
        clean_hashes = verify_file_hashes(workflow, clean_root, copied)
        clean_result = validate_clean_extraction(clean_root, python)
        clean_result.update({"projection": clean_projection, "file_hashes": clean_hashes})
        digest = sha256(final_zip)
        report: dict[str, Any] = {
            "status": "pass", "validation_scope": "program_and_package_only",
            "candidate": candidate, "content_acceptance": "not_assessed_by_builder",
            "release_version": RELEASE_VERSION, "workflow_version": WORKFLOW_VERSION,
            "created_at": now(), "source": source_result, "acceptance": acceptance_result,
            "projection": {**projection, "allowlisted_file_count": len(copied)},
            "source_projection_hashes": source_hashes,
            "zip": zip_result, "zip_filename": zip_name, "clean": clean_result,
            "final_zip_sha256": digest,
        }
        if validation_report is not None:
            report["external_validation_report"] = copy_validation_report(validation_report, staging)
        for name in ROOT_DOCUMENTS:
            shutil.copyfile(workflow / name, staging / name)
            os.chmod(staging / name, 0o644)
        checksum_name = zip_name + ".sha256"
        (staging / checksum_name).write_text(f"{digest}  {zip_name}\n", encoding="utf-8")
        (staging / REPORT_NAME).write_text(report_markdown(report), encoding="utf-8")
        (staging / PROGRAM_REPORT_NAME).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        shutil.rmtree(extraction_parent)
        expected = {RELEASE_ROOT_NAME, zip_name, checksum_name, REPORT_NAME, PROGRAM_REPORT_NAME, *ROOT_DOCUMENTS}
        if report.get("external_validation_report"):
            expected.add(report["external_validation_report"]["filename"])
        actual = {item.name for item in staging.iterdir()}
        if actual != expected:
            raise ReleaseError(f"release deliverables mismatch: {sorted(actual)}")
        os.rename(staging, output)
        report["output_dir"] = str(output)
        report["deliverables"] = sorted(expected)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Build FrontMind Content Workflow v4.13.2")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--acceptance-source", type=Path, help="optional legacy anonymous eight-article fixture result")
    parser.add_argument("--validation-report", type=Path, help="copy an external four-part validation report intact, outside the ZIP")
    parser.add_argument("--candidate", action="store_true", help="label and name the package as a candidate; program checks still run")
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        report = build(arguments.source, arguments.acceptance_source, arguments.output_dir,
                       candidate=arguments.candidate, validation_report=arguments.validation_report)
    except (OSError, ValueError, ReleaseError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
