"""Frozen title policies: v4 adds independent reader hooks and placement hints.

The v1 policy and absent-policy requests retain their original behavior.
"""
from __future__ import annotations

LEGACY_CONTRACT = "frontmind-category-titles/1"
LEGACY_MARKER = '<frontmind_category_titles version="1" />'
LEGACY_POLICY = {"contract": LEGACY_CONTRACT, "requested_count": 10, "brand_policy": "omit_by_default"}
V2_CONTRACT = "frontmind-category-titles/2"
V2_MARKER = '<frontmind_category_titles version="2" />'
V2_POLICY = {"contract": V2_CONTRACT, "requested_count": 10, "brand_policy": "omit_by_default"}
V3_CONTRACT = "frontmind-category-titles/3"
V3_MARKER = '<frontmind_category_titles version="3" />'
V3_POLICY = {"contract": V3_CONTRACT, "requested_count": 10, "brand_policy": "preserve_pattern_policy"}
CONTRACT = "frontmind-category-titles/4"
MARKER = '<frontmind_category_titles version="4" />'
DEFAULT = {"contract": CONTRACT, "requested_count": 10, "brand_policy": "preserve_pattern_policy"}
TITLE_HOOKS_CONTRACT_VERSION = "16.8-diverse-headlines-1"
STYLE_SEQUENCE = ("formal",) * 5 + ("scenario",) * 5
STYLE_LABELS = {"formal": "正式标题", "scenario": "场景卖点"}


def validate_policy(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value not in (DEFAULT, V3_POLICY, V2_POLICY, LEGACY_POLICY):
        raise ValueError("未知或不一致的标题策略")
    return dict(value)


def grouped(value):
    return validate_policy(value) in (DEFAULT, V3_POLICY, V2_POLICY)


def style_label(style):
    return STYLE_LABELS.get(style, "")


def marker(value):
    value = validate_policy(value)
    return MARKER if value == DEFAULT else V3_MARKER if value == V3_POLICY else V2_MARKER if value == V2_POLICY else LEGACY_MARKER if value == LEGACY_POLICY else ""


def eligible(state):
    return state.get("job_kind") == "p0" or (state.get("job_kind") == "article" and state.get("selected_pattern_id") in {"P01", "P02", "P03", "P04", "P05", "P06"})


def policy(state):
    if not eligible(state):
        return None
    meta = state.get("metadata", {})
    # A frozen revision wins even when it predates this policy.
    revision = meta.get("p0_title_revision" if state.get("job_kind") == "p0" else "article_title_revision")
    source = revision if revision is not None else meta
    value = source.get("title_strategy")
    value = validate_policy(value)
    if value in (V2_POLICY, LEGACY_POLICY) and (state.get("job_kind") != "article" or state.get("selected_pattern_id") not in {"P01", "P02"}):
        return None
    return value


def enabled(state):
    return policy(state) is not None


def expected_count(state):
    return 10 if enabled(state) else 20


def request_policy(prompt):
    # Match only the host-owned prefix, never a marker quoted in source prose.
    from .writing_context_v14 import MARKER as EDITOR_MARKER
    if isinstance(prompt, str):
        for value in (DEFAULT, V3_POLICY, V2_POLICY, LEGACY_POLICY):
            if prompt.startswith(EDITOR_MARKER + "\n" + marker(value) + "\n"):
                return dict(value)
    return None


def matches(prompt):
    return request_policy(prompt) is not None
