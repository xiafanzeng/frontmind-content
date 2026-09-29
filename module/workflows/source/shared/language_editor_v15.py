"""Versioned, bounded XTY sentence edits applied to the actual writer manuscript.

This module validates editing permissions and provenance, not prose quality.
Old editorial contracts remain handled by natural_editor without migration.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

CONTRACT = "frontmind-natural-prose/15"
MARKER = '<frontmind_natural_prose version="15">'


def enabled(state):
    return (state.get("metadata", {}).get("natural_prose_contract") in {CONTRACT, "frontmind-natural-prose/16"}
            and state.get("selected_pattern_id") in {"P01", "P02"})


def matches(prompt):
    return isinstance(prompt, str) and prompt.startswith((MARKER + "\n", '<frontmind_natural_prose version="16">\n'))


def contract_for(wf, job):
    return wf.load_state(job).get("metadata", {}).get("natural_prose_contract", CONTRACT)


def validate_body_character_range(value):
    if (not isinstance(value, dict) or set(value) != {"minimum", "maximum"}
            or any(type(value[key]) is not int for key in ("minimum", "maximum"))
            or not 0 < value["minimum"] <= value["maximum"]):
        raise ValueError("body_character_range须包含正整数minimum与maximum，且minimum不大于maximum")
    return dict(value)


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def review_schema():
    return {"type": "object", "properties": {
        "needs_revision": {"type": "boolean", "description": "是否有须由作者处理的内容组织问题，包括内容主次、多段内的项目目录与逐词释义、同义铺陈和重复赘述；不限于章节重排。句级微调用local_edits直接完成。"},
        "comments": {"type": "array", "items": {"type": "string"},
                     "description": "只给需要作者处理的少量主要问题；无需结构返工时为空。"},
        "local_edits": {"type": "array", "items": {"type": "object", "properties": {
            "original": {"type": "string", "minLength": 1, "description": "从当前稿连续摘录的单段片段，必须唯一命中。"},
            "replacement": {"type": "string", "description": "句级修改，不改变标题、加粗主体或段落结构。"}},
            "required": ["original", "replacement"], "additionalProperties": False}}},
        "required": ["needs_revision", "comments", "local_edits"], "additionalProperties": False}


def _structure(body):
    paragraphs = re.split(r"\n\s*\n", body.strip())
    return (len(paragraphs), re.findall(r"(?m)^#{1,6}\s+[^\n]*", body),
            re.findall(r"\*\*[^\n]*?\*\*|__[^\n]*?__", body))


def apply_local_edits(body, edits):
    """Apply exact non-overlapping spans simultaneously, preserving structure."""
    if not isinstance(body, str) or not body.strip():
        raise ValueError("局部编辑缺少完整基稿")
    spans = []
    headings = [(m.start(), m.end()) for m in re.finditer(r"(?m)^#{1,6}\s+[^\n]*", body)]
    for edit in edits:
        original, replacement = edit["original"], edit["replacement"]
        if any(c in original or c in replacement for c in ("\n", "\r")):
            raise ValueError("局部修改只能替换单段片段，不能增删或重排段落")
        if original == replacement:
            raise ValueError("局部修改必须有实际文字变化")
        start = body.find(original)
        if start < 0 or body.find(original, start + 1) >= 0:
            raise ValueError("局部修改原文必须在当前完整稿中唯一命中")
        end = start + len(original)
        if any(start < right and end > left for left, right in headings):
            raise ValueError("局部修改不能改变文章标题或小标题")
        spans.append((start, end, replacement))
    spans.sort(key=lambda row: row[0])
    if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
        raise ValueError("局部修改片段不能重叠")
    result = body
    for start, end, replacement in reversed(spans):
        result = result[:start] + replacement + result[end:]
    if _structure(result) != _structure(body):
        raise ValueError("局部修改不能改变标题、加粗主体或段落结构")
    return result


def validate_review(value, body=None):
    if not isinstance(value, dict) or set(value) != {"needs_revision", "comments", "local_edits"}:
        raise ValueError("v15文字编辑只提交needs_revision、comments和local_edits")
    needs, comments, edits = value["needs_revision"], value["comments"], value["local_edits"]
    if type(needs) is not bool or not isinstance(comments, list) or not isinstance(edits, list):
        raise ValueError("v15文字编辑字段类型错误")
    if any(not isinstance(item, str) or not item.strip() for item in comments):
        raise ValueError("结构意见须为具体非空文字")
    if bool(comments) != needs or (needs and edits):
        raise ValueError("结构返工只给意见；原文通过或局部编辑不能同时要求返工")
    for edit in edits:
        if (not isinstance(edit, dict) or set(edit) != {"original", "replacement"}
                or not isinstance(edit["original"], str) or not edit["original"].strip()
                or not isinstance(edit["replacement"], str)):
            raise ValueError("局部修改须给出原文及替换文字")
    if body is not None:
        apply_local_edits(body, edits)
    return value


def input_body(wf, job, *, after_repair=False):
    from .editorial_contracts import prepare_finalize_input
    from .natural_editor import validate_repair
    if after_repair:
        return validate_repair(wf.read_json(Path(job) / "production/article_repaired.json"))["article_markdown"]
    return prepare_finalize_input(wf, Path(job), p0=False)["candidate_markdown"]


def artifact_names(action):
    if action == "article_finalize":
        return "editorial_review", "editorial_input"
    if action == "article_polish":
        return "polish_review", "polish_input"
    raise ValueError("不支持的v15终稿编辑动作")


def bind_input(wf, job, action):
    _, suffix = artifact_names(action)
    body = input_body(wf, job, after_repair=action == "article_polish")
    value = {"contract": contract_for(wf, job), "action": action, "base_sha256": digest(body)}
    wf.atomic_json(Path(job) / "production" / f"article_{suffix}.json", value)
    return body


def bound_input(wf, job, action):
    _, suffix = artifact_names(action)
    body = input_body(wf, job, after_repair=action == "article_polish")
    binding = wf.read_json(Path(job) / "production" / f"article_{suffix}.json")
    if binding != {"contract": contract_for(wf, job), "action": action, "base_sha256": digest(body)}:
        raise ValueError("XTY文字修改没有绑定本次实际完整稿")
    return body


def validate_action(wf, job, action, value):
    body = bound_input(wf, job, action)
    value = validate_review(value, body)
    state = wf.load_state(job)
    bounds = state.get("metadata", {}).get("body_character_range")
    if not value["needs_revision"] and enabled(state) and bounds is not None:
        bounds = validate_body_character_range(bounds)
        from .natural_editor import character_count
        actual = character_count(apply_local_edits(body, value["local_edits"]))
        if not bounds["minimum"] <= actual <= bounds["maximum"]:
            raise ValueError(f"应用local_edits后实际正文字符数为{actual}；允许范围为"
                             f"{bounds['minimum']}—{bounds['maximum']}。请在原有句级编辑权限内调整提交。")
    return value


def _identity(wf, job, action):
    if wf.load_state(job).get("flags", {}).get("offline_fixture") is True:
        return {"action": action, "attempt_id": None, "source": "offline_fixture"}
    root = Path(job) / "provider" / action / "runtime"
    latest = wf.read_json(root / "latest.json")
    record = wf.read_json(root / "attempts" / latest["attempt_id"] / "execution.json")
    return {"action": action, "attempt_id": latest["attempt_id"],
            "source": record["requested_configuration"]["model"]}


def _selected(wf, job):
    root = Path(job) / "production"
    first = validate_action(wf, job, "article_finalize", wf.read_json(root / "article_editorial_review.json"))
    after_repair = first["needs_revision"]
    action = "article_polish" if after_repair else "article_finalize"
    suffix, _ = artifact_names(action)
    base = bound_input(wf, job, action)
    review = validate_action(wf, job, action, wf.read_json(root / f"article_{suffix}.json"))
    if review["needs_revision"]:
        raise ValueError("实际终稿仍需结构修改，不能进入标题或交付")
    body = apply_local_edits(base, review["local_edits"])
    writer_action = "article_repair" if after_repair else "article_edit"
    author = _identity(wf, job, writer_action)
    editor = _identity(wf, job, action)
    final = {"contract": contract_for(wf, job), "outcome": "revised" if after_repair or review["local_edits"] else "accepted",
             "article_markdown": body, "editorial_notes": [], "reason": ""}
    from .natural_editor import character_count
    final["character_count"] = character_count(body)
    source = {"contract": contract_for(wf, job), **editor, "author": author, "editor": editor,
              "candidate_source": "deepseek_repair" if after_repair else "deepseek_edit",
              "base_sha256": digest(base), "body_sha256": digest(body),
              "review_action": action, "review_sha256": digest(json.dumps(review, ensure_ascii=False, sort_keys=True)),
              "result_file": f"production/article_{suffix}.json"}
    return final, source


def select_final(wf, job):
    final, source = _selected(wf, job)
    wf.atomic_json(Path(job) / "production/article_finalized.json", final)
    wf.atomic_json(Path(job) / "production/article_final_source.json", source)
    return final


def validate_selected(wf, job):
    final, source = _selected(wf, job)
    root = Path(job) / "production"
    if wf.read_json(root / "article_finalized.json") != final or wf.read_json(root / "article_final_source.json") != source:
        raise ValueError("交付稿与当前作者基稿、XTY局部修改及真实来源不一致")
    return final
