"""Read local Jobs and project only business reviews and public execution events."""
from __future__ import annotations
import importlib.util
import json
import re
from pathlib import Path
import sys

EXPORTER = Path(__file__).resolve().parents[1] / "module/workflows/scripts/export-managed-timeline.py"
sys.path.insert(0, str(EXPORTER.parent))
from portable_lock import file_lock
spec = importlib.util.spec_from_file_location("public_timeline", EXPORTER)
timeline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timeline)


def within(path: Path, root: Path) -> bool:
    return not path.is_symlink() and path.resolve().is_relative_to(root.resolve())


def public_business_file(path: Path, job: Path) -> bool:
    if not path.is_file() or not within(path, job):
        return False
    parts = path.resolve().relative_to(job.resolve()).parts
    return (parts[0] in {"reviews", "research", "examples", "inputs", "positioning",
                         "question_positioning", "blueprints", "deliverables"}
            and path.suffix.lower() in {".md", ".txt", ".json", ".html", ".docx", ".zip"})


def public_review(text: str, job: Path) -> tuple[str, dict]:
    links = {}
    def replace(match):
        label, original = match.groups()
        path = Path(original)
        if not public_business_file(path, job):
            return label + "（本地附件不可公开读取）"
        token = "frontmind-local:" + str(len(links))
        links[token] = path.resolve().relative_to(job.resolve()).as_posix()
        return f"[{label}]({token})"
    return re.sub(r"\[([^\]]+)\]\(<?((?:/|[A-Za-z]:[\\/])[^>\n]+)>\)", replace, text), links


def snapshot(job: Path) -> dict:
    state = json.loads((job / "job_state.json").read_text(encoding="utf-8"))
    lock = job.parent / ("." + job.name + ".frontmind.lock")
    busy = False
    if lock.exists():
        with lock.open("r+b") as handle:
            try:
                with file_lock(handle, blocking=False):
                    pass
            except BlockingIOError:
                busy = True
    reviews = []
    for file in sorted((job / "reviews").glob("*.md")):
        if within(file, job) and file.stat().st_size < 2_000_000:
            text, links = public_review(file.read_text(encoding="utf-8"), job)
            reviews.append({"path": file.relative_to(job).as_posix(), "text": text, "links": links,
                            "time": int(file.stat().st_mtime * 1000)})
    files = []
    delivery_roots = [job / "deliverables"]
    for rerun in state.get("metadata", {}).get("writing_reruns", []):
        name = rerun.get("rerun_id", "")
        if name and Path(name).name == name and name not in {".", ".."}:
            delivery_roots.append(job / "deliverables" / name)
    # Packs contain an unpacked source tree beside their ZIP. Its internal
    # materials are not separate deliverables; native writing reruns are.
    for directory in delivery_roots:
        for file in sorted(directory.glob("*")):
            if file.is_file() and within(file, job) and file.suffix.lower() in {".md", ".docx", ".html", ".zip"}:
                files.append(file.relative_to(job).as_posix())
    delivery = (state.get("metadata", {}).get("reference_pack_delivery") or {})
    for value in delivery.values():
        if isinstance(value, str):
            file = Path(value)
            if not file.is_absolute():
                file = job / file
            if file.is_file() and within(file, job) and file.suffix.lower() == ".zip":
                files.append(file.relative_to(job).as_posix())
    processes = []
    try:
        execution = timeline.export_job(job, task_id=state["job_id"], active=busy)
        processes = timeline.conversation_projection(execution)
    except (timeline.ExportError, OSError, ValueError, TypeError, KeyError) as exc:
        # A Job before its first completed provider event has no timeline yet.
        pass  # Summary failures must not block business reviews or delivery.
    brand = (state.get("reference_pack") or {}).get("brand") or state.get("metadata", {}).get("reference_pack_brand_hint") or "内容任务"
    fact_gate = None
    gate_file = job / "production" / "industry_roundup_quality_gate.json"
    if (state.get("pending_action") or {}).get("action") == "article_fact_repair" and gate_file.is_file() and within(gate_file, job) and gate_file.stat().st_size < 200_000:
        try:
            gate = json.loads(gate_file.read_text(encoding="utf-8"))
            issues = gate.get("issues", [])
            labels = (("正文缺少主体", "主体覆盖不足"), ("正文缺少对比维度", "对比维度不足"),
                      ("正文缺少横向对比表", "缺少横向对比表"), ("读者问题未落到章节", "用户问题未落到章节"),
                      ("正文引用了未登记的事实", "引用未登记事实"), ("正文缺少该主体的事实引用", "主体缺少事实引用"),
                      ("正文沿用了已否决事实", "沿用了已否决事实"), ("具体数字缺少同句原文依据", "数字缺少同句依据"))
            if gate.get("contract") == "frontmind-industry-roundup/1" and isinstance(issues, list):
                fact_gate = {"issueCount": min(len(issues), 10000), "publishReady": gate.get("publish_ready") is True,
                             "categories": list(dict.fromkeys(label for issue in issues if isinstance(issue, str)
                                  for prefix, label in labels if issue.startswith(prefix)))[:8]}
        except (OSError, ValueError, TypeError):
            pass
    return {"directory": job.name, "brand": brand, "state": {key: state.get(key) for key in (
        "schema_version", "artifact_type", "workflow_version", "job_id", "job_kind",
        "updated_at", "created_at", "stage", "status", "revision", "current_pause",
        "pending_action", "flags", "decisions", "p0_route")},
        "busy": busy, "reviews": reviews, "files": sorted(set(files)), "processes": processes, "factGate": fact_gate}


def main():
    root = Path(sys.argv[1]).resolve(strict=True)
    jobs = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and within(child, root) and (child / "job_state.json").is_file():
            jobs.append(snapshot(child))
    # ASCII JSON survives Windows console encodings; Node decodes it as UTF-8.
    print(json.dumps(jobs, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("LOCAL_WORKFLOW_SNAPSHOT_FAILED", file=sys.stderr)
        raise SystemExit(1)
