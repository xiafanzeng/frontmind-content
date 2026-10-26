#!/usr/bin/env python3
"""Export saved production Managed events as a public GeneralExecutionDto.

This reads local evidence only: it never calls a provider or changes a Job.
Coverage is always partial: saved Managed events and writer attempt summaries
do not cover outer Dashboard execution, human confirmations or GEO effects.
Only validated public summaries, diagnostics and identities/times cross this
boundary. Raw provider prose, reasoning, arguments/results and errors never do.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import os
sys.path.insert(0, str(Path(__file__).resolve().parent))
from portable_lock import file_lock
from process_summary import cached_rows, safe_summary, summary_sources, sdk_tool_records, identity as summary_identity


WIRE_API = "zhipu_managed_agents"
SDK_WIRE_API = "openai_agents_sdk"
TOOL_LABELS = {
    "list_materials": "查看目录", "read_material": "读取文件",
    "search_materials": "检索文本", "extract_document": "读取文件",
    "web_search": "搜索网页", "web_read": "读取网页", "ocr": "读取文件",
    "submit_result": "调用工具",
}
OPERATIONS = set(TOOL_LABELS) | {"count_article"}
ACTIONS = {"positioning_market_research", "positioning_value_synthesis", "answer_analysis", "article_editorial_preparation", "article_polish"} | {
    prefix + suffix for prefix in ("p0_", "article_") for suffix in
    ("blueprint", "draft", "edit", "style", "finalize", "repair", "titles", "title_review")}
ERROR_CODES = {
    "managed_network_error": "network_error", "network_error": "network_error",
    "managed_http_error": "http_error", "http_error": "http_error",
    "invalid_result_contract": "invalid_result", "invalid_json": "invalid_result",
    "tool_request_rejected": "tool_request_rejected", "source_acquisition_failed": "source_unavailable",
    "managed_retries_exhausted": "retries_exhausted",
    "non_public_address": "non_public_address",
    "material_reference_missing": "material_reference_missing",
    "material_reference_ambiguous": "material_reference_ambiguous",
    "material_boundary_rejected": "material_boundary_rejected",
    "invalid_tool_arguments": "invalid_tool_arguments",
    "deterministic_tool_repeat": "deterministic_tool_repeat",
}


class ExportError(ValueError):
    """Stable safe code, never a provider diagnostic or source payload."""


def _identity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _timestamp(value: object) -> int:
    if not isinstance(value, str):
        raise ExportError("MANAGED_EVENT_TIMESTAMP_MISSING")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None:
            raise ValueError()
        return int(instant.timestamp() * 1000)
    except (ValueError, OverflowError):
        raise ExportError("MANAGED_EVENT_TIMESTAMP_INVALID") from None


def _phase(action: object) -> str:
    if action in {"positioning_market_research", "article_editorial_preparation"}:
        return "researching"
    if action == "positioning_value_synthesis":
        return "organizing_evidence"
    if isinstance(action, str) and action.endswith("_blueprint"):
        return "preparing_requirements"
    if isinstance(action, str) and action.endswith(("_finalize", "_polish", "_title_review")):
        return "checking_content"
    return "generating_content"


def _diagnostic(error: object) -> str:
    if not isinstance(error, dict):
        return "execution_error"
    code = error.get("code") or error.get("error")
    # Match an exact known host diagnostic; never expose its payload or guess
    # the reason behind old, generic tool_request_rejected receipts.
    if code == "source_acquisition_failed" and str(error.get("message", "")).startswith(
            "web URL resolves to a non-public address"):
        return "non_public_address"
    return ERROR_CODES.get(code, "execution_error") if isinstance(code, str) else "execution_error"


def _tool_diagnostic(result: dict) -> str:
    for item in result.get("content", []):
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            try:
                payload = json.loads(item["text"])
            except (ValueError, TypeError):
                continue
            if isinstance(payload, dict) and ("error" in payload or "code" in payload):
                return _diagnostic(payload)
    return "execution_error"


def _attempt_identity(record: dict) -> str:
    # Native Managed records exist before create_session returns. The attempt
    # must keep its identity when session_id arrives or creation fails.
    return "attempt-" + _identity(str(record.get("action", "")) + ":" +
                                   str(record.get("attempt_id", "")))


def project_attempt(record: dict, events: list, *, task_id: str,
                    turn_id: str | None = None, user_sequence: int = 1,
                    active: bool = False) -> list[dict]:
    """Project one saved attempt; callers retain the untouched raw evidence."""
    if record.get("requested_configuration", {}).get("wire_api") != WIRE_API:
        raise ExportError("MANAGED_ATTEMPT_REQUIRED")
    if record.get("execution_mode") != "production":
        raise ExportError("MANAGED_PRODUCTION_EVIDENCE_REQUIRED")
    if not isinstance(events, list):
        raise ExportError("MANAGED_EVENTS_INVALID")
    session = record.get("session_id")
    if not isinstance(session, str) or not session:
        raise ExportError("MANAGED_SESSION_ID_MISSING")
    run_id = "managed-" + _identity(session)
    phase = _phase(record.get("action"))
    unique = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get("id"), str):
            raise ExportError("MANAGED_EVENT_INVALID")
        if "encrypted" in event:
            raise ExportError("MANAGED_EVENTS_ENCRYPTED")
        prior = unique.get(event["id"])
        if prior is not None and prior != event:
            raise ExportError("MANAGED_EVENT_CHANGED")
        unique[event["id"]] = event
    ordered = sorted(
        (event for event in unique.values() if event.get("processed_at")),
        key=lambda event: (_timestamp(event["processed_at"]), event["processed_at"], event["id"]),
    )
    calls = {event["id"]: event for event in ordered if event.get("type") == "agent.custom_tool_use"}
    resolutions = {}
    for event in ordered:
        if event.get("type") == "user.custom_tool_result":
            call_id = event.get("custom_tool_use_id")
            if isinstance(call_id, str):
                resolutions[call_id] = event
    timeline = []
    for event in ordered:
        timestamp = _timestamp(event["processed_at"])
        row = {"id": "event-" + _identity(session + ":" + event["id"]),
               "runId": run_id, "phase": phase, "turnId": turn_id or _attempt_identity(record),
               "attemptId": _attempt_identity(record),
               "userSequence": user_sequence, "timestamp": timestamp, "rank": len(timeline)}
        kind = event.get("type")
        if kind == "agent.custom_tool_use":
            result = resolutions.get(event["id"])
            row.update(kind="tool", label=TOOL_LABELS.get(event.get("name"), "调用工具"),
                       toolKind="custom", status="running" if active and record.get("status") == "running" else "unconfirmed")
            if event.get("name") in OPERATIONS:
                row["operation"] = event["name"]
            if result is not None:
                finished = _timestamp(result["processed_at"])
                if finished < timestamp:
                    raise ExportError("MANAGED_RESULT_PRECEDES_CALL")
                row.update(status="failed" if result.get("is_error") is True else "returned", finishedAt=finished)
                if result.get("is_error") is True:
                    row["diagnosticCode"] = _tool_diagnostic(result)
        elif kind == "user.custom_tool_result":
            if event.get("custom_tool_use_id") in calls:
                continue
            row.update(kind="tool", label="调用工具", toolKind="custom", resultOnly=True,
                       status="failed" if event.get("is_error") is True else "returned", finishedAt=timestamp)
            if event.get("is_error") is True:
                row["diagnosticCode"] = _tool_diagnostic(event)
        elif kind == "span.model_request_end":
            row.update(kind="status", status="error" if event.get("is_error") is True else "running",
                       label="已收到模型响应的执行记录。")
        elif kind == "session.status_running":
            row.update(kind="status", status="running", label="托管会话开始执行。")
        elif kind == "session.status_idle":
            reason = (event.get("stop_reason") or {}).get("type")
            if reason == "requires_action":
                # Managed custom-tool handoff is not a human approval gate.
                row.update(kind="status", status="running", label="模型请求工具，等待本地执行回传。")
            elif reason == "end_turn":
                row.update(kind="status", status="ended", label="本轮托管会话已结束；业务交付以工作流状态为准。")
            elif reason == "retries_exhausted":
                row.update(kind="status", status="error", label="托管会话重试耗尽。")
            else:
                continue
        elif kind == "session.error":
            row.update(kind="status", status="error", label="托管会话返回执行异常。")
        elif kind == "session.deleted":
            row.update(kind="status", status="cancelled", label="托管会话已删除。")
        else:
            # user/agent text, thinking and arbitrary extension events are private.
            continue
        timeline.append(row)
    return timeline


def _writer_tool_counts(path: Path) -> dict:
    calls, receipts = set(), {}
    # This is the native writer's persisted, completed response shape. Reading
    # only call identities avoids counting resumed requests twice.
    for file in sorted(path.parent.glob("round_*_response.json")):
        response = json.loads(file.read_text(encoding="utf-8"))
        for call in response.get("tool_calls", []):
            if isinstance(call, dict) and isinstance(call.get("id"), str):
                calls.add(call["id"])
    for file in sorted(path.parent.glob("tool_*.json")):
        tool = json.loads(file.read_text(encoding="utf-8"))
        identity = tool.get("tool_call_id")
        if not isinstance(identity, str):
            continue
        calls.add(identity)
        result = tool.get("result")
        result = result if isinstance(result, dict) else {}
        if result.get("error") or result.get("ok") is False:
            receipts[identity] = "failed"
        elif tool.get("name") == "count_article" and type(result.get("body_characters")) is int and result["body_characters"] >= 0:
            receipts[identity] = "returned"
    returned = sum(value == "returned" for value in receipts.values())
    failed = sum(value == "failed" for value in receipts.values())
    return {"calls": len(calls), "returned": returned, "failed": failed,
            "unconfirmed": len(calls) - returned - failed}


def _attempt_summary(record: dict, path: Path, *, active: bool) -> dict:
    managed = record.get("requested_configuration", {}).get("wire_api") == WIRE_API
    sdk = record.get("requested_configuration", {}).get("wire_api") == SDK_WIRE_API
    identity = _attempt_identity(record)
    session = record.get("session_id")
    status = record.get("status")
    # A saved running flag is not proof that a process is still executing.
    status = status if status in {"succeeded", "failed"} or (status == "running" and active) else "unknown"
    summary = {"id": identity, "turnId": identity,
               "action": record.get("action") if record.get("action") in ACTIONS else "unknown",
               "phase": _phase(record.get("action")), "provider": "zhipu" if managed else "xty" if sdk else "deepseek",
               "status": status, "startedAt": _timestamp(record.get("started_at"))}
    end = record.get("finished_at") or record.get("completed_at")
    if not end and status == "failed":
        end = record.get("failed_at")
    if end:
        summary["finishedAt"] = _timestamp(end)
    if status == "failed":
        summary["diagnosticCode"] = _diagnostic(record.get("error"))
    previous = sorted(path.parent.glob("resume_*_previous_execution.json"))
    for file in previous:
        prior = json.loads(file.read_text(encoding="utf-8"))
        if (managed or sdk) and isinstance(session, str) and session and prior.get("session_id") == session and prior.get("attempt_id") == record.get("attempt_id"):
            summary["recovery"] = "same_session"
            if prior.get("status") == "failed":
                summary["recoveryDiagnosticCode"] = _diagnostic(prior.get("error"))
    if sdk:
        summary["toolSummaries"] = sdk_tool_summaries(path, identity, active=active)
    elif not managed:
        summary["toolCounts"] = _writer_tool_counts(path)
        summary["toolSummaries"] = writer_tool_summaries(path, identity)
    return summary


def _active_attempt(path: Path, record: dict, *, job_active: bool) -> bool:
    """Require the native action lock and its current attempt pointer.

    A retry can leave an older execution.json marked running. The job lock
    alone says nothing about which action or attempt owns current execution.
    """
    if not job_active or record.get("status") != "running":
        return False
    runtime = path.parents[2]
    latest, lock = runtime / "latest.json", runtime / "execution.lock"
    if not latest.is_file() or not lock.is_file():
        return False
    pointer = json.loads(latest.read_text(encoding="utf-8"))
    if pointer.get("attempt_id") != record.get("attempt_id") or record.get("attempt_id") != path.parent.name:
        return False
    with lock.open("r+b") as handle:
        try:
            with file_lock(handle, blocking=False):
                pass
        except BlockingIOError:
            return True
    return False


def export_job(job_dir: Path, *, task_id: str, turn_id: str | None = None,
               user_sequence: int = 1, active: bool = False) -> dict:
    timeline, attempts, records, sources = [], [], [], set()
    for path in sorted(job_dir.glob("provider/*/runtime/attempts/*/execution.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("execution_mode") != "production":
            continue
        configuration = record.get("requested_configuration", {})
        managed = configuration.get("wire_api") == WIRE_API
        sdk = configuration.get("wire_api") == SDK_WIRE_API
        if not managed and not sdk and configuration.get("provider") != "deepseek":
            continue
        attempt_active = _active_attempt(path, record, job_active=active)
        summary = _attempt_summary(record, path, active=attempt_active)
        if turn_id is not None:
            summary["turnId"] = turn_id
        attempts.append(summary)
        records.append((record, summary))
        sources.add("zhipu_managed" if managed else "openai_agents_sdk" if sdk else "deepseek_writer")
        if not managed:
            continue
        # Native startup persists events.json before the execution record gets
        # its session_id. Keep the stable attempt summary during that window;
        # event identities cannot be projected until the session is known.
        if not isinstance(record.get("session_id"), str) or not record["session_id"]:
            continue
        events_path = path.with_name("events.json")
        if not events_path.is_file():
            continue
        raw_events = events_path.read_bytes()
        expected = record.get("managed_evidence_sha256", {}).get("events.json")
        if expected and hashlib.sha256(raw_events).hexdigest() != expected:
            raise ExportError("MANAGED_EVENTS_HASH_MISMATCH")
        events = json.loads(raw_events)
        rows = project_attempt(record, events, task_id=task_id,
                               turn_id=turn_id, user_sequence=user_sequence, active=attempt_active)
        summary["thinking"] = project_thinking(record, events, rows)
        timeline.extend(rows)
    if not timeline and not attempts:
        raise ExportError("MANAGED_PRODUCTION_EVENTS_UNAVAILABLE")
    for record, summary in records:
        if summary.get("recovery") or record.get("retry_explicit") is not True:
            continue
        previous = [other for other_record, other in records if other["action"] == summary["action"]
                    and other["provider"] == summary["provider"] and other["status"] == "failed"
                    and other["startedAt"] < summary["startedAt"] and other["id"] != summary["id"]]
        if previous:
            summary["recovery"] = "new_attempt"
            summary["recoveryDiagnosticCode"] = max(previous, key=lambda item: item["startedAt"])["diagnosticCode"]
    cache = os.environ.get("FRONTMIND_PROCESS_SUMMARY_CACHE")
    summaries = cached_rows(cache, job_dir)
    native = {r["id"]:r for r in summary_sources(job_dir, 0)} if summaries else {}
    for attempt in attempts:
        accepted = []
        for row in summaries.values():
            source = native.get(row.get("id"))
            if not source or source["attemptId"] != attempt["id"] or row.get("sourceHash") != summary_identity(json.dumps(source["payload"], sort_keys=True, ensure_ascii=False)):
                continue
            if row.get("summaryState") == "ready" and safe_summary(row.get("text")):
                accepted.append({k:row[k] for k in ("id","kind","timestamp","sequence","text","revision") if k in row})
        attempt["modelSummaries"] = accepted
    attempts.sort(key=lambda row: (row["startedAt"], row["id"]))
    timeline.sort(key=lambda row: (row["timestamp"], row["runId"], row["rank"]))
    for rank, row in enumerate(timeline):
        row["rank"] = rank
    return {"schemaVersion": 1, "taskId": task_id, "coverage": "partial", "timeline": timeline,
            "attempts": attempts, "sources": sorted(sources)}



# Source facts remain available for unsummarized historical tools. Dynamic
# content is supplied only by the independent server-side summary API cache.
ACTION_TEXT = {
    "positioning_market_research": "公开资料研究", "positioning_value_synthesis": "品牌定位整理",
    "answer_analysis": "现有回答分析", "article_blueprint": "问题文章方案", "p0_blueprint": "品牌文章方案",
    "article_editorial_preparation": "案例研究与编辑准备", "article_polish": "问题文章终稿润色",
}
for prefix, title in (("article_", "问题文章"), ("p0_", "品牌文章")):
    for suffix, label in (("draft", "初稿"), ("edit", "编辑"), ("style", "润色"), ("finalize", "复核"),
                          ("repair", "修订"), ("titles", "标题"), ("title_review", "标题复核")):
        ACTION_TEXT[prefix + suffix] = title + label
TOOL_TEXT = {
    "list_materials": "查看材料目录", "read_material": "读取登记材料", "search_materials": "检索登记材料",
    "extract_document": "提取文档内容", "web_search": "检索公开来源", "web_read": "核对网页来源",
    "ocr": "识别图片文字", "submit_result": "提交阶段结果", "count_article": "检查文章字数",
}
DIAGNOSTIC_TEXT = {
    "non_public_address": ("来源地址未通过公网校验。", "检查网络解析或补充可核验材料；保留地址安全校验。"),
    "material_reference_missing": ("材料标识未登记。", "从材料目录复制准确标识后再读取。"),
    "material_reference_ambiguous": ("材料引用不唯一。", "从材料目录选择准确标识后再读取。"),
    "material_boundary_rejected": ("材料超出允许范围或内容已变更。", "重新登记并确认材料后继续。"),
    "invalid_tool_arguments": ("读取要求不符合约定。", "修正读取要求后再继续。"),
    "deterministic_tool_repeat": ("相同读取错误重复出现，已停止本次尝试。", "修正来源或材料标识后显式恢复。"),
    "tool_request_rejected": ("读取请求被拒绝，历史记录未保存具体原因。", "核对来源和登记材料；修正后显式恢复。"),
    "network_error": ("连接中断。", "检查连接后显式恢复。"),
    "http_error": ("服务请求失败。", "检查服务与账户配置后显式恢复。"),
    "invalid_result": ("阶段结果未通过校验。", "检查来源引用与结果格式后显式恢复。"),
    "source_unavailable": ("来源读取失败。", "检查来源或补充可核验材料。"),
    "retries_exhausted": ("服务重试已耗尽。", "检查服务状态后显式恢复。"),
    "execution_error": ("执行结果尚未确认。", "检查后台诊断后显式恢复。"),
}


def project_thinking(record: dict, events: list, rows: list) -> list[dict]:
    """Native thinking progress alone has no public content to project."""
    # Progress signals are not content. Dedicated API summaries are added from
    # the external cache; old records never pretend to have model summaries.
    return []


def writer_tool_summaries(path: Path, identity: str) -> list[dict]:
    calls, receipts = {}, {}
    for file in sorted(path.parent.glob("round_*_response.json")):
        response = json.loads(file.read_text(encoding="utf-8"))
        for call in response.get("tool_calls", []):
            if isinstance(call, dict) and isinstance(call.get("id"), str):
                calls.setdefault(call["id"], (call.get("function", {}).get("name"), int(file.stem.split("_")[1])*1000+800+len(calls)))
    for file in sorted(path.parent.glob("tool_*.json")):
        receipt = json.loads(file.read_text(encoding="utf-8"))
        call_id = receipt.get("tool_call_id")
        if isinstance(call_id, str):
            calls.setdefault(call_id, (receipt.get("name"), 100000+len(calls)))
            receipts[call_id] = receipt
    running = json.loads(path.read_text(encoding="utf-8")).get("status") == "running"
    rows = []
    for call_id, (name, sequence) in calls.items():
        result = receipts.get(call_id, {}).get("result", {})
        result = result if isinstance(result, dict) else {}
        pending = call_id not in receipts and running
        failed = bool(result.get("error") or result.get("ok") is False)
        returned = name == "count_article" and type(result.get("body_characters")) is int and result["body_characters"] >= 0
        prefix = "未能完成" if failed else "已完成" if returned else "结果未确认："
        row = {"id": identity + "-tool-" + _identity(call_id), "sequence": sequence,
               "text": "正在调用工具。" if pending else prefix + TOOL_TEXT.get(name, "处理工具结果") + "。",
               "status": "running" if pending else "failed" if failed else "completed" if returned else "unknown"}
        if failed:
            row["reason"], row["nextStep"] = DIAGNOSTIC_TEXT.get(_diagnostic(result), DIAGNOSTIC_TEXT["execution_error"])
        rows.append(row)
    return rows


def sdk_tool_summaries(path: Path, ident: str, *, active: bool) -> list[dict]:
    rows = []
    for evidence in sdk_tool_records(path.parent):
        call, receipt = evidence["call"], evidence["receipt"] or {}
        output = receipt.get("output")
        returned = receipt.get("status") == "completed"
        failed = returned and isinstance(output, dict) and (bool(output.get("error")) or output.get("ok") is False)
        status = "failed" if failed else "completed" if returned else "running" if active else "unknown"
        task = TOOL_TEXT.get(call.get("name"), "处理工具结果")
        prefix = {"failed":"未能完成", "completed":"已完成", "unknown":"结果未确认："}.get(status)
        row = {"id":ident+"-tool-"+_identity(call["call_id"]), "sequence":evidence["sequence"],
               "text":prefix+task+"。" if prefix else "正在调用工具。", "status":status}
        if returned and not failed and call.get("name") == "extract_document" and isinstance(output, dict) and output.get("image_text_status") == "not_extracted":
            row["pendingImageText"] = True
        timestamp = receipt.get("started_at")
        if timestamp:
            row["timestamp"] = _timestamp(timestamp)
        elif evidence["timestamp"] is not None:
            row["timestamp"] = evidence["timestamp"]
        if returned and receipt.get("completed_at"):
            row["finishedAt"] = _timestamp(receipt["completed_at"])
        if failed:
            row["reason"], row["nextStep"] = DIAGNOSTIC_TEXT.get(_diagnostic(output), DIAGNOSTIC_TEXT["execution_error"])
        rows.append(row)
    return rows


def conversation_projection(execution: dict) -> list[dict]:
    """Only business text, state, time and anonymous identities leave the server."""
    processes = []
    for attempt in execution.get("attempts", []):
        ident = attempt["id"]
        status = {"running": "running", "succeeded": "completed", "failed": "failed"}.get(attempt["status"], "unknown")
        title = ACTION_TEXT.get(attempt["action"], "工作流阶段")
        thoughts, tools = list(attempt.get("thinking", [])), list(attempt.get("toolSummaries", []))
        for row in execution.get("timeline", []):
            if row.get("attemptId") != ident or row["kind"] != "tool":
                continue
            text = TOOL_TEXT.get(row.get("operation"), "处理工具结果")
            state = row["status"]
            prefix = {"running": "正在", "returned": "已完成", "failed": "未能完成"}.get(state, "结果未确认：")
            item = {"id": row["id"], "timestamp": row["timestamp"], "text": "正在调用工具。" if state == "running" else prefix + text + "。",
                    "status": {"returned": "completed", "failed": "failed", "running": "running"}.get(state, "unknown")}
            if "finishedAt" in row:
                item["finishedAt"] = row["finishedAt"]
            if row.get("diagnosticCode"):
                item["reason"], item["nextStep"] = DIAGNOSTIC_TEXT.get(row["diagnosticCode"], DIAGNOSTIC_TEXT["execution_error"])
            tools.append(item)
        model_rows = {r["id"]:r for r in attempt.get("modelSummaries", [])}
        for item in tools:
            model = model_rows.get(item["id"])
            if model and safe_summary(model.get("text")):
                item.update(text=model["text"], summaryOrigin="model", summaryRevision=model["revision"])
        thoughts = [{k:r[k] for k in ("id","timestamp","sequence","text") if k in r} | {"status":"recorded", "summaryOrigin":"model", "summaryRevision":r["revision"]} for r in model_rows.values() if r["kind"] == "thinking"]
        process = {"id": ident, "startedAt": attempt["startedAt"], "status": status, "thinking": thoughts, "tools": tools}
        if attempt.get("finishedAt"):
            process["finishedAt"] = attempt["finishedAt"]
        if attempt.get("diagnosticCode"):
            process["reason"], process["nextStep"] = DIAGNOSTIC_TEXT.get(attempt["diagnosticCode"], DIAGNOSTIC_TEXT["execution_error"])
            if status == "failed" and process["reason"] == "执行结果尚未确认。":
                process["reason"] = "本轮执行失败。"
        if attempt.get("recovery"):
            process["recovery"] = "已沿用原会话恢复。" if attempt["recovery"] == "same_session" else "已创建新尝试；历史失败保留。"
        processes.append(process)
    return processes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-dir", type=Path, required=True, help="Original local Job directory (read-only)")
    parser.add_argument("--task-id", required=True, help="Application task to own the imported timeline")
    parser.add_argument("--output", type=Path, required=True, help="New public JSON file; never overwrite an existing file")
    parser.add_argument("--turn-id", help="Optional application turn identity; defaults to a stable hashed attempt identity")
    parser.add_argument("--user-sequence", type=int, default=1, help="Owning user-message sequence (default: 1)")
    args = parser.parse_args()
    try:
        if args.user_sequence < 1:
            raise ExportError("MANAGED_USER_SEQUENCE_INVALID")
        job_dir = args.job_dir.resolve(strict=True)
        output = args.output.resolve()
        if output.is_relative_to(job_dir):
            raise ExportError("MANAGED_OUTPUT_MUST_BE_OUTSIDE_JOB")
        value = export_job(job_dir, task_id=args.task_id, turn_id=args.turn_id,
                           user_sequence=args.user_sequence)
        public = {"schemaVersion": 2, "taskId": "task-" + _identity(args.task_id), "processes": conversation_projection(value)}
        with output.open("x", encoding="utf-8") as handle:
            json.dump(public, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except ExportError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, AttributeError):
        print("MANAGED_TIMELINE_EXPORT_FAILED", file=sys.stderr)
        return 1
    print(json.dumps({"output": str(output), "coverage": "partial", "entries": len(value["timeline"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
