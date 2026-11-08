"""Import a standalone monitoring-answer export into a portable question bank.

No LLM calls. Answers stay research context, never business facts. A missing
citation workbook is represented explicitly, not treated as missing answers.
"""
from __future__ import annotations

import copy
import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import question_research as qr, research_ingestion as ri
from .question_semantics import classify_question, normalize_question_key

ROOT = qr.QUESTION_RESEARCH_ROOT_MEMBER
INDEX = qr.QUESTION_RESEARCH_INDEX_MEMBER
UNKNOWN_PLATFORMS = {"", "unspecified", "unknown", "未知平台", "详细表格", "未提供"}


def now():
    return datetime.now(timezone.utc).isoformat()


def platform_key(value):
    # No fuzzy brand/platform merging. Obvious casing/whitespace only.
    return ri.normal(value).casefold()


def known_platforms(answers):
    return sorted({platform_key(x.get("platform")) for x in answers
                   if isinstance(x, dict) and str(x.get("answer_text") or "").strip()
                   and platform_key(x.get("platform")) not in UNKNOWN_PLATFORMS})


def export_rows(path: Path):
    path = ri._regular_file(Path(path), ri.MONITORING_SUFFIXES, "monitoring-answer export")
    if path.suffix.casefold() == ".xlsx":
        rows = ri._rows_from_xlsx(path, with_provenance=True)
    elif path.suffix.casefold() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = [("CSV", {**row, "__frontmind_source_row__": n}) for n, row in enumerate(csv.DictReader(handle), 2)]
    else:
        raw = ri._strict_json_bytes(path.read_bytes(), path.name)
        raw = raw.get("rows", []) if isinstance(raw, dict) else raw
        if not isinstance(raw, list):
            raise qr.QuestionResearchError("问答JSON应是原始行数组或rows数组，不接收概括稿。")
        rows = [("JSON", {**row, "__frontmind_source_row__": n}) for n, row in enumerate(raw, 1) if isinstance(row, dict)]
    return rows


def looks_like_monitoring(path: Path) -> bool:
    if path.suffix.casefold() not in ri.MONITORING_SUFFIXES:
        return False
    # Only divert positively identified tables. Never infer type from filename.
    for _, row in export_rows(path):
        fields = {ri.field_key(k) for k in row}
        if (fields & {ri.field_key(k) for k in ri.QUESTION_ALIASES}
                and fields & {ri.field_key(k) for k in ri.PLATFORM_ALIASES}
                and fields & {ri.field_key(k) for k in ri.ANSWER_ALIASES}):
            return True
    return False


