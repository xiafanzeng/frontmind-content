#!/usr/bin/env python3
"""Normalize multi-question research exports into exact-question period slices.

The raw monitoring and citation workbooks remain workspace data.  This module
builds the portable, execution-facing research library: the same-period
intersection is sliced by exact question, while the index retains the union of
all complete periods.  Monitoring answers are research context, never factual
evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Sequence
from urllib.parse import urlsplit

try:  # package import
    from . import research_ingestion as ingestion
    from .question_semantics import classify_question, normalize_question_key
except ImportError:  # direct script/import compatibility
    import research_ingestion as ingestion  # type: ignore
    from question_semantics import classify_question, normalize_question_key  # type: ignore


INDEX_SCHEMA_VERSION = "1.1.0"
LEGACY_INDEX_SCHEMA_VERSION = "1.0.0"
INDEX_ARTIFACT_TYPE = "frontmind_question_research_index"
INDEX_USAGE_POLICY = "execution_context_only_not_factual_evidence"
MONITORING_SCHEMA_VERSION = "1.0.0"
MONITORING_ARTIFACT_TYPE = "frontmind_question_monitoring_slice"
CITATION_SCHEMA_VERSION = "1.0.0"
CITATION_ARTIFACT_TYPE = "frontmind_question_citation_slice"

QUESTION_RESEARCH_ROOT_MEMBER = "research/question_research"
QUESTION_RESEARCH_INDEX_MEMBER = f"{QUESTION_RESEARCH_ROOT_MEMBER}/index.json"
WORKSPACE_DATA_DIR = "workspace_data"
WORKSPACE_PERIODS_DIR = f"{WORKSPACE_DATA_DIR}/periods"
PERIOD_COMPLETE_MARKER = ".frontmind-period-complete.json"
LIFECYCLE_MARKER = "state.json"
LEGACY_LIFECYCLE_MARKER = "question_research_lifecycle.json"
ACTIVE_QUESTIONS_DIR = "active_questions"

MONITORING_SLICE_NAME = "monitoring_observations.json"
CITATION_SLICE_NAME = "citation_observations.json"

_QUESTION_PATH = re.compile(r"^q[0-9]{6}$")
_PERIOD_PATH = re.compile(r"^p[0-9]{6}$")
_ANSWER_GROUP = re.compile(r"^(?:答案|answer)(\d+)(.*)$", re.IGNORECASE)

_DETAIL_ALIASES = {
    "question": ingestion.QUESTION_ALIASES,
    "url": ingestion.URL_ALIASES,
    "date": ingestion.DATE_ALIASES,
    "model": {"模型", "平台模型", "model", "provider", "模型名称"},
    "title": {"内容标题", "标题", "文章标题", "title", "contenttitle"},
    "media_name": {"媒体名称", "媒体", "发布者", "publisher", "medianame"},
    "media_domain": {"媒体url", "媒体域名", "域名", "domain", "mediaurl"},
}


class QuestionResearchError(ValueError):
    """The research library cannot be built or selected safely."""


@dataclass(frozen=True)
class PeriodIngestResult:
    index: dict[str, Any]
    actions: tuple[dict[str, Any], ...]
    period_ids: tuple[str, ...]
    question_uids: tuple[str, ...]


@dataclass(frozen=True)
class QuestionResearchSelection:
    question: dict[str, Any]
    slices: tuple[dict[str, Any], ...]
    selection_mode: str
    history_change: dict[str, Any]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _PairSpec:
    monitoring_path: Path
    source_path: Path
    marker_path: Path | None
    workspace_period_label: str | None
    declared_period_label: str | None
    ingested_at: str
    requested_period_id: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _normal(value: Any) -> str:
    return ingestion.normal(value)


def _key(value: Any) -> str:
    return normalize_question_key(value)


def _strict_json(path: Path) -> Any:
    try:
        return ingestion._strict_json_bytes(path.read_bytes(), str(path))
    except ingestion.ResearchIngestionError as exc:
        raise QuestionResearchError(str(exc)) from exc


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _pair_fingerprint(monitoring: Path, source: Path) -> str:
    digest = hashlib.sha256()
    digest.update(b"frontmind-question-research-period-v1\0monitoring\0")
    digest.update(monitoring.read_bytes())
    digest.update(b"\0citation\0")
    digest.update(source.read_bytes())
    return f"sha256:{digest.hexdigest()}"


def _next_id(values: Iterable[str], prefix: str) -> str:
    numbers = [int(value[1:]) for value in values if re.fullmatch(fr"{prefix}[0-9]{{6}}", value)]
    return f"{prefix}{(max(numbers, default=0) + 1):06d}"


def _slice_member(question_uid: str, period_id: str, filename: str) -> str:
    return f"{QUESTION_RESEARCH_ROOT_MEMBER}/questions/{question_uid}/periods/{period_id}/{filename}"


def _member_path(root: Path, member: str) -> Path:
    if not ingestion.safe_relative(member) or not member.startswith(QUESTION_RESEARCH_ROOT_MEMBER + "/"):
        raise QuestionResearchError(f"unsafe question-research member: {member!r}")
    relative = PurePosixPath(member).relative_to(QUESTION_RESEARCH_ROOT_MEMBER)
    destination = root.resolve().joinpath(*relative.parts)
    if root.resolve() not in destination.parents and destination != root.resolve():
        raise QuestionResearchError(f"question-research member escapes root: {member}")
    return destination


def _field_by_alias(row: dict[str, Any], aliases: set[str]) -> Any:
    choices = {ingestion.field_key(value) for value in aliases}
    for name, value in row.items():
        if value not in (None, "") and ingestion.field_key(name) in choices:
            return value
    return None


def _answer_groups(row: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[int, dict[str, Any]] = {}
    for name, value in row.items():
        match = _ANSWER_GROUP.match(ingestion.field_key(name))
        if not match:
            continue
        number = int(match.group(1))
        role = match.group(2)
        groups.setdefault(number, {})[role] = value

    answers: list[dict[str, Any]] = []
    for number in sorted(groups):
        group = groups[number]
        content = next((value for role, value in group.items() if role in {"内容", "content"} and _normal(value)), None)
        if content is None:
            continue
        answers.append({
            "slot": number,
            "answer_text": _normal(content),
            "region": _normal(next((value for role, value in group.items() if role in {"区域", "region"}), None)) or None,
            "exported_rank": _normal(next((value for role, value in group.items() if role in {"排名", "rank", "ranking"}), None)) or None,
            "monitor_keyword_rank": _normal(next((value for role, value in group.items() if role in {"监控词排名", "keywordrank", "monitorkeywordrank"}), None)) or None,
        })
    if answers:
        return answers

    return [
        {
            "slot": index,
            "answer_text": _normal(value),
            "region": None,
            "exported_rank": None,
            "monitor_keyword_rank": None,
        }
        for index, value in enumerate(ingestion._answer_values(row), 1)
        if _normal(value)
    ]


def _date_first(value: Any) -> str | None:
    values = ingestion._date_values(value)
    return values[0] if values else None


def _monitoring_rows(
    path: Path,
    canonical_brand: str = "",
    aliases: Sequence[str] = (),
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    inventory = ingestion._monitoring_inventory(path, canonical_brand, aliases)
    suffix = path.suffix.casefold()
    by_question: dict[str, dict[str, Any]] = {}

    if suffix == ".json":
        raw = _strict_json(path)
        if isinstance(raw, dict) and isinstance(raw.get("answers"), list) and _normal(raw.get("question")):
            question = _normal(raw["question"])
            key = _key(question)
            records = []
            for item in raw["answers"]:
                if not isinstance(item, dict) or not _normal(item.get("answer_text")):
                    continue
                records.append({
                    "platform": _normal(item.get("platform")) or "unspecified",
                    "model": _normal(item.get("model")) or None,
                    "sampled_at": _date_first(item.get("sampled_at")),
                    "answer_text": _normal(item.get("answer_text")),
                    # The overall monitoring export is an answer-landscape
                    # input, not the citation source of record.  In particular,
                    # do not carry screenshot links or arbitrary embedded URLs
                    # into the portable Pack; citation observations are rebuilt
                    # only from the paired source workbook.
                    "citations": [],
                    "region": _normal(item.get("region")) or None,
                    "exported_rank": _normal(item.get("exported_rank")) or None,
                    "monitor_keyword_rank": _normal(item.get("monitor_keyword_rank")) or None,
                    "brand": _normal(item.get("brand") or item.get("brand_name")) or None,
                    "question_keyword": _normal(item.get("question_keyword")) or None,
                })
            by_question[key] = {"texts": [question], "answers": records}
            return by_question, inventory
        raw_rows = raw if isinstance(raw, list) else raw.get("rows") if isinstance(raw, dict) else []
        rows = [("unspecified", item) for item in raw_rows if isinstance(item, dict)]
    elif suffix == ".xlsx":
        rows = ingestion._rows_from_xlsx(path)
    elif suffix == ".csv":
        rows = ingestion._rows_from_csv(path)
    else:  # guarded by research-ingestion validator
        raise QuestionResearchError(f"unsupported monitoring export: {path.name}")

    for sheet, row in rows:
        question = _normal(_field_by_alias(row, ingestion.QUESTION_ALIASES))
        key = _key(question)
        if not key:
            continue
        grouped = _answer_groups(row)
        if not grouped:
            continue
        target = by_question.setdefault(key, {"texts": [], "answers": []})
        if question not in target["texts"]:
            target["texts"].append(question)
        platform = _normal(_field_by_alias(row, ingestion.PLATFORM_ALIASES)) or _normal(sheet) or "unspecified"
        sampled_at = _date_first(_field_by_alias(row, ingestion.DATE_ALIASES))
        brand = _normal(_field_by_alias(row, ingestion.BRAND_ALIASES)) or None
        question_keyword = _normal(next((value for name, value in row.items() if ingestion.field_key(name) in {"问题核心词", "questionkeyword", "keyword"}), None)) or None
        for item in grouped:
            target["answers"].append({
                "platform": platform,
                "model": None,
                "sampled_at": sampled_at,
                "answer_text": item["answer_text"],
                "citations": [],
                "region": item["region"],
                "exported_rank": item["exported_rank"],
                "monitor_keyword_rank": item["monitor_keyword_rank"],
                "brand": brand,
                "question_keyword": question_keyword,
            })
    return by_question, inventory


def _detail_columns(sheet: Any) -> tuple[dict[str, int], int]:
    aliases = {name: {ingestion.field_key(item) for item in values} for name, values in _DETAIL_ALIASES.items()}
    for row_number in (1, 2):
        values = next(sheet.iter_rows(min_row=row_number, max_row=row_number, values_only=True), ())
        normalized = [ingestion.field_key(value) for value in values]
        columns: dict[str, int] = {}
        for name, choices in aliases.items():
            for index, value in enumerate(normalized):
                if value in choices:
                    columns[name] = index
                    break
        if "question" in columns and "url" in columns:
            return columns, row_number + 1
    return {}, 2


def _citation_rows(path: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    inventory = ingestion._source_inventory(path)
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover
        raise QuestionResearchError("openpyxl is required to read citation workbooks") from exc
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        candidates: list[tuple[Any, dict[str, int], int]] = []
        named_aliases = {ingestion.field_key(item) for item in ingestion.DETAIL_SHEET_ALIASES}
        for sheet in workbook.worksheets:
            columns, start = _detail_columns(sheet)
            if "question" in columns and "url" in columns:
                candidates.append((sheet, columns, start))
        named = [item for item in candidates if ingestion.field_key(item[0].title) in named_aliases]
        selected = named or candidates
        if len(selected) != 1:
            raise QuestionResearchError("citation workbook has no unique detail sheet with question and HTTP(S) URL")
        sheet, columns, start = selected[0]
        by_question: dict[str, dict[str, Any]] = {}
        for values in sheet.iter_rows(min_row=start, values_only=True):
            def cell(name: str) -> Any:
                position = columns.get(name)
                return values[position] if position is not None and position < len(values) else None

            question = _normal(cell("question"))
            key = _key(question)
            url = ingestion._http_url(cell("url"))
            if not key or not url:
                continue
            target = by_question.setdefault(key, {"texts": [], "details": []})
            if question not in target["texts"]:
                target["texts"].append(question)
            domain = _normal(cell("media_domain"))
            if not domain:
                domain = (urlsplit(url).hostname or "").casefold().removeprefix("www.")
            observed_values = ingestion._date_values(cell("date"))
            target["details"].append({
                "observed_at": _normal(cell("date")) or None,
                "observed_date": observed_values[0] if observed_values else None,
                "model": _normal(cell("model")) or None,
                "content_title": _normal(cell("title")) or None,
                "canonical_url": url,
                "media_name": _normal(cell("media_name")) or None,
                "media_domain": domain or None,
            })
        return by_question, inventory
    finally:
        workbook.close()


def _rank_citations(details: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    first_order: dict[str, int] = {}
    for index, item in enumerate(details):
        url = item["canonical_url"]
        grouped.setdefault(url, []).append(item)
        first_order.setdefault(url, index)
    total = len(details) or 1
    ranked: list[dict[str, Any]] = []
    for url, rows in grouped.items():
        dates = [item["observed_date"] for item in rows if item.get("observed_date")]
        exemplar = rows[0]
        ranked.append({
            "content_title": exemplar.get("content_title"),
            "canonical_url": url,
            "media_name": exemplar.get("media_name"),
            "media_domain": exemplar.get("media_domain"),
            "citation_date_from": min(dates) if dates else None,
            "citation_date_to": max(dates) if dates else None,
            "citation_count": len(rows),
            "citation_share": round(len(rows) / total, 12),
            "detail_ids": [item["detail_id"] for item in rows],
            "_first_order": first_order[url],
        })
    ranked.sort(key=lambda item: (-item["citation_count"], item["_first_order"], item["canonical_url"]))
    for rank, item in enumerate(ranked, 1):
        item["raw_rank"] = rank
        item.pop("_first_order", None)
    return ranked


def _project_overlays(project_questions: Any) -> dict[str, dict[str, Any]]:
    values = project_questions.get("questions", []) if isinstance(project_questions, dict) else project_questions or []
    result: dict[str, dict[str, Any]] = {}
    for order, item in enumerate(values, 1):
        if isinstance(item, str):
            text = _normal(item)
            payload: dict[str, Any] = {}
        elif isinstance(item, dict):
            text = _normal(item.get("question_text") or item.get("question") or item.get("text"))
            payload = item
        else:
            continue
        key = _key(text)
        if not key:
            continue
        result.setdefault(key, {
            "question_text": text,
            "question_id": _normal(payload.get("question_id")) or None,
            "source_order": int(payload.get("source_order") or order),
            "primary_intent_tag": _normal(payload.get("primary_intent_tag")) or None,
            "category": _normal(payload.get("category")) or None,
            "entry_category": _normal(payload.get("entry_category") or payload.get("suggested_entry_category")) or None,
        })
    return result


def _classification(text: str, overlay: dict[str, Any] | None) -> dict[str, Any]:
    inferred = classify_question(text)
    return {
        "primary_intent_tag": (overlay or {}).get("primary_intent_tag") or inferred["primary_intent_tag"],
        "category": (overlay or {}).get("category") or inferred["category"],
        "entry_category": (overlay or {}).get("entry_category") or inferred["suggested_entry_category"],
        "classification_rule_id": inferred["classification_rule_id"],
    }


def _period_sort_value(period: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(period.get("observed_to") or ""),
        str(period.get("ingested_at") or ""),
        str(period.get("period_id") or ""),
    )


def _delta(current: Any, previous: Any) -> float | int | None:
    if isinstance(current, bool) or isinstance(previous, bool):
        return None
    if not isinstance(current, (int, float)) or not isinstance(previous, (int, float)):
        return None
    value = current - previous
    if isinstance(current, int) and isinstance(previous, int):
        return int(value)
    return round(float(value), 6)


def _history_for(question_uid: str, slices: list[dict[str, Any]], periods: dict[str, dict[str, Any]]) -> dict[str, Any]:
    relevant = [item for item in slices if item.get("question_uid") == question_uid]
    relevant.sort(key=lambda item: _period_sort_value(periods[item["period_id"]]))
    latest = relevant[-1]
    previous = relevant[-2] if len(relevant) > 1 else None
    metric_names = (
        "answer_observation_count", "platform_count", "citation_detail_count",
        "unique_citation_content_count", "brand_mention_rate", "top1_rate",
        "top3_rate", "average_rank", "citation_domain_count",
        "citation_domain_concentration_top3",
    )
    deltas = {
        f"{name}_delta": _delta(latest.get(name), previous.get(name) if previous else None)
        for name in metric_names
    }
    return {
        "period_count": len(relevant),
        "baseline_type": "change" if previous else "snapshot",
        "latest_period_id": latest["period_id"],
        "previous_period_id": previous["period_id"] if previous else None,
        "latest_observed_from": periods[latest["period_id"]].get("observed_from"),
        "latest_observed_to": periods[latest["period_id"]].get("observed_to"),
        "deltas": deltas,
    }


def _monitoring_slice(
    question_uid: str,
    question_text: str,
    question_key: str,
    period_id: str,
    records: dict[str, Any],
    inventory_item: dict[str, Any],
    observed_from: str | None,
    observed_to: str | None,
) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    for number, item in enumerate(records["answers"], 1):
        answers.append({
            "answer_id": f"a{number:06d}",
            "platform": item.get("platform") or "unspecified",
            "model": item.get("model"),
            "sampled_at": item.get("sampled_at"),
            "answer_text": item["answer_text"],
            "citations": [citation for citation in item.get("citations", []) if isinstance(citation, dict)],
            "region": item.get("region"),
            "exported_rank": item.get("exported_rank"),
            "monitor_keyword_rank": item.get("monitor_keyword_rank"),
            "brand": item.get("brand"),
            "question_keyword": item.get("question_keyword"),
        })
    return {
        "schema_version": MONITORING_SCHEMA_VERSION,
        "artifact_type": MONITORING_ARTIFACT_TYPE,
        "usage_policy": INDEX_USAGE_POLICY,
        "question": question_text,
        "question_key": question_key,
        "question_uid": question_uid,
        "period_id": period_id,
        "observed_from": observed_from,
        "observed_to": observed_to,
        "platforms": sorted({item["platform"] for item in answers}),
        "answer_count": len(answers),
        "answers": answers,
        "research_metrics": _clone(inventory_item.get("research_metrics") or {}),
    }


def _citation_slice(
    question_uid: str,
    question_text: str,
    question_key: str,
    period_id: str,
    records: dict[str, Any],
    observed_from: str | None,
    observed_to: str | None,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    for number, item in enumerate(records["details"], 1):
        details.append({"detail_id": f"d{number:06d}", **item})
    return {
        "schema_version": CITATION_SCHEMA_VERSION,
        "artifact_type": CITATION_ARTIFACT_TYPE,
        "usage_policy": INDEX_USAGE_POLICY,
        "question": question_text,
        "question_key": question_key,
        "question_uid": question_uid,
        "period_id": period_id,
        "observed_from": observed_from,
        "observed_to": observed_to,
        "detail_count": len(details),
        "unique_content_count": len({item["canonical_url"] for item in details}),
        "details": details,
        "cited_content_pool": _rank_citations(details),
    }


def empty_question_research_index() -> dict[str, Any]:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "artifact_type": INDEX_ARTIFACT_TYPE,
        "usage_policy": INDEX_USAGE_POLICY,
        "index_revision": 0,
        "updated_at": None,
        "periods": [],
        "questions": [],
        "slices": [],
        "incomplete_observations": [],
        "retired_question_markers": [],
        "warnings": [],
    }


def upgrade_question_research_index(index: Any) -> Any:
    """Upgrade a v1.0 index without turning one-sided rows into candidates.

    Version 1.0 already retained each period's monitoring-only and
    citation-only normalized keys, but it had no display-only record for
    them. When raw overall tables are unavailable, the key is a safe fallback
    label because these records never receive a qUID or formal eligibility.
    """

    if not isinstance(index, dict) or index.get("schema_version") != LEGACY_INDEX_SCHEMA_VERSION:
        return index
    upgraded = _clone(index)
    if "incomplete_observations" not in upgraded:
        observations: list[dict[str, Any]] = []
        fallback_count = 0
        for period in upgraded.get("periods", []):
            if not isinstance(period, dict) or not isinstance(period.get("period_id"), str):
                continue
            for availability, field in (
                ("monitoring_only", "monitoring_only_question_keys"),
                ("citation_only", "citation_only_question_keys"),
            ):
                for key in period.get(field, []) or []:
                    if not isinstance(key, str) or not key:
                        continue
                    observations.append({
                        "period_id": period["period_id"],
                        "question_key": key,
                        "question_text": key,
                        "availability": availability,
                    })
                    fallback_count += 1
        upgraded["incomplete_observations"] = observations
        warnings = [str(item) for item in upgraded.get("warnings", []) if str(item).strip()]
        warnings.append("question_research_index_upgraded_from_1.0.0")
        if fallback_count:
            warnings.append(
                "legacy_incomplete_question_text_unavailable: normalized keys are used only as display labels"
            )
        upgraded["warnings"] = list(dict.fromkeys(warnings))
    upgraded["schema_version"] = INDEX_SCHEMA_VERSION
    return upgraded


def validate_question_research_index(
    index: Any,
    available_members: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(index, dict):
        return ["question research index must be an object"], warnings
    if index.get("schema_version") != INDEX_SCHEMA_VERSION:
        errors.append(f"schema_version must equal {INDEX_SCHEMA_VERSION}")
    if index.get("artifact_type") != INDEX_ARTIFACT_TYPE:
        errors.append(f"artifact_type must equal {INDEX_ARTIFACT_TYPE}")
    if index.get("usage_policy") != INDEX_USAGE_POLICY:
        errors.append(f"usage_policy must equal {INDEX_USAGE_POLICY}")
    if not isinstance(index.get("index_revision"), int) or index.get("index_revision", -1) < 0:
        errors.append("index_revision must be a non-negative integer")

    periods = index.get("periods")
    questions = index.get("questions")
    slices = index.get("slices")
    incomplete = index.get("incomplete_observations")
    markers = index.get("retired_question_markers")
    if (
        not isinstance(periods, list)
        or not isinstance(questions, list)
        or not isinstance(slices, list)
        or not isinstance(incomplete, list)
        or not isinstance(markers, list)
    ):
        errors.append(
            "periods, questions, slices, incomplete_observations and "
            "retired_question_markers must be arrays"
        )
        return errors, warnings

    period_by_id: dict[str, dict[str, Any]] = {}
    for position, period in enumerate(periods):
        label = f"periods[{position}]"
        if not isinstance(period, dict):
            errors.append(f"{label} must be an object")
            continue
        period_id = period.get("period_id")
        if not isinstance(period_id, str) or not _PERIOD_PATH.fullmatch(period_id):
            errors.append(f"{label}.period_id must match pNNNNNN")
        elif period_id in period_by_id:
            errors.append(f"duplicate period_id: {period_id}")
        else:
            period_by_id[period_id] = period
        for field in ("monitoring_question_count", "citation_question_count", "complete_question_count"):
            if not isinstance(period.get(field), int) or period.get(field, -1) < 0:
                errors.append(f"{label}.{field} must be a non-negative integer")
        if period.get("complete_question_count", 0) < 1:
            errors.append(f"{label}.complete_question_count must be at least one")

    incomplete_keys: set[tuple[str, str, str]] = set()
    incomplete_by_period: dict[str, dict[str, set[str]]] = {}
    for position, item in enumerate(incomplete):
        label = f"incomplete_observations[{position}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        period_id = item.get("period_id")
        key = item.get("question_key")
        availability = item.get("availability")
        text = item.get("question_text")
        if period_id not in period_by_id:
            errors.append(f"{label} references unknown period_id: {period_id}")
        if not isinstance(key, str) or not key or _key(key) != key:
            errors.append(f"{label}.question_key is not an exact normalized key")
        if availability not in {"monitoring_only", "citation_only"}:
            errors.append(f"{label}.availability is invalid")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{label}.question_text must be non-empty")
        elif isinstance(key, str) and _key(text) != key:
            errors.append(f"{label}.question_text does not normalize to question_key")
        identity = (str(period_id), str(key), str(availability))
        if identity in incomplete_keys:
            errors.append(f"duplicate incomplete observation: {identity}")
        incomplete_keys.add(identity)
        if period_id in period_by_id and isinstance(key, str) and availability in {"monitoring_only", "citation_only"}:
            incomplete_by_period.setdefault(period_id, {"monitoring_only": set(), "citation_only": set()})[
                availability
            ].add(key)

    for period_id, period in period_by_id.items():
        actual = incomplete_by_period.get(period_id, {"monitoring_only": set(), "citation_only": set()})
        for availability, field in (
            ("monitoring_only", "monitoring_only_question_keys"),
            ("citation_only", "citation_only_question_keys"),
        ):
            declared = set(period.get(field) or [])
            if actual[availability] != declared:
                errors.append(
                    f"period {period_id} {field} does not match incomplete_observations"
                )

    question_by_uid: dict[str, dict[str, Any]] = {}
    question_by_key: dict[str, dict[str, Any]] = {}
    marker_keys: set[str] = set()
    for position, marker in enumerate(markers):
        if not isinstance(marker, dict) or not _key(marker.get("question_key")):
            errors.append(f"retired_question_markers[{position}] is invalid")
            continue
        if marker.get("question_uid") is not None and (
            not isinstance(marker.get("question_uid"), str) or not _QUESTION_PATH.fullmatch(marker["question_uid"])
        ):
            errors.append(f"retired_question_markers[{position}].question_uid is invalid")
        marker_key = marker["question_key"]
        if marker_key in marker_keys:
            errors.append(f"duplicate retired marker: {marker_key}")
        marker_keys.add(marker_key)
    for position, question in enumerate(questions):
        label = f"questions[{position}]"
        if not isinstance(question, dict):
            errors.append(f"{label} must be an object")
            continue
        uid = question.get("question_uid")
        key = question.get("question_key")
        if not isinstance(uid, str) or not _QUESTION_PATH.fullmatch(uid):
            errors.append(f"{label}.question_uid must match qNNNNNN")
        elif uid in question_by_uid:
            errors.append(f"duplicate question_uid: {uid}")
        else:
            question_by_uid[uid] = question
        if not isinstance(key, str) or not key or _key(key) != key:
            errors.append(f"{label}.question_key is not an exact normalized key")
        elif key in question_by_key:
            errors.append(f"duplicate question_key: {key}")
        else:
            question_by_key[key] = question
        text = question.get("question_text")
        if not isinstance(text, str) or not text.strip() or (isinstance(key, str) and _key(text) != key):
            errors.append(f"{label}.question_text does not normalize to question_key")
        state = (question.get("lifecycle") or {}).get("state")
        if state not in {"active", "retired"}:
            errors.append(f"{label}.lifecycle.state must be active or retired")
        if state == "retired" and key not in marker_keys:
            errors.append(f"{label} is retired without a matching marker")
        if state == "active" and question.get("formal_question_eligible") is not True:
            errors.append(f"{label} active question must be formal_question_eligible")
        if state == "retired" and question.get("formal_question_eligible") is not False:
            errors.append(f"{label} retired question cannot be formal_question_eligible")

    slice_ids: set[str] = set()
    periods_by_question: dict[str, list[str]] = {}
    for position, item in enumerate(slices):
        label = f"slices[{position}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        slice_id = item.get("slice_id")
        uid = item.get("question_uid")
        key = item.get("question_key")
        period_id = item.get("period_id")
        if slice_id != f"{uid}-{period_id}":
            errors.append(f"{label}.slice_id does not match question_uid-period_id")
        elif slice_id in slice_ids:
            errors.append(f"duplicate slice_id: {slice_id}")
        slice_ids.add(str(slice_id))
        if uid not in question_by_uid or question_by_uid.get(uid, {}).get("question_key") != key:
            errors.append(f"{label} references an unknown or mismatched question")
        if period_id not in period_by_id:
            errors.append(f"{label} references unknown period_id: {period_id}")
        periods_by_question.setdefault(str(uid), []).append(str(period_id))
        for role in ("monitoring_path", "citation_path"):
            member = item.get(role)
            if not isinstance(member, str) or not ingestion.safe_relative(member) or not member.startswith(QUESTION_RESEARCH_ROOT_MEMBER + "/"):
                errors.append(f"{label}.{role} is not a safe canonical member")
            elif available_members is not None and member not in available_members:
                errors.append(f"{label}.{role} is missing: {member}")
        for field in ("answer_observation_count", "platform_count", "citation_detail_count", "unique_citation_content_count"):
            if not isinstance(item.get(field), int) or item.get(field, -1) < 0:
                errors.append(f"{label}.{field} must be a non-negative integer")

    complete_by_period: dict[str, set[str]] = {period_id: set() for period_id in period_by_id}
    for item in slices:
        if not isinstance(item, dict):
            continue
        period_id = item.get("period_id")
        key = item.get("question_key")
        if period_id in complete_by_period and isinstance(key, str):
            complete_by_period[period_id].add(key)
    for period_id, period in period_by_id.items():
        complete_keys = complete_by_period[period_id]
        monitoring_only = set(period.get("monitoring_only_question_keys") or [])
        citation_only = set(period.get("citation_only_question_keys") or [])
        if monitoring_only & citation_only:
            errors.append(f"period {period_id} has keys marked monitoring-only and citation-only")
        if complete_keys & monitoring_only:
            errors.append(f"period {period_id} complete keys overlap monitoring-only keys")
        if complete_keys & citation_only:
            errors.append(f"period {period_id} complete keys overlap citation-only keys")
        expected_counts = {
            "complete_question_count": len(complete_keys),
            "monitoring_question_count": len(complete_keys) + len(monitoring_only),
            "citation_question_count": len(complete_keys) + len(citation_only),
        }
        for field, expected in expected_counts.items():
            if period.get(field) != expected:
                errors.append(
                    f"period {period_id} {field}={period.get(field)!r} does not match "
                    f"{expected} indexed questions"
                )

    for uid, question in question_by_uid.items():
        actual = sorted(set(periods_by_question.get(uid, [])), key=lambda value: _period_sort_value(period_by_id[value]))
        declared = question.get("complete_period_ids")
        if declared != actual:
            errors.append(f"question {uid} complete_period_ids do not match slices")
        if not actual:
            errors.append(f"question {uid} has no complete period slice")
        else:
            if question.get("first_complete_period_id") != actual[0]:
                errors.append(f"question {uid} first_complete_period_id is stale")
            if question.get("latest_complete_period_id") != actual[-1]:
                errors.append(f"question {uid} latest_complete_period_id is stale")
    return errors, warnings


def load_question_research_index(path: Path) -> dict[str, Any]:
    candidate = Path(path)
    if candidate.is_file() and candidate.suffix.casefold() == ".zip":
        reader = ingestion._ZipPackageReader(candidate)
        try:
            names = set(reader.names())
            if QUESTION_RESEARCH_INDEX_MEMBER not in names:
                return empty_question_research_index()
            try:
                payload = ingestion._strict_json_bytes(reader.read(QUESTION_RESEARCH_INDEX_MEMBER), QUESTION_RESEARCH_INDEX_MEMBER)
            except ingestion.ResearchIngestionError as exc:
                raise QuestionResearchError(str(exc)) from exc
            payload = upgrade_question_research_index(payload)
            errors, _warnings = validate_question_research_index(payload, names)
            if errors:
                raise QuestionResearchError("invalid question research index: " + "; ".join(errors))
            return payload
        finally:
            reader.close()
    if candidate.is_dir():
        direct = candidate / "index.json"
        canonical = candidate / QUESTION_RESEARCH_INDEX_MEMBER
        if canonical.is_file():
            reader = ingestion._DirectoryPackageReader(candidate)
            try:
                names = set(reader.names())
                payload = ingestion._strict_json_bytes(reader.read(QUESTION_RESEARCH_INDEX_MEMBER), QUESTION_RESEARCH_INDEX_MEMBER)
                payload = upgrade_question_research_index(payload)
                errors, _warnings = validate_question_research_index(payload, names)
                if errors:
                    raise QuestionResearchError("invalid question research index: " + "; ".join(errors))
                return payload
            except ingestion.ResearchIngestionError as exc:
                raise QuestionResearchError(str(exc)) from exc
            finally:
                reader.close()
        if direct.is_file():
            if candidate.is_symlink() or any(path.is_symlink() for path in candidate.rglob("*")):
                raise QuestionResearchError(f"question research directory contains a symlink: {candidate}")
            payload = _strict_json(direct)
            payload = upgrade_question_research_index(payload)
            names = {
                f"{QUESTION_RESEARCH_ROOT_MEMBER}/{path.relative_to(candidate).as_posix()}"
                for path in candidate.rglob("*") if path.is_file()
            }
            errors, _warnings = validate_question_research_index(payload, names)
            if errors:
                raise QuestionResearchError("invalid question research index: " + "; ".join(errors))
            return payload
        candidate = canonical
    if not candidate.is_file():
        return empty_question_research_index()
    payload = _strict_json(candidate)
    payload = upgrade_question_research_index(payload)
    errors, _warnings = validate_question_research_index(payload)
    if errors:
        raise QuestionResearchError("invalid question research index: " + "; ".join(errors))
    return payload


def write_question_research_index(path: Path, index: dict[str, Any]) -> None:
    errors, _warnings = validate_question_research_index(index)
    if errors:
        raise QuestionResearchError("refusing to write invalid question research index: " + "; ".join(errors))
    _atomic_json(path, index)


def _read_period_marker(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = _strict_json(path)
    if not isinstance(payload, dict):
        raise QuestionResearchError(f"period marker must be an object: {path}")
    if payload.get("schema_version") != "1.0.0" or payload.get("artifact_type") != "frontmind_question_research_period_marker":
        raise QuestionResearchError(f"unsupported question-research period marker: {path}")
    period_id = payload.get("period_id")
    fingerprint = payload.get("pair_fingerprint")
    if not isinstance(period_id, str) or not _PERIOD_PATH.fullmatch(period_id):
        raise QuestionResearchError(f"period marker has invalid period_id: {path}")
    if not isinstance(fingerprint, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", fingerprint):
        raise QuestionResearchError(f"period marker has invalid pair_fingerprint: {path}")
    for role in ("monitoring_file", "source_file"):
        value = payload.get(role)
        if not isinstance(value, str) or PurePosixPath(value).name != value or not value:
            raise QuestionResearchError(f"period marker has unsafe {role}: {path}")
    return payload


def _marker_payload(spec: _PairSpec, period_id: str, fingerprint: str, completed_at: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "artifact_type": "frontmind_question_research_period_marker",
        "period_id": period_id,
        "pair_fingerprint": fingerprint,
        "monitoring_file": spec.monitoring_path.name,
        "source_file": spec.source_path.name,
        "workspace_period_label": spec.workspace_period_label,
        "completed_at": completed_at,
    }


def _lifecycle_marker_path(workspace_data: Path) -> Path:
    return Path(workspace_data) / LIFECYCLE_MARKER


def load_lifecycle_markers(workspace_data: Path) -> list[dict[str, Any]]:
    path = _lifecycle_marker_path(Path(workspace_data))
    if not path.is_file():
        legacy = Path(workspace_data) / LEGACY_LIFECYCLE_MARKER
        if legacy.is_file():
            path = legacy
    if not path.is_file():
        return []
    payload = _strict_json(path)
    if not isinstance(payload, dict) or payload.get("artifact_type") != "frontmind_question_research_lifecycle_markers":
        raise QuestionResearchError(f"invalid lifecycle marker file: {path}")
    markers = payload.get("retired_question_markers")
    if not isinstance(markers, list):
        raise QuestionResearchError(f"lifecycle marker file has no retired_question_markers array: {path}")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in markers:
        if not isinstance(item, dict):
            raise QuestionResearchError(f"lifecycle marker contains a non-object entry: {path}")
        key = _key(item.get("question_key"))
        if not key or key != item.get("question_key") or key in seen:
            raise QuestionResearchError(f"lifecycle marker contains an invalid or duplicate question_key: {path}")
        seen.add(key)
        result.append({
            "question_key": key,
            "question_uid": item.get("question_uid") if isinstance(item.get("question_uid"), str) and _QUESTION_PATH.fullmatch(item["question_uid"]) else None,
            "retired_at": _normal(item.get("retired_at")) or None,
            "reason": _normal(item.get("reason")) or "user_retired",
        })
    return result


def write_lifecycle_markers(workspace_data: Path, index: dict[str, Any]) -> None:
    markers = _clone(index.get("retired_question_markers") or [])
    state_path = _lifecycle_marker_path(Path(workspace_data))
    retained: dict[str, Any] = {}
    if state_path.is_file() and not state_path.is_symlink():
        existing = _strict_json(state_path)
        portable_zip_path = existing.get("portable_zip_path") if isinstance(existing, dict) else None
        if isinstance(portable_zip_path, str) and portable_zip_path.strip():
            retained["portable_zip_path"] = portable_zip_path
    _atomic_json(state_path, {
        "schema_version": "1.0.0",
        "artifact_type": "frontmind_question_research_lifecycle_markers",
        "retired_question_markers": markers,
        **retained,
    })
    legacy = Path(workspace_data) / LEGACY_LIFECYCLE_MARKER
    if legacy.is_file() and not legacy.is_symlink():
        legacy.unlink()


def _active_questions_path(workspace_data: Path) -> Path:
    return Path(workspace_data) / ACTIVE_QUESTIONS_DIR


def load_active_question_markers(workspace_data: Path) -> dict[str, dict[str, Any]]:
    directory = _active_questions_path(Path(workspace_data))
    if not directory.exists():
        return {}
    if directory.is_symlink() or not directory.is_dir():
        raise QuestionResearchError(f"active question marker path must be a regular directory: {directory}")
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.iterdir()):
        if path.is_symlink():
            raise QuestionResearchError(f"active question marker cannot be a symlink: {path}")
        if not path.is_file() or path.suffix.casefold() != ".json":
            continue
        payload = _strict_json(path)
        if not isinstance(payload, dict) or payload.get("artifact_type") != "frontmind_active_question_marker":
            raise QuestionResearchError(f"invalid active question marker: {path}")
        uid = payload.get("question_uid")
        key = payload.get("question_key")
        if not isinstance(uid, str) or not _QUESTION_PATH.fullmatch(uid) or path.name != f"{uid}.json":
            raise QuestionResearchError(f"active question marker filename/uid mismatch: {path}")
        if not isinstance(key, str) or not key or _key(key) != key:
            raise QuestionResearchError(f"active question marker has invalid question_key: {path}")
        if key in result:
            raise QuestionResearchError(f"duplicate active question marker key: {key}")
        result[key] = payload
    return result


def write_active_question_markers(workspace_data: Path, index: dict[str, Any]) -> None:
    directory = _active_questions_path(Path(workspace_data))
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise QuestionResearchError(f"active question marker path cannot be a symlink: {directory}")
    expected: set[str] = set()
    for question in index.get("questions", []):
        if question.get("lifecycle", {}).get("state") != "active" or question.get("formal_question_eligible") is not True:
            continue
        path = directory / f"{question['question_uid']}.json"
        expected.add(path.name)
        _atomic_json(path, {
            "schema_version": "1.0.0",
            "artifact_type": "frontmind_active_question_marker",
            "question_uid": question["question_uid"],
            "question_key": question["question_key"],
            "question_text": question["question_text"],
            "source_order": question["source_order"],
        })
    for path in directory.glob("*.json"):
        if path.name not in expected:
            path.unlink()


def _retire_deleted_active_markers(
    index: dict[str, Any],
    active_markers: dict[str, dict[str, Any]],
    *,
    marker_directory_existed: bool,
    changed_at: str,
) -> list[dict[str, Any]]:
    markers = {item["question_key"]: _clone(item) for item in index.get("retired_question_markers", [])}
    if not marker_directory_existed:
        return [markers[key] for key in sorted(markers)]
    for question in index.get("questions", []):
        if question.get("lifecycle", {}).get("state") != "active":
            continue
        key = question["question_key"]
        marker = active_markers.get(key)
        if marker and marker.get("question_uid") == question.get("question_uid"):
            continue
        markers[key] = {
            "question_key": key,
            "question_uid": question["question_uid"],
            "retired_at": changed_at,
            "reason": "active_question_marker_deleted",
        }
    return [markers[key] for key in sorted(markers)]


def _apply_marker_set(index: dict[str, Any], markers: Sequence[dict[str, Any]]) -> dict[str, Any]:
    updated = _clone(index)
    by_key = {item["question_key"]: _clone(item) for item in markers}
    updated["retired_question_markers"] = [by_key[key] for key in sorted(by_key)]
    for question in updated.get("questions", []):
        marker = by_key.get(question.get("question_key"))
        if marker:
            question["lifecycle"] = {
                "state": "retired",
                "reason": marker.get("reason") or "user_retired",
                "changed_at": marker.get("retired_at"),
            }
            question["formal_question_eligible"] = False
        else:
            question["lifecycle"] = {
                "state": "active",
                "reason": "complete_period_intersection",
                "changed_at": question.get("lifecycle", {}).get("changed_at"),
            }
            question["formal_question_eligible"] = True
    return updated


def _prepare_pair(
    spec: _PairSpec,
    canonical_brand: str,
    aliases: Sequence[str],
) -> dict[str, Any]:
    try:
        monitoring_path = ingestion._regular_file(spec.monitoring_path, ingestion.MONITORING_SUFFIXES, "question-research monitoring answers")
        source_path = ingestion._regular_file(spec.source_path, {".xlsx"}, "question-research citation workbook")
    except ingestion.ResearchIngestionError as exc:
        raise QuestionResearchError(str(exc)) from exc
    if monitoring_path == source_path:
        raise QuestionResearchError("monitoring answers and citation workbook must be different files")
    fingerprint = _pair_fingerprint(monitoring_path, source_path)
    marker = _read_period_marker(spec.marker_path)
    if marker and marker["pair_fingerprint"] != fingerprint:
        marker = {**marker, "source_changed": True}

    monitoring_rows, monitoring_inventory = _monitoring_rows(monitoring_path, canonical_brand, aliases)
    citation_rows, citation_inventory = _citation_rows(source_path)
    monitor_keys = set(monitoring_inventory["questions"])
    citation_keys = set(citation_inventory["questions"])
    citation_placeholders: list[str] = []
    for key in sorted(monitor_keys - citation_keys):
        monitor_rows = monitoring_rows.get(key, {})
        monitor_inventory = monitoring_inventory["questions"][key]
        texts = list(monitor_rows.get("texts") or monitor_inventory.get("texts") or [])
        citation_rows[key] = {"texts": texts, "details": []}
        citation_inventory["questions"][key] = {
            "texts": texts,
            "citation_detail_count": 0,
            "research_metrics": {
                "citation_domain_count": 0,
                "top_citation_domains": [],
                "citation_domain_concentration_top3": None,
                "warnings": ["citation_details_unavailable"],
            },
        }
        citation_placeholders.append(key)
    citation_keys = set(citation_inventory["questions"])
    complete_keys = monitor_keys
    if not complete_keys:
        raise QuestionResearchError("monitoring answers contain no usable question")
    observed_brands = sorted(set(monitoring_inventory.get("brands", [])) | set(citation_inventory.get("brands", [])))
    if canonical_brand:
        brand_ok, brand_warning = ingestion._brand_compatible(observed_brands, canonical_brand, aliases)
        if not brand_ok:
            raise QuestionResearchError(brand_warning or "research pair brand does not match")
    else:
        brand_warning = "canonical brand was not supplied; brand compatibility was not evaluated" if observed_brands else None
    try:
        observed_from, observed_to, warnings = ingestion._effective_dates(monitoring_inventory, citation_inventory)
    except ingestion.ResearchIngestionError as exc:
        raise QuestionResearchError(str(exc)) from exc
    if brand_warning:
        warnings.append(brand_warning)
    if citation_placeholders:
        warnings.append(
            "citation details were not supplied for one or more monitoring questions; empty citation slices were retained"
        )
    ordered_complete = [key for key in monitoring_rows if key in complete_keys]
    ordered_complete.extend(sorted(complete_keys - set(ordered_complete)))
    return {
        "spec": spec,
        "fingerprint": fingerprint,
        "marker": marker,
        "monitoring_rows": monitoring_rows,
        "citation_rows": citation_rows,
        "monitoring_inventory": monitoring_inventory,
        "citation_inventory": citation_inventory,
        "monitor_keys": monitor_keys,
        "citation_keys": citation_keys,
        "complete_keys": ordered_complete,
        "observed_from": observed_from,
        "observed_to": observed_to,
        "warnings": list(dict.fromkeys(warnings)),
    }


def _copy_tree_for_transaction(root: Path) -> Path:
    root.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{root.name}.transaction.", dir=root.parent))
    if root.is_dir():
        for child in root.iterdir():
            destination = temporary / child.name
            if child.is_dir():
                shutil.copytree(child, destination)
            elif child.is_file() and not child.is_symlink():
                shutil.copy2(child, destination)
            else:
                raise QuestionResearchError(f"question-research root contains an unsupported entry: {child}")
    return temporary


def _publish_tree(temporary: Path, root: Path) -> None:
    backup = root.parent / f".{root.name}.backup.{os.getpid()}"
    if backup.exists():
        shutil.rmtree(backup)
    moved_old = False
    try:
        if root.exists():
            os.replace(root, backup)
            moved_old = True
        os.replace(temporary, root)
        if moved_old:
            shutil.rmtree(backup)
    except Exception:
        if not root.exists() and moved_old and backup.exists():
            os.replace(backup, root)
        raise


def _same_existing_period(
    root: Path,
    old_slices: Sequence[dict[str, Any]],
    payloads: dict[str, dict[str, Any]],
) -> bool:
    if set(item["monitoring_path"] for item in old_slices) != {
        payload["monitoring_member"] for payload in payloads.values()
    }:
        return False
    for payload in payloads.values():
        monitor_path = _member_path(root, payload["monitoring_member"])
        citation_path = _member_path(root, payload["citation_member"])
        if not monitor_path.is_file() or not citation_path.is_file():
            return False
        if monitor_path.read_bytes() != _canonical_bytes(payload["monitoring_payload"]) + b"\n":
            return False
        if citation_path.read_bytes() != _canonical_bytes(payload["citation_payload"]) + b"\n":
            return False
    return True


def _matching_existing_period(
    root: Path,
    slices: Sequence[dict[str, Any]],
    payloads: dict[str, dict[str, Any]],
    periods: Sequence[dict[str, Any]],
    monitoring_only_keys: set[str],
    citation_only_keys: set[str],
) -> str | None:
    """Find a byte-equivalent complete period without exporting input hashes."""

    by_period: dict[str, list[dict[str, Any]]] = {}
    for item in slices:
        by_period.setdefault(item["period_id"], []).append(item)
    for period_id, records in sorted(by_period.items()):
        if {item["question_key"] for item in records} != set(payloads):
            continue
        period = next((item for item in periods if item.get("period_id") == period_id), None)
        if not period:
            continue
        if set(period.get("monitoring_only_question_keys") or []) != monitoring_only_keys:
            continue
        if set(period.get("citation_only_question_keys") or []) != citation_only_keys:
            continue
        matches = True
        for old in records:
            payload = payloads[old["question_key"]]
            monitor_path = _member_path(root, old["monitoring_path"])
            citation_path = _member_path(root, old["citation_path"])
            if not monitor_path.is_file() or not citation_path.is_file():
                matches = False
                break
            monitor = _clone(payload["monitoring_payload"])
            citation = _clone(payload["citation_payload"])
            monitor["period_id"] = period_id
            citation["period_id"] = period_id
            if monitor_path.read_bytes() != _canonical_bytes(monitor) + b"\n":
                matches = False
                break
            if citation_path.read_bytes() != _canonical_bytes(citation) + b"\n":
                matches = False
                break
        if matches:
            return period_id
    return None


def _write_canonical_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def _ingest_specs(
    index: dict[str, Any] | None,
    specs: Sequence[_PairSpec],
    derived_root: Path,
    *,
    canonical_brand: str,
    aliases: Sequence[str],
    project_questions: Any,
    replace_changed_periods: bool,
    lifecycle_markers: Sequence[dict[str, Any]] | None = None,
    question_uid_hints: dict[str, str] | None = None,
) -> PeriodIngestResult:
    original = _clone(index or empty_question_research_index())
    errors, _warnings = validate_question_research_index(original)
    if errors:
        raise QuestionResearchError("existing question research index is invalid: " + "; ".join(errors))
    current = _clone(original)
    root = Path(derived_root).resolve()
    overlays = _project_overlays(project_questions)
    marker_values = list(lifecycle_markers) if lifecycle_markers is not None else list(current.get("retired_question_markers") or [])
    uid_hints = {
        key: uid for key, uid in (question_uid_hints or {}).items()
        if _key(key) == key and isinstance(uid, str) and _QUESTION_PATH.fullmatch(uid)
    }
    uid_hints.update({
        item["question_key"]: item["question_uid"]
        for item in marker_values
        if isinstance(item.get("question_uid"), str) and _QUESTION_PATH.fullmatch(item["question_uid"])
    })
    current = _apply_marker_set(current, marker_values)

    prepared = [_prepare_pair(spec, canonical_brand, aliases) for spec in specs]
    existing_periods = {item["period_id"]: item for item in current["periods"]}
    existing_by_label = {
        item["workspace_period_label"]: item
        for item in current["periods"]
        if item.get("workspace_period_label")
    }
    used_period_ids = set(existing_periods)
    next_period_number = max((int(item[1:]) for item in used_period_ids), default=0)
    seen_fingerprints: dict[str, str] = {}
    actions: list[dict[str, Any]] = []
    process: list[dict[str, Any]] = []
    marker_writes: list[tuple[Path, dict[str, Any]]] = []

    for item in prepared:
        spec: _PairSpec = item["spec"]
        marker = item.get("marker")
        requested = spec.requested_period_id or (marker or {}).get("period_id")
        if not requested and spec.workspace_period_label in existing_by_label:
            requested = existing_by_label[spec.workspace_period_label]["period_id"]
        duplicate_period = seen_fingerprints.get(item["fingerprint"])
        if duplicate_period:
            actions.append({
                "action": "duplicate_pair_skipped",
                "period_id": duplicate_period,
                "workspace_period_label": spec.workspace_period_label,
            })
            if spec.marker_path:
                marker_writes.append((spec.marker_path, _marker_payload(spec, duplicate_period, item["fingerprint"], spec.ingested_at)))
            continue
        if requested:
            if not _PERIOD_PATH.fullmatch(requested):
                raise QuestionResearchError(f"invalid requested period_id: {requested}")
            existing = existing_periods.get(requested)
            if existing and spec.workspace_period_label and existing.get("workspace_period_label") not in {None, spec.workspace_period_label}:
                raise QuestionResearchError(
                    f"period marker {requested} belongs to {existing.get('workspace_period_label')!r}, "
                    f"not {spec.workspace_period_label!r}"
                )
        else:
            next_period_number += 1
            requested = f"p{next_period_number:06d}"
        used_period_ids.add(requested)
        item["period_id"] = requested

        seen_fingerprints[item["fingerprint"]] = requested

        if marker and marker.get("source_changed") and not replace_changed_periods:
            raise QuestionResearchError(
                f"workspace period {spec.workspace_period_label or requested!r} changed after completion; "
                "pass replace_changed_periods=True to replace that period atomically"
            )
        item["replace_existing"] = requested in existing_periods
        process.append(item)

    candidate = _clone(current)
    periods_by_id = {item["period_id"]: item for item in candidate["periods"]}
    questions_by_key = {item["question_key"]: item for item in candidate["questions"]}
    questions_by_uid = {item["question_uid"]: item for item in candidate["questions"]}
    retired = {item["question_key"]: item for item in candidate.get("retired_question_markers", [])}
    next_question_number = max((int(item[1:]) for item in questions_by_uid), default=0)
    max_source_order = max((int(item.get("source_order") or 0) for item in candidate["questions"]), default=0)
    payloads_by_period: dict[str, dict[str, dict[str, Any]]] = {}
    file_changes = False

    for item in process:
        spec = item["spec"]
        period_id = item["period_id"]
        existing_period = periods_by_id.get(period_id)
        old_slices = [entry for entry in candidate["slices"] if entry.get("period_id") == period_id]

        for key in item["complete_keys"]:
            if key in questions_by_key:
                continue
            hinted_uid = uid_hints.get(key)
            if hinted_uid and hinted_uid not in questions_by_uid:
                uid = hinted_uid
                next_question_number = max(next_question_number, int(uid[1:]))
            else:
                next_question_number += 1
                while f"q{next_question_number:06d}" in questions_by_uid:
                    next_question_number += 1
                uid = f"q{next_question_number:06d}"
            max_source_order += 1
            monitoring_texts = item["monitoring_rows"].get(key, {}).get("texts", [])
            citation_texts = item["citation_rows"].get(key, {}).get("texts", [])
            variants = list(dict.fromkeys([*monitoring_texts, *citation_texts]))
            overlay = overlays.get(key)
            text = (overlay or {}).get("question_text") or variants[0]
            marker = retired.get(key)
            question = {
                "question_uid": uid,
                "question_key": key,
                "question_text": text,
                "text_variants": variants,
                "question_id": (overlay or {}).get("question_id"),
                "source_order": int((overlay or {}).get("source_order") or max_source_order),
                "source_kind": "project_optimization_target",
                "classification": _classification(text, overlay),
                "lifecycle": {
                    "state": "retired" if marker else "active",
                    "reason": (marker or {}).get("reason") or "complete_period_intersection",
                    "changed_at": (marker or {}).get("retired_at"),
                },
                "formal_question_eligible": not bool(marker),
                "first_complete_period_id": period_id,
                "latest_complete_period_id": period_id,
                "complete_period_ids": [],
                "history": {},
            }
            questions_by_key[key] = question
            questions_by_uid[uid] = question
            candidate["questions"].append(question)

        period_payloads: dict[str, dict[str, Any]] = {}
        for key in item["complete_keys"]:
            question = questions_by_key[key]
            overlay = overlays.get(key)
            monitoring_texts = item["monitoring_rows"].get(key, {}).get("texts", [])
            citation_texts = item["citation_rows"].get(key, {}).get("texts", [])
            question["text_variants"] = list(dict.fromkeys([
                *question.get("text_variants", []), *monitoring_texts, *citation_texts,
            ]))
            if overlay:
                question["question_text"] = overlay["question_text"]
                question["question_id"] = overlay.get("question_id")
                question["source_order"] = overlay["source_order"]
                question["classification"] = _classification(question["question_text"], overlay)
            monitor_inventory = item["monitoring_inventory"]["questions"][key]
            citation_inventory = item["citation_inventory"]["questions"][key]
            monitoring_payload = _monitoring_slice(
                question["question_uid"], question["question_text"], key, period_id,
                item["monitoring_rows"][key], monitor_inventory,
                item["observed_from"], item["observed_to"],
            )
            citation_payload = _citation_slice(
                question["question_uid"], question["question_text"], key, period_id,
                item["citation_rows"][key], item["observed_from"], item["observed_to"],
            )
            monitoring_member = _slice_member(question["question_uid"], period_id, MONITORING_SLICE_NAME)
            citation_member = _slice_member(question["question_uid"], period_id, CITATION_SLICE_NAME)
            period_payloads[key] = {
                "monitoring_payload": monitoring_payload,
                "citation_payload": citation_payload,
                "monitoring_member": monitoring_member,
                "citation_member": citation_member,
            }
        payloads_by_period[period_id] = period_payloads

        if existing_period is None and item.get("marker") is None:
            duplicate_of = _matching_existing_period(
                root,
                candidate["slices"],
                period_payloads,
                candidate["periods"],
                set(item["monitor_keys"]) - set(item["citation_keys"]),
                set(item["citation_keys"]) - set(item["monitor_keys"]),
            )
            if duplicate_of:
                payloads_by_period.pop(period_id, None)
                actions.append({
                    "action": "duplicate_pair_skipped",
                    "period_id": duplicate_of,
                    "workspace_period_label": spec.workspace_period_label,
                })
                if spec.marker_path:
                    marker_writes.append((
                        spec.marker_path,
                        _marker_payload(spec, duplicate_of, item["fingerprint"], spec.ingested_at),
                    ))
                continue

        marker_same = bool(item.get("marker") and not item["marker"].get("source_changed"))
        marker_files_present = bool(old_slices) and all(
            _member_path(root, old[role]).is_file()
            for old in old_slices for role in ("monitoring_path", "citation_path")
        )
        existing_same = bool(
            existing_period
            and set(existing_period.get("monitoring_only_question_keys") or [])
            == set(item["monitor_keys"]) - set(item["citation_keys"])
            and set(existing_period.get("citation_only_question_keys") or [])
            == set(item["citation_keys"]) - set(item["monitor_keys"])
            and _same_existing_period(root, old_slices, period_payloads)
        )
        if existing_period and not (marker_same and marker_files_present) and not existing_same and not marker_same and not replace_changed_periods:
            raise QuestionResearchError(
                f"period {period_id} already exists with different normalized research; "
                "pass replace_changed_periods=True to replace it"
            )
        if existing_period and ((marker_same and marker_files_present) or existing_same):
            actions.append({
                "action": "marker_recovered" if not item.get("marker") else "duplicate_pair_skipped",
                "period_id": period_id,
                "workspace_period_label": spec.workspace_period_label,
            })
            if spec.marker_path:
                marker_writes.append((spec.marker_path, _marker_payload(spec, period_id, item["fingerprint"], spec.ingested_at)))
            continue

        if existing_period:
            candidate["periods"] = [entry for entry in candidate["periods"] if entry.get("period_id") != period_id]
            candidate["slices"] = [entry for entry in candidate["slices"] if entry.get("period_id") != period_id]
            candidate["incomplete_observations"] = [
                entry for entry in candidate["incomplete_observations"]
                if entry.get("period_id") != period_id
            ]
            recovered = marker_same and not marker_files_present
            actions.append({
                "action": "period_recovered" if recovered else "period_replaced",
                "period_id": period_id,
                "workspace_period_label": spec.workspace_period_label,
            })
        else:
            actions.append({"action": "period_added", "period_id": period_id, "workspace_period_label": spec.workspace_period_label})

        monitor_keys = set(item["monitor_keys"])
        citation_keys = set(item["citation_keys"])
        period = {
            "period_id": period_id,
            "workspace_period_label": spec.workspace_period_label,
            "declared_period_label": spec.declared_period_label,
            "ingested_at": spec.ingested_at,
            "monitoring_observed_from": item["monitoring_inventory"].get("observed_from"),
            "monitoring_observed_to": item["monitoring_inventory"].get("observed_to"),
            "citation_observed_from": item["citation_inventory"].get("observed_from"),
            "citation_observed_to": item["citation_inventory"].get("observed_to"),
            "observed_from": item["observed_from"],
            "observed_to": item["observed_to"],
            "platforms": item["monitoring_inventory"].get("platforms", []),
            "monitoring_question_count": len(monitor_keys),
            "citation_question_count": len(citation_keys),
            "complete_question_count": len(item["complete_keys"]),
            "monitoring_only_question_keys": sorted(monitor_keys - citation_keys),
            "citation_only_question_keys": sorted(citation_keys - monitor_keys),
            "status": "complete",
            "warnings": item["warnings"],
        }
        candidate["periods"].append(period)
        periods_by_id[period_id] = period

        for availability, keys, rows in (
            ("monitoring_only", monitor_keys - citation_keys, item["monitoring_rows"]),
            ("citation_only", citation_keys - monitor_keys, item["citation_rows"]),
        ):
            for key in sorted(keys):
                texts = rows.get(key, {}).get("texts", [])
                candidate["incomplete_observations"].append({
                    "period_id": period_id,
                    "question_key": key,
                    "question_text": texts[0] if texts else key,
                    "availability": availability,
                })

        for key, payload in period_payloads.items():
            question = questions_by_key[key]
            monitoring_payload = payload["monitoring_payload"]
            citation_payload = payload["citation_payload"]
            visibility = monitoring_payload.get("research_metrics", {}).get("brand_visibility") or {}
            citation_metrics = item["citation_inventory"]["questions"][key].get("research_metrics") or {}
            candidate["slices"].append({
                "slice_id": f"{question['question_uid']}-{period_id}",
                "question_uid": question["question_uid"],
                "question_key": key,
                "period_id": period_id,
                "status": "complete",
                "monitoring_path": payload["monitoring_member"],
                "citation_path": payload["citation_member"],
                "answer_observation_count": monitoring_payload["answer_count"],
                "platform_count": len(monitoring_payload["platforms"]),
                "citation_detail_count": citation_payload["detail_count"],
                "unique_citation_content_count": citation_payload["unique_content_count"],
                "brand_mention_rate": visibility.get("brand_mention_rate"),
                "top1_rate": visibility.get("top1_rate"),
                "top3_rate": visibility.get("top3_rate"),
                "average_rank": visibility.get("average_rank"),
                "citation_domain_count": citation_metrics.get("citation_domain_count"),
                "citation_domain_concentration_top3": citation_metrics.get("citation_domain_concentration_top3"),
                "observed_from": item["observed_from"],
                "observed_to": item["observed_to"],
            })
        file_changes = True
        if spec.marker_path:
            marker_writes.append((spec.marker_path, _marker_payload(spec, period_id, item["fingerprint"], spec.ingested_at)))

    # Apply overlays even when every submitted pair was an idempotent no-op.
    for key, question in list(questions_by_key.items()):
        overlay = overlays.get(key)
        if overlay:
            question["question_text"] = overlay["question_text"]
            question["question_id"] = overlay.get("question_id")
            question["source_order"] = overlay["source_order"]
            question["classification"] = _classification(question["question_text"], overlay)

    period_lookup = {item["period_id"]: item for item in candidate["periods"]}
    slice_uids = {item["question_uid"] for item in candidate["slices"]}
    candidate["questions"] = [item for item in candidate["questions"] if item["question_uid"] in slice_uids]
    retired_keys = {item["question_key"] for item in candidate.get("retired_question_markers", [])}
    for question in candidate["questions"]:
        relevant = [item for item in candidate["slices"] if item["question_uid"] == question["question_uid"]]
        period_ids = sorted({item["period_id"] for item in relevant}, key=lambda value: _period_sort_value(period_lookup[value]))
        question["complete_period_ids"] = period_ids
        question["first_complete_period_id"] = period_ids[0]
        question["latest_complete_period_id"] = period_ids[-1]
        question["history"] = _history_for(question["question_uid"], candidate["slices"], period_lookup)
        marker = next((item for item in candidate["retired_question_markers"] if item["question_key"] == question["question_key"]), None)
        if question["question_key"] in retired_keys:
            question["lifecycle"] = {"state": "retired", "reason": marker.get("reason") or "user_retired", "changed_at": marker.get("retired_at")}
            question["formal_question_eligible"] = False
        else:
            question["lifecycle"] = {"state": "active", "reason": "complete_period_intersection", "changed_at": question.get("lifecycle", {}).get("changed_at")}
            question["formal_question_eligible"] = True

    candidate["periods"].sort(key=_period_sort_value)
    candidate["questions"].sort(key=lambda item: (int(item.get("source_order") or 10**9), item["question_uid"]))
    candidate["slices"].sort(key=lambda item: (item["question_uid"], _period_sort_value(period_lookup[item["period_id"]])))
    candidate["incomplete_observations"].sort(
        key=lambda item: (
            _period_sort_value(period_lookup[item["period_id"]]),
            item["availability"],
            item["question_key"],
        )
    )

    old_comparable = _clone(original)
    new_comparable = _clone(candidate)
    for value in (old_comparable, new_comparable):
        value["updated_at"] = None
        value["index_revision"] = 0
    changed = file_changes or old_comparable != new_comparable
    if changed:
        candidate["index_revision"] = int(original.get("index_revision") or 0) + 1
        candidate["updated_at"] = max((spec.ingested_at for spec in specs), default=_now())
        temporary = _copy_tree_for_transaction(root)
        try:
            # Remove every replaced period's old slice files before writing.
            replaced = {action["period_id"] for action in actions if action["action"] in {"period_replaced", "period_recovered"}}
            for old in current["slices"]:
                if old.get("period_id") in replaced:
                    for role in ("monitoring_path", "citation_path"):
                        path = _member_path(temporary, old[role])
                        if path.is_file():
                            path.unlink()
            for period_id, values in payloads_by_period.items():
                if not any(action.get("period_id") == period_id and action["action"] in {"period_added", "period_replaced", "period_recovered"} for action in actions):
                    continue
                for payload in values.values():
                    _write_canonical_json(_member_path(temporary, payload["monitoring_member"]), payload["monitoring_payload"])
                    _write_canonical_json(_member_path(temporary, payload["citation_member"]), payload["citation_payload"])
            _write_canonical_json(temporary / "index.json", candidate)
            members = {
                f"{QUESTION_RESEARCH_ROOT_MEMBER}/{path.relative_to(temporary).as_posix()}"
                for path in temporary.rglob("*") if path.is_file()
            }
            validation_errors, _ = validate_question_research_index(candidate, members)
            if validation_errors:
                raise QuestionResearchError("generated question research index is invalid: " + "; ".join(validation_errors))
            _publish_tree(temporary, root)
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary, ignore_errors=True)
            raise
    else:
        candidate = current

    for marker_path, payload in marker_writes:
        _atomic_json(marker_path, payload)
    period_ids = tuple(action["period_id"] for action in actions if action.get("period_id"))
    question_uids = tuple(item["question_uid"] for item in candidate["questions"])
    return PeriodIngestResult(candidate, tuple(actions), tuple(dict.fromkeys(period_ids)), question_uids)


def ingest_overall_pair(
    index: dict[str, Any] | None,
    monitoring_path: Path,
    source_path: Path,
    derived_root: Path,
    *,
    canonical_brand: str = "",
    aliases: Sequence[str] = (),
    project_questions: Any = None,
    ingested_at: str | None = None,
    declared_period_label: str | None = None,
    workspace_period_label: str | None = None,
    marker_path: Path | None = None,
    requested_period_id: str | None = None,
    replace_changed_periods: bool = False,
    lifecycle_markers: Sequence[dict[str, Any]] | None = None,
) -> PeriodIngestResult:
    """Atomically add or replace one same-period overall research pair."""

    timestamp = ingested_at or _now()
    spec = _PairSpec(
        Path(monitoring_path), Path(source_path), Path(marker_path) if marker_path else None,
        _normal(workspace_period_label) or None,
        _normal(declared_period_label) or None,
        timestamp,
        requested_period_id,
    )
    return _ingest_specs(
        index, [spec], Path(derived_root), canonical_brand=canonical_brand,
        aliases=aliases, project_questions=project_questions,
        replace_changed_periods=replace_changed_periods,
        lifecycle_markers=lifecycle_markers,
    )


def build_from_research_ingestion_index(
    ingestion_index: dict[str, Any],
    ingestion_staging_root: Path,
    derived_root: Path,
    *,
    canonical_brand: str = "",
    aliases: Sequence[str] = (),
    project_questions: Any = None,
    existing_index: dict[str, Any] | None = None,
    replace_changed_periods: bool = False,
) -> PeriodIngestResult:
    """Build normalized question slices from the neutral research-ingestion index."""

    ingestion_errors, _ = ingestion.validate_index_payload(ingestion_index)
    if ingestion_errors:
        raise QuestionResearchError("invalid research-ingestion index: " + "; ".join(ingestion_errors))
    raw_root = Path(ingestion_staging_root).resolve()
    current = existing_index if existing_index is not None else load_question_research_index(Path(derived_root))
    specs: list[_PairSpec] = []
    datasets = sorted(
        ingestion_index.get("datasets", []),
        key=lambda item: (
            str(item.get("effective_observed_to") or ""),
            str(item.get("ingested_at") or ""),
            str(item.get("dataset_id") or ""),
        ),
    )
    for order, dataset in enumerate(datasets, 1):
        try:
            monitoring = ingestion.staging_member_path(raw_root, dataset["monitoring_answers_path"])
            source = ingestion.staging_member_path(raw_root, dataset["source_workbook_path"])
        except ingestion.ResearchIngestionError as exc:
            raise QuestionResearchError(str(exc)) from exc
        dataset_dir = monitoring.parent
        specs.append(_PairSpec(
            monitoring,
            source,
            dataset_dir / PERIOD_COMPLETE_MARKER,
            f"observation-period-{order:03d}",
            dataset.get("declared_period_label"),
            dataset.get("ingested_at") or _now(),
            None,
        ))
    return _ingest_specs(
        current, specs, Path(derived_root), canonical_brand=canonical_brand,
        aliases=aliases, project_questions=project_questions,
        replace_changed_periods=replace_changed_periods,
    )


def _discover_workspace_pair(
    period_dir: Path,
    canonical_brand: str,
    aliases: Sequence[str],
) -> tuple[Path, Path, dict[str, Any] | None]:
    marker_path = period_dir / PERIOD_COMPLETE_MARKER
    marker = _read_period_marker(marker_path)
    if marker:
        monitoring = period_dir / marker["monitoring_file"]
        source = period_dir / marker["source_file"]
        if monitoring.is_file() and source.is_file():
            return monitoring, source, marker
        # The user may replace a completed period with differently named
        # overall exports. Preserve its stable period_id, but rediscover both
        # roles by content and let the transactional replacement rewrite the
        # marker only after the new pair fully validates.

    files = sorted(
        path for path in period_dir.iterdir()
        if path.is_file() and not path.is_symlink() and not path.name.startswith(".")
    )
    canonical_monitoring = [path for path in files if path.stem.casefold() == "monitoring_answers" and path.suffix.casefold() in ingestion.MONITORING_SUFFIXES]
    canonical_sources = [path for path in files if path.name.casefold() == "source_workbook.xlsx"]
    if len(canonical_monitoring) == 1 and len(canonical_sources) == 1 and canonical_monitoring[0] != canonical_sources[0]:
        return canonical_monitoring[0], canonical_sources[0], marker

    pairs: list[tuple[Path, Path]] = []
    for monitoring in files:
        if monitoring.suffix.casefold() not in ingestion.MONITORING_SUFFIXES:
            continue
        try:
            monitoring_inventory = ingestion._monitoring_inventory(monitoring, canonical_brand, aliases)
        except Exception:
            continue
        for source in files:
            if source == monitoring or source.suffix.casefold() != ".xlsx":
                continue
            try:
                source_inventory = ingestion._source_inventory(source)
            except Exception:
                continue
            if set(monitoring_inventory["questions"]) & set(source_inventory["questions"]):
                pairs.append((monitoring, source))
    unique = list(dict.fromkeys(pairs))
    if len(unique) != 1:
        if not unique:
            raise QuestionResearchError(f"workspace period has no complete monitoring/citation pair: {period_dir}")
        raise QuestionResearchError(f"workspace period has multiple possible monitoring/citation pairs: {period_dir}")
    return unique[0][0], unique[0][1], marker


def scan_workspace_periods(
    workspace_data: Path,
    index: dict[str, Any] | None = None,
    project_questions: Any = None,
    *,
    derived_root: Path | None = None,
    canonical_brand: str = "",
    aliases: Sequence[str] = (),
    replace_changed_periods: bool = False,
) -> PeriodIngestResult:
    """Scan maintainable-Pack workspace periods and atomically refresh slices."""

    workspace = Path(workspace_data).resolve()
    periods_root = workspace / "periods"
    target = Path(derived_root).resolve() if derived_root else workspace.parent / QUESTION_RESEARCH_ROOT_MEMBER
    current = index if index is not None else load_question_research_index(target)
    active_directory_existed = _active_questions_path(workspace).exists()
    active_markers = load_active_question_markers(workspace)
    lifecycle_index = _clone(current)
    lifecycle_index["retired_question_markers"] = load_lifecycle_markers(workspace)
    lifecycle = _retire_deleted_active_markers(
        lifecycle_index,
        active_markers,
        marker_directory_existed=active_directory_existed,
        changed_at=_now(),
    )
    specs: list[_PairSpec] = []
    ignored: list[dict[str, Any]] = []
    if periods_root.exists() and (periods_root.is_symlink() or not periods_root.is_dir()):
        raise QuestionResearchError(f"workspace periods path must be a regular directory: {periods_root}")
    if periods_root.is_dir():
        for period_dir in sorted(path for path in periods_root.iterdir() if path.is_dir() and not path.is_symlink()):
            symlinks = [path for path in period_dir.iterdir() if path.is_symlink()]
            if symlinks:
                raise QuestionResearchError(f"workspace period contains a symlink: {symlinks[0]}")
            try:
                monitoring, source, marker = _discover_workspace_pair(period_dir, canonical_brand, aliases)
            except QuestionResearchError as exc:
                ignored.append({
                    "action": "ignored_invalid_period",
                    "workspace_period_label": period_dir.name,
                    "warning": str(exc),
                })
                continue
            spec = _PairSpec(
                monitoring,
                source,
                period_dir / PERIOD_COMPLETE_MARKER,
                period_dir.name,
                period_dir.name,
                (marker or {}).get("completed_at") or _now(),
                (marker or {}).get("period_id"),
            )
            try:
                _prepare_pair(spec, canonical_brand, aliases)
            except QuestionResearchError as exc:
                ignored.append({
                    "action": "ignored_invalid_period",
                    "workspace_period_label": period_dir.name,
                    "warning": str(exc),
                })
                continue
            specs.append(spec)
    result = _ingest_specs(
        current, specs, target, canonical_brand=canonical_brand,
        aliases=aliases, project_questions=project_questions,
        replace_changed_periods=replace_changed_periods,
        lifecycle_markers=lifecycle,
        question_uid_hints={key: item["question_uid"] for key, item in active_markers.items()},
    )
    write_lifecycle_markers(workspace, result.index)
    write_active_question_markers(workspace, result.index)
    actions = tuple([*ignored, *result.actions])
    return PeriodIngestResult(result.index, actions, result.period_ids, result.question_uids)


def refresh_workspace(
    pack_dir: Path,
    *,
    canonical_brand: str = "",
    aliases: Sequence[str] = (),
    project_questions: Any = None,
    replace_changed_periods: bool = False,
) -> PeriodIngestResult:
    """Refresh ``research/question_research`` from ``workspace_data/periods``."""

    root = Path(pack_dir).resolve()
    if not root.is_dir() or root.is_symlink():
        raise QuestionResearchError(f"maintainable Pack must be a regular directory: {pack_dir}")
    return scan_workspace_periods(
        root / WORKSPACE_DATA_DIR,
        project_questions=project_questions,
        derived_root=root / QUESTION_RESEARCH_ROOT_MEMBER,
        canonical_brand=canonical_brand,
        aliases=aliases,
        replace_changed_periods=replace_changed_periods,
    )


def _resolve_question(index: dict[str, Any], value: Any) -> dict[str, Any]:
    raw = _normal(value)
    key = _key(value)
    matches = [
        item for item in index.get("questions", [])
        if raw in {item.get("question_uid"), item.get("question_id")}
        or key == item.get("question_key")
    ]
    if len(matches) != 1:
        if not matches:
            raise QuestionResearchError(f"question is not present in the complete-period union: {raw!r}")
        raise QuestionResearchError(f"question reference is ambiguous: {raw!r}")
    return matches[0]


def bind_question_lifecycle(
    index: dict[str, Any],
    project_questions: Any = None,
    decisions: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """Overlay display metadata and apply explicit retire/restore decisions.

    The project list never filters the same-period intersection union.
    """

    updated = _clone(index)
    overlays = _project_overlays(project_questions)
    for question in updated.get("questions", []):
        overlay = overlays.get(question["question_key"])
        if overlay:
            question["question_text"] = overlay["question_text"]
            question["question_id"] = overlay.get("question_id")
            question["source_order"] = overlay["source_order"]
            question["classification"] = _classification(question["question_text"], overlay)
    for decision in decisions:
        if not isinstance(decision, dict):
            raise QuestionResearchError("question lifecycle decision must be an object")
        action = decision.get("action")
        reference = decision.get("question_uid") or decision.get("question_key") or decision.get("question")
        if action == "retire":
            updated = retire_question(updated, reference, reason=decision.get("reason") or "user_retired")
        elif action == "restore":
            updated = restore_question(updated, reference)
        else:
            raise QuestionResearchError(f"unsupported question lifecycle action: {action!r}")
    return updated


def retire_question(
    index: dict[str, Any],
    question: Any,
    reason: str = "user_retired",
    *,
    changed_at: str | None = None,
    workspace_data: Path | None = None,
) -> dict[str, Any]:
    updated = _clone(index)
    target = _resolve_question(updated, question)
    timestamp = changed_at or _now()
    marker = {
        "question_key": target["question_key"],
        "question_uid": target["question_uid"],
        "retired_at": timestamp,
        "reason": _normal(reason) or "user_retired",
    }
    markers = [item for item in updated.get("retired_question_markers", []) if item.get("question_key") != target["question_key"]]
    markers.append(marker)
    updated["retired_question_markers"] = sorted(markers, key=lambda item: item["question_key"])
    target["lifecycle"] = {"state": "retired", "reason": marker["reason"], "changed_at": timestamp}
    target["formal_question_eligible"] = False
    updated["index_revision"] = int(updated.get("index_revision") or 0) + 1
    updated["updated_at"] = timestamp
    if workspace_data is not None:
        write_lifecycle_markers(Path(workspace_data), updated)
        write_active_question_markers(Path(workspace_data), updated)
    return updated


def restore_question(
    index: dict[str, Any],
    question: Any,
    *,
    changed_at: str | None = None,
    workspace_data: Path | None = None,
) -> dict[str, Any]:
    updated = _clone(index)
    target = _resolve_question(updated, question)
    markers = [item for item in updated.get("retired_question_markers", []) if item.get("question_key") != target["question_key"]]
    if len(markers) == len(updated.get("retired_question_markers", [])) and target.get("lifecycle", {}).get("state") == "active":
        return updated
    timestamp = changed_at or _now()
    updated["retired_question_markers"] = markers
    target["lifecycle"] = {"state": "active", "reason": "explicit_restore", "changed_at": timestamp}
    target["formal_question_eligible"] = True
    updated["index_revision"] = int(updated.get("index_revision") or 0) + 1
    updated["updated_at"] = timestamp
    if workspace_data is not None:
        write_lifecycle_markers(Path(workspace_data), updated)
        write_active_question_markers(Path(workspace_data), updated)
    return updated


def remove_period(index: dict[str, Any], period_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove one derived period from an index; callers delete returned paths transactionally."""

    updated = _clone(index)
    matches = [item for item in updated.get("periods", []) if item.get("period_id") == period_id]
    if len(matches) != 1:
        raise QuestionResearchError(f"unknown period_id: {period_id}")
    removed_slices = [item for item in updated["slices"] if item.get("period_id") == period_id]
    updated["periods"] = [item for item in updated["periods"] if item.get("period_id") != period_id]
    updated["slices"] = [item for item in updated["slices"] if item.get("period_id") != period_id]
    updated["incomplete_observations"] = [
        item for item in updated.get("incomplete_observations", [])
        if item.get("period_id") != period_id
    ]
    period_lookup = {item["period_id"]: item for item in updated["periods"]}
    active_uids = {item["question_uid"] for item in updated["slices"]}
    updated["questions"] = [item for item in updated["questions"] if item["question_uid"] in active_uids]
    for question in updated["questions"]:
        relevant = [item for item in updated["slices"] if item["question_uid"] == question["question_uid"]]
        ids = sorted({item["period_id"] for item in relevant}, key=lambda value: _period_sort_value(period_lookup[value]))
        question["complete_period_ids"] = ids
        question["first_complete_period_id"] = ids[0]
        question["latest_complete_period_id"] = ids[-1]
        question["history"] = _history_for(question["question_uid"], updated["slices"], period_lookup)
    timestamp = _now()
    updated["index_revision"] = int(updated.get("index_revision") or 0) + 1
    updated["updated_at"] = timestamp
    return updated, {"period": matches[0], "slices": removed_slices}


