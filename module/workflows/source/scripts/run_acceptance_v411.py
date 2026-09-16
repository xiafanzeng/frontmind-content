#!/usr/bin/env python3
"""Create the anonymous v4.11 P0 plus seven-question acceptance run."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.docx_font_embedding import audit_docx_embedded_fonts  # noqa: E402


LAUNCHER = ROOT / "scripts/frontmind"
FIXTURE = ROOT / "acceptance_fixtures/v4.11_synthetic"
FORBIDDEN_PAGE_TOKENS = (
    "candidate_", "Fact ID", "answer_span", "dimension_first", "first_tier",
    "supported", "blocked", "score", "coverage", "同分窗口", "evidence overlay",
)


class AcceptanceError(RuntimeError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run(*arguments: str) -> dict:
    completed = subprocess.run(
        [str(LAUNCHER), *arguments], cwd=ROOT, text=True, capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}, check=False,
    )
    if completed.returncode != 0:
        raise AcceptanceError(
            f"command failed ({completed.returncode}): {' '.join(arguments)}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    text = completed.stdout.strip()
    if text.startswith("{"):
        try:
            value, _ = json.JSONDecoder().raw_decode(text)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def state(job: Path) -> dict:
    return json.loads((job / "job_state.json").read_text(encoding="utf-8"))


def require_status(job: Path, expected: str) -> dict:
    current = state(job)
    if current["status"] != expected:
        raise AcceptanceError(f"{job.name}: expected {expected}, got {current['status']}")
    return current


def resume(job: Path, *arguments: str) -> dict:
    current = state(job)
    run(
        "continue", "--job-dir", str(job), "--revision", str(current["revision"]),
        *arguments,
    )
    return state(job)


def relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def validate_public_reviews(job: Path) -> None:
    for review in (job / "reviews").glob("*.md"):
        text = review.read_text(encoding="utf-8")
        for token in FORBIDDEN_PAGE_TOKENS:
            if token.casefold() in text.casefold():
                raise AcceptanceError(f"{job.name}: review contains internal token {token}: {review.name}")


def validate_delivery(job: Path, prefix: str, root: Path) -> dict[str, str]:
    paths = {
        "markdown": job / f"deliverables/{prefix}.md",
        "html": job / f"deliverables/{prefix}.html",
        "docx": job / f"deliverables/{prefix}.docx",
        "title_map": job / f"deliverables/{prefix}_title_map.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise AcceptanceError(f"{job.name}: missing deliverables: {', '.join(missing)}")
    title_map = json.loads(paths["title_map"].read_text(encoding="utf-8"))
    if title_map.get("total_count") != 20 or len(title_map.get("options") or []) != 20:
        raise AcceptanceError(f"{job.name}: title map does not contain 20 titles")
    if len({item.get("title_text") for item in title_map["options"]}) != 20:
        raise AcceptanceError(f"{job.name}: title map contains duplicate titles")
    with __import__("zipfile").ZipFile(paths["docx"]) as archive:
        if "word/document.xml" not in archive.namelist():
            raise AcceptanceError(f"{job.name}: DOCX has no document.xml")
    font_audit = audit_docx_embedded_fonts(paths["docx"])
    if not font_audit.get("passed") or font_audit.get("external_font_dependency"):
        raise AcceptanceError(f"{job.name}: DOCX portable Chinese font audit failed")
    return {name: relative(path, root) for name, path in paths.items()}


def build_positioning_pack(output: Path, fixture: dict) -> tuple[Path, dict]:
    job = output / "reference_pack"
    run(
        "reference-pack", "create", "--brand", fixture["brand"],
        "--input", str(FIXTURE / "brand_material.md"),
        "--job-dir", str(job), "--offline-fixture",
    )
    candidate_state = require_status(job, "awaiting_competitor_selection")
    if not candidate_state["current_pause"]["must_stop"] or candidate_state.get("pending_action") is not None:
        raise AcceptanceError("research did not stop at competitor selection")
    if (job / "positioning/core_positioning.json").exists():
        raise AcceptanceError("core positioning was generated before competitor confirmation")
    selection = json.loads((job / "positioning/competitor_selection.json").read_text(encoding="utf-8"))
    if not selection.get("comparison_targets"):
        raise AcceptanceError("acceptance fixture did not provide selectable comparison targets")
    # The acceptance script acts as the fixture user; the product must not skip this pause.
    resume(job, "--confirm-competitors")
    final_pause = require_status(job, "awaiting_core_positioning_confirmation")
    if final_pause["revision"] != candidate_state["revision"] + 1:
        raise AcceptanceError("competitor confirmation did not advance the revision once")
    scope = final_pause["decisions"]["comparison_scope"]
    core = json.loads((job / "positioning/core_positioning.json").read_text(encoding="utf-8"))
    if not scope.get("confirmed") or scope["revision"] != candidate_state["revision"] or core.get("comparison_scope") != scope:
        raise AcceptanceError("controller-owned scope was not preserved in core positioning")
    confirmation_page = Path(state(job)["current_pause"]["review_markdown_path"]).read_text(encoding="utf-8")
    sections = ("## 核心定位", "## 与已确认竞品的比较", "## 您可以选择")
    for token in sections:
        if token not in confirmation_page:
            raise AcceptanceError(f"core positioning confirmation misses {token}")
    if [confirmation_page.index(token) for token in sections] != sorted(confirmation_page.index(token) for token in sections):
        raise AcceptanceError("core positioning confirmation sections are out of order")
    if final_pause["current_pause"]["full_text_links"] or final_pause["current_pause"]["source_links"]:
        raise AcceptanceError("final positioning page unexpectedly exposes research attachments")
    if any(token in confirmation_page for token in ("## 证明材料", "## 适用条件与研究限制", "## 为什么值得选择", "[完整研究]")):
        raise AcceptanceError("final positioning page contains a removed evidence or summary section")
    resume(job, "--confirm-core-positioning")
    final = require_status(job, "positioning_ready")
    delivery = final.get("metadata", {}).get("reference_pack_delivery") or {}
    pack = Path(delivery.get("pack_path") or "")
    if not pack.is_dir() or delivery.get("pack_version") != 1:
        raise AcceptanceError("positioning_ready Reference Pack v1 was not produced")
    exported = json.loads((pack / "strategy/core_positioning.json").read_text(encoding="utf-8"))
    if exported != core:
        raise AcceptanceError("Pack export changed the confirmed positioning or comparison scope")
    validate_public_reviews(job)
    return pack, final


def build_p0(output: Path, positioning_pack: Path) -> tuple[Path, dict, dict[str, str]]:
    job = output / "p0"
    run(
        "p0", "--reference-pack", str(positioning_pack),
        "--job-dir", str(job), "--offline-fixture",
    )
    require_status(job, "awaiting_reference_pack_route")
    resume(job, "--reference-pack-route", "use")
    require_status(job, "awaiting_p0_route")
    resume(job, "--p0-route", "create")
    require_status(job, "awaiting_p0_example_confirmation")
    resume(job, "--accept-p0-example-route", "top20")
    require_status(job, "awaiting_p0_blueprint_confirmation")
    resume(job, "--accept-p0-blueprint")
    final = require_status(job, "p0_ready")
    if final.get("pending_action") is not None:
        raise AcceptanceError("terminal P0 state retained a provider action")
    delivery = final.get("metadata", {}).get("reference_pack_delivery") or {}
    pack = Path(delivery.get("pack_path") or "")
    if not pack.is_dir() or delivery.get("pack_version") != 2:
        raise AcceptanceError("p0_ready Reference Pack v2 was not produced")
    validate_public_reviews(job)
    return pack, final, validate_delivery(job, "p0", output)


def build_article(output: Path, pack: Path, case: dict) -> tuple[Path, dict, dict[str, str], Path]:
    job = output / f"article_{case['case_id']}"
    run(
        "article", "--reference-pack", str(pack), "--job-dir", str(job),
        "--question-id", case["question_id"], "--question", case["question"],
        "--answer", str(FIXTURE / "answer_01.md"),
        "--answer", str(FIXTURE / "answer_02.md"), "--offline-fixture",
    )
    require_status(job, "awaiting_reference_pack_route")
    resume(job, "--reference-pack-route", "use")
    require_status(job, "awaiting_response_brief")
    resume(job, "--no-extra-response-requirements", "--ai-brand-recognition", "insufficient")
    require_status(job, "awaiting_pattern_confirmation")
    pattern_page = Path(state(job)["current_pause"]["review_markdown_path"]).read_text(encoding="utf-8")
    if any(pattern not in pattern_page for pattern in ("P00", "P01", "P02", "P03", "P04", "P05", "P06")):
        raise AcceptanceError(f"{case['case_id']}: Pattern page is incomplete")
    resume(job, "--pattern", case["pattern_id"])
    require_status(job, "awaiting_example_confirmation")
    if len(state(job)["current_pause"].get("full_text_links") or []) != 4:
        raise AcceptanceError(f"{case['case_id']}: example page does not link four complete texts")
    resume(job, "--example-route", "A")
    if case["question_positioning"]:
        require_status(job, "awaiting_question_positioning_confirmation")
        positioning_page = Path(state(job)["current_pause"]["review_markdown_path"]).read_text(encoding="utf-8")
        required = ("本题需求", "替代选择", "并列说明") if case["pattern_id"] == "P02" else ("主要推荐对象", "其他选择")
        if any(token not in positioning_page for token in required):
            raise AcceptanceError(f"{case['case_id']}: P02 positioning page is incomplete")
        resume(job, "--confirm-question-positioning")
    require_status(job, "awaiting_blueprint_confirmation")
    resume(job, "--accept-blueprint")
    final = require_status(job, "completed")
    if final.get("pending_action") is not None:
        raise AcceptanceError(f"{case['case_id']}: terminal article retained a provider action")
    actual_positioning = (job / "question_positioning/question_positioning.json").is_file()
    if actual_positioning is not bool(case["question_positioning"]):
        raise AcceptanceError(f"{case['case_id']}: question-positioning route mismatch")
    if final.get("selected_pattern_id") != case["pattern_id"]:
        raise AcceptanceError(f"{case['case_id']}: Pattern mismatch")
    validate_public_reviews(job)
    next_pack = Path(final["reference_pack"]["path"])
    return job, final, validate_delivery(job, "article", output), next_pack


def resolve_command(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    raise AcceptanceError(f"required render command is unavailable: {' or '.join(names)}")


def render_docx_qa(output: Path, docx_paths: list[str]) -> dict:
    soffice = resolve_command("soffice", "libreoffice")
    pdfinfo = resolve_command("pdfinfo")
    pdftoppm = resolve_command("pdftoppm")
    pdffonts = resolve_command("pdffonts")
    qa_root = output / "docx_visual_qa"
    qa_root.mkdir()
    documents: list[dict] = []
    for index, relative_path in enumerate(docx_paths, 1):
        docx = output / relative_path
        render_dir = qa_root / f"document_{index:02d}"
        render_dir.mkdir()
        conversion = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(render_dir), str(docx)],
            text=True, capture_output=True, check=False, timeout=120,
        )
        pdf = render_dir / f"{docx.stem}.pdf"
        if conversion.returncode != 0 or not pdf.is_file():
            raise AcceptanceError(f"DOCX render failed: {relative_path}: {conversion.stderr}")
        font_report = subprocess.run(
            [pdffonts, str(pdf)], text=True, capture_output=True, check=False, timeout=30,
        )
        if font_report.returncode != 0 or "NotoSansCJKsc" not in font_report.stdout:
            raise AcceptanceError(f"DOCX render did not use embedded Chinese fonts: {relative_path}")
        info = subprocess.run([pdfinfo, str(pdf)], text=True, capture_output=True, check=False, timeout=30)
        page_line = next((line for line in info.stdout.splitlines() if line.startswith("Pages:")), "")
        try:
            page_count = int(page_line.split(":", 1)[1].strip())
        except (IndexError, ValueError) as exc:
            raise AcceptanceError(f"cannot determine PDF page count: {relative_path}") from exc
        raster = subprocess.run(
            [pdftoppm, "-png", "-r", "96", str(pdf), str(render_dir / "page")],
            text=True, capture_output=True, check=False, timeout=120,
        )
        pages = sorted(render_dir.glob("page-*.png"))
        if raster.returncode != 0 or len(pages) != page_count or any(path.stat().st_size < 1000 for path in pages):
            raise AcceptanceError(f"DOCX page rasterization failed: {relative_path}")
        documents.append({
            "path": relative_path, "status": "pass", "page_count": page_count,
            "embedded_chinese_font_rendered": True,
            "pdf": relative(pdf, output), "page_images": [relative(path, output) for path in pages],
        })
    result = {
        "schema_version": "4.11", "artifact_type": "frontmind_docx_visual_qa",
        "status": "pass", "method": "LibreOffice PDF render plus complete page rasterization",
        "documents": documents,
    }
    (output / "docx_visual_qa.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    return result


def create_acceptance(output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise AcceptanceError("acceptance output must not already exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    fixture = json.loads((FIXTURE / "manifest.json").read_text(encoding="utf-8"))
    try:
        positioning_pack, positioning_state = build_positioning_pack(output, fixture)
        p0_pack, p0_state, p0_delivery = build_p0(output, positioning_pack)
        records = [{
            "case_id": "p0", "kind": "p0", "pattern_id": "P00",
            "question": None, "question_positioning": False,
            "job": "p0", "pack_version": 2, "deliverables": p0_delivery,
        }]
        current_pack = p0_pack
        versions = [1, 2]
        for case in fixture["cases"]:
            job, article_state, delivery, current_pack = build_article(output, current_pack, case)
            version = int(article_state["reference_pack"]["pack_version"])
            versions.append(version)
            records.append({
                "case_id": case["case_id"], "kind": "question",
                "pattern_id": case["pattern_id"], "question": case["question"],
                "question_positioning": (job / "question_positioning/question_positioning.json").is_file(),
                "job": relative(job, output), "pack_version": version,
                "deliverables": delivery,
            })
        if versions != list(range(1, 10)):
            raise AcceptanceError(f"Reference Pack versions are not sequential: {versions}")
        pack_ids = {
            positioning_state["metadata"]["reference_pack_delivery"]["pack_id"],
            p0_state["metadata"]["reference_pack_delivery"]["pack_id"],
            *[state(output / f"article_{case['case_id']}")["reference_pack"]["pack_id"] for case in fixture["cases"]],
        }
        if len(pack_ids) != 1:
            raise AcceptanceError("acceptance tasks did not stay in one Reference Pack series")
        qa = render_docx_qa(output, [item["deliverables"]["docx"] for item in records])
        result = {
            "schema_version": "4.11",
            "artifact_type": "frontmind_v411_acceptance_run",
            "status": "pass", "fixture_only": True, "brand": fixture["brand"],
            "created_at": now(), "pack_id": next(iter(pack_ids)),
            "pack_versions": versions, "final_pack": relative(current_pack, output),
            "counts": {
                "p0": 1, "question_articles": 7, "markdown": 8,
                "html": 8, "docx": 8, "title_maps": 8, "titles": 160,
            },
            "docx_visual_qa": {"status": qa["status"], "document_count": len(qa["documents"])},
            "cases": records,
        }
        (output / "acceptance_manifest.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        return result
    except Exception:
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run anonymous FrontMind v4.11 acceptance")
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        result = create_acceptance(arguments.output.expanduser().resolve())
    except (AcceptanceError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "fail", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