def read_export(path: Path, *, brand: str = "", aliases=()):
    path = ri._regular_file(Path(path), ri.MONITORING_SUFFIXES, "monitoring-answer export")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    by_date: dict[str, dict[str, Any]] = {}
    total_rows = 0
    question_order = []
    warnings = []
    for sheet, row in export_rows(path):
        text = ri.normal(ri._field(row, ri.QUESTION_ALIASES))
        key = normalize_question_key(text)
        if not key:
            continue
        # Ignore explanatory sheets even if they repeat a header word.
        fields = {ri.field_key(k) for k in row}
        if not fields & {ri.field_key(k) for k in ri.ANSWER_ALIASES}:
            continue
        raw_brand = ri.normal(ri._field(row, ri.BRAND_ALIASES))
        if brand and raw_brand:
            ok, warning = ri._brand_compatible([raw_brand], brand, aliases)
            if not ok:
                raise qr.QuestionResearchError(f"问答表品牌 {raw_brand!r} 与Pack品牌 {brand!r} 不匹配；确属同一品牌时显式提供--brand-alias。")
            if warning:
                warnings.append(warning)
        raw_date = ri._field(row, ri.DATE_ALIASES)
        sampled_at = qr._date_first(raw_date)
        if raw_date not in (None, "") and sampled_at is None:
            raise qr.QuestionResearchError(f"{sheet}第{row.get('__frontmind_source_row__')}行监控日期无法解析：{raw_date}")
        if key not in question_order:
            question_order.append(key)
        date_key = sampled_at or "undated"
        group = by_date.setdefault(date_key, {})
        target = group.setdefault(key, {"text": text, "texts": [], "answers": [], "rows": [], "question_ids": []})
        if text not in target["texts"]:
            target["texts"].append(text)
        external = ri.normal(ri._field(row, {"question_id", "问题ID", "问题编号", "正式问题编号"}))
        if external and external not in target["question_ids"]:
            target["question_ids"].append(external)
        if len(target["question_ids"]) > 1:
            raise qr.QuestionResearchError(f"同一问题出现多个原始ID：{text}；须先明确归属，不能静默覆盖。")
        source = {"file_name": path.name, "file_sha256": "sha256:" + digest,
                  "sheet": sheet, "row": row.get("__frontmind_source_row__"),
                  "date_raw": str(raw_date) if raw_date is not None else None,
                  "question_text": text}
        target["rows"].append(source)
        platform = ri.normal(ri._field(row, ri.PLATFORM_ALIASES)) or "未知平台"
        rank = ri._field(row, ri.RANK_ALIASES)
        keyword = ri.normal(ri._field(row, {"核心词", "问题核心词", "keyword", "questionkeyword"})) or None
        for entry in qr._answer_groups(row):
            # Do not normalize whitespace in an answer. Headings, paragraph
            # breaks, citations and original text are retained byte-for-text.
            answer = {"platform": platform, "model": None, "sampled_at": sampled_at,
                      "answer_text": entry["answer_text"], "citations": [],
                      "region": entry.get("region"), "exported_rank": str(rank) if rank is not None else entry.get("exported_rank"),
                      "monitor_keyword_rank": entry.get("monitor_keyword_rank"), "brand": raw_brand or None,
                      "question_keyword": keyword, "source_record": source,
                      "sample_label": ri.normal(ri._field(row, {"提问次数", "sample", "sample_id"})) or None,
                      "screenshot_url": ri._http_url(ri._field(row, {"回答截图", "截图链接", "screenshot"}))}
            target["answers"].append(answer)
        total_rows += 1
    if not by_date:
        raise qr.QuestionResearchError("没有识别到监控问题、平台及回答内容列；不会把普通资料猜成问答数据。")
    if "undated" in by_date:
        warnings.append("部分观察没有监控日期；单独保存，不从文件名推断采样日。")
    return {"sha256": "sha256:" + digest, "file_name": path.name, "dates": by_date,
            "row_count": total_rows, "question_order": question_order, "warnings": list(dict.fromkeys(warnings))}


