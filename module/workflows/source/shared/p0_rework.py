"""Explicit repairs of a rejected P0, reusing E8/style rather than a new stage.

The short host reason and exact rejected candidate are frozen. A repair is not
an automatic paid retry or an authoring action by the host. Per-stage pointers
keep an E8 repair's input stable during subsequent style repairs.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from . import editorial_contracts as ec
from . import manuscript_revision as mr

CONTRACT = "frontmind-p0-rework/4.12.7"
POINTERS = "p0_rework_inputs"


def current(wf: Any, root: Path | str, stage: str) -> dict[str, Any] | None:
    if stage not in {"edit", "style"}:
        raise ValueError("P0返工仅支持现有E8或第三遍动作")
    root = Path(root)
    state = wf.load_state(root)
    pointer = (state.get("metadata", {}).get(POINTERS) or {}).get(stage)
    if not pointer:
        return None
    try:
        path = mr.local_file(root, pointer["path"])
        if mr.file_hash(path) != pointer.get("sha256"):
            raise ValueError("冻结返工记录已改变")
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("contract") != CONTRACT or record.get("route") != stage
                or record.get("job_contract") != state.get("metadata", {}).get("p0_style_contract")):
            raise ValueError("冻结返工记录与当前任务不匹配")
        body = record.get("candidate_markdown")
        if (not isinstance(body, str) or not body.strip()
                or mr.text_hash(body) != record.get("candidate_sha256")
                or not isinstance(record.get("reason"), str) or not record["reason"].strip()):
            raise ValueError("返工基稿或问题说明不完整")
        for relative, expected in record["upstream"].items():
            if mr.file_hash(mr.local_file(root, relative)) != expected:
                raise ValueError("返工期间蓝图或上游正文已改变，应返回对应上游流程")
        return record
    except (KeyError, TypeError, OSError, ValueError) as exc:
        raise ec.EditorialContractError("p0_rework_binding", "无法使用冻结返工输入：" + str(exc)) from exc


def rejected_input(wf: Any, root: Path | str) -> dict[str, Any]:
    """Validate the current four-field rejection without a provider call."""
    from . import prose_only
    root = Path(root)
    state = wf.load_state(root)
    pending = state.get("pending_action") or {}
    if (not prose_only.enabled(state) or state.get("status") != "running_p0_production"
            or pending.get("action") != "p0_finalize"
            or (pending.get("error") or {}).get("code") != "host_incomplete"):
        raise ValueError("当前不是可显式返工的P0终审未通过任务")
    candidate = ec.prepare_finalize_input(wf, root, p0=True)["candidate_markdown"]
    path = mr.local_file(root, "provider/p0_finalize/result.json")
    result = json.loads(path.read_text(encoding="utf-8"))
    prose_only.validate_final(result, candidate)
    if result["outcome"] != "incomplete":
        raise ValueError("当前没有可返工的incomplete结论")
    offline = state.get("flags", {}).get("offline_fixture") is True
    evidence: dict[str, Any] = {"execution_mode": "offline_fixture" if offline else "production"}
    if not offline:
        # Reuse the existing original-model checks. No fabricated provenance,
        # new model call, or host-authored replacement is accepted here.
        from . import model_runtime as rt
        latest = wf.read_json(root / "provider/p0_finalize/runtime/latest.json")
        attempt_id = latest.get("attempt_id")
        if not isinstance(attempt_id, str) or not re.fullmatch(r"[A-Za-z0-9_]+", attempt_id):
            raise ValueError("终审缺少有效的模型尝试标识")
        prompt_path = mr.local_file(root, "provider/p0_finalize/runtime/attempts/" + attempt_id + "/prompt.md")
        if prompt_path.read_text(encoding="utf-8") != prose_only.finalize_prompt(wf, root):
            raise ValueError("终审结论不属于当前候选和事实输入")
        evidence["finalize"] = mr._verified_action(
            wf, root, "p0_finalize", path,
            lambda v: prose_only.validate_final(v, candidate), offline=False)
        evidence["style"] = mr._verified_action(
            wf, root, "p0_style", mr.local_file(root, "production/p0_styled.json"),
            lambda v: wf.validate_action_result(root, "p0_style", v), offline=False)
        # Verify the current context as well as the original receipt.
        record = rt.action_record(root, "p0_finalize")
        from .host_tools import HostTools
        tools = HostTools(wf.ROOT, root, "p0_finalize")
        if record.get("requested_configuration", {}).get("wire_api") == "openai_agents_sdk":
            # SDK-hosted attempts record the agents_runtime fingerprint scheme, so
            # verify exactly what that runtime verifies on resume. The verdict was
            # rendered under the reviewer system prompt shipped at attempt time;
            # a package upgrade may legitimately revise that system text, so the
            # verdict binds to the candidate input, tools, model identity and the
            # remaining plan fields, tolerating only instruction-version drift.
            attempt_dir = mr.local_file(root, "provider/p0_finalize/runtime/attempts/" + attempt_id + "/request_plan.json").parent
            stored_plan = json.loads((attempt_dir / "request_plan.json").read_text(encoding="utf-8"))
            rebuilt_plan = rt.build_payload("p0_finalize", prose_only.finalize_prompt(wf, root),
                tools=tools.definitions())
            # Profile excluded: its model identity belongs to the attempt's own
            # record (and the fingerprint below binds the stored plan itself);
            # temporary host switches must not strand authentic verdicts.
            comparable = ("contract", "action", "input", "tools",
                          "session_storage", "checkpoint", "stop_at_tool_names")
            if any(stored_plan.get(key) != rebuilt_plan.get(key) for key in comparable):
                raise ValueError("终审结论不属于当前候选和事实输入")
            from . import agents_runtime
            expected = agents_runtime.fingerprint(stored_plan,
                rt.context_fingerprint(root, "p0_finalize", tools), offline=False)
        else:
            expected = rt.request_fingerprint("p0_finalize", prose_only.finalize_prompt(wf, root),
                tool_definitions=tools.definitions(), offline=False,
                context_hash=rt.context_fingerprint(root, "p0_finalize", tools))
        if record.get("fingerprint") != expected:
            raise ValueError("终审上下文已改变，不能用旧结论启动返工")
    return {"result": result, "path": path, "candidate_markdown": candidate, "evidence": evidence}


def begin(wf: Any, root: Path | str, route: str) -> dict[str, Any]:
    """Freeze one explicit repair; caller chooses when to resume its driver."""
    root = Path(root)
    if route not in {"style", "edit"}:
        raise ValueError("请选择style或edit；补料与业务变更使用已有蓝图流程")
    rejected = rejected_input(wf, root)  # Validate before any mutation.
    state = wf.load_state(root)
    stage_names = ("style", "finalize", "titles", "title_review")
    if route == "edit":
        stage_names = ("edit", *stage_names)
    upstream_names = ["blueprints/p0_blueprint.json", "production/p0_draft.json"]
    if route == "style":
        upstream_names.append("production/p0_edited.json")
    upstream = {name: mr.file_hash(mr.local_file(root, name)) for name in upstream_names}
    identity = "rework_" + uuid.uuid4().hex
    archive = root / "production/quality_rejections" / identity
    archive.mkdir(parents=True)
    rejection_path = archive / "result.json"
    candidate_path = archive / "candidate.json"
    wf.copy_stream(rejected["path"], rejection_path)
    wf.copy_stream(mr.local_file(root, "production/p0_styled.json"), candidate_path)
    record = {
        "contract": CONTRACT, "job_contract": state["metadata"]["p0_style_contract"],
        "rework_id": identity, "route": route, "created_at": wf.now(),
        "candidate_markdown": rejected["candidate_markdown"],
        "candidate_sha256": mr.text_hash(rejected["candidate_markdown"]),
        "reason": rejected["result"]["reason"], "upstream": upstream,
        "evidence": rejected["evidence"],
        "result_sha256": mr.file_hash(rejection_path),
    }
    record_path = archive / "rework.json"
    wf.atomic_json(record_path, record)
    pointer = {"path": record_path.relative_to(root).as_posix(), "sha256": mr.file_hash(record_path)}
    inputs = state["metadata"].setdefault(POINTERS, {})
    if route == "edit":
        inputs.pop("style", None)  # This repair will produce a new E8.
    inputs[route] = pointer
    history = {
        "revision": state["revision"], "recorded_at": wf.now(), "requested_route": route,
        "result_path": rejection_path.relative_to(root).as_posix(), "result_sha256": mr.file_hash(rejection_path),
        "candidate_path": candidate_path.relative_to(root).as_posix(), "candidate_sha256": mr.file_hash(candidate_path),
        "reason": record["reason"], "rework_input": pointer,
    }
    state["metadata"].setdefault("p0_quality_rework_history", []).append(history)
    bindings = state["metadata"].setdefault("p0_production_bindings", {})
    for stage in stage_names:
        bindings.pop(stage, None)
        state["flags"].setdefault("model_action_epochs", {})["p0_" + stage] = identity
    state["flags"].pop("retry_current_action", None)
    state["flags"]["p0_production_step"] = route
    state["pending_action"] = None
    state["revision"] += 1
    wf.save_state(root, state)
    for stage in stage_names:
        wf.invalidate_action(root, "p0_" + stage)
    wf.set_status(root, "running_p0_production", "p0_production")
    return history


def clear(wf: Any, root: Path | str) -> None:
    """An upstream change ends repair inputs, never deletes their history."""
    state = wf.load_state(root)
    if state.get("metadata", {}).pop(POINTERS, None) is not None:
        wf.save_state(root, state)
