"""Zhipu Managed Agents adapter (HTTP event history, not a chat-completions loop).

The platform owns model iteration. This client only provisions pinned resources,
reads durable events, dispatches the existing restricted HostTools and returns
custom-tool results. No built-in shell/file tools or model fallback are enabled.

A write with an uncertain acknowledgement is never blindly repeated. An existing
Session is resumed on explicit retry; history is reconciled before any resolution
is resent. Completed results are revalidated against the saved event evidence.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

BASE_URL = "https://agent-api.bigmodel.cn/api/agent/managed"
API_VERSION = "2026-05-26"
BETA_VERSION = "managed-agents-2026-05-26"
WIRE_API = "zhipu_managed_agents"
SCHEMA = "frontmind-managed-runtime/4.12.3-1"
MAX_HTTP_BYTES = 64 * 1024 * 1024
POLL_INTERVAL = 2.0
SESSION_SECONDS = 3600


def _rt():
    from . import model_runtime
    return model_runtime


def _fail(code: str, message: str, *, action: str = ""):
    return _rt().ProviderActionError(code, message, action=action)


def digest(value: Any) -> str:
    return hashlib.sha256(_rt()._json(value).encode("utf-8")).hexdigest()


def custom_tools(definitions: list[dict]) -> list[dict]:
    tools = []
    names = set()
    for tool in definitions:
        f = tool.get("function", {})
        name = f.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name) or name in names:
            raise _fail("managed_tool_schema", "托管工具名称缺失、重复或非法。")
        if name.startswith("mcp__"):
            raise _fail("managed_tool_schema", "自定义工具不能使用 MCP 保留前缀。")
        schema = f.get("parameters")
        if not isinstance(schema, dict) or schema.get("type") != "object" or not isinstance(schema.get("properties"), dict):
            raise _fail("managed_tool_schema", "托管自定义工具必须声明对象参数。")
        desc = f.get("description", "")
        if not isinstance(desc, str) or not 1 <= len(desc) <= 4096:
            raise _fail("managed_tool_schema", "托管工具说明长度不符合接口要求。")
        names.add(name)
        tools.append({"type": "custom", "name": name, "description": desc, "input_schema": schema})
    return tools


def request_plan(action: str, profile: dict, messages: list[dict], definitions: list[dict]) -> dict:
    """A fingerprintable API plan. Never sent as one Chat Completions request."""
    system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
    task = "\n\n".join(m["content"] for m in messages if m.get("role") == "user")
    if not system or len(system) > 100000:
        raise _fail("managed_system_invalid", "托管宿主系统提示为空或超过接口上限。", action=action)
    return {
        "wire_api": WIRE_API,
        "agent": {"name": "FrontMind " + action, "model": {"id": profile["model"], "effort": profile["effort"]},
                  "system": system, "tools": custom_tools(definitions)},
        "environment": {"name": "FrontMind restricted custom tools", "config": {
            "type": "cloud", "networking": {"type": "limited", "allowed_hosts": [],
                "allow_package_managers": False, "allow_mcp_servers": False}}},
        "user_event": {"type": "user.message", "content": [{"type": "text", "text": task}]},
    }


class ManagedClient:
    """Fixed-origin HTTP client. It never retries writes or follows redirects."""
    def __init__(self, api_key: str, *, timeout: int = 300):
        if not api_key:
            raise _fail("missing_api_key", "缺少智谱 API 凭据。")
        self.api_key, self.timeout = api_key, timeout
        self.opener = urllib.request.build_opener(_rt()._NoRedirect())

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        if not path.startswith("/v1/") or ".." in path or "\\" in path or "#" in path:
            raise _fail("managed_path_invalid", "托管请求路径非法。")
        headers = {"Authorization": "Bearer " + self.api_key, "zai-version": API_VERSION,
                   "zai-beta": BETA_VERSION, "Accept": "application/json"}
        data = None
        if body is not None:
            data = _rt()._json(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(BASE_URL + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as response:
                raw = response.read(MAX_HTTP_BYTES + 1)
            if len(raw) > MAX_HTTP_BYTES:
                raise _fail("managed_response_too_large", "托管接口返回超过安全容量。")
            result = _rt().strict_json(raw.decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError("object required")
            return result
        except urllib.error.HTTPError as exc:
            # Authentication details and provider text are deliberately not logged.
            if exc.code in (401, 403):
                raise _fail("managed_authentication_failed", f"智谱 Managed Agents 返回 HTTP {exc.code}；未切换模型。") from None
            raise _fail("managed_http_error", f"智谱 Managed Agents 返回 HTTP {exc.code}；请求未自动重发。") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, socket.gaierror):
                raise _fail("managed_dns_unresolved", "智谱Managed Agents域名解析失败，HTTP请求尚未发送，鉴权与工具执行均未验证。") from None
            code = "managed_write_outcome_unknown" if method != "GET" else "managed_network_error"
            raise _fail(code, "智谱托管接口网络请求未完成；保留会话和写入意图，禁止盲目重发。") from None
        except (UnicodeError, ValueError):
            raise _fail("managed_response_invalid", "托管接口响应不是完整 JSON 对象。") from None


def validate_agent_echo(agent: dict, plan: dict) -> None:
    expected = plan["agent"]
    model = agent.get("model")
    if not isinstance(model, dict) or model.get("id") != expected["model"]["id"] or model.get("effort") != expected["model"]["effort"]:
        raise _fail("managed_model_mismatch", "托管 Agent 回显模型或思考强度与指定配置不一致。")
    if agent.get("system") != expected["system"]:
        raise _fail("managed_configuration_mismatch", "托管 Agent 回显系统提示不一致。")
    actual_tools = agent.get("tools")
    if not isinstance(actual_tools, list) or any(t.get("type") != "custom" for t in actual_tools):
        raise _fail("managed_configuration_mismatch", "托管宿主意外启用了未授权的内置或 MCP 工具。")
    # Providers may add nullable metadata to tool objects; compare contract fields.
    projection = [{k: t.get(k) for k in ("type", "name", "description", "input_schema")} for t in actual_tools]
    if projection != expected["tools"]:
        raise _fail("managed_configuration_mismatch", "托管 Agent 回显工具合同不一致。")


def validate_session_echo(session: dict, state: dict, plan: dict) -> None:
    if session.get("id") != state["session_id"] or session.get("environment_id") != state["environment_id"]:
        raise _fail("managed_session_mismatch", "托管会话或环境标识不一致。")
    agent = session.get("agent", {})
    if agent.get("id") != state["agent_id"] or agent.get("version") != state["agent_version"]:
        raise _fail("managed_session_mismatch", "托管会话没有使用已固定的 Agent 版本。")
    validate_agent_echo(agent, plan)


def _identifier(value: Any, kind: str) -> str:
    # Opaque IDs are used only in fixed-origin resource paths.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", value):
        raise _fail("managed_identifier_invalid", f"托管 {kind} 标识缺失或非法。")
    return value


def _save_state(attempt: Path, state: dict) -> None:
    _rt()._atomic(attempt / "managed_state.json", state)


def _write(client, attempt: Path, state: dict, label: str, path: str, payload: dict) -> dict:
    """Write-ahead journal: an unknown POST result is not a licence to resend."""
    rt = _rt()
    name = f"http_{state.get('http_sequence', 0):04d}_{label}"
    state["http_sequence"] = state.get("http_sequence", 0) + 1
    state["pending_write"] = {"label": label, "path": path, "payload": payload, "journal": name}
    _save_state(attempt, state)
    rt._atomic(attempt / (name + "_request.json"), {"method": "POST", "path": path, "body": payload})
    try:
        result = client.request("POST", path, payload)
    except rt.ProviderActionError as exc:
        if exc.code == "managed_dns_unresolved":
            state["pending_write"] = None
            rt._atomic(attempt / (name + "_unsent.json"), {"code": exc.code, "request_sent": False})
            _save_state(attempt, state)
        raise
    rt._atomic(attempt / (name + "_response.json"), result)
    # Keep the returned value in the state before forgetting the intent.
    state["completed_writes"][label] = result
    state["pending_write"] = None
    _save_state(attempt, state)
    return result


def read_history(client, session_id: str, existing: list[dict]) -> list[dict]:
    """Replay from the timestamp boundary; deduplicate by authoritative event ID."""
    known = {e["id"]: e for e in existing}
    after = existing[-1].get("processed_at") if existing else None
    query: dict[str, Any] = {"order": "asc", "limit": 100}
    if after:
        query["created_at[gte]"] = after
    seen_pages = set()
    for _ in range(1000):
        page = client.request("GET", f"/v1/sessions/{session_id}/events?" + urllib.parse.urlencode(query))
        rows = page.get("data")
        if not isinstance(rows, list):
            raise _fail("managed_event_page_invalid", "托管历史事件页缺少 data 数组。")
        for event in rows:
            if not isinstance(event, dict) or not event.get("processed_at") or not isinstance(event.get("type"), str):
                raise _fail("managed_event_invalid", "托管事件缺少类型或处理时间。")
            eid = _identifier(event.get("id"), "事件")
            if "encrypted" in event:
                raise _fail("managed_encrypted_event", "当前客户端未配置业务事件解密，不能把密文作为完整材料。")
            if eid in known:
                if known[eid] != event:
                    raise _fail("managed_event_changed", "同一托管事件标识返回了不同内容。")
            else:
                existing.append(event)
                known[eid] = event
        cursor = page.get("next_page") or (page.get("pagination") or {}).get("next_page")
        # Listing APIs may expose the continuation as page; compatible envelopes
        # also use next_cursor. A full page without end/cursor metadata is unsafe.
        cursor = cursor or page.get("next_cursor") or page.get("page")
        if not cursor:
            if page.get("has_more") or (len(rows) >= query["limit"] and not any(k in page for k in ("page", "next_page", "next_cursor", "has_more", "pagination"))):
                raise _fail("managed_pagination_missing", "历史事件仍有下一页，但没有可用游标；停止而非丢弃事件。")
            return existing
        if not isinstance(cursor, str) or cursor in seen_pages:
            raise _fail("managed_pagination_invalid", "托管事件游标非法或循环。")
        seen_pages.add(cursor)
        query["page"] = cursor
    raise _fail("managed_history_limit", "托管历史事件超过读取上限。")


def _same_resolution(event: dict, pending: dict) -> bool:
    return (event.get("type") == "user.custom_tool_result" and
            event.get("custom_tool_use_id") == pending.get("custom_tool_use_id") and
            event.get("content", []) == pending.get("content", []) and
            bool(event.get("is_error", False)) == bool(pending.get("is_error", False)))


def _reconcile_pending(attempt: Path, state: dict, events: list[dict]) -> None:
    pending = state.get("pending_write")
    if not pending:
        return
    label = pending["label"]
    # A request acknowledgement may have reached disk immediately before a crash.
    response = attempt / (pending["journal"] + "_response.json")
    if response.is_file():
        state["completed_writes"][label] = _rt()._read_json(response)
        state["pending_write"] = None
        _save_state(attempt, state)
        return
    if label == "message":
        wanted = pending["payload"]["events"][0]
        if any(e.get("type") == "user.message" and e.get("content") == wanted["content"] for e in events):
            state["message_sent"] = True
            state["pending_write"] = None
    elif label.startswith("resolution_"):
        wanted = pending["payload"]["events"][0]
        if any(_same_resolution(e, wanted) for e in events):
            state["resolved_ids"].append(wanted["custom_tool_use_id"])
            state["pending_write"] = None
    if state.get("pending_write"):
        raise _fail("managed_write_outcome_unknown", "上次托管写入结果仍不确定，不能重复创建或重复投递。请核对该尝试的远端会话记录。")
    _save_state(attempt, state)


def _provision(client, attempt: Path, state: dict, plan: dict) -> None:
    if state.get("pending_write"):
        _reconcile_pending(attempt, state, [])
    done = state["completed_writes"]
    if not state.get("agent_id"):
        value = done.get("create_agent") or _write(client, attempt, state, "create_agent", "/v1/agents", plan["agent"])
        validate_agent_echo(value, plan)
        state.update(agent_id=_identifier(value.get("id"), "Agent"), agent_version=value.get("version"))
        if not isinstance(state["agent_version"], int) or state["agent_version"] < 1:
            raise _fail("managed_version_missing", "托管 Agent 未回显有效版本。")
        _save_state(attempt, state)
    if not state.get("environment_id"):
        value = done.get("create_environment") or _write(client, attempt, state, "create_environment", "/v1/environments", plan["environment"])
        state["environment_id"] = _identifier(value.get("id"), "环境")
        network = value.get("config", {}).get("networking", {})
        if network.get("type") != "limited" or network.get("allowed_hosts", []) or network.get("allow_mcp_servers") or network.get("allow_package_managers"):
            raise _fail("managed_environment_mismatch", "托管环境网络策略不符合受限配置。")
        _save_state(attempt, state)
    if not state.get("session_id"):
        payload = {"agent": {"type": "agent", "id": state["agent_id"], "version": state["agent_version"]},
                   "environment_id": state["environment_id"], "title": state["title"],
                   "metadata": {"frontmind_attempt": state["attempt_id"], "frontmind_action": state["action"]}}
        value = done.get("create_session") or _write(client, attempt, state, "create_session", "/v1/sessions", payload)
        state["session_id"] = _identifier(value.get("id"), "会话")
        validate_session_echo(value, state, plan)
        _save_state(attempt, state)


def _evidence_manifest(attempt: Path) -> dict[str, str]:
    names = ["request_plan.json", "events.json", "managed_state.json", "checkpoint.json", "session_final.json"]
    names += [p.name for p in sorted(attempt.glob("tool_*.json"))]
    names += [p.name for p in sorted(attempt.glob("http_*_response.json"))]
    return {name: _rt()._hash_file(attempt / name) for name in names if (attempt / name).is_file()}


def restore_result(attempt: Path, record: dict, tools, validator, *, verify_current_inputs: bool = True) -> dict:
    rt = _rt()
    rt.configure_host_tools(tools, (attempt / "prompt.md").read_text(encoding="utf-8"))
    manifest = record.get("managed_evidence_sha256")
    if not manifest or manifest != _evidence_manifest(attempt):
        raise ValueError("managed evidence changed or incomplete")
    plan = rt._read_json(attempt / "request_plan.json")
    state = rt._read_json(attempt / "managed_state.json")
    session = rt._read_json(attempt / "session_final.json")
    validate_session_echo(session, state, plan)
    if verify_current_inputs and not rt._dependencies_match(attempt.parents[4], record.get("dependencies", [])):
        raise ValueError("managed dependencies changed")
    events = rt._read_json(attempt / "events.json", [])
    submissions = [e for e in events if e.get("type") == "agent.custom_tool_use" and e.get("name") == "submit_result"]
    if len(submissions) != 1:
        raise ValueError("exactly one authoritative managed submission required")
    event = submissions[0]
    result = rt._submission_result(event.get("input"))
    stop = [e for e in events if e.get("type") == "session.status_idle"]
    if not stop or (stop[-1].get("stop_reason") or {}).get("type") != "end_turn":
        raise ValueError("managed session did not finish normally")
    if events.index(stop[-1]) < events.index(event):
        raise ValueError("managed completion precedes submission")
    if any(e.get("type") == "agent.custom_tool_use" for e in events[events.index(event)+1:]):
        raise ValueError("tool or repeated submission after final submit")
    resolved = [e for e in events if e.get("type") == "user.custom_tool_result" and e.get("custom_tool_use_id") == event["id"] and not e.get("is_error")]
    if not resolved:
        raise ValueError("managed final submission was not acknowledged")
    rt._restore_checkpoint(attempt, tools)
    tools.assert_required_reads_complete()
    checked = rt._checked(validator, result, tools)
    if rt._read_json(attempt / "parsed_result.json") != result or rt._read_json(attempt / "validated_result.json") != checked or digest(checked) != record.get("result_sha256"):
        raise ValueError("managed validated result differs from source event")
    return checked


def run_managed_action(package_root: Path, job_root: Path, action: str, prompt: str, validator,
                       retry: bool = False, *, host_tools=None, client=None, offline: bool = False) -> dict:
    rt = _rt()
    if client is not None and not offline:
        raise _fail("production_transport_override", "生产模式不允许注入托管响应。", action=action)
    if offline and client is None:
        raise _fail("missing_offline_transport", "离线托管测试必须显式提供模拟服务器。", action=action)
    profile = rt.profile_for(action)
    if profile.get("wire_api") != WIRE_API:
        raise _fail("managed_profile_invalid", "当前动作不是托管宿主路由。", action=action)
    config = {"api_key": "", "source": "explicit offline managed fixture"} if offline else rt.load_configuration(package_root, "zhipu")
    secrets = [config["api_key"]]
    for provider in ("zhipu", "deepseek"):
        c = rt.load_configuration(package_root, provider, required=False)
        if c.get("api_key"):
            secrets.append(c["api_key"])
    if any(key and key in prompt for key in secrets):
        raise _fail("credential_in_prompt", "任务输入含凭据，未发送或保存。", action=action)
    if host_tools is None:
        from .host_tools import HostTools
        host_tools = HostTools(package_root, job_root, action)
    rt.configure_host_tools(host_tools, prompt)
    defs = host_tools.definitions() if callable(host_tools.definitions) else host_tools.definitions
    definitions = defs + [rt.submit_tool_for(action, deep=rt._deep_prompt(action, prompt), prompt=prompt)]
    messages = rt._initial_messages(action, prompt)
    plan = request_plan(action, profile, messages, definitions)
    fingerprint = rt.request_fingerprint(action, prompt, tool_definitions=defs, offline=offline,
        context_hash=rt.context_fingerprint(job_root, action, host_tools))
    root = job_root / "provider" / action / "runtime"
    with rt.action_lock(root):
        matches = [(p.parent, rt._read_json(p, {})) for p in sorted((root / "attempts").glob("*/execution.json"), reverse=True)]
        matches = [(p, r) for p, r in matches if r.get("fingerprint") == fingerprint and r.get("requested_configuration", {}).get("wire_api") == WIRE_API]
        if matches:
            attempt, record = matches[0]
            if record.get("status") in ("succeeded", "result_complete"):
                try:
                    result = restore_result(attempt, record, host_tools, validator)
                except Exception:
                    raise _fail("cached_result_invalid", "托管缓存证据或正文校验失败，不能使用已存在文件冒充成功。", action=action) from None
                record.update(status="succeeded")
                rt._atomic(attempt / "execution.json", record)
                rt._atomic(root / "latest.json", {"attempt_id": attempt.name, "fingerprint": fingerprint})
                return result
            if not retry:
                raise _fail("managed_explicit_retry_required", "上次托管动作未完成；普通继续不会重复发起。请显式重试当前动作。", action=action)
            if (record.get("error") or {}).get("code") in {"invalid_result_contract", "managed_duplicate_submission", "managed_tool_after_submission"}:
                raise _fail("saved_submission_not_recoverable", "已完成提交存在内容或合同错误；需要修正上游输入，不能自动生成第二份终稿。", action=action)
            state = rt._read_json(attempt / "managed_state.json", {})
            if rt._read_json(attempt / "request_plan.json") != plan:
                raise _fail("managed_input_changed", "托管恢复输入与原请求不一致。", action=action)
            rt._restore_checkpoint(attempt, host_tools)
            rt._atomic(attempt / ("resume_%03d_previous_execution.json" % (record.get("resume_count", 0)+1)), record)
            record["resume_count"] = record.get("resume_count", 0) + 1
            record["retry_explicit"] = True
        else:
            aid = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "_" + uuid.uuid4().hex[:12]
            attempt = root / "attempts" / aid
            attempt.mkdir(parents=True)
            state = {"schema": SCHEMA, "action": action, "attempt_id": aid, "title": f"FrontMind {action} {aid}",
                     "completed_writes": {}, "pending_write": None, "resolved_ids": [], "tool_count": 0,
                     "message_sent": False, "submission": None, "http_sequence": 0}
            record = {"schema": SCHEMA, "action": action, "attempt_id": aid, "fingerprint": fingerprint,
                      "execution_mode": "offline_simulated" if offline else "production", "requested_configuration": profile,
                      "configuration_source": config["source"], "status": "running", "started_at": rt.utcnow(),
                      "dependencies": [], "rounds": [], "retry_explicit": bool(retry)}
            rt._atomic(attempt / "request_plan.json", plan)
            rt._atomic(attempt / "prompt.md", prompt)
            _save_state(attempt, state)
        rt._atomic(root / "latest.json", {"attempt_id": attempt.name, "fingerprint": fingerprint})
        record.update(status="running", error=None)
        rt._atomic(attempt / "execution.json", record)
        rt._record_inline_inputs(host_tools, messages)
        rt._checkpoint(attempt, messages, host_tools, state["tool_count"], state.get("submission"))
        client = client or ManagedClient(config["api_key"], timeout=profile["timeout_seconds"])
        deadline = time.monotonic() + SESSION_SECONDS
        try:
            if state.get("session_id"):
                events = read_history(client, state["session_id"], rt._read_json(attempt / "events.json", []))
                rt._atomic(attempt / "events.json", events)
                _reconcile_pending(attempt, state, events)
            _provision(client, attempt, state, plan)
            if "message" in state["completed_writes"]:
                state["message_sent"] = True
            if not state["message_sent"]:
                _write(client, attempt, state, "message", f"/v1/sessions/{state['session_id']}/events", {"events": [plan["user_event"]]})
                state["message_sent"] = True
                _save_state(attempt, state)
            while time.monotonic() < deadline:
                events = read_history(client, state["session_id"], rt._read_json(attempt / "events.json", []))
                rt._atomic(attempt / "events.json", events)
                # Persist progress without inventing a returned Chat Completion.
                spans = [e for e in events if e.get("type") == "span.model_request_end"]
                for e in spans:
                    model = e.get("model")
                    mid = model.get("id") if isinstance(model, dict) else model
                    if mid is not None and mid != profile["model"]:
                        raise _fail("managed_model_mismatch", "托管执行事件回显了不同模型。", action=action)
                record["rounds"] = [{"event_id": e["id"], "usage": e.get("model_usage", {}), "is_error": bool(e.get("is_error"))} for e in spans]
                record["session_id"] = state["session_id"]
                record["dependencies"] = rt._safe_deps(host_tools)
                rt._atomic(attempt / "execution.json", record)
                if len(spans) > rt.MAX_ROUNDS or state["tool_count"] > rt.MAX_TOOL_CALLS:
                    raise _fail("managed_execution_limit", "托管动作达到既定执行上限。", action=action)
                terminals = [e for e in events if e.get("type") == "session.error" and (e.get("error") or {}).get("retry_status") in {"terminal", "exhausted"}]
                if terminals:
                    raise _fail("managed_session_error", "托管会话报告终止错误；原始事件已保留。", action=action)
                lifecycles = [e for e in events if e.get("type") in {"session.status_running", "session.status_idle", "session.deleted"}]
                last = lifecycles[-1] if lifecycles else {}
                if last.get("type") == "session.deleted":
                    raise _fail("managed_session_deleted", "托管会话已被删除。", action=action)
                if last.get("type") == "session.status_idle":
                    reason = last.get("stop_reason") or {}
                    if reason.get("type") == "end_turn":
                        if state.get("submission") is None:
                            raise _fail("managed_missing_submission", "托管会话结束但未提交合法业务结果。", action=action)
                        session = client.request("GET", f"/v1/sessions/{state['session_id']}")
                        validate_session_echo(session, state, plan)
                        host_tools.assert_required_reads_complete()
                        result = rt._checked(validator, state["submission"], host_tools)
                        rt._atomic(attempt / "parsed_result.json", state["submission"])
                        rt._atomic(attempt / "validated_result.json", result)
                        rt._atomic(attempt / "session_final.json", session)
                        rt._checkpoint(attempt, messages, host_tools, state["tool_count"], state["submission"])
                        _save_state(attempt, state)
                        record.update(status="result_complete", finished_at=rt.utcnow(), dependencies=rt._safe_deps(host_tools),
                                      result_sha256=digest(result), resolved_model=session["agent"]["model"],
                                      usage=session.get("usage", {}), managed_evidence_sha256=_evidence_manifest(attempt))
                        rt._atomic(attempt / "execution.json", record)
                        restore_result(attempt, record, host_tools, validator)
                        record["status"] = "succeeded"
                        rt._atomic(attempt / "execution.json", record)
                        return result
                    if reason.get("type") == "retries_exhausted":
                        raise _fail("managed_retries_exhausted", "托管平台重试耗尽；未切换模型。", action=action)
                    if reason.get("type") == "requires_action":
                        ids = reason.get("event_ids")
                        if not isinstance(ids, list) or not ids:
                            raise _fail("managed_waiting_ids_missing", "托管会话未提供待处理调用标识。", action=action)
                        by_id = {e["id"]: e for e in events}
                        calls = [by_id.get(eid) for eid in ids]
                        if any(not e or e.get("type") != "agent.custom_tool_use" for e in calls):
                            raise _fail("managed_unexpected_approval", "托管会话请求了非本工作流允许的工具或审批。", action=action)
                        if any(e.get("name") == "submit_result" for e in calls) and len(calls) != 1:
                            raise _fail("managed_mixed_submission", "最终提交不能与读取工具放在同一批。", action=action)
                        for event in calls:
                            eid = event["id"]
                            if eid in state["resolved_ids"]:
                                continue
                            name, arguments = event.get("name"), event.get("input")
                            if not isinstance(arguments, dict):
                                raise _fail("managed_tool_arguments", "托管工具参数不是完整对象。", action=action)
                            tool_path = attempt / ("tool_" + eid + ".json")
                            old = rt._read_json(tool_path)
                            if old:
                                if old.get("source_event") != event:
                                    raise _fail("managed_tool_evidence_changed", "已执行工具的源事件发生变化。", action=action)
                                output = old["resolution"]
                                if old.get("host_state") is not None:
                                    host_tools.restore_state(old["host_state"])
                                if name == "submit_result":
                                    state["submission"] = old["business_result"]
                            else:
                                if state.get("submission") is not None:
                                    raise _fail("managed_tool_after_submission", "最终提交后又出现工具或重复提交，停止交付。", action=action)
                                if name == "submit_result":
                                    host_tools.assert_required_reads_complete()
                                    business = rt._submission_result(arguments)
                                    try:
                                        rt._checked(validator, business, host_tools)
                                    except Exception:
                                        rt._atomic(attempt / "rejected_submission.json", business)
                                        raise _fail("invalid_result_contract", "托管最终提交未通过当前内容合同；没有重复请求改稿。", action=action) from None
                                    state["submission"] = business
                                    tool_result = {"saved": True, "instruction": '只回复 {"submitted":true}，不要再调用工具。'}
                                    is_error = False
                                else:
                                    if name not in {d["function"]["name"] for d in defs}:
                                        raise _fail("managed_unknown_tool", "托管会话请求了未声明工具。", action=action)
                                    try:
                                        tool_result = host_tools.execute(name, arguments)
                                        is_error = False
                                    except Exception:
                                        tool_result = {"error": "tool_request_rejected", "message": "工具参数或读取范围不符合本任务要求。"}
                                        is_error = True
                                output = {"type": "user.custom_tool_result", "custom_tool_use_id": eid,
                                          "content": [{"type": "text", "text": rt._json(tool_result)}], "is_error": is_error}
                                if any(k and k in rt._json(output) for k in secrets):
                                    raise _fail("credential_in_tool_result", "工具结果含凭据，未回传。", action=action)
                                state["tool_count"] += 1
                                rt._atomic(tool_path, {"source_event": event, "resolution": output,
                                    "business_result": state.get("submission") if name == "submit_result" else None,
                                    "host_state": host_tools.export_state() if hasattr(host_tools, "export_state") else None})
                                rt._checkpoint(attempt, messages, host_tools, state["tool_count"], state.get("submission"))
                                _save_state(attempt, state)
                            if any(_same_resolution(e, output) for e in events):
                                state["resolved_ids"].append(eid)
                                _save_state(attempt, state)
                                continue
                            _write(client, attempt, state, "resolution_" + eid, f"/v1/sessions/{state['session_id']}/events", {"events": [output]})
                            state["resolved_ids"].append(eid)
                            _save_state(attempt, state)
                if not offline:
                    time.sleep(POLL_INTERVAL)
                elif getattr(client, "exhausted", False):
                    raise _fail("offline_events_exhausted", "模拟托管事件结束但没有完成结果。", action=action)
            raise _fail("managed_session_timeout", "托管动作超过本地等待时限；会话保留，显式重试会先回读历史。", action=action)
        except Exception as exc:
            code = exc.code if isinstance(exc, rt.ProviderActionError) else "managed_local_error"
            message = str(exc) if isinstance(exc, rt.ProviderActionError) else "托管动作本地处理失败；证据保留，未回退其他模型。"
            record.update(status="failed", error={"code": code, "message": rt.redact(message, secrets)}, failed_at=rt.utcnow(), dependencies=rt._safe_deps(host_tools))
            rt._atomic(attempt / "execution.json", record)
            if isinstance(exc, rt.ProviderActionError):
                exc.action, exc.attempt_id = action, attempt.name
                raise
            raise _fail(code, message, action=action) from None
