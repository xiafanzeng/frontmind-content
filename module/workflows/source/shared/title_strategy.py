"""Frozen title policies: v2 has five formal and five scenario titles.

The v1 policy and absent-policy requests retain their original behavior.
"""
from __future__ import annotations

LEGACY_CONTRACT = "frontmind-category-titles/1"
LEGACY_MARKER = '<frontmind_category_titles version="1" />'
LEGACY_POLICY = {"contract": LEGACY_CONTRACT, "requested_count": 10, "brand_policy": "omit_by_default"}
CONTRACT = "frontmind-category-titles/2"
MARKER = '<frontmind_category_titles version="2" />'
DEFAULT = {"contract": CONTRACT, "requested_count": 10, "brand_policy": "omit_by_default"}
STYLE_SEQUENCE = ("formal",) * 5 + ("scenario",) * 5
STYLE_LABELS = {"formal": "严肃推荐", "scenario": "场景卖点"}


def validate_policy(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value not in (DEFAULT, LEGACY_POLICY):
        raise ValueError("未知或不一致的标题策略")
    return dict(value)


def grouped(value):
    return validate_policy(value) == DEFAULT


def style_label(style):
    return STYLE_LABELS.get(style, "")


def marker(value):
    value = validate_policy(value)
    return MARKER if value == DEFAULT else LEGACY_MARKER if value == LEGACY_POLICY else ""


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
    return validate_policy(value)


def enabled(state):
    return policy(state) is not None


def expected_count(state):
    return 10 if enabled(state) else 20


def request_policy(prompt):
    # Match only the host-owned prefix, never a marker quoted in source prose.
    from .writing_context_v14 import MARKER as EDITOR_MARKER
    if isinstance(prompt, str):
        for value in (DEFAULT, LEGACY_POLICY):
            if prompt.startswith(EDITOR_MARKER + "\n" + marker(value) + "\n"):
                return dict(value)
    return None


def matches(prompt):
    return request_policy(prompt) is not None
