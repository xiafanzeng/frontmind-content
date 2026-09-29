"""FrontMind's local, durable OpenAI Agents SDK host (not a remote Agent service).

The SDK controls model/tool iteration. FrontMind retains business validation,
read permissions and explicit retries. Approval interruptions are internal write-
ahead boundaries; they do NOT add human review stages or approve business choices.
Only server-owned local RunState files are deserialized. Hashes detect corruption,
not malicious rewriting by someone with filesystem access.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import importlib.metadata
import inspect
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

WIRE_API = "openai_agents_sdk"
SDK_VERSION = "0.22.3"
OPENAI_VERSION = "3.16.2"
CONTRACT = "frontmind-agents-runtime/4.13.4-local.3"
# Local fix 2026-09-21: a submit_result that fails content validation is now
# returned to the model as durable bounded tool feedback instead of killing the
# run, and the agent no longer hard-stops at submit_result, so the model can
# correct and resubmit inside the same paid run; a resume replays the recorded
# feedback instead of dead-looping on the same pending call.
# Request identity is deliberately stable: CONTRACT is implementation metadata,
# not a prompt/input change. Existing 4.13.0/4.13.1 checkpoints retain their exact
# plan and fingerprint; never create another paid attempt merely for this patch.
REQUEST_CONTRACT = "frontmind-agents-runtime/4.13.0-1"
READONLY_REPLAY_TOOLS = frozenset({"list_materials", "read_material", "search_materials"})
DEFAULT_MODEL = "gpt-5.6-sol"  # User-directed host since 2026-09-21 evening; claude-sonnet-5 gateway pool dropped every large request that night (524/404/conn-kill).
# Optional config/xty.json "completion_transport": "stream_merged" makes the
# gateway HTTP call streamed and merges chunks back into one completion here,
# because the gateway's proxy kills any NON-streamed response at ~120s while
# blueprint submit turns legitimately need 3-5 minutes. Guards, journaling and
# the SDK conversion above the client are unchanged. Absent value keeps the
# legacy non-streamed wire path bit-for-bit.
STREAM_TRANSPORT = "stream_merged"
DEFAULT_BASE_URL = "https://api.xty.app/v1"
PROTOCOL = """\n本次宿主运行在本地 OpenAI Agents SDK。只使用列出的工具；工具调用由SDK处理，不输出假工具回执。
必须先完成所需原文读取，最后单独调用一次submit_result提交完整业务对象；成功提交即结束，不再另写稿件。
任务已有的用户确认仍由FrontMind控制，不能代替用户决定。不要调用未提供的shell、代码、远端会话或文件管理工具。
"""


def _rt():
    from . import model_runtime
    return model_runtime


def digest(value: Any) -> str:
    return hashlib.sha256(_rt()._json(value).encode()).hexdigest()


def fail(code: str, message: str):
    return _rt().ProviderActionError(code, message)


def public_profile(package_root: Path | str | None = None) -> dict:
    """Read no secret into the returned fingerprintable model configuration."""
    root = Path(package_root) if package_root else Path(__file__).resolve().parents[1]
    path = root / "config/xty.json"
    data = _rt()._read_json(path, {})
    if not isinstance(data, dict):
        raise fail("invalid_host_configuration", "config/xty.json 必须是JSON对象。")
    base = data.get("base_url", DEFAULT_BASE_URL)
    model = data.get("model", DEFAULT_MODEL)
    if not isinstance(base, str):
        raise fail("invalid_gateway_url", "网关base_url必须是HTTPS地址。")
    try:
        url = urlsplit(base)
        port = url.port
    except ValueError as exc:
        raise fail("invalid_gateway_url", "网关URL或端口格式无效。") from exc
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or port not in (None, 443):
        raise fail("invalid_gateway_url", "网关必须使用无用户信息、无查询参数的HTTPS地址；不跟随重定向。")
    if not url.path.rstrip("/").endswith("/v1"):
        raise fail("invalid_gateway_url", "网关base_url必须指向/v1，不是文档地址或/chat/completions。")
    if not isinstance(model, str) or not model.strip() or len(model) > 200 or model != model.strip() or any(c.isspace() for c in model):
        raise fail("invalid_host_model", "必须配置一个明确的模型ID；不自动替换或降级。")
    limits = {}
    for key, default, low, high in (("timeout_seconds",300,5,1800),("max_turns",40,1,100),("max_tool_calls",200,1,1000),("max_tokens",16384,256,131072)):
        value = data.get(key, default)
        if type(value) is not int or not low <= value <= high:
            raise fail("invalid_host_configuration", f"{key}必须在{low}到{high}之间。")
        limits[key] = value
    transport = data.get("completion_transport")
    if transport is not None and transport != STREAM_TRANSPORT:
        raise fail("invalid_host_configuration", f"completion_transport只支持{STREAM_TRANSPORT}或省略(非流式)。")
    effort = data.get("reasoning_effort")
    if effort is not None and effort not in {"low", "medium", "high"}:
        raise fail("invalid_host_configuration", "reasoning_effort只支持low/medium/high或省略(模型默认档)。")
    backup_model = data.get("backup_model")
    if backup_model is not None and (not isinstance(backup_model, str) or not backup_model.strip()
            or len(backup_model) > 200 or backup_model != backup_model.strip() or any(c.isspace() for c in backup_model)):
        raise fail("invalid_host_configuration", "backup_model必须是明确的模型ID或省略。")
    backup_effort = data.get("backup_reasoning_effort")
    if backup_effort is not None:
        if backup_model is None:
            raise fail("invalid_host_configuration", "backup_reasoning_effort需要先配置backup_model。")
        if backup_effort not in {"low", "medium", "high", "max"}:
            raise fail("invalid_host_configuration", "backup_reasoning_effort只支持low/medium/high/max或省略。")
    profile = {"provider":"xty", "wire_api":WIRE_API, "api_url":base.rstrip("/")+"/chat/completions", "base_url":base.rstrip("/"),
            "model":model, "openai_version":OPENAI_VERSION, "sdk_version":SDK_VERSION, "model_api":"chat_completions", "automatic_retries":0,
            "tracing_disabled":True, "parallel_tool_calls":False, **limits}
    # Only present when configured; it changes wire behavior and must change the fingerprint.
    if transport is not None:
        profile["completion_transport"] = STREAM_TRANSPORT
    if effort is not None:
        profile["reasoning_effort"] = effort
    return profile


def backup_profile(package_root: Path | str | None = None) -> dict | None:
    """Secondary host profile used ONLY for transport-class failures.

    Never a quality downgrade or an automatic provider switch: same gateway,
    same wire contract, same guards; only the model (and optionally its
    reasoning effort) differs, and every attempt records its own identity.
    """
    primary = public_profile(package_root)
    root = Path(package_root) if package_root else Path(__file__).resolve().parents[1]
    data = _rt()._read_json(root / "config/xty.json", {})
    model = data.get("backup_model") if isinstance(data, dict) else None
    if not isinstance(model, str) or not model:
        return None
    profile = dict(primary)
    profile["model"] = model
    effort = data.get("backup_reasoning_effort")
    if effort is not None:
        profile["reasoning_effort"] = effort
    else:
        profile.pop("reasoning_effort", None)
    return profile


def _transport_message_failure(message: str) -> bool:
    """Recognize explicit transport errors, including persisted gateway 408s.

    A known non-transport HTTP status wins over incidental wording in its body.
    This helper is used for legacy records only after checking their error code.
    """
    text = message.lower()
    status = re.search(r"\berror code:\s*(\d{3})\b", text)
    if status:
        code = int(status.group(1))
        return code == 408 or 500 <= code <= 599
    return ("connection error" in text
            or "stream disconnected before completion" in text
            or bool(re.search(r"stream closed before [^\r\n]{0,120}\.completed\b", text))
            or "offline simulated lost response" in text)


def _transport_failure(exc: BaseException) -> bool:
    """Classify gateway/network transport failures eligible for backup failover.

    Content-contract, tool-protocol and budget errors never qualify: those mean
    the model answered; retrying on another model is a paid rework decision.
    """
    if isinstance(exc, _rt().ProviderActionError):
        return False
    chain = []
    node = exc
    while node is not None and len(chain) < 6 and all(node is not item for item in chain):
        # A backup executes inside the primary error handler. Its implicit
        # context may contain the previous ProviderActionError, which must not
        # override the backup's own exception or leak earlier error wording.
        if isinstance(node, _rt().ProviderActionError):
            break
        chain.append(node)
        if isinstance(node.__cause__, _rt().ProviderActionError):
            return False
        node = node.__cause__ or (None if node.__suppress_context__ else node.__context__)
    try:
        import openai as _openai
    except Exception:
        _openai = None
    if _openai is not None:
        for node in chain:
            if isinstance(node, (_openai.APIConnectionError, _openai.APITimeoutError)):
                return True
            if isinstance(node, _openai.APIStatusError):
                try:
                    return node.status_code == 408 or 500 <= node.status_code <= 599
                except Exception:
                    pass
    return any(_transport_message_failure(str(node)) for node in chain)


def request_plan(action: str, profile: dict, messages: list, definitions: list) -> dict:
    return {"contract":REQUEST_CONTRACT, "action":action, "profile":profile,
            "instructions":"\n\n".join(m["content"] for m in messages if m["role"]=="system")+PROTOCOL,
            "input":[copy.deepcopy(m) for m in messages if m["role"]!="system"],
            "tools":copy.deepcopy(definitions), "session_storage":"local_sqlite",
            "checkpoint":"sdk_run_state_before_each_tool_batch", "stop_at_tool_names":["submit_result"]}


def fingerprint(plan: dict, context_hash: str, offline: bool) -> str:
    return digest({"plan":plan,"context_hash":context_hash,"execution_mode":"offline_simulated" if offline else "production"})


def _write(path: Path, value: Any) -> None:
    # No keys should reach any persisted SDK/context data. Caller also compares exact secrets.
    _rt()._atomic(path,value)
    try: path.chmod(0o600)
    except OSError: pass


def _safe_json(value: Any, secrets: list[str]) -> Any:
    text = _rt()._json(value)
    if any(secret and secret in text for secret in secrets):
        raise fail("credential_in_runtime_data", "模型或工具数据包含凭据，未写入会话。")
    return value


def _sdk():
    """Lazy import: status/old artifacts can be inspected without starting an SDK."""
    try:
        import agents
        import openai
    except ImportError as exc:
        raise fail("agents_sdk_missing", "缺少运行依赖；请在虚拟环境运行 python -m pip install -r requirements.txt。") from exc
    version = importlib.metadata.version("openai-agents")
    if version != SDK_VERSION:
        raise fail("agents_sdk_version_mismatch", f"当前动作需openai-agents=={SDK_VERSION}；跨版本恢复前需使用原版本。")
    if importlib.metadata.version("openai") != OPENAI_VERSION:
        raise fail("openai_client_version_mismatch", f"当前动作需openai=={OPENAI_VERSION}；请安装包内requirements.txt。")
    return agents, openai


def _output_items(response: Any) -> list:
    return [x.model_dump(mode="json") if hasattr(x,"model_dump") else copy.deepcopy(x) for x in response.output]


def _calls(output: list) -> list[dict]:
    return [x for x in output if isinstance(x,dict) and x.get("type")=="function_call"]


def _source_call(attempt: Path, call_id: str, name: str, arguments: dict) -> dict:
    found = []
    for path in sorted(attempt.glob("model_*_response.json")):
        row = _rt()._read_json(path,{})
        for call in _calls(row.get("output",[])):
            if call.get("call_id")==call_id:
                if call.get("name")!=name or _rt().strict_json(call.get("arguments",""))!=arguments:
                    raise fail("tool_call_source_mismatch", "工具调用与保存的模型输出不一致。")
                found.append({"file":path.name,"sha256":_rt()._hash_file(path)})
    if not found:
        raise fail("tool_call_without_model_evidence", "没有找到该工具调用的原始模型输出，未执行。")
    return found[-1]


def _restore_tools(attempt: Path, tools: Any, state: dict) -> None:
    tools.restore_state(state)
    # HostTools intentionally drops saved inline-read assertions. Recompute
    # from the complete original input rather than trusting cached claims.
    plan=_rt()._read_json(attempt/"request_plan.json")
    _rt()._record_inline_inputs(tools,[{"role":"system","content":plan["instructions"]}]+plan["input"])


class ToolJournal:
    """At-most-once for a *completed* call ID. Unknown side effects stop closed.

    Only the three local read-only tools may replay a started-only receipt on
    explicit action resume. External/writing/submission tools still fail closed.
    A known HostTools contract error becomes a durable model-visible receipt;
    unexpected exceptions propagate rather than concealing unknown side effects.

    Local fix 2026-09-21: a *final submit* that fails content validation also
    becomes durable model-visible feedback (bounded per run) instead of a fatal
    error: the model gets the exact validator message and may resubmit inside
    the same paid run. No success receipt is written until validation passes,
    so plain text still cannot impersonate a business result.
    """
    SUBMIT_FEEDBACK_LIMIT = 3

    def __init__(self, attempt: Path, record: dict, tools: Any, validator: Any, secrets: list[str]):
        self.attempt,self.record,self.tools,self.validator,self.secrets=attempt,record,tools,validator,secrets
        self.lock=asyncio.Lock()
        self.submit_feedback_count=0

    async def invoke(self, name: str, call_id: str, text: str) -> str:
        rt=_rt()
        async with self.lock:
            if not isinstance(call_id,str) or not call_id:
                raise fail("missing_tool_call_id", "SDK未提供工具调用ID。")
            args=rt.strict_json(text)
            if not isinstance(args,dict):
                raise fail("invalid_tool_arguments", "工具参数必须是一个完整JSON对象。")
            _safe_json(args,self.secrets)
            source=_source_call(self.attempt,call_id,name,args)
            path=self.attempt/("tool_"+hashlib.sha256(call_id.encode()).hexdigest()+".json")
            prior=rt._read_json(path)
            signature=digest({"name":name,"arguments":args,"call_id":call_id})
            if prior is not None:
                if prior.get("signature")!=signature:
                    raise fail("tool_call_id_reused", "同一工具ID携带不同参数，未执行。")
                if prior.get("status")=="completed":
                    _restore_tools(self.attempt,self.tools,prior["host_state"])
                    if name=="submit_result":
                        prior_output=prior.get("output")
                        if isinstance(prior_output,dict) and prior_output.get("submitted"):
                            result=rt._submission_result(prior["arguments"])
                            checked=rt._checked(self.validator,result,self.tools)
                            _write(self.attempt/"submission.json",{"call_id":call_id,"tool_file":path.name,"result":result,"checked":checked,"source":source})
                            _write(self.attempt/"parsed_result.json",result)
                            _write(self.attempt/"validated_result.json",checked)
                        # else: a completed FEEDBACK receipt for this call ID. Replay
                        # it verbatim; these arguments were already rejected, so do
                        # not re-validate them as if they were a success receipt.
                    return rt._json(prior["output"])
                if prior.get("status")!="started" or name not in READONLY_REPLAY_TOOLS:
                    raise fail("tool_outcome_unknown", "上次工具已开始但没有完整回执；此工具不属于本地只读白名单，未自动重做。请先核对运行记录。")
                # Re-execute through HostTools, not from guessed/cached text:
                # registry, path, credential and content hashes are rechecked.
                # Keep the prior marker's timing/source in the replacement receipt.
            if (self.attempt/"submission.json").exists():
                sub=rt._read_json(self.attempt/"submission.json")
                if name=="submit_result" and isinstance(sub,dict) and sub.get("tool_file"):
                    prior_sub=rt._read_json(self.attempt/sub["tool_file"],{})
                    if prior_sub.get("arguments")==args:
                        return rt._json({"submitted":True})
                # The validated final result is already durable; later tool calls
                # cannot change it. Answer with feedback so the model ends its run
                # cleanly instead of crashing a finished action.
                output={"ok":False,"error":"already_submitted","message":"最终提交已完成；请直接结束，不再调用任何工具。"}
                _write(path,{"call_id":call_id,"name":name,"arguments":args,"signature":signature,"source":source,"status":"completed",
                             "output":output,"host_state":self.tools.export_state(),"completed_at":rt.utcnow()})
                return rt._json(output)
            if prior is None and len(list(self.attempt.glob("tool_*.json")))>=self.record["requested_configuration"]["max_tool_calls"]:
                raise fail("tool_limit", "达到当前动作工具次数上限。")
            row={"call_id":call_id,"name":name,"arguments":args,"signature":signature,"source":source,"status":"started","started_at":rt.utcnow()}
            if prior is not None:
                history=list(prior.get("readonly_replay_history", []))
                history.append({"started_at":prior.get("started_at"), "source":prior.get("source")})
                row.update(readonly_replay_count=len(history), readonly_replay_history=history,
                           replay_policy="local_readonly_started_only")
            # Validate a final result BEFORE the write-ahead side-effect marker.
            if name=="submit_result":
                try:
                    result=rt._submission_result(args)
                    self.tools.assert_required_reads_complete()
                    checked=rt._checked(self.validator,result,self.tools)
                except Exception as exc:
                    message="最终提交不符合原有业务或全文读取合同："+rt.redact(str(exc),self.secrets)
                    self.submit_feedback_count+=1
                    if self.submit_feedback_count>self.SUBMIT_FEEDBACK_LIMIT:
                        raise fail("invalid_result_contract", message+f"（已反馈{self.SUBMIT_FEEDBACK_LIMIT}次仍未通过，终止本动作；请修正上游输入后再试。）") from exc
                    output={"ok":False,"error":"invalid_result_contract","message":message,
                            "retry_instruction":f"请修正上述合同问题后，重新单独调用submit_result提交完整JSON（第{self.submit_feedback_count}/{self.SUBMIT_FEEDBACK_LIMIT}次反馈；达上限未通过将终止）。"}
                    # Durable feedback receipt: a resume replays this exact feedback
                    # (same call ID + arguments) instead of re-validating the same
                    # dead pending call forever. submission.json stays absent, so no
                    # success is claimed and plain text still cannot impersonate it.
                    _write(path,row)
                    row.update(status="completed",output=output,host_state=self.tools.export_state(),completed_at=rt.utcnow())
                    _write(path,_safe_json(row,self.secrets))
                    return rt._json(output)
                output={"submitted":True}
            _write(path,row)
            if name!="submit_result":
                from .host_tools import ToolError
                try:
                    output=await asyncio.to_thread(self.tools.execute,name,args)
                except ToolError as exc:
                    if getattr(exc, "outcome_unknown", False):
                        # HostTools transport failures used to share ToolError;
                        # do not turn an ambiguous paid call into retry feedback.
                        raise fail("tool_outcome_unknown", "外部工具结果未完整取得，保留started记录，未自动重做：" + rt.redact(str(exc), self.secrets)) from exc
                    # A known contract/read error is feedback, not a crashed run.
                    # Do not catch arbitrary I/O/provider failures here: an absent
                    # receipt for those may hide a charge or a filesystem effect.
                    output={"ok":False, "error":getattr(exc,"code","tool_error"),
                            "message":rt.redact(str(exc),self.secrets)[:3000]}
            state=self.tools.export_state()
            row.update(status="completed",output=output,host_state=state,completed_at=rt.utcnow())
            _write(path,_safe_json(row,self.secrets))
            if name=="submit_result":
                _write(self.attempt/"submission.json",{"call_id":call_id,"tool_file":path.name,"result":result,"checked":checked,"source":source})
                _write(self.attempt/"parsed_result.json",result)
                _write(self.attempt/"validated_result.json",checked)
            return rt._json(output)


async def _consume_stream(stream: Any) -> list[dict]:
    """Drain a gateway chat.completions stream into raw chunk dicts."""
    chunks: list[dict] = []
    async for chunk in stream:
        chunks.append(chunk.model_dump(mode="json") if hasattr(chunk, "model_dump") else copy.deepcopy(chunk))
    if not chunks:
        raise fail("stream_response_incomplete", "网关响应流未返回任何chunk即结束；断点已保留。")
    return chunks


def _merge_streamed_completion(chunks: list[dict]) -> dict:
    """Rebuild one non-streaming chat.completion shape from streamed chunks.

    Only standard fields are reconstructed (role, content, tool_calls with
    concatenated argument fragments, finish_reason, usage from the final
    chunk). Gateway extras such as reasoning_content are preserved in the
    message only so the wire receipt stays faithful; the SDK ignores them.
    """
    merged: dict[int, dict] = {}
    usage = None; model = None; cid = None; created = None
    for chunk in chunks:
        model = model or chunk.get("model")
        cid = cid or chunk.get("id")
        created = created or chunk.get("created")
        if chunk.get("usage"):
            usage = chunk["usage"]
        for choice in chunk.get("choices") or []:
            slot = merged.setdefault(choice.get("index", 0),
                                     {"role": None, "content": None, "reasoning_content": None,
                                      "tool_calls": {}, "finish_reason": None})
            delta = choice.get("delta") or {}
            if delta.get("role") and slot["role"] is None:
                slot["role"] = delta["role"]
            if delta.get("content"):
                slot["content"] = (slot["content"] or "") + delta["content"]
            if delta.get("reasoning_content"):
                slot["reasoning_content"] = (slot["reasoning_content"] or "") + delta["reasoning_content"]
            for call in delta.get("tool_calls") or []:
                index = call.get("index", 0)
                target = slot["tool_calls"].setdefault(index,
                        {"id": None, "type": "function", "name": None, "arguments": ""})
                if call.get("id"):
                    target["id"] = call["id"]
                function = call.get("function") or {}
                if function.get("name"):
                    target["name"] = function["name"]
                if function.get("arguments"):
                    target["arguments"] += function["arguments"]
            if choice.get("finish_reason"):
                slot["finish_reason"] = choice["finish_reason"]
    choices_out = []
    for index in sorted(merged):
        slot = merged[index]
        message: dict[str, Any] = {"role": slot["role"] or "assistant", "content": slot["content"]}
        if slot["reasoning_content"] is not None:
            message["reasoning_content"] = slot["reasoning_content"]
        if slot["tool_calls"]:
            message["tool_calls"] = [
                {"id": slot["tool_calls"][i]["id"], "type": "function",
                 "function": {"name": slot["tool_calls"][i]["name"] or "",
                              "arguments": slot["tool_calls"][i]["arguments"]}}
                for i in sorted(slot["tool_calls"])]
        choices_out.append({"index": index, "message": message, "finish_reason": slot["finish_reason"]})
    return {"id": cid or "stream-merged", "object": "chat.completion", "created": created or 0,
            "model": model or "unknown", "choices": choices_out, "usage": usage}


def _streamed_completion_object(oa: Any, raw: dict) -> Any:
    """Build a ChatCompletion instance from the merged shape without validation."""
    completion_types = oa.types.chat.chat_completion
    function_type = oa.types.chat.chat_completion_message_function_tool_call.Function
    choices = []
    for choice in raw["choices"]:
        message = choice["message"]
        tool_calls = None
        if message.get("tool_calls") is not None:
            tool_calls = [oa.types.chat.ChatCompletionMessageToolCall.construct(
                    id=call["id"], type=call["type"],
                    function=function_type.construct(
                        name=call["function"]["name"], arguments=call["function"]["arguments"]))
                for call in message["tool_calls"]]
        choices.append(completion_types.Choice.construct(
            index=choice["index"], finish_reason=choice["finish_reason"],
            message=completion_types.ChatCompletionMessage.construct(
                role=message["role"], content=message.get("content"), tool_calls=tool_calls)))
    usage = None
    if raw.get("usage"):
        u = raw["usage"]
        usage = completion_types.CompletionUsage.construct(
            prompt_tokens=u.get("prompt_tokens") or 0, completion_tokens=u.get("completion_tokens") or 0,
            total_tokens=u.get("total_tokens") or 0)
    return completion_types.ChatCompletion.construct(id=raw["id"], object=raw["object"], created=raw["created"],
                                         model=raw["model"], choices=choices, usage=usage)


def evidence_manifest(attempt: Path) -> dict:
    names=["request_plan.json","submission.json","checkpoint.json","completion.json","parsed_result.json","validated_result.json"]
    names += [p.name for pattern in ("model_*_request.json","model_*_response.json","model_*_wire.json","tool_*.json") for p in sorted(attempt.glob(pattern))]
    return {n:_rt()._hash_file(attempt/n) for n in sorted(names) if (attempt/n).is_file()}


def restore_result(attempt: Path, record: dict, tools: Any, validator: Any, *, verify_current_inputs: bool=True) -> dict:
    rt=_rt()
    rt.configure_host_tools(tools,(attempt/"prompt.md").read_text(encoding="utf-8"))
    if not record.get("agents_evidence_sha256") or record["agents_evidence_sha256"]!=evidence_manifest(attempt):
        raise ValueError("Agents evidence missing or changed")
    plan=rt._read_json(attempt/"request_plan.json")
    if plan.get("profile")!=record.get("requested_configuration"):
        raise ValueError("model configuration changed")
    completion=rt._read_json(attempt/"completion.json",{})
    if completion.get("status")!="submitted": raise ValueError("SDK did not complete submission")
    sub=rt._read_json(attempt/"submission.json",{})
    if not isinstance(sub.get("tool_file"),str) or Path(sub["tool_file"]).name!=sub["tool_file"]: raise ValueError("bad receipt path")
    receipt=rt._read_json(attempt/sub["tool_file"],{})
    if receipt.get("name")!="submit_result" or receipt.get("status")!="completed" or receipt.get("call_id")!=sub.get("call_id"):
        raise ValueError("invalid final receipt")
    source=_source_call(attempt,sub["call_id"],"submit_result",receipt["arguments"])
    if source!=sub.get("source"): raise ValueError("submission source changed")
    if verify_current_inputs and not rt._dependencies_match(attempt.parents[4],record.get("dependencies",[])):
        raise ValueError("source inputs changed")
    _restore_tools(attempt,tools,receipt["host_state"])
    tools.assert_required_reads_complete()
    result=rt._submission_result(receipt["arguments"])
    checked=rt._checked(validator,result,tools)
    if result!=sub["result"] or checked!=sub["checked"] or result!=rt._read_json(attempt/"parsed_result.json") or checked!=rt._read_json(attempt/"validated_result.json") or digest(checked)!=record.get("result_sha256"):
        raise ValueError("result differs from model submission")
    return checked


async def execute_sdk(plan: dict, attempt: Path, record: dict, tools: Any, validator: Any, config: dict, secrets: list[str], *, sdk_override=None) -> dict:
    """Real Agent/Runner execution; sdk_override is accepted ONLY by offline caller."""
    rt=_rt()
    ag,oa=sdk_override if sdk_override is not None else _sdk()
    profile=plan["profile"]
    journal=ToolJournal(attempt,record,tools,validator,secrets)
    definitions={t["function"]["name"]:t["function"] for t in plan["tools"]}
    local_tools=[]
    for name,definition in definitions.items():
        async def invoke(ctx,text,_name=name):
            return await journal.invoke(_name,ctx.tool_call_id,text)
        local_tools.append(ag.FunctionTool(name=name,description=definition["description"],params_json_schema=copy.deepcopy(definition["parameters"]),
                on_invoke_tool=invoke,strict_json_schema=False,needs_approval=True))
    client=None;session=None
    try:
        from .runtime_credentials import transport_url
        client=oa.AsyncOpenAI(api_key=config["api_key"],base_url=transport_url("xty", profile["base_url"]),timeout=profile["timeout_seconds"],max_retries=0,
                             http_client=oa.DefaultAsyncHttpxClient(follow_redirects=False))
        # Record the gateway's actual completion before the SDK converts it;
        # detect truncation instead of accepting partial tool JSON. With
        # completion_transport=stream_merged the HTTP call is streamed (the
        # gateway proxy kills non-streamed responses at ~120s while large
        # submit turns need minutes), fully drained here and merged back into
        # one completion, so the SDK and every guard above stay unchanged.
        if hasattr(client,"chat"):
            create_completion=client.chat.completions.create
            async def checked_completion(*args,**kwargs):
                if profile.get("reasoning_effort") is not None:
                    kwargs.setdefault("reasoning_effort", profile["reasoning_effort"])
                if kwargs.get("stream") is True and profile.get("completion_transport")!=STREAM_TRANSPORT:
                    raise fail("unexpected_stream_mode", "本适配器使用非流式SDK运行，不能把流对象当成完成结果。")
                via_stream=False; chunk_count=0
                if profile.get("completion_transport")==STREAM_TRANSPORT and kwargs.get("stream") is not True:
                    kwargs=dict(kwargs); kwargs["stream"]=True
                    kwargs.setdefault("stream_options",{"include_usage":True})
                    chunks=await _consume_stream(await create_completion(*args,**kwargs))
                    chunk_count=len(chunks)
                    raw=_merge_streamed_completion(chunks)
                    via_stream=True
                    completion=_streamed_completion_object(oa,raw)
                else:
                    completion=await create_completion(*args,**kwargs)
                    raw=completion.model_dump(mode="json")
                wire=_safe_json(raw,secrets)
                if via_stream:
                    wire=dict(wire); wire["via_stream"]=True; wire["stream_chunk_count"]=chunk_count
                _write(attempt/f"model_{record['model_calls']:04d}_wire.json",wire)
                choices=raw.get("choices",[])
                if any(c.get("finish_reason") in {"length","content_filter"} for c in choices):
                    raise fail("model_output_incomplete", "网关输出被截断或过滤；未当作完整结果执行。")
                if via_stream and (not choices or any(c.get("finish_reason") is None for c in choices)):
                    raise fail("stream_response_incomplete", "网关响应流提前结束，缺少正常结束标记finish_reason；断点已保留。")
                if not choices:
                    raise fail("empty_model_response", "网关没有返回有效choice。")
                return completion
            client.chat.completions.create=checked_completion
        class RecordedChatModel(ag.OpenAIChatCompletionsModel):
            async def get_response(self,*args,**kwargs):
                number=len(list(attempt.glob("model_*_request.json")))+1
                if number>profile["max_turns"]:
                    raise fail("model_turn_limit", "达到动作模型请求次数上限，停止而不继续计费。")
                prefix=attempt/f"model_{number:04d}"
                request={"profile":profile,"system_instructions":kwargs.get("system_instructions",args[0] if args else None),
                         "input":kwargs.get("input",args[1] if len(args)>1 else None),"started_at":rt.utcnow()}
                _write(prefix.with_name(prefix.name+"_request.json"),_safe_json(request,secrets))
                record["model_calls"]=number
                _write(attempt/"execution.json",record)
                response=await super().get_response(*args,**kwargs)
                output=_output_items(response)
                _write(prefix.with_name(prefix.name+"_response.json"),_safe_json({"output":output,"response_id":getattr(response,"response_id",None),"completed_at":rt.utcnow()},secrets))
                return response
        model=RecordedChatModel(model=profile["model"],openai_client=client)
        # Local fix 2026-09-21: submit_result is no longer a hard stop. Completion
        # is detected from the durable validated receipt (submission.json); a
        # submit that fails content validation must flow back to the model as
        # tool feedback so it can correct and resubmit within the same run.
        agent=ag.Agent(name="FrontMind_"+plan["action"],instructions=plan["instructions"],model=model,tools=local_tools,
                       model_settings=ag.ModelSettings(parallel_tool_calls=False,max_tokens=profile["max_tokens"]))
        session=ag.SQLiteSession(record["session_id"],str(attempt/"session.sqlite3"))
        cp=rt._read_json(attempt/"checkpoint.json")
        if cp:
            if cp.get("sdk_version")!=SDK_VERSION or cp.get("fingerprint")!=record["fingerprint"]:
                raise fail("checkpoint_incompatible", "断点版本或请求不一致；不自动重写历史。")
            # Restore the matching history snapshot after interrupted SDK writes.
            await session.clear_session()
            await session.add_items(cp["session_items"])
            _restore_tools(attempt,tools,cp["host_state"])
            current=await ag.RunState.from_json(agent,cp["run_state"]) if cp.get("run_state") is not None else plan["input"]
        else:
            rt._record_inline_inputs(tools,[{"role":"system","content":plan["instructions"]}]+plan["input"])
            current=plan["input"]
            cp={"sdk_version":SDK_VERSION,"fingerprint":record["fingerprint"],"run_state":None,"host_state":tools.export_state(),"session_items":await session.get_items()}
            _write(attempt/"checkpoint.json",_safe_json(cp,secrets))
        # A durable final receipt is enough to finish without another paid call.
        # This covers a crash after validated submit but before Runner returned.
        if (attempt/"submission.json").is_file():
            sub=rt._read_json(attempt/"submission.json")
            _restore_tools(attempt,tools,rt._read_json(attempt/sub["tool_file"])["host_state"])
            return sub["checked"]
        while True:
            result=await ag.Runner.run(agent,current,session=session,max_turns=profile["max_turns"],
                                     run_config=ag.RunConfig(tracing_disabled=True,trace_include_sensitive_data=False,
                                                            session_input_callback=lambda history,new: history+new))
            interruptions=list(result.interruptions)
            if not interruptions:
                sub=rt._read_json(attempt/"submission.json")
                if sub is None:
                    raise fail("missing_submit_result", "Agent结束但没有通过校验的submit_result；普通文本不能冒充业务结果。")
                return sub["checked"]
            pending=[];rejected=[]
            for interruption in interruptions:
                name=getattr(interruption,"name",None)
                raw=getattr(interruption,"raw_item",None)
                call_id=raw.get("call_id") if isinstance(raw,dict) else getattr(raw,"call_id",None)
                try:
                    args=rt.strict_json(interruption.arguments)
                except Exception as parse_exc:
                    # A malformed tool-call body (duplicate keys, trailing text)
                    # used to kill the whole paid session. Feed the exact parse
                    # error back so the model can reissue one corrected call in
                    # this same session; bounded like submit feedback.
                    record["tool_argument_feedback"]=record.get("tool_argument_feedback",0)+1
                    if record["tool_argument_feedback"]>3:
                        raise fail("invalid_tool_arguments","工具参数JSON连续无法解析；停止而不继续计费。") from None
                    _write(attempt/"execution.json",record)
                    rejected.append((interruption,"工具参数JSON解析失败("+rt.redact(str(parse_exc),secrets)[:200]+")；请重新发起同一调用：参数必须是单个合法JSON对象，不得有重复键、注释或代码围栏。"))
                    continue
                if name not in definitions or not isinstance(args,dict):
                    raise fail("unexpected_tool", "SDK请求了未允许的工具或无效参数。")
                _source_call(attempt,call_id,name,args)
                pending.append((interruption,name))
            if any(name=="submit_result" for _,name in pending) and len(pending)!=1:
                raise fail("mixed_final_submission", "最终提交必须单独调用，不能与其他工具混在一批。")
            state=result.to_state()
            # Internally authorize only existing read/search/submit capabilities;
            # no new user confirmation or permission escalation is introduced.
            for interruption,_ in pending: state.approve(interruption,always_approve=False)
            for interruption,message in rejected:
                state.reject(interruption,rejection_message=message)
            cp={"sdk_version":SDK_VERSION,"fingerprint":record["fingerprint"],"run_state":state.to_json(),
                "host_state":tools.export_state(),"session_items":await session.get_items(),"saved_at":rt.utcnow()}
            _write(attempt/"checkpoint.json",_safe_json(cp,secrets))
            current=state
    finally:
        if session is not None:
            closed=session.close()
            if inspect.isawaitable(closed): await closed
        if client is not None: await client.close()


def _run_agents_action_once(package_root: Path, job_root: Path, action: str, prompt: str, validator: Any, retry: bool=False,
                      *, host_tools=None, sdk_override=None, offline: bool=False, force_profile=None, fallback_for=None,
                      resume_attempt_id: str | None = None) -> dict:
    rt=_rt();package_root=Path(package_root);job_root=Path(job_root)
    if sdk_override is not None and not offline:
        raise fail("production_transport_override", "生产模式不接受替代SDK或模型响应。")
    if offline and sdk_override is None:
        raise fail("missing_offline_transport", "离线SDK测试需显式模拟组件。")
    profile=force_profile or public_profile(package_root)
    config={"api_key":"offline-fixture-not-a-key","source":"explicit offline SDK fixture"} if offline else rt.load_configuration(package_root,"xty")
    secrets=[]
    for provider in ("xty","zhipu","deepseek"):
        c=rt.load_configuration(package_root,provider,required=False)
        if c.get("api_key"):secrets.append(c["api_key"])
    if any(key in prompt for key in secrets): raise fail("credential_in_prompt", "任务包含凭据，未发送或保存。")
    if host_tools is None:
        from .host_tools import HostTools
        host_tools=HostTools(package_root,job_root,action)
    rt.configure_host_tools(host_tools,prompt)
    defs=host_tools.definitions() if callable(host_tools.definitions) else host_tools.definitions
    plan=request_plan(action,profile,rt._initial_messages(action,prompt),list(defs)+[rt.submit_tool_for(action,deep=rt._deep_prompt(action,prompt),prompt=prompt)])
    fp=fingerprint(plan,rt.context_fingerprint(job_root,action,host_tools),offline)
    root=job_root/"provider"/action/"runtime"
    # The CLI also locks the whole business Job. This extra lock protects direct
    # Python adapter callers from concurrent host actions on one Job.
    with rt.action_lock(job_root/"provider"/"agents_job_lock"),rt.action_lock(root):
        matches=[]
        for path in sorted((root/"attempts").glob("*/execution.json"),reverse=True):
            r=rt._read_json(path,{})
            if r.get("fingerprint")==fp and r.get("requested_configuration",{}).get("wire_api")==WIRE_API:
                matches.append((path.parent,r))
        if resume_attempt_id is not None and (not matches or matches[0][0].name != resume_attempt_id):
            raise fail("agents_input_changed", "当前备用断点与请求身份不一致；未重新启动或重绑历史尝试。")
        if matches:
            attempt,record=matches[0]
            if record.get("status")=="succeeded":
                try:return restore_result(attempt,record,host_tools,validator)
                except Exception as exc:raise fail("cached_result_invalid","已保存SDK结果的来源或校验发生变化；未重写稿件。") from exc
            if not retry:
                raise rt.ProviderActionError("agents_explicit_retry_required","上次动作未完成；请使用 --retry-current-action 从本地断点继续，普通继续不重发模型请求。",
                                             action=action,attempt_id=attempt.name)
            if rt._read_json(attempt/"request_plan.json")!=plan: raise fail("agents_input_changed","恢复请求与原始请求不一致。")
            if not rt._dependencies_match(job_root,record.get("dependencies",[])):
                raise fail("agents_input_changed","断点依赖的原文已改变；需要显式回到上游动作，不能恢复旧工具调用。")
            if record.get("error",{}).get("code") in {"invalid_result_contract","tool_after_submission","mixed_final_submission","model_turn_limit"}:
                raise fail("saved_submission_not_recoverable","结果或次数上限问题需修正上游输入；不再次付费生成同一稿。")
            _write(attempt/f"resume_{record.get('resume_count',0)+1:03d}_previous_execution.json",record)
            record.update(resume_count=record.get("resume_count",0)+1,retry_explicit=True,resumed_at=rt.utcnow(),status="running",
                          resumed_with_agents_contract=CONTRACT)
        else:
            attempt_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ_")+uuid.uuid4().hex[:8]
            attempt=root/"attempts"/attempt_id;attempt.mkdir(parents=True)
            attempt.chmod(0o700)
            record={"schema":rt.CONTRACT_VERSION,"agents_contract":CONTRACT,"action":action,"attempt_id":attempt_id,"fingerprint":fp,
                    "requested_configuration":profile,"configuration_source":config["source"],"status":"running","started_at":rt.utcnow(),
                    "execution_mode":"offline_simulated" if offline else "production","session_id":"frontmind:"+action+":"+attempt_id,
                    "sdk_version":SDK_VERSION,"model_calls":0,"rounds":[],"tool_calls":0,"dependencies":[],"retry_explicit":bool(retry)}
            if fallback_for is not None:
                record["fallback_for"]=fallback_for
            _write(attempt/"request_plan.json",_safe_json(plan,secrets))
            _write(attempt/"prompt.md",prompt)
        _write(root/"latest.json",{"attempt_id":attempt.name,"fingerprint":fp})
        _write(attempt/"execution.json",record)
        try:
            result=asyncio.run(execute_sdk(plan,attempt,record,host_tools,validator,config,secrets,sdk_override=sdk_override))
            result=rt._checked(validator,result,host_tools)
            _write(attempt/"completion.json",{"status":"submitted","completed_at":rt.utcnow(),"session_id":record["session_id"]})
            record.update(status="succeeded",completed_at=rt.utcnow(),dependencies=rt._safe_deps(host_tools),result_sha256=digest(result),
                          tool_calls=len(list(attempt.glob("tool_*.json"))),agents_evidence_sha256=evidence_manifest(attempt))
            record.pop("error",None);_write(attempt/"execution.json",record)
            return restore_result(attempt,record,host_tools,validator)
        except BaseException as exc:
            code=exc.code if isinstance(exc,rt.ProviderActionError) else "agents_interrupted" if isinstance(exc,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)) else "agents_execution_failed"
            transport=code=="stream_response_incomplete" or (_transport_failure(exc) if code=="agents_execution_failed" else False)
            if isinstance(exc,rt.ProviderActionError):
                exc.action=exc.action or action
                exc.attempt_id=exc.attempt_id or attempt.name
                exc.transport_failure=transport
            message=rt.redact(str(exc),secrets)[:1200]
            record.update(status="failed",failed_at=rt.utcnow(),dependencies=rt._safe_deps(host_tools),
                          error={"code":code,"message":message or "执行中断；已有断点保留。","transport":transport})
            _write(attempt/"execution.json",record)
            if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
            if isinstance(exc,rt.ProviderActionError):raise
            wrapped=rt.ProviderActionError(code,"SDK执行失败；未自动重试，断点已保留。"+message,action=action,attempt_id=attempt.name)
            wrapped.transport_failure=transport
            raise wrapped from None


def _latest_transport_failure(job_root: Path, action: str, attempt_id: str | None = None) -> str | None:
    """Identify a failed transport attempt without rewriting historical errors.

    Prefer the exact fingerprint-matched attempt from the runtime guard. Legacy
    408/stream failures were saved as transport=false; classify their message
    only for agents_execution_failed, never for a business/protocol failure.
    """
    try:
        rt=_rt()
        if attempt_id is None:
            latest=rt._read_json(Path(job_root)/"provider"/action/"runtime"/"latest.json",{})
            attempt_id=latest.get("attempt_id")
        if not isinstance(attempt_id,str) or Path(attempt_id).name != attempt_id:
            return None
        record=rt._read_json(Path(job_root)/"provider"/action/"runtime"/"attempts"/attempt_id/"execution.json",{})
        error=record.get("error") or {}
        if (record.get("status")=="failed"
                and (error.get("code")=="stream_response_incomplete"
                     or (error.get("code")=="agents_execution_failed"
                         and (error.get("transport") is True
                              or _transport_message_failure(str(error.get("message", ""))))))):
            return attempt_id
    except Exception:
        return None
    return None


def _mark_failed_over(job_root: Path, action: str, attempt_id: str | None) -> None:
    """Best-effort audit marker on the superseded primary attempt."""
    if not attempt_id:
        return
    try:
        rt=_rt()
        path=Path(job_root)/"provider"/action/"runtime"/"attempts"/attempt_id/"execution.json"
        record=rt._read_json(path,{})
        if record.get("status")=="failed":
            record["failed_over_to_backup"]=True
            _write(path,record)
    except Exception:
        pass


def run_agents_action(package_root: Path, job_root: Path, action: str, prompt: str, validator: Any, retry: bool=False,
                      *, host_tools=None, sdk_override=None, offline: bool=False) -> dict:
    """Run one host action; transport-class failures fail over to the backup host.

    The backup (config/xty.json backup_model, e.g. glm-5.3 with
    backup_reasoning_effort max) runs the SAME prompt, tools and guards on the
    same gateway; every attempt records its own model identity and the pair is
    linked (fallback_for / failed_over_to_backup) for audit. Content-contract,
    tool-protocol and budget errors never switch models: those are explicit
    retry or rework decisions, not gateway instability.
    """
    rt=_rt()
    if retry:
        # Explicit retry resumes the active backup checkpoint instead of
        # reissuing the failed primary. The core rechecks its exact fingerprint,
        # plan and dependencies; this never rebinds a changed request.
        backup=backup_profile(package_root)
        root=Path(job_root)/"provider"/action/"runtime"
        latest=rt._read_json(root/"latest.json",{})
        active_id=latest.get("attempt_id")
        if backup is not None and isinstance(active_id,str) and Path(active_id).name==active_id:
            active=rt._read_json(root/"attempts"/active_id/"execution.json",{})
            if (active.get("status")=="failed" and active.get("fallback_for")
                    and active.get("action")==action and active.get("requested_configuration")==backup):
                return _run_agents_action_once(package_root,job_root,action,prompt,validator,True,
                    host_tools=host_tools,sdk_override=sdk_override,offline=offline,
                    force_profile=backup,fallback_for=active["fallback_for"],resume_attempt_id=active_id)
    try:
        return _run_agents_action_once(package_root,job_root,action,prompt,validator,retry,
                                       host_tools=host_tools,sdk_override=sdk_override,offline=offline)
    except rt.ProviderActionError as exc:
        backup=backup_profile(package_root)
        primary=public_profile(package_root)
        if backup is None or backup.get("model")==primary.get("model"):
            raise
        pending_transport=getattr(exc,"transport_failure",False)
        primary_attempt=getattr(exc,"attempt_id",None)
        if not pending_transport and exc.code=="agents_explicit_retry_required":
            # Plain continue on a transport-failed breakpoint: the pending
            # attempt already proved the primary path unstable; use backup.
            latest=_latest_transport_failure(job_root,action,primary_attempt)
            if latest is not None:
                pending_transport=True
                primary_attempt=primary_attempt or latest
        if not pending_transport:
            raise
        _mark_failed_over(job_root,action,primary_attempt)
        try:
            return _run_agents_action_once(package_root,job_root,action,prompt,validator,retry,
                                           host_tools=host_tools,sdk_override=sdk_override,offline=offline,
                                           force_profile=backup,fallback_for=primary_attempt)
        except rt.ProviderActionError as backup_exc:
            backup_attempt=getattr(backup_exc,"attempt_id",None)
            combined=("主宿主与备用宿主均未完成；主宿主为传输故障，备用宿主错误见下文。断点已保留。"
                      "主("+str(primary.get("model"))+"):"+str(exc)[:300]+"; "
                      "备("+str(backup.get("model"))+"):"+str(backup_exc)[:500])
            wrapped=rt.ProviderActionError(backup_exc.code,combined,action=action,attempt_id=backup_attempt or primary_attempt)
            wrapped.transport_failure=bool(getattr(backup_exc,"transport_failure",False))
            raise wrapped from None
