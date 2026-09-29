"""Frozen category-title policy; absent policy means the historical 20 titles."""
from __future__ import annotations

CONTRACT = "frontmind-category-titles/1"
MARKER = '<frontmind_category_titles version="1" />'
DEFAULT = {"contract": CONTRACT, "requested_count": 10, "brand_policy": "omit_by_default"}


def eligible(state):
    return state.get("job_kind") == "article" and state.get("selected_pattern_id") in {"P01", "P02"}


def policy(state):
    if not eligible(state):
        return None
    meta = state.get("metadata", {})
    # A frozen revision wins even when it predates this policy.
    revision = meta.get("article_title_revision")
    source = revision if revision is not None else meta
    value = source.get("title_strategy")
    if value is None:
        return None
    if value != DEFAULT:
        raise ValueError("未知或不一致的标题策略")
    return dict(value)


def enabled(state):
    return policy(state) is not None


def expected_count(state):
    return 10 if enabled(state) else 20


def matches(prompt):
    # Match only the host-owned prefix, never a marker quoted in source prose.
    from .writing_context_v14 import MARKER as EDITOR_MARKER
    return isinstance(prompt, str) and prompt.startswith(EDITOR_MARKER + "\n" + MARKER + "\n")
