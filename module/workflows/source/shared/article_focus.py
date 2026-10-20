"""Freeze the reader task and content boundary for a new article Job.

This is a task contract, not a claim that the suggested questions came from
monitoring. Older Jobs have no such contract and keep their frozen prompts.
"""
from __future__ import annotations

import json

CONTRACT = "frontmind-article-focus/1"
PREVIOUS_PROMPT_REVISION = "fdnv2-focus-1"
PROMPT_REVISION = "fdnv2-focus-2"
MARKER = '<frontmind_article_focus version="1" />'
DRAFT_MARKER = '<frontmind_editorial_revision version="2" />'


def configure(state: dict, *, focus: str = "", reader_questions: list[str] | None = None,
              excluded_topics: list[str] | None = None) -> None:
    """只在新建 Job 时调用；空字段不冒充用户确认。"""
    topic = str(focus or "").strip()
    questions = [str(item).strip() for item in (reader_questions or [])]
    exclusions = [str(item).strip() for item in (excluded_topics or [])]
    if any(not item for item in questions + exclusions):
        raise ValueError("读者问题和排除主题不能是空白")
    if len(questions) > 8 or len(exclusions) > 12:
        raise ValueError("读者问题最多 8 条，排除主题最多 12 条")
    if len(set(questions)) != len(questions) or len(set(exclusions)) != len(exclusions):
        raise ValueError("读者问题或排除主题不能重复")
    if len(topic) > 300 or any(len(item) > 300 for item in questions + exclusions):
        raise ValueError("写作聚焦字段不能超过 300 字")
    state.setdefault("metadata", {})["article_focus"] = {
        "contract": CONTRACT, "focus": topic,
        "reader_questions": questions, "excluded_topics": exclusions,
        "question_origin": "user_input" if questions else "none",
    }
    state["metadata"]["prompt_revision"] = PROMPT_REVISION


def spec(state: dict) -> dict | None:
    value = state.get("metadata", {}).get("article_focus")
    return value if isinstance(value, dict) and value.get("contract") == CONTRACT else None


def enabled(state: dict) -> bool:
    return spec(state) is not None and state.get("metadata", {}).get("prompt_revision") in {
        PREVIOUS_PROMPT_REVISION, PROMPT_REVISION,
    }


def revised(state: dict) -> bool:
    """新任务启用新的蓝图及初稿规则；既有任务继续使用冻结版本。"""
    return enabled(state) and state.get("metadata", {}).get("prompt_revision") == PROMPT_REVISION


def context(state: dict) -> str:
    value = spec(state)
    if not value:
        return ""
    return "<article_focus>\n" + json.dumps(value, ensure_ascii=False, indent=2) + (
        "\n主题和问题是本篇边界；未填写时以正式问题和已确认 article_brief 为准。"
        "只从实际材料中选相关事实，排除主题不进正文；必要的事实限定仍须保留。"
        "用户输入的问题不等于已验证的监控搜索词。\n</article_focus>"
    )
