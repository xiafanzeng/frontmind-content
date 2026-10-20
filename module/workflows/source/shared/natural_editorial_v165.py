"""Six-genre writing with a full editor and a prose-only read-through.

Each rejected candidate remains a real manuscript. Revision rounds preserve
their inputs and provider attempts; no fact ledger, score or repair gate runs.
"""
from __future__ import annotations

import hashlib
import html
import json
import uuid
from pathlib import Path

CONTRACT = "frontmind-natural-prose/16.5"
PATTERNS = frozenset({"P01", "P02", "P03", "P04", "P05", "P06"})


def enabled(state):
    return (state.get("job_kind") == "article"
            and state.get("selected_pattern_id") in PATTERNS
            and state.get("metadata", {}).get("natural_prose_contract") == CONTRACT)


def digest(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def review_schema():
    return {"type": "object", "properties": {
        "needs_revision": {"type": "boolean", "description": "当前完整稿是否仍有实际影响发布的阅读问题，需要全文编辑处理。"},
        "comments": {"type": "array", "items": {"type": "string"},
                     "description": "具体原句或段落、阅读问题和修改方向；已自然可发布时为空。"}},
        "required": ["needs_revision", "comments"], "additionalProperties": False}


def validate_review(value):
    from .natural_editor import validate_review as validate
    return validate(value)


def input_body(wf, job, *, after_repair=False):
    from .editorial_contracts import prepare_finalize_input
    from .natural_editor import validate_repair
    if after_repair:
        return validate_repair(wf.read_json(Path(job) / "production/article_repaired.json"))["article_markdown"]
    return prepare_finalize_input(wf, job, p0=False)["candidate_markdown"]


def repair_context(wf, job):
    value = wf.read_json(Path(job) / "production/article_revision_input.json")
    if value.get("contract") != CONTRACT or digest(value["article_markdown"]) != value.get("base_sha256"):
        raise ValueError("全文修订输入不是当前已保存的失败候选")
    validate_review({"needs_revision": True, "comments": value["comments"]})
    return value


def _review_input(wf, job, action):
    return {"contract": CONTRACT, "action": action,
            "base_sha256": digest(input_body(wf, job, after_repair=action == "article_polish"))}


def validate_action(wf, job, action, value):
    validate_review(value)
    binding = wf.read_json(Path(job) / "production/article_review_input.json")
    if binding != _review_input(wf, job, action):
        raise ValueError("验读输入已改变，请读取当前完整候选")
    if not value["needs_revision"]:
        from .writing_context_v165 import hard_length_range
        bounds = hard_length_range(wf, job)
        if bounds:
            from .natural_editor import character_count
            actual = character_count(input_body(wf, job, after_repair=action == "article_polish"))
            if not bounds["minimum"] <= actual <= bounds["maximum"]:
                raise ValueError("当前稿未满足用户明确指定的硬性篇幅要求")
    return value


def _round_dir(wf, job):
    state = wf.load_state(job)
    meta = state["metadata"]
    if not meta.get("natural_editorial_session"):
        meta["natural_editorial_session"] = uuid.uuid4().hex
        wf.save_state(job, state)
    return Path(job) / "production/editorial_rounds" / meta["natural_editorial_session"] / f'{meta.get("natural_editorial_round", 0):03d}'


def _source(wf, job, action, body, review_action):
    state = wf.load_state(job)
    offline = state.get("flags", {}).get("offline_fixture") is True
    latest = {} if offline else wf.read_json(Path(job) / "provider" / action / "runtime/latest.json")
    return {"contract": CONTRACT, "action": action, "attempt_id": latest.get("attempt_id"),
            "source": "offline_fixture" if offline else wf.profile_for(action)["model"],
            "result_file": "production/article_repaired.json" if action == "article_repair" else "production/article_edited.json",
            "body_sha256": digest(body), "review_action": review_action,
            "review_round": state.get("metadata", {}).get("natural_editorial_round", 0)}


def _accept(wf, job, body, action, review_action):
    from .natural_editor import character_count
    wf.atomic_json(Path(job) / "production/article_finalized.json", {
        "contract": CONTRACT, "outcome": "accepted", "article_markdown": body,
        "editorial_notes": [], "reason": "", "character_count": character_count(body)})
    wf.atomic_json(Path(job) / "production/article_final_source.json", _source(wf, job, action, body, review_action))


def validate_selected(wf, job):
    final = wf.read_json(Path(job) / "production/article_finalized.json")
    source = wf.read_json(Path(job) / "production/article_final_source.json")
    body = wf.read_json(Path(job) / source["result_file"])["article_markdown"]
    review = wf.read_json(Path(job) / "production" / ("article_polish_review.json" if source["review_action"] == "article_polish" else "article_editorial_review.json"))
    validate_review(review)
    if (final.get("contract") != CONTRACT or source.get("contract") != CONTRACT
            or review["needs_revision"] or final.get("article_markdown") != body
            or source.get("body_sha256") != digest(body)):
        raise ValueError("交付正文须为通过当前验读的实际完整稿")
    binding = wf.read_json(Path(job) / "production/article_review_input.json")
    if binding != {"contract": CONTRACT, "action": source["review_action"], "base_sha256": digest(body)}:
        raise ValueError("通过的验读未绑定交付正文")
    if not wf.load_state(job).get("flags", {}).get("offline_fixture"):
        attempt = Path(job) / "provider" / source["action"] / "runtime/attempts" / source["attempt_id"]
        actual = wf.read_json(attempt / "validated_result.json")
        if actual.get("article_markdown") != body:
            raise ValueError("交付正文与实际作者请求结果不一致")
    return final


def stage_signature(wf, job, stage):
    names = {"draft": "draft", "edit": "edited", "finalize": "editorial_review",
             "repair": "repaired", "polish": "polish_review", "titles": "titles", "title_review": "title_review"}
    path = Path(job) / "production" / f'article_{names.get(stage, stage)}.json'
    value = {"contract": CONTRACT, "stage": stage, "output": wf.sha256_file(path) if path.is_file() else None}
    from . import writing_context_v165 as prose
    builders = {"draft": prose.prompt_article, "edit": prose.prompt_edit,
                "titles": lambda module, root: module.prompt_titles(root, p0=False),
                "title_review": lambda module, root: module.writing_context.prompt_title_review(module, root, p0=False)}
    if stage in builders:
        from .model_runtime import request_fingerprint
        value["request"] = request_fingerprint("article_" + stage, builders[stage](wf, job))
    return digest(json.dumps(value, sort_keys=True))


def _advance(wf, job, stage, next_stage):
    state = wf.load_state(job)
    state["pending_action"] = None
    state["metadata"].setdefault("article_production_bindings", {})[stage] = stage_signature(wf, job, stage)
    state["flags"]["article_production_step"] = next_stage
    wf.save_state(job, state)
    render_process(wf, job)


def render_process(wf, job):
    """Render only actual artifacts and editorial results, with no model call."""
    root = Path(job)
    state = wf.load_state(job)
    labels = {"draft": "初稿", "edited": "全文编辑稿", "repaired": "全文修订稿", "finalized": "通过验读的正文"}
    links = []
    for suffix, label in labels.items():
        path = root / f"production/article_{suffix}.json"
        if path.is_file():
            manuscript = wf.read_json(path)
            body = manuscript.get("article_markdown", "")
            if body:
                wf.atomic_text(root / f"reviews/manuscripts/article_{suffix}.html", wf.markdown_to_html(body, label))
                links.append(f'<li><a href="manuscripts/article_{suffix}.html">{label}</a></li>')
    notes = []
    for path in sorted((root / "production/editorial_rounds").glob("*/*/review.json")):
        value = wf.read_json(path)
        status = "需要全文编辑" if value["needs_revision"] else "自然文风验读通过"
        candidate = wf.read_json(path.parent / "candidate.json")
        wf.atomic_text(path.parent / "candidate.html", wf.markdown_to_html(candidate["article_markdown"], "本轮完整稿"))
        notes.append(f'<article><h2>第 {int(path.parent.name) + 1} 次验读：{status}</h2>'
                     + '<a href="../'+(path.parent / 'candidate.html').relative_to(root).as_posix()+'">本轮完整候选</a>'
                     + ''.join('<p>'+html.escape(x)+'</p>' for x in value["comments"]) + '</article>')
    receipts = []
    for path in (root / "provider").glob("*/runtime/attempts/*/execution.json"):
        value = wf.read_json(path)
        if value.get("action", "").startswith("article_"):
            receipts.append((value.get("started_at", ""), value.get("action", ""), value.get("status", ""), value.get("completed_at") or ""))
    tools = []
    for path in (root / "provider").glob("*/runtime/attempts/*/tool_*.json"):
        value = wf.read_json(path)
        tools.append((value.get("started_at", ""), value.get("name", ""), value.get("status", ""), value.get("completed_at") or ""))
    def table(rows):
        return '<table><tr><th>开始时间</th><th>动作</th><th>实际状态</th><th>完成时间</th></tr>' + ''.join(
            '<tr>' + ''.join('<td>'+html.escape(str(cell))+'</td>' for cell in row) + '</tr>' for row in sorted(rows)) + '</table>'
    executions = ('<h2>实际阶段记录</h2>' + table(receipts) if receipts else '')
    executions += ('<details><summary>实际工具回执</summary>' + table(tools) + '</details>' if tools else '')
    page = ('<!doctype html><meta charset="utf-8"><title>写作过程</title>'
            '<style>body{max-width:1000px;margin:48px auto;padding:0 24px;font:17px/1.8 system-ui;background:#faf8f3;color:#24352f}a{color:#276456}article{border-top:1px solid #ddd;margin-top:28px}h1,h2{line-height:1.4}table{width:100%;font-size:13px;border-collapse:collapse}th,td{padding:8px;border:1px solid #ddd;text-align:left}details{margin-top:24px}</style>'
            '<h1>'+html.escape(state.get("question", {}).get("question_text", "写作过程"))+'</h1>'
            '<p>当前步骤：'+html.escape(state.get("flags", {}).get("article_production_step", state.get("status", "")))+'</p>'
            '<p>初稿与全文编辑：DeepSeek high。页面展示实际稿件和验读意见。</p><ul>'+''.join(links)+'</ul>'+''.join(notes)+executions)
    wf.atomic_text(root / "reviews/article_process.html", page)


def run_production(wf, job):
    from . import editorial_contracts as ec, natural_editor, writing_context_v165 as prose
    from . import title_publication, title_strategy
    root = Path(job)
    state = wf.load_state(root)
    step = state.get("flags", {}).get("article_production_step", "draft")
    production = root / "production"
    from .manuscript_revision import current_revision, current_title_revision
    title_only = current_title_revision(wf, root, p0=False)
    revision = current_revision(wf, root, p0=False)
    prior = (["titles", "title_review"] if title_only else
             (["edit"] if revision else ["draft", "edit"]) + ["titles", "title_review"])
    preceding = {"draft": [], "edit": ["draft"], "finalize": ["draft", "edit"],
                 "repair": ["draft", "edit"], "polish": ["draft", "edit"],
                 "titles": ["draft", "edit"], "title_review": ["draft", "edit", "titles"],
                 "deliver": ["draft", "edit", "titles", "title_review"]}.get(step, [])
    bindings = state.get("metadata", {}).get("article_production_bindings", {})
    for previous in (x for x in preceding if x in prior):
        if bindings.get(previous) != stage_signature(wf, root, previous):
            state["flags"]["article_production_step"] = previous
            wf.save_state(root, state)
            for target in ("draft", "edit", "finalize", "repair", "polish", "titles", "title_review"):
                if target != "draft" or previous == "draft":
                    wf.invalidate_action(root, "article_" + target)
            return None
    if step == "draft":
        wf.archive_production_stage(root, "article", "draft")
        result = wf.ensure_action(root, "article_draft", prose.prompt_article(wf, root),
                                  fixture_builder=lambda: wf.fixture_article(root, p0=False))
        if result is None:
            return 0
        if result.get("requires_blueprint_reconfirmation"):
            return wf._return_blueprint_after_substantive_edit(root, p0=False, reason=result["reconfirmation_reason"])
        wf.atomic_json(production / "article_draft.json", result)
        _advance(wf, root, step, "edit")
        return None
    if step == "edit":
        wf.archive_production_stage(root, "article", "edit")
        result = wf.ensure_action(root, "article_edit", prose.prompt_edit(wf, root),
                                  fixture_builder=lambda: wf.fixture_edit(root, p0=False))
        if result is None:
            return 0
        if result.get("edit_status") == "requires_blueprint_reconfirmation":
            return wf._return_blueprint_after_substantive_edit(root, p0=False, reason=result["reconfirmation_reason"])
        wf.atomic_json(production / "article_edited.json", result)
        state = wf.load_state(root)
        state["metadata"].update(natural_editorial_session=uuid.uuid4().hex, natural_editorial_round=0)
        wf.save_state(root, state)
        _advance(wf, root, step, "finalize")
        return None
    if step in {"finalize", "polish"}:
        action = "article_" + step
        body = input_body(wf, root, after_repair=step == "polish")
        wf.atomic_json(production / "article_review_input.json", _review_input(wf, root, action))
        result = wf.ensure_action(root, action, prose.prompt_finish(wf, root, after_repair=step == "polish"),
                                  fixture_builder=lambda: {"needs_revision": False, "comments": []})
        if result is None:
            return 0
        validate_action(wf, root, action, result)
        round_dir = _round_dir(wf, root)
        wf.atomic_json(round_dir / "candidate.json", {"article_markdown": body, "base_sha256": digest(body)})
        wf.atomic_json(round_dir / "review.json", result)
        wf.atomic_json(production / ("article_editorial_review.json" if step == "finalize" else "article_polish_review.json"), result)
        if result["needs_revision"]:
            wf.atomic_json(production / "article_revision_input.json", {
                "contract": CONTRACT, "article_markdown": body, "base_sha256": digest(body),
                "comments": result["comments"], "review_action": action})
            state = wf.load_state(root)
            state["metadata"]["natural_editorial_round"] = state["metadata"].get("natural_editorial_round", 0) + 1
            epochs = state["flags"].setdefault("model_action_epochs", {})
            for target in ("article_repair", "article_polish"):
                epochs[target] = uuid.uuid4().hex
            wf.save_state(root, state)
            wf.invalidate_action(root, "article_repair")
            wf.invalidate_action(root, "article_polish")
            _advance(wf, root, step, "repair")
        else:
            _accept(wf, root, body, "article_repair" if step == "polish" else "article_edit", action)
            _advance(wf, root, step, "titles")
        return None
    if step == "repair":
        context = repair_context(wf, root)
        result = wf.ensure_action(root, "article_repair", prose.prompt_repair(wf, root),
                                  fixture_builder=lambda: {"article_markdown": context["article_markdown"]})
        if result is None:
            return 0
        natural_editor.validate_repair(result)
        wf.atomic_json(_round_dir(wf, root) / "writer.json", result)
        wf.atomic_json(production / "article_repaired.json", result)
        _advance(wf, root, step, "polish")
        return None
    if step == "titles":
        validate_selected(wf, root)
        wf.archive_production_stage(root, "article", "titles")
        result = wf.ensure_action(root, "article_titles", wf.prompt_titles(root, p0=False),
                                  fixture_builder=lambda: wf.fixture_titles(root, p0=False))
        if result is None:
            return 0
        wf.atomic_json(production / "article_titles.json", result)
        _advance(wf, root, step, "title_review")
        return None
    if step == "title_review":
        raw = wf.read_json(production / "article_titles.json")
        result = wf.ensure_action(root, "article_title_review", wf.writing_context.prompt_title_review(wf, root, p0=False),
            fixture_builder=lambda: {"outcome": "accepted", **title_publication.title_review_input(raw, p0=False,
                expected_count=title_strategy.expected_count(state), expected_policy=title_strategy.policy(state)), "title_notes": [], "reason": ""})
        if result is None:
            return 0
        wf.atomic_json(production / "article_title_review.json", result)
        if result["outcome"] == "incomplete":
            raise wf.WorkflowError("标题编辑未完成：" + result["reason"])
        _advance(wf, root, step, "deliver")
        return None
    if step == "deliver":
        final = validate_selected(wf, root)
        delivery = wf.deliver_article(root, final["article_markdown"], wf.read_json(production / "article_titles.json"),
            prefix="article", title_review=wf.read_json(production / "article_title_review.json"))
        state = wf.load_state(root)
        state["flags"].pop("article_production_step", None)
        state["metadata"]["delivery"] = delivery
        wf.save_state(root, state)
        wf.set_status(root, "completed", "E10")
        render_process(wf, root)
        selection = state.get("metadata", {}).get("p02_reference_pack_delivery")
        original_pack = {"pack_id": state["reference_pack"]["pack_id"], "pack_version": state["reference_pack"]["pack_version"]}
        return wf.emit_completed_delivery({"status": "completed", "job_id": state["job_id"],
            "reference_pack": ({"pack_id": selection["pack_id"], "pack_version": selection["pack_version"],
                                "path": selection["pack_path"], "portable_zip": selection["portable_zip_path"]} if selection else original_pack),
            **({"source_reference_pack": original_pack, "p02_reference_pack_delivery": selection} if selection else {}),
            **({"question_source_delivery": state["metadata"]["question_source_delivery"]} if state.get("metadata", {}).get("question_source_delivery") else {}),
            "pattern_id": state["selected_pattern_id"], "delivery": delivery,
            "title_count": wf.read_json(Path(delivery["title_map"]))["total_count"]}, delivery)
    raise wf.WorkflowError("未知自然写作步骤：" + step)
