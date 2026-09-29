"""One editorial response followed, when needed, by one writer revision.

The selected manuscript is a projection of an actual writer result. The host's
comments remain a separate artifact and never claim to be a rewritten body.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

CONTRACT = "frontmind-natural-editor/4.13.2-final12"
MARKER = '<frontmind_natural_editor version="4.13.2-final12">'


def enabled(state):
    meta = state.get("metadata", {})
    return (meta.get("writing_editor_contract") == CONTRACT or
            meta.get("article_reader_contract") == "frontmind-article-editor/4.13.2-final12")


def matches(prompt):
    from .language_editor_v15 import matches as v15_matches
    if v15_matches(prompt):
        return True
    from .writing_requirements import MARKER as CURRENT_MARKER, MISSION_MARKER
    from .writing_context_v14 import MARKER as GENERAL_MARKER
    return isinstance(prompt, str) and prompt.startswith((MARKER + "\n", CURRENT_MARKER + "\n", MISSION_MARKER + "\n", GENERAL_MARKER + "\n"))


def system(action, prompt=""):
    from . import writing_context_v16
    if writing_context_v16.matches(prompt):
        return writing_context_v16.system(action, prompt)
    from . import writing_context_v15
    if writing_context_v15.matches(prompt):
        return writing_context_v15.system(action, prompt)
    from . import writing_context_v14
    if writing_context_v14.matches(prompt):
        return writing_context_v14.system(action, prompt)
    from . import writing_requirements
    from .article_positioning import natural_system
    from .model_runtime import WRITING_FACTS_CORE, DEEPSEEK_TITLES_SYSTEM, GLM_TITLE_REVIEW_SYSTEM
    if action.endswith("_titles"):
        return DEEPSEEK_TITLES_SYSTEM
    if action.endswith("_title_review"):
        return GLM_TITLE_REVIEW_SYSTEM
    if prompt.startswith(writing_requirements.MISSION_MARKER + "\n"):
        return writing_requirements.editorial_system(action)
    if prompt.startswith(writing_requirements.MARKER + "\n"):
        return writing_requirements.system(action, facts_core=WRITING_FACTS_CORE)
    return natural_system(action, facts_core=WRITING_FACTS_CORE)


def validate_review(value):
    if not isinstance(value, dict) or set(value) != {"needs_revision", "comments"}:
        raise ValueError("编辑意见只包含 needs_revision 和 comments，不返回改写正文")
    if type(value["needs_revision"]) is not bool or not isinstance(value["comments"], list):
        raise ValueError("编辑意见格式无效")
    if any(not isinstance(x, str) or not x.strip() for x in value["comments"]):
        raise ValueError("编辑意见须为具体的非空文字")
    if bool(value["comments"]) != value["needs_revision"]:
        raise ValueError("是否返工与编辑意见不一致")
    return value


def review_schema():
    return {"type": "object", "properties": {
        "needs_revision": {"type": "boolean"},
        "comments": {"type": "array", "items": {"type": "string"}}},
        "required": ["needs_revision", "comments"], "additionalProperties": False}


def validate_repair(value):
    if not isinstance(value, dict) or set(value) != {"article_markdown"} or not isinstance(value["article_markdown"], str) or not value["article_markdown"].strip():
        raise ValueError("返工须返回完整 article_markdown")
    return value


def character_count(markdown):
    """Visible non-whitespace characters, excluding Markdown formatting."""
    text = re.sub(r"\A\s*# [^\n]*(?:\n|$)", "", markdown, count=1)
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    return len(re.sub(r"\s|[*_`]", "", text))


def digest(body):
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def select_final(wf, job, *, p0):
    from . import language_editor_v15
    if not p0 and language_editor_v15.enabled(wf.load_state(job)):
        return language_editor_v15.select_final(wf, job)
    from .editorial_contracts import prepare_finalize_input
    prefix = "p0" if p0 else "article"
    context = prepare_finalize_input(wf, job, p0=p0)
    review = validate_review(wf.read_json(job / "production" / f"{prefix}_editorial_review.json"))
    if review["needs_revision"]:
        action = prefix + "_repair"
        file = f"production/{prefix}_repaired.json"
        body = validate_repair(wf.read_json(job / file))["article_markdown"]
    else:
        source = context["candidate_source"]
        suffix = {"deepseek_style": "style", "deepseek_edit": "edit", "deepseek_draft": "draft"}.get(source)
        if suffix is None:
            raise ValueError("候选正文没有成功的作者来源")
        action = prefix + "_" + suffix
        file = f"production/{prefix}_" + {"style": "styled", "edit": "edited", "draft": "draft"}[suffix] + ".json"
        body = context["candidate_markdown"]
    offline = wf.load_state(job).get("flags", {}).get("offline_fixture") is True
    latest = {} if offline else wf.read_json(job / "provider" / action / "runtime/latest.json")
    record = {} if offline else wf.read_json(job / "provider" / action / "runtime/attempts" / latest["attempt_id"] / "execution.json")
    source = {"contract": CONTRACT, "action": action, "attempt_id": latest.get("attempt_id"),
              "source": "offline_fixture" if offline else record["requested_configuration"]["model"],
              "result_file": file, "candidate_source": context["candidate_source"],
              "body_sha256": digest(body), "review_action": prefix + "_finalize"}
    final = {"contract": CONTRACT, "outcome": "revised" if review["needs_revision"] else "accepted",
             "article_markdown": body, "editorial_notes": [], "reason": "",
             "character_count": character_count(body)}
    wf.atomic_json(job / "production" / f"{prefix}_finalized.json", final)
    wf.atomic_json(job / "production" / f"{prefix}_final_source.json", source)
    return final


def validate_selected(wf, job, candidate, *, p0):
    from . import language_editor_v15
    if not p0 and language_editor_v15.enabled(wf.load_state(job)):
        return language_editor_v15.validate_selected(wf, job)
    prefix = "p0" if p0 else "article"
    final = wf.read_json(job / "production" / f"{prefix}_finalized.json")
    review = validate_review(wf.read_json(job / "production" / f"{prefix}_editorial_review.json"))
    expected = (validate_repair(wf.read_json(job / "production" / f"{prefix}_repaired.json"))["article_markdown"]
                if review["needs_revision"] else candidate)
    if final.get("contract") != CONTRACT or final.get("article_markdown") != expected or final.get("outcome") != ("revised" if review["needs_revision"] else "accepted"):
        raise ValueError("最终正文与实际选定的作者稿不一致")
    return final
