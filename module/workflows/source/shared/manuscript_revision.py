"""Frozen, explicit local edits of a previously completed model manuscript."""
from __future__ import annotations

from . import title_strategy

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

CONTRACT_VERSION = "frontmind-manuscript-revision/4.11.5"


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_file(job: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("精修记录路径无效")
    member = PurePosixPath(relative)
    if member.is_absolute() or ".." in member.parts:
        raise ValueError("精修记录路径无效")
    path = job.joinpath(*member.parts)
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(job.resolve()):
        raise ValueError("精修原件不存在或路径不安全")
    return path


def current_revision(wf: Any, job_root: Path, *, p0: bool) -> dict | None:
    prefix = "p0" if p0 else "article"
    pointer = wf.load_state(job_root).get("metadata", {}).get(prefix + "_manuscript_revision")
    if not pointer:
        return None
    path = local_file(Path(job_root), pointer["path"])
    if file_hash(path) != pointer.get("sha256"):
        raise ValueError("冻结精修委托被修改；请重新提交明确的精修任务")
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("contract") != CONTRACT_VERSION or value.get("prefix") != prefix:
        raise ValueError("精修委托合同不匹配")
    for key in ("base", "edits"):
        body = value.get(key + "_markdown")
        if not isinstance(body, str) or not body.strip() or text_hash(body) != value.get(key + "_sha256"):
            raise ValueError("精修基稿或委托与冻结哈希不匹配")
    for key, relative in (("draft_sha256", f"production/{prefix}_draft.json"),
                          ("blueprint_sha256", f"blueprints/{prefix}_blueprint.json")):
        if file_hash(local_file(Path(job_root), relative)) != value["source"].get(key):
            raise ValueError("精修期间原始初稿或确认蓝图发生变化；应返回原蓝图流程")
    from . import editorial_preparation
    if editorial_preparation.enabled(wf.load_state(job_root)) and value.get("writing_materials") is not None:
        raise ValueError("v16正文精修只复用已完成编辑准备的素材；新增材料须回到蓝图补料入口")
    return value


def clear_revision(wf: Any, job_root: Path, *, p0: bool) -> None:
    """A deliberate upstream change ends local-edit mode, retaining its record."""
    prefix = "p0" if p0 else "article"
    state = wf.load_state(job_root)
    pointer = state.get("metadata", {}).pop(prefix + "_manuscript_revision", None)
    title_revision = state.get("metadata", {}).pop(prefix + "_title_revision", None)
    if title_revision:
        state["metadata"].setdefault(prefix + "_title_revision_history", []).append(title_revision)
    if pointer:
        state["metadata"].setdefault(prefix + "_manuscript_revision_history", []).append(pointer)
    if pointer or title_revision:
        wf.save_state(job_root, state)
    if p0:
        from . import p0_rework
        p0_rework.clear(wf, job_root)


def current_title_revision(wf: Any, job_root: Path, *, p0: bool) -> dict | None:
    prefix = "p0" if p0 else "article"
    value = wf.load_state(job_root).get("metadata", {}).get(prefix + "_title_revision")
    if not value:
        return None
    final_path = local_file(Path(job_root), f"production/{prefix}_finalized.json")
    if (file_hash(final_path) != value["source"]["finalized_sha256"]
            or text_hash(wf.read_json(final_path)["article_markdown"]) != value["source"].get("host_final_markdown_sha256", value["base_sha256"])
            or text_hash(value["base_markdown"]) != value["base_sha256"]
            or text_hash(value["edits_markdown"]) != value["edits_sha256"]):
        raise ValueError("标题修订的冻结正文或修改要求发生变化")
    return value


def _verified_action(wf: Any, job: Path, action: str, production: Path, validator, *, offline: bool) -> dict:
    from . import model_runtime as runtime
    value = wf.read_json(production)
    validator(value)
    if offline:
        return {"action": action, "execution_mode": "offline_fixture", "result_sha256": file_hash(production)}
    root = job / "provider" / action / "runtime"
    latest = wf.read_json(root / "latest.json")
    identity = latest.get("attempt_id")
    if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_]+", identity):
        raise ValueError("原稿缺少合法模型尝试标识")
    attempt = root / "attempts" / identity
    record = wf.read_json(attempt / "execution.json")
    if record.get("status") != "succeeded" or record.get("execution_mode") != "production" or record.get("action") != action:
        raise ValueError("原稿必须来自真实成功模型链，不能精修代填或模拟稿")
    profile = runtime.profile_for(action)
    requested = record.get("requested_configuration") or {}
    # Historical articles retain their actual model identity. Reading a prior
    # completed chain is distinct from accepting a cache for a new action.
    current_identity = all(requested.get(key) == profile.get(key) for key in
                           ("provider", "model", "wire_api", "thinking", "reasoning_effort", "reasoning", "effort"))
    legacy_host = (action in runtime.HOST_ACTIONS and requested.get("provider") == "zhipu"
                   and requested.get("model") == "glm-5.3"
                   and requested.get("reasoning_effort") in {"high", "max"}
                   and requested.get("thinking", {}).get("type") == "enabled"
                   and requested.get("wire_api") in {None, "chat_completions"})
    legacy_writer = (action in runtime.DEEPSEEK_ACTIONS and requested.get("provider") == "deepseek"
                     and requested.get("model") == "deepseek-v4-pro"
                     and requested.get("reasoning_effort") in {"high", "max"}
                     and requested.get("thinking", {}).get("type") == "enabled"
                     and requested.get("wire_api") in {None, "chat_completions"})
    legacy_xty_host = (action in runtime.HOST_ACTIONS and requested.get("provider") == "xty"
                       and requested.get("model") == "gpt-6-astra"
                       and requested.get("wire_api") == "responses"
                       and requested.get("reasoning", {}).get("effort") == "high")
    # Transport-failover results: same gateway and wire contract, model is the
    # configured backup host; the attempt record links fallback_for/failed_over.
    # Also accept the locally validated xty SDK-host family (see
    # LOCAL_MODIFICATION): temporary primary switches (e.g. gpt-5.6-luna during
    # the 2026-09-22 gateway window) produced real verdicts whose receipts are
    # fully verified by _saved_result below; only the model-name allowlist
    # needed widening, never the receipt verification itself.
    backup_model = runtime.host_backup_model()
    local_xty_hosts = {"gpt-5.6-sol", "gpt-5.6-luna", "gpt-5.6-terra", "glm-5.3"}
    backup_identity = (action in runtime.HOST_ACTIONS and requested.get("provider") == "xty"
                       and requested.get("wire_api") == "openai_agents_sdk"
                       and (requested.get("model") == backup_model or requested.get("model") in local_xty_hosts))
    if not (current_identity or legacy_host or legacy_writer or legacy_xty_host or backup_identity):
        raise ValueError("原稿缺少受支持的真实历史模型身份")
    if action == "p0_style":
        # This action first exists in the new, explicitly versioned P0 chain.
        # Historical host/writer replay tolerates old prompts, but a style
        # result must belong to this complete E8, fixed pair and edit request.
        # Authentic output from some other input is not a valid chain link.
        from . import writing_context
        expected_prompt = writing_context.prompt_p0_style(wf, job)
        recorded_prompt = local_file(job, str((attempt / "prompt.md").relative_to(job))).read_text(encoding="utf-8")
        if recorded_prompt != expected_prompt:
            # Tolerance: the frozen-candidate opening strip (skill v1.1.5,
            # 2026-09-22) changed the rework prompt; attempts recorded before
            # that change verify against the identical inputs without it.
            legacy_expected = writing_context.prompt_p0_style(wf, job, strip_opening=False)
            if recorded_prompt != legacy_expected:
                raise ValueError("原文采模型请求未绑定当前完整 E8、固定例文及本轮精修委托")
    tools = None
    if action in runtime.HOST_ACTIONS:
        from .host_tools import HostTools
        tools = HostTools(wf.ROOT, job, action)
    original = runtime._saved_result(attempt, record, tools, validator, persist=False, verify_current_inputs=False)
    if original != value or wf.read_json(job / "provider" / action / "result.json") != value:
        raise ValueError("原稿与实际模型结果不一致")
    return {"action": action, "attempt_id": identity, "execution_mode": "production",
            "model": requested["model"], "provider": requested["provider"],
            "execution_sha256": file_hash(attempt / "execution.json"), "result_sha256": file_hash(production)}


