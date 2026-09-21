#!/usr/bin/env python3
"""Build the self-contained FrontMind Content Workflow v4.11.0 release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
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


RELEASE_VERSION = "4.11.0"
WORKFLOW_VERSION = "4.11"
RELEASE_ROOT_NAME = "FrontMind_Content_Workflow_v4.11.0"
FINAL_ZIP_NAME = "FrontMind_Content_Workflow_v4.11.0_Final.zip"
CHECKSUM_NAME = FINAL_ZIP_NAME + ".sha256"
REPORT_NAME = "acceptance-report-v4.11.0.md"
ZIP_TIME = (2026, 1, 1, 0, 0, 0)

# This is deliberately an allowlist. Historical source remains available to
# maintainers, while old package models, ledgers, scoring modules, tests and
# work output cannot enter the v4.11 release projection.
RELEASE_FILES = frozenset({
    ".codex/config.toml",
    "00.FrontMind内容制作总控.skill/SKILL.md",
    "AGENTS.md",
    "README.md",
    "START_HERE.md",
    "RUNBOOK.md",
    "FrontMind_执行手册_v4.11.0.md",
    "CHANGELOG_v4.11.0.md",
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
    "shared/assets/fonts",
    "shared/vendor/fonttools_4_63_0",
)
ROOT_DOCUMENTS = (
    "START_HERE.md",
    "FrontMind_执行手册_v4.11.0.md",
    "RUNBOOK.md",
    "CHANGELOG_v4.11.0.md",
    "REFERENCE_PACK_4.1_ARCHITECTURE.md",
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
    ("东莞" + "台心").encode("utf-8"),
    ("台心" + "医院").encode("utf-8"),
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
            if "__pycache__" in relative_parts or path.suffix.casefold() == ".pyc":
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
        os.chmod(target, 0o755 if relative_text == "scripts/frontmind" else 0o644)
        copied.append(relative_text)
    return copied


def audit_projection(root: Path, expected_files: Iterable[str] | None = None) -> dict[str, Any]:
    files = [path for path in root.rglob("*") if path.is_file()]
    actual = {path.relative_to(root).as_posix() for path in files}
    expected = set(expected_files) if expected_files is not None else set(release_file_set(root))
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ReleaseError(f"release projection mismatch; missing={missing}, extra={extra}")
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
        for marker in PRIVATE_MARKERS:
            if marker in data:
                raise ReleaseError(f"private/client marker entered release: {relative}")
    launcher_mode = stat.S_IMODE((root / "scripts/frontmind").stat().st_mode)
    if launcher_mode != 0o755:
        raise ReleaseError("projected scripts/frontmind mode is not 0755")
    return {"file_count": len(files), "launcher_mode": "0755"}


def write_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            name = f"{RELEASE_ROOT_NAME}/{relative}"
            info = zipfile.ZipInfo(name, ZIP_TIME)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if relative == "scripts/frontmind" else 0o644
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
        return {"member_count": len(infos), "launcher_mode": "0755"}


def extract_zip(path: Path, destination: Path) -> Path:
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
        [python, "-B", "scripts/validate_workflow.py", "--run-tests", "--release-projection"],
        root, "clean validation and tests",
    )
    return {"preflight": preflight, "validation": validation}


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
        if title_payload.get("total_count") != 20 or len(title_payload.get("options") or []) != 20:
            raise ReleaseError(f"acceptance Title Map is incomplete: {case['case_id']}")
        title_count += 20
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
    tests = report["validation"].get("tests") or {}
    return f"{tests.get('test_count', 'unknown')} tests, {tests.get('status', 'unknown')}"


def report_markdown(report: dict[str, Any]) -> str:
    acceptance = report["acceptance"]
    counts = acceptance["counts"]
    return f"""# FrontMind Content Workflow v4.11.0 验收报告

- 发行版本：`{RELEASE_VERSION}`
- 运行时合同：`{WORKFLOW_VERSION}`
- 生成时间：`{report['created_at']}`
- 构建与流程验收状态：**PASS**（定位生成质量单独说明）

## 源码目录验证

- 预检：`{report['source']['preflight']['status']}`
- 完整测试：`{test_summary(report['source'])}`

## 启动协议验收

- `./scripts/frontmind` 无参数启动与 `./scripts/frontmind start` 返回同一标准启动页；
- 启动页区分新建 Reference Pack、刷新已有 Reference Pack、P0 和单问题文章；
- 启动页不创建 Job，品牌名称不能被解释为已选择新建 Pack；
- P0 与 article 选定后仍进入 Reference Pack 路由。

## 定位流程与接口验收