def build_artifacts(path: Path, *, brand: str, existing_index=None, aliases=()):
    """Return normalized members + index; caller owns atomic Pack commit."""
    exported = read_export(path, brand=brand, aliases=aliases)
    index = copy.deepcopy(existing_index or qr.empty_question_research_index())
    if any(x.get("source_sha256") == exported["sha256"] for x in index.get("monitoring_imports", [])):
        return {}, index, {"status": "already_imported", "source_sha256": exported["sha256"]}
    questions = {x["question_key"]: x for x in index["questions"]}
    uid_number = max((int(x["question_uid"][1:]) for x in questions.values()), default=0)
    period_number = max((int(x["period_id"][1:]) for x in index["periods"]), default=0)
    source_order = max((int(x.get("source_order") or 0) for x in questions.values()), default=0)
    artifacts = {}
    new_keys = [key for key in exported["question_order"] if key not in questions]
    reserved = {key: (f"q{uid_number+n:06d}", source_order+n) for n,key in enumerate(new_keys,1)}
    imported_uids, period_ids = [], []
    # Date grouping never mixes platforms across observation dates. This is
    # an ingestion snapshot, not a claim that missing web citations were read.
    for date_key, groups in sorted(exported["dates"].items(), key=lambda pair: (pair[0] != "undated", pair[0])):
        period_number += 1
        pid = f"p{period_number:06d}"
        period_ids.append(pid)
        date = None if date_key == "undated" else date_key
        platforms = sorted({a["platform"] for x in groups.values() for a in x["answers"]})
        period = {"period_id": pid, "status": "complete", "ingested_at": now(),
                  "workspace_period_label": None, "declared_period_label": f"监控答案导入 {date_key}",
                  "observed_from": date, "observed_to": date,
                  "monitoring_observed_from": date, "monitoring_observed_to": date,
                  "citation_observed_from": None, "citation_observed_to": None,
                  "platforms": platforms, "complete_question_count": len(groups),
                  "monitoring_question_count": len(groups), "citation_question_count": len(groups),
                  "monitoring_only_question_keys": [], "citation_only_question_keys": [],
                  "citation_availability": "not_supplied", "source_sha256": exported["sha256"],
                  "warnings": ["未提供独立引用明细；空引用切片只表示没有导入引用，不表示没有引用。"]}
        index["periods"].append(period)
        for key, record in groups.items():
            question = questions.get(key)
            external = next(iter(record["question_ids"]), None)
            if external and any(x.get("question_id") == external and x["question_key"] != key for x in questions.values()):
                raise qr.QuestionResearchError(f"原始问题ID {external} 指向不同问题；未写入。")
            if question is None:
                uid, order = reserved[key]
                question = {"question_uid": uid, "question_key": key, "question_text": record["text"],
                            "text_variants": [], "question_id": external, "source_order": order,
                            "source_kind": "project_optimization_target",
                            "classification": qr._classification(record["text"], None),
                            "lifecycle": {"state": "active", "reason": "monitoring_export_import", "changed_at": None},
                            "formal_question_eligible": True, "complete_period_ids": [], "history": {}}
                # Explicit retirement is sticky across imports.
                if any(x["question_key"] == key for x in index.get("retired_question_markers", [])):
                    question["lifecycle"] = {"state": "retired", "reason": "existing_retirement_marker", "changed_at": None}
                    question["formal_question_eligible"] = False
                questions[key] = question; index["questions"].append(question)
            elif external:
                if question.get("question_id") not in (None, external):
                    raise qr.QuestionResearchError(f"问题原始ID冲突：{record['text']}")
                question["question_id"] = external
            uid = question["question_uid"]
            imported_uids.append(uid)
            question["text_variants"] = list(dict.fromkeys([*question.get("text_variants", []), *record["texts"]]))
            mpath = f"{ROOT}/questions/{uid}/periods/{pid}/monitoring_observations.json"
            cpath = f"{ROOT}/questions/{uid}/periods/{pid}/citation_observations.json"
            monitoring = qr._monitoring_slice(uid, question["question_text"], key, pid,
                                               {"answers": record["answers"]}, {}, date, date)
            for actual, original in zip(monitoring["answers"], record["answers"]):
                actual.update({k: original[k] for k in ("source_record", "sample_label", "screenshot_url")})
            monitoring["source_rows"] = record["rows"]
            citation = qr._citation_slice(uid, question["question_text"], key, pid, {"details": []}, None, None)
            citation["availability"] = "not_supplied"
            artifacts[mpath] = monitoring; artifacts[cpath] = citation
            index["slices"].append({"slice_id": f"{uid}-{pid}", "question_uid": uid, "question_key": key,
                "period_id": pid, "status": "complete", "observed_from": date, "observed_to": date,
                "monitoring_path": mpath, "citation_path": cpath,
                "answer_observation_count": len(record["answers"]), "platform_count": len(known_platforms(record["answers"])),
                "citation_detail_count": 0, "unique_citation_content_count": 0,
                "citation_availability": "not_supplied",
                "brand_mention_rate": None, "top1_rate": None, "top3_rate": None, "average_rank": None,
                "citation_domain_count": 0, "citation_domain_concentration_top3": None})
    index["questions"].sort(key=lambda q:(int(q.get("source_order") or 0),q["question_uid"]))
    period_map = {x["period_id"]: x for x in index["periods"]}
    for q in index["questions"]:
        ids = sorted({x["period_id"] for x in index["slices"] if x["question_uid"] == q["question_uid"]},
                     key=lambda p: qr._period_sort_value(period_map[p]))
        if not ids:
            continue
        q.update(complete_period_ids=ids, first_complete_period_id=ids[0], latest_complete_period_id=ids[-1])
        q["history"] = {"period_count": len(ids), "baseline_type": "snapshot" if len(ids) == 1 else "change",
                        "latest_period_id": ids[-1], "previous_period_id": ids[-2] if len(ids) > 1 else None,
                        "deltas": {}}
    latest = max(index["periods"], key=qr._period_sort_value)["period_id"]
    index["current_period_id"] = latest
    index["index_revision"] += 1; index["updated_at"] = now()
    summary = {"status": "imported", "file_name": exported["file_name"], "source_sha256": exported["sha256"],
               "question_count": len(set(imported_uids)), "row_count": exported["row_count"],
               "answer_count": sum(len(x["answers"]) for groups in exported["dates"].values() for x in groups.values()),
               "period_ids": period_ids, "observed_dates": [x for x in exported["dates"] if x != "undated"],
               "current_period_id": latest, "imported_at": now(), "warnings": exported["warnings"]}
    index.setdefault("monitoring_imports", []).append(summary)
    members = {x[k] for x in index["slices"] for k in ("monitoring_path", "citation_path")}
    errors, _ = qr.validate_question_research_index(index, members)
    if errors:
        raise qr.QuestionResearchError("导入结果结构无效：" + "; ".join(errors))
    artifacts[INDEX] = index
    return artifacts, index, summary