def validate_completed_manuscript(wf: Any, job_root: Path, *, p0: bool) -> dict:
    """Verify the existing chain without calling providers or rewriting results."""
    from . import editorial_contracts as contracts, natural_editor, language_editor_v15
    job = Path(job_root);prefix = "p0" if p0 else "article";state = wf.load_state(job)
    v15 = not p0 and language_editor_v15.enabled(state)
    if state.get("status") != ("p0_ready" if p0 else "completed"):
        raise ValueError("成稿精修仅用于已完成的文章任务")
    offline = state.get("flags", {}).get("offline_fixture") is True
    draft_path = local_file(job, f"production/{prefix}_draft.json")
    # Replay v12 writers through the same validator used on arrival. The
    # stored raw response may contain explicit null for an unused reason;
    # only that versioned metadata normalization is allowed, never a rewrite.
    draft_validator = (lambda value: wf.validate_action_result(job, prefix + "_draft", value)) if natural_editor.enabled(state) else contracts.validate_draft_result
    draft = draft_validator(wf.read_json(draft_path))
    if draft["requires_blueprint_reconfirmation"]:
        raise ValueError("原始初稿尚需蓝图确认")
    base = contracts.edit_base_input(wf, job, p0=p0)["article_markdown"]
    edited_path = local_file(job, f"production/{prefix}_edited.json")
    edit_validator = ((lambda value: wf.validate_action_result(job, prefix + "_edit", value)) if natural_editor.enabled(state)
                      else lambda value: contracts.validate_edit_result(value, base))
    edited = edit_validator(wf.read_json(edited_path))
    if edited["edit_status"] == "requires_blueprint_reconfirmation":
        raise ValueError("原 E8 尚需蓝图确认")
    from . import p0_style, brand_stage
    new_brand_chain = p0 and brand_stage.enabled(state)
    styled_chain = p0 and p0_style.is_enabled(state)
    candidate = edited["article_markdown"]
    styled_path = None
    if styled_chain:
        p0_style.job_examples(wf.ROOT, job, freeze=False)
        styled_path = local_file(job, "production/p0_styled.json")
        styled = (brand_stage.validate_style(wf.read_json(styled_path), candidate, state=state) if new_brand_chain else contracts.validate_style_result(wf.read_json(styled_path), candidate))
        if styled.get("edit_status") == "requires_blueprint_reconfirmation":
            raise ValueError("原文采稿尚需蓝图确认")
        candidate = styled["article_markdown"]
    final_path = local_file(job, f"production/{prefix}_finalized.json")
    final = (natural_editor.validate_selected(wf, job, candidate, p0=p0) if natural_editor.enabled(state) else
             brand_stage.validate_final(wf.read_json(final_path), candidate, state=state) if new_brand_chain else
             contracts.validate_finalize_result(wf.read_json(final_path), candidate, require_quality_review=p0 and p0_style.is_deep(state)))
    if final["outcome"] not in ("accepted", "revised"):
        raise ValueError("原稿尚未完成宿主验读")
    wf.validate_article_markdown(final["article_markdown"], allow_flat=natural_editor.enabled(state))
    review_validator = ((lambda value: language_editor_v15.validate_action(wf, job, "article_finalize", value))
                        if v15 else natural_editor.validate_review)
    actions = [
        _verified_action(wf, job, prefix + "_draft", draft_path, draft_validator, offline=offline),
        _verified_action(wf, job, prefix + "_edit", edited_path, edit_validator, offline=offline),
        *([_verified_action(wf, job, "p0_style", styled_path,
            lambda v: (brand_stage.validate_style(v, edited["article_markdown"], state=state) if new_brand_chain else contracts.validate_style_result(v, edited["article_markdown"])), offline=offline)] if styled_chain else []),
        *([_verified_action(wf, job, prefix + "_finalize", local_file(job, f"production/{prefix}_editorial_review.json"), review_validator, offline=offline)] if natural_editor.enabled(state) else
          [_verified_action(wf, job, prefix + "_finalize", final_path, lambda v: (brand_stage.validate_final(v, candidate, state=state) if new_brand_chain else contracts.validate_finalize_result(v, candidate, require_quality_review=p0 and p0_style.is_deep(state))), offline=offline)]),
        _verified_action(wf, job, prefix + "_titles", local_file(job, f"production/{prefix}_titles.json"), lambda v: (wf.validate_title_map(v, p0=p0, legacy=True, expected_count=title_strategy.expected_count(state)), v)[1], offline=offline),
    ]
    from . import editorial_preparation
    if editorial_preparation.enabled(state, p0=p0):
        preparation = editorial_preparation.load(job)
        blueprint = wf.read_json(local_file(job, "blueprints/article_blueprint.json"))
        if any(blueprint.get(key) != preparation[key] for key in editorial_preparation.FIELDS):
            raise ValueError("当前蓝图素材未继承已冻结的编辑准备结果")
        actions.insert(0, _verified_action(wf, job, editorial_preparation.ACTION,
            local_file(job, editorial_preparation.PATH), editorial_preparation.validate, offline=offline))
    source = wf.read_json(local_file(job, f"production/{prefix}_final_source.json"))
    if v15:
        review = review_validator(wf.read_json(local_file(job, "production/article_editorial_review.json")))
        if review["needs_revision"]:
            actions.append(_verified_action(wf, job, "article_repair", local_file(job, "production/article_repaired.json"), natural_editor.validate_repair, offline=offline))
            actions.append(_verified_action(wf, job, "article_polish", local_file(job, "production/article_polish_review.json"),
                lambda value: language_editor_v15.validate_action(wf, job, "article_polish", value), offline=offline))
        expected_action = "article_polish" if review["needs_revision"] else "article_finalize"
        actual_host = next(item for item in actions if item["action"] == expected_action)
        writer_action = "article_repair" if review["needs_revision"] else "article_edit"
        actual_writer = next(item for item in actions if item["action"] == writer_action)
        if (source.get("contract") != language_editor_v15.contract_for(wf, job) or source.get("action") != expected_action
                or source.get("attempt_id") != actual_host.get("attempt_id")
                or source.get("author") != {"action": writer_action, "attempt_id": actual_writer.get("attempt_id"),
                    "source": "offline_fixture" if offline else actual_writer["model"]}):
            raise ValueError("最终正文未绑定实际作者基稿与最后XTY文字编辑")
    elif natural_editor.enabled(state):
        review = natural_editor.validate_review(wf.read_json(local_file(job, f"production/{prefix}_editorial_review.json")))
        if review["needs_revision"]:
            actions.append(_verified_action(wf, job, prefix + "_repair", local_file(job, f"production/{prefix}_repaired.json"), natural_editor.validate_repair, offline=offline))
        expected_action = prefix + ("_repair" if review["needs_revision"] else "_style" if styled_chain else "_edit")
        actual_host = next(item for item in actions if item["action"] == expected_action)
        if source.get("contract") != natural_editor.CONTRACT or source.get("action") != expected_action or source.get("attempt_id") != actual_host.get("attempt_id"):
            raise ValueError("最终正文的作者动作或尝试记录不一致")
    else:
        actual_host = next(item for item in actions if item["action"] == prefix + "_finalize")
    if source.get("source") != ("offline_fixture" if offline else actual_host["model"]) or source.get("body_sha256") != text_hash(final["article_markdown"]):
        raise ValueError("已完成稿来源标记不一致")
    if styled_chain and source.get("candidate_source") != "deepseek_style":
        raise ValueError("新版 P0 终稿未绑定已成功的文采稿")
    delivery = state.get("metadata", {}).get("delivery") or {}
    delivered = Path(delivery.get("markdown", ""))
    if not delivered.is_absolute():delivered = job / delivered
    if delivered.is_symlink() or not delivered.is_file() or not delivered.resolve().is_relative_to(job.resolve()):
        raise ValueError("当前交付正文不存在或路径无效")
    published = delivered.read_bytes().decode("utf-8")
    publication_source = None
    title_result = wf.read_json(local_file(job, f"production/{prefix}_titles.json"))
    if delivery.get("publication"):
        from . import title_publication
        publication_path = Path(delivery["publication"])
        if not publication_path.is_absolute():publication_path = job / publication_path
        if publication_path.is_symlink() or not publication_path.is_file() or not publication_path.resolve().is_relative_to(job.resolve()):
            raise ValueError("发布稿来源记录不存在或路径无效")
        publication_source = wf.read_json(publication_path)
        title_review = None
        if publication_source.get("title_review_result_sha256"):
            review_path = local_file(job, f"production/{prefix}_title_review.json")
            title_review = wf.read_json(review_path)
            actions.append(_verified_action(wf, job, prefix + "_title_review", review_path,
                lambda v: title_publication.validate_title_review_result(v, title_result, p0=p0, expected_count=title_strategy.expected_count(state)), offline=offline))
            if publication_source.get("title_review_result_file_sha256") != file_hash(review_path):
                raise ValueError("已完成稿的标题编辑结果文件与交付绑定不一致")
        expected_map = title_publication.verify_publication(final["article_markdown"], title_result, published,
                                                            publication_source, p0=p0, title_review=title_review, expected_count=title_strategy.expected_count(state))
        for name in ("finalized", "titles"):
            if publication_source.get(name + "_result_file_sha256") != file_hash(local_file(job, f"production/{prefix}_{name}.json")):
                raise ValueError("发布来源与模型结果文件不一致")
        title_path = Path(delivery.get("title_map", ""))
        if not title_path.is_absolute():title_path = job / title_path
        if title_path.is_symlink() or not title_path.is_file() or not title_path.resolve().is_relative_to(job.resolve()):
            raise ValueError("已发布标题记录不存在或路径无效")
        title_map = wf.read_json(title_path)
        if title_map != {**expected_map, "publication": publication_source}:
            raise ValueError("标题候选记录与模型结果或正文绑定不一致")
    elif title_result.get("canonical_title_id") is not None:
        raise ValueError("新标题合同的完成稿缺少独立发布来源记录")
    elif published != final["article_markdown"]:
        raise ValueError("旧版交付正文与宿主终稿不一致")
    blueprint = local_file(job, f"blueprints/{prefix}_blueprint.json")
    wf.validate_blueprint(wf.read_json(blueprint), p0=p0)
    # The external body is an exact title-free projection in 4.11.9. Keep the
    # original complete host manuscript internally for the established editor
    # contract; its heading is never put back into the delivered document.
    body_only_delivery = bool(publication_source and publication_source.get("transformation") == "remove_first_h1_line_only")
    base_markdown = final["article_markdown"] if body_only_delivery else published
    result = {"base_markdown": base_markdown, "base_sha256": text_hash(base_markdown),
              "base_source": ("previous_final" if natural_editor.enabled(state) else "previous_host_final" if body_only_delivery else
                              "previous_published_final" if publication_source else "previous_glm_final"),
              "source": {"finalized_sha256": file_hash(final_path), "draft_sha256": file_hash(draft_path),
                         "host_final_markdown_sha256": text_hash(final["article_markdown"]),
                         "publication": publication_source,
                         "blueprint_sha256": file_hash(blueprint), "actions": actions,
                         "delivery_markdown": str(delivered.resolve()), "source_revision": state["revision"]}}
    if p0:
        pack = state.get("metadata", {}).get("reference_pack_delivery") or {}
        path = Path(pack.get("portable_zip_path", ""))
        if not path.is_absolute():path = job / path
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(job.resolve()):
            raise ValueError("缺少最近交付的可继承资料包")
        digest = file_hash(path)
        if pack.get("portable_zip_sha256") != "sha256:" + digest:
            raise ValueError("最近资料包哈希不匹配")
        validation = wf.validate_reference_pack(path)
        pack_root = wf.reference_pack_root(path)
        if validation.get("status") != "pass" or not validation.get("readiness", {}).get("p0_ready") or pack_root["pack_id"] != state["reference_pack"]["pack_id"] or pack_root["pack_version"] != pack.get("pack_version"):
            raise ValueError("最近资料包无效或不属于原任务资料包系列")
        if wf.read_reference_member(path, wf.P0_MEMBERS["p0_brand_article"]).decode("utf-8") != published:
            raise ValueError("最近资料包正文与当前完成稿不一致")
        result["source_pack"] = {"path": str(path.resolve()), "sha256": digest,
                                 "pack_id": pack_root["pack_id"], "pack_version": pack_root["pack_version"]}
    return result