def formal_question_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the active complete-period union as formal project questions."""

    rows: list[dict[str, Any]] = []
    for item in sorted(index.get("questions", []), key=lambda value: (int(value.get("source_order") or 10**9), value.get("question_uid", ""))):
        if item.get("lifecycle", {}).get("state") != "active" or item.get("formal_question_eligible") is not True:
            continue
        classification = item.get("classification") or {}
        row = {
            "question_uid": item["question_uid"],
            "question_key": item["question_key"],
            "question_text": item["question_text"],
            "source_order": item["source_order"],
            "source_kind": "project_optimization_target",
            "frequency": None,
            "formal_question_eligible": True,
            "primary_intent_tag": classification.get("primary_intent_tag"),
            "category": classification.get("category"),
            "entry_category": classification.get("entry_category"),
            "research_period_count": len(item.get("complete_period_ids", [])),
            "latest_complete_period_id": item.get("latest_complete_period_id"),
        }
        if item.get("question_id"):
            row["question_id"] = item["question_id"]
        rows.append(row)
    return rows


def select_question_periods(
    index: dict[str, Any],
    question: Any,
    mode: str = "latest_complete",
    period_ids: Sequence[str] = (),
    observed_from: str | None = None,
    observed_to: str | None = None,
    require_active: bool = True,
) -> QuestionResearchSelection:
    target = _resolve_question(index, question)
    if require_active and (
        target.get("lifecycle", {}).get("state") != "active"
        or target.get("formal_question_eligible") is not True
    ):
        raise QuestionResearchError(f"question is retired and cannot be selected automatically: {target['question_text']}")
    periods = {item["period_id"]: item for item in index.get("periods", [])}
    candidates = [item for item in index.get("slices", []) if item.get("question_uid") == target["question_uid"] and item.get("status") == "complete"]
    candidates.sort(key=lambda item: _period_sort_value(periods[item["period_id"]]))
    warnings: list[str] = []
    if mode == "latest_complete":
        selected = candidates[-1:] if candidates else []
    elif mode in {"history", "all_complete"}:
        selected = candidates
    elif mode == "explicit_periods":
        requested = list(dict.fromkeys(period_ids))
        missing = [value for value in requested if value not in {item["period_id"] for item in candidates}]
        if missing:
            raise QuestionResearchError(f"question has no complete slice for periods: {', '.join(missing)}")
        order = {value: position for position, value in enumerate(requested)}
        selected = sorted([item for item in candidates if item["period_id"] in order], key=lambda item: order[item["period_id"]])
    elif mode == "date_range":
        if not observed_from and not observed_to:
            raise QuestionResearchError("date_range selection requires observed_from or observed_to")
        selected = []
        for item in candidates:
            period = periods[item["period_id"]]
            start, end = period.get("observed_from"), period.get("observed_to")
            if not start or not end:
                warnings.append(f"period {item['period_id']} was excluded because its observed range is unknown")
                continue
            if observed_from and end < observed_from:
                continue
            if observed_to and start > observed_to:
                continue
            selected.append(item)
    else:
        raise QuestionResearchError(f"unsupported question research selection mode: {mode}")
    if not selected:
        raise QuestionResearchError(f"question has no complete research slice for selection mode {mode}")
    return QuestionResearchSelection(
        question=_clone(target),
        slices=tuple(_clone(item) for item in selected),
        selection_mode=mode,
        history_change=_clone(target.get("history") or {}),
        warnings=tuple(warnings),
    )


def _read_research_member(source: Path, member: str) -> bytes:
    origin = Path(source)
    if origin.is_file() and origin.suffix.casefold() == ".zip":
        reader = ingestion._ZipPackageReader(origin)
        try:
            return reader.read(member)
        finally:
            reader.close()
    if not origin.is_dir():
        raise QuestionResearchError(f"research source is not a directory or ZIP: {source}")
    direct = origin / member
    if direct.is_file():
        return direct.read_bytes()
    if origin.name == "question_research" and (origin / "index.json").is_file():
        relative = PurePosixPath(member).relative_to(QUESTION_RESEARCH_ROOT_MEMBER)
        direct = origin.joinpath(*relative.parts)
        if direct.is_file():
            return direct.read_bytes()
    raise QuestionResearchError(f"research member is missing: {member}")


def materialize_question_selection(
    selection: QuestionResearchSelection,
    research_source: Path,
    destination: Path,
    *,
    write_selection_manifest: bool = True,
) -> dict[str, Any]:
    """Materialize one or more whole period pairs without cross-period mixing."""

    target = Path(destination).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{target.name}.transaction.", dir=target.parent))
    period_rows: list[dict[str, Any]] = []
    history_periods: list[dict[str, Any]] = []
    try:
        multi = len(selection.slices) > 1
        for item in selection.slices:
            period_id = item["period_id"]
            folder = temporary / "periods" / period_id if multi else temporary
            folder.mkdir(parents=True, exist_ok=True)
            monitor_bytes = _read_research_member(Path(research_source), item["monitoring_path"])
            citation_bytes = _read_research_member(Path(research_source), item["citation_path"])
            monitor_payload = ingestion._strict_json_bytes(monitor_bytes, item["monitoring_path"])
            citation_payload = ingestion._strict_json_bytes(citation_bytes, item["citation_path"])
            if monitor_payload.get("question_key") != selection.question["question_key"] or citation_payload.get("question_key") != selection.question["question_key"]:
                raise QuestionResearchError(f"slice question key mismatch for period {period_id}")
            if monitor_payload.get("period_id") != period_id or citation_payload.get("period_id") != period_id:
                raise QuestionResearchError(f"slice period mismatch for period {period_id}")
            monitor_name = MONITORING_SLICE_NAME
            citation_name = CITATION_SLICE_NAME
            (folder / monitor_name).write_bytes(monitor_bytes)
            (folder / citation_name).write_bytes(citation_bytes)
            period_rows.append({
                "period_id": period_id,
                "monitoring_observations_path": (folder / monitor_name).relative_to(temporary).as_posix(),
                "citation_observations_path": (folder / citation_name).relative_to(temporary).as_posix(),
                "answer_observation_count": item["answer_observation_count"],
                "platform_count": item["platform_count"],
                "citation_detail_count": item["citation_detail_count"],
            })
            visibility = (
                monitor_payload.get("research_metrics", {}).get("brand_visibility")
                if isinstance(monitor_payload.get("research_metrics"), dict)
                else None
            )
            visibility = visibility if isinstance(visibility, dict) else {}
            history_periods.append({
                "period_id": period_id,
                "observed_from": item.get("observed_from"),
                "observed_to": item.get("observed_to"),
                "answer_observation_count": item["answer_observation_count"],
                "platform_count": item["platform_count"],
                "citation_detail_count": item["citation_detail_count"],
                "brand_mention_rate": visibility.get("brand_mention_rate"),
                "average_rank": visibility.get("average_rank"),
                "top1_rate": visibility.get("top1_rate"),
                "top3_rate": visibility.get("top3_rate"),
                "citation_domain_count": item.get("citation_domain_count"),
                "citation_domain_concentration_top3": item.get("citation_domain_concentration_top3"),
            })
        history_payload = {
            "schema_version": "1.0.0",
            "artifact_type": "frontmind_question_research_history",
            "usage_policy": INDEX_USAGE_POLICY,
            "question": selection.question["question_text"],
            "question_key": selection.question["question_key"],
            "question_uid": selection.question["question_uid"],
            "selection_mode": selection.selection_mode,
            "selected_period_ids": [item["period_id"] for item in selection.slices],
            "periods": history_periods,
            "history_change": selection.history_change,
            "warnings": list(selection.warnings),
        }
        manifest = {
            "schema_version": "1.0.0",
            "artifact_type": "frontmind_question_research_selection",
            "usage_policy": INDEX_USAGE_POLICY,
            "question": selection.question["question_text"],
            "question_key": selection.question["question_key"],
            "question_uid": selection.question["question_uid"],
            "selection_mode": selection.selection_mode,
            "periods": period_rows,
            "history_path": "research_history.json",
            "warnings": list(selection.warnings),
        }
        _write_canonical_json(temporary / "research_history.json", history_payload)
        if write_selection_manifest:
            _write_canonical_json(temporary / "selection_manifest.json", manifest)
        _publish_tree(temporary, target)
        return manifest
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        raise


__all__ = [
    "ACTIVE_QUESTIONS_DIR",
    "CITATION_ARTIFACT_TYPE",
    "CITATION_SCHEMA_VERSION",
    "CITATION_SLICE_NAME",
    "INDEX_ARTIFACT_TYPE",
    "INDEX_SCHEMA_VERSION",
    "INDEX_USAGE_POLICY",
    "LEGACY_INDEX_SCHEMA_VERSION",
    "LIFECYCLE_MARKER",
    "LEGACY_LIFECYCLE_MARKER",
    "MONITORING_ARTIFACT_TYPE",
    "MONITORING_SCHEMA_VERSION",
    "MONITORING_SLICE_NAME",
    "PERIOD_COMPLETE_MARKER",
    "PeriodIngestResult",
    "QUESTION_RESEARCH_INDEX_MEMBER",
    "QUESTION_RESEARCH_ROOT_MEMBER",
    "QuestionResearchError",
    "QuestionResearchSelection",
    "WORKSPACE_DATA_DIR",
    "WORKSPACE_PERIODS_DIR",
    "bind_question_lifecycle",
    "build_from_research_ingestion_index",
    "empty_question_research_index",
    "formal_question_rows",
    "ingest_overall_pair",
    "load_lifecycle_markers",
    "load_active_question_markers",
    "load_question_research_index",
    "materialize_question_selection",
    "refresh_workspace",
    "remove_period",
    "restore_question",
    "retire_question",
    "scan_workspace_periods",
    "select_question_periods",
    "upgrade_question_research_index",
    "validate_question_research_index",
    "write_lifecycle_markers",
    "write_active_question_markers",
    "write_question_research_index",
]