def readiness_for(index, read_json):
    slices = {(x["question_uid"], x["period_id"]): x for x in index["slices"]}
    result = {}
    for q in index["questions"]:
        x = slices.get((q["question_uid"], q["latest_complete_period_id"]))
        answers = read_json(x["monitoring_path"]).get("answers", []) if x else []
        result[q["question_uid"]] = q.get("lifecycle", {}).get("state") == "active" and q.get("formal_question_eligible") is True and len(known_platforms(answers)) >= 2
    return result


def install_in_staging(root: Path, export_path: Path, *, brand: str, aliases=()):
    """Use only inside an unpublished Pack staging transaction."""
    index_path = root / INDEX
    old = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else None
    artifacts, index, summary = build_artifacts(export_path, brand=brand, existing_index=old, aliases=aliases)
    for member, obj in artifacts.items():
        qr._atomic_json(root / member, obj)
    manifest_path = root / "materials/index.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["question_research_index_path"] = INDEX
    qr._atomic_json(manifest_path, manifest)
    pack_path = root / "reference_pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["readiness"]["question_ready"] = readiness_for(index, lambda p: json.loads((root/p).read_text(encoding="utf-8")))
    qr._atomic_json(pack_path, pack)
    return summary


def import_into_pack(*, pack: Path, monitoring_answers: Path, output=None, portable_zip=None, aliases=()):
    from Reference_Pack_Workflow.shared import reference_pack_builder as b
    source = Path(pack).expanduser().resolve()
    before = b.validate_reference_pack(source)
    if before.get("status") != "pass":
        raise b.ReferencePackBuildError("导入前Pack校验失败：" + "; ".join(before.get("errors", [])))
    old_root = b._pack_root_payload(source)
    reader = ri._DirectoryPackageReader(source) if source.is_dir() else ri._ZipPackageReader(source)
    try:
        names = set(reader.names())
        def read(member):
            return ri._strict_json_bytes(reader.read(member), member)
        artifacts, index, summary = build_artifacts(monitoring_answers, brand=old_root["brand_name"],
                                                    existing_index=read(INDEX) if INDEX in names else None, aliases=aliases)
        if not artifacts:
            return {**summary, "pack_path": str(source), "pack_version": old_root["pack_version"],
                    "pack_id": old_root["pack_id"], "readiness": before["readiness"]}
        material = read("materials/index.json")
        if any(x.get("source_sha256") == summary.get("source_sha256") for x in material.get("items", [])):
            summary.setdefault("warnings", []).append("此表曾被列作普通材料；后续业务事实投射已排除该源。历史定位与P0原文保留，须核对是否曾引用AI答案，不自动重写旧结论。")
        material["question_research_index_path"] = INDEX
        artifacts["materials/index.json"] = material
        ready = readiness_for(index, lambda m: artifacts[m] if m in artifacts else read(m))
        destination = Path(output) if output else source.with_name(f"{source.stem}_questions_v{int(old_root['pack_version'])+1}")
        result = b.create_next_reference_pack_version(pack=source, output=destination,
                  artifacts={m: json.dumps(obj, ensure_ascii=False, indent=2) + "\n" for m, obj in artifacts.items()},
                  readiness_updates={"question_ready": ready}, portable_zip=portable_zip)
        return {**result, "question_import": summary}
    finally:
        close = getattr(reader, "close", None)
        if close:
            close()


def monitoring_exclusions(index, material_index):
    """Known answer exports, not guesses based on filenames or prose."""
    hashes={x.get("source_sha256") for x in (index or {}).get("monitoring_imports", [])}
    members=set(); sources=set()
    for item in (material_index or {}).get("items", []):
        if item.get("source_sha256") in hashes:
            members.add(str(item.get("path") or ""))
            sources.add("src_"+str(item["source_sha256"]).removeprefix("sha256:")[:16])
    return members,sources


def business_registry_view(value, excluded_members, excluded_sources):
    """Project legacy mixed registries for reading; never rewrite old Pack files."""
    value=copy.deepcopy(value)
    for field in ("items","sources","knowledge_units","claims","images"):
        if isinstance(value.get(field),list):
            value[field]=[item for item in value[field] if not isinstance(item,dict) or not (
                {str(item.get(k) or "") for k in ("path","file_path","package_path")} & excluded_members
                or item.get("source_id") in excluded_sources
                or set(item.get("source_ids") or []) & excluded_sources)]
    return value
