"""在已完成阶段上显式接续原 Job，保留身份、历史确认和交付文件。"""
from __future__ import annotations

import json
from pathlib import Path

CONTRACT = "frontmind-session-phases/1"


def advance(controller, args, job_root: Path) -> int:
    state = controller.load_state(job_root)
    controller.require_revision(args, state)
    target = args.next_task
    expected = {"p0": ({"reference_pack", "reference_pack_refresh"}, "positioning_ready"),
                "article": ({"p0"}, "p0_ready")}
    kinds, status = expected[target]
    if state.get("job_kind") not in kinds or state.get("status") != status:
        raise controller.WorkflowError("只能从已交付资料包继续 P0，或从已完成 P0 继续问题文章；不能重复接续或跳过阶段。")
    if state.get("current_pause") or state.get("pending_action"):
        raise controller.WorkflowError("当前仍有待确认或待完成动作，不能切换阶段。")
    delivery = state.get("metadata", {}).get("reference_pack_delivery") or {}
    source = controller.assert_regular_source(Path(delivery.get("pack_path", "")), allow_directory=True)
    if not source.resolve().is_relative_to(job_root.resolve()):
        raise controller.WorkflowError("续接必须沿用本 Job 内实际交付的资料包。")
    validation = controller.validate_reference_pack(source)
    root = controller.reference_pack_root(source)
    ready = "positioning_ready" if target == "p0" else "p0_ready"
    if (validation.get("status") != "pass" or not validation.get("readiness", {}).get(ready)
            or root.get("pack_id") != state.get("reference_pack", {}).get("pack_id")
            or root.get("pack_version") != delivery.get("pack_version")):
        raise controller.WorkflowError("最近交付资料包的系列、版本或完成状态不匹配。")
    # 先保存不可覆盖的阶段状态，再接续；不搬走、删除或改写历史交付。
    archive = job_root / "working/phase_history" / f"{state['job_kind']}_r{state['revision']}.json"
    archive.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    if archive.exists():
        if archive.read_text(encoding="utf-8") != data:
            raise controller.WorkflowError("已保存的阶段历史不一致，停止接续。")
    else:
        with archive.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
    if target == "p0":
        controller.p0_style.freeze_examples(controller.ROOT, job_root)
    next_state = controller.make_state(state["job_id"], target)
    next_state.update(created_at=state["created_at"], revision=state["revision"] + 1,
                      schema_version=state["schema_version"], workflow_version=state["workflow_version"])
    history = list(state.get("metadata", {}).get("completed_phases", []))
    history.append({"kind": state["job_kind"], "revision": state["revision"], "state_path": str(archive.relative_to(job_root)),
                    "pack_id": root["pack_id"], "pack_version": root["pack_version"]})
    next_state["metadata"].update(session_phase_contract=CONTRACT, completed_phases=history)
    next_state["metadata"].update(startup_target=target, startup_entrypoint=target)
    confirmations = list(state.get("metadata", {}).get("completed_phase_confirmations", []))
    decisions = state.get("decisions", {})
    for key, label in (("reference_pack_route", "awaiting_reference_pack_route"),
                       ("comparison_scope", "awaiting_competitor_selection"),
                       ("positioning_direction", "awaiting_core_positioning_direction"),
                       ("core_positioning_confirmation", "awaiting_core_positioning_confirmation"),
                       ("p0_blueprint_confirmation", "awaiting_p0_blueprint_confirmation")):
        decision = decisions.get(key)
        if decision and (key not in {"comparison_scope", "core_positioning_confirmation"} or decision.get("confirmed")):
            confirmations.append(label)
    if state.get("p0_route"):
        confirmations.append("awaiting_p0_route")
    if state.get("job_kind") == "p0" and decisions.get("example_route"):
        confirmations.append("awaiting_p0_example_confirmation")
    next_state["metadata"]["completed_phase_confirmations"] = list(dict.fromkeys(confirmations))
    if "offline_fixture" in state.get("flags", {}):
        next_state["flags"]["offline_fixture"] = state["flags"]["offline_fixture"]
    controller.save_state(job_root, next_state)
    controller.bind_reference_pack(job_root, source)
    return controller.after_reference_bound(job_root)