- 正常流程为 `positioning_market_research` → `awaiting_competitor_selection` 用户确认比较范围 → `positioning_value_synthesis` → 最终定位确认；两个 Provider 动作、两个定位业务暂停；
- 研究提供轻量 `competitor_candidates`；控制器维护 `comparison_scope` 并随核心 JSON 导出，旧 Pack 缺少该字段仍可读，不自动推定范围，不增加旧 Pack 必需文件；
- 类型间、同类型和混合比较使用用户确认的实际对象；同类举例不参与优劣论证，目标品牌档内首展示不代表同档胜出或全市场第一；
- `--competitor-selection` 接收 JSON 或文件路径，`--confirm-competitors` 确认范围，`--return-to-competitors` 返回竞品页；用户对话不要求填写 JSON；
- 无分档、单项优势和自然改写可正常确认，不补造排名和经营取舍；
- 最终定位页与公开定位 Markdown 只呈现核心定位和已确认竞品比较，不附研究附件或来源链接；原始研究与历史必要条件继续供内部写作读取；
- 通用写作指令要求核心采用客群、实现价值的方式、用户收益的自然叙事，公开比较不谈资料状况，真实取舍按需保留；这些是指令要求，实际遵循情况见生成观察报告；
- P01/P02 相同条件沿用已确认比较依据，条件变化说明调整；本次实际模型参数固定为 glm-5.3 / high / standard；
- 修改表述保留范围、仅重新综合；补充事实保留范围、补研后再综合；重新探索回竞品页，旧选择作为可编辑预选；旧方向仅作最终结果投影；
- Pack、P0、P01/P02 与作者上下文传递已确认范围，本题需要不同对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。

## 定位生成质量

本构建报告的自动测试与匿名验收使用受控 Provider 输出或离线夹具，验证的是结构、路由、传递与导出，**不证明真实模型的定位生成质量**。
本次真实 glm-5.3 集中表达修订的主运行、独立复测、失败与针对性修正、跨行业和 P02 观察见单独报告。历史三轮只用于对照；程序通过不表示实际文字达标。没有实测报告时应视为尚未验证真实生成质量，不以示意段落或手工改写替代，也不增加生产调用、语义评分或用户审批。

## 匿名内容验收

- P0：`{counts['p0']}`
- 问题文章：`{counts['question_articles']}`
- Markdown / HTML / DOCX / Title Map：`{counts['markdown']} / {counts['html']} / {counts['docx']} / {counts['title_maps']}`
- 标题：`{counts['titles']}`
- 单一 Reference Pack：同一 `pack_id`，版本连续为 `v1–v9`
- 八份 DOCX 渲染与逐页检查：`pass`
- 七题 Pattern：P02、P06、P02、P06、P05、P02、P02
- P03–P06 不产生逐题定位；四个 P02 产生自然问题定位。

## 全新解压目录验证

- 预检：`{report['clean']['preflight']['status']}`
- 完整测试：`{test_summary(report['clean'])}`
- ZIP 成员数：`{report['zip']['member_count']}`
- `scripts/frontmind` ZIP 权限：`{report['zip']['launcher_mode']}`

## 发行边界

发行投射采用精确 allowlist。最终 ZIP 不含客户资料、验收成稿、私有 Top20
全文、Provider 输出、日志、缓存、凭据、旧答案账本、旧定位评分、旧证据
叠加模块或独立的旧品牌基础包结构。

## 校验值

- `{FINAL_ZIP_NAME}` SHA-256：`{report['final_zip_sha256']}`
"""


def build(source: Path, acceptance_source: Path, output_dir: Path) -> dict[str, Any]:
    source = regular_directory(source, "source")
    acceptance = regular_directory(acceptance_source, "acceptance source")
    output = ensure_new_output(output_dir, source)
    python = choose_python()
    source_result = validate_source(source, python)
    acceptance_result = validate_acceptance(acceptance)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output.name}.staging-", dir=output.parent))
    try:
        workflow = staging / RELEASE_ROOT_NAME
        copied = copy_projection(source, workflow)
        projection = audit_projection(workflow, copied)
        run_json(
            [python, "-B", "scripts/validate_workflow.py", "--release-projection"],
            workflow, "release projection validation",
        )
        final_zip = staging / FINAL_ZIP_NAME
        write_zip(workflow, final_zip)
        zip_result = inspect_release_zip(final_zip)
        extraction_parent = staging / "clean-extraction"
        clean_root = extract_zip(final_zip, extraction_parent)
        clean_result = validate_clean_extraction(clean_root, python)
        digest = sha256(final_zip)
        report: dict[str, Any] = {
            "status": "pass",
            "release_version": RELEASE_VERSION,
            "workflow_version": WORKFLOW_VERSION,
            "created_at": now(),
            "source": source_result,
            "acceptance": acceptance_result,
            "projection": {**projection, "allowlisted_file_count": len(copied)},
            "zip": zip_result,
            "clean": clean_result,
            "final_zip_sha256": digest,
        }
        for name in ROOT_DOCUMENTS:
            shutil.copyfile(workflow / name, staging / name)
            os.chmod(staging / name, 0o644)
        (staging / CHECKSUM_NAME).write_text(f"{digest}  {FINAL_ZIP_NAME}\n", encoding="utf-8")
        (staging / REPORT_NAME).write_text(report_markdown(report), encoding="utf-8")
        shutil.rmtree(extraction_parent)
        expected = {
            RELEASE_ROOT_NAME, FINAL_ZIP_NAME, CHECKSUM_NAME, REPORT_NAME, *ROOT_DOCUMENTS,
        }
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
    parser = argparse.ArgumentParser(description="Build FrontMind Content Workflow v4.11.0")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--acceptance-source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        report = build(arguments.source, arguments.acceptance_source, arguments.output_dir)
    except (OSError, ValueError, ReleaseError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
