#!/usr/bin/env python3
"""Version and state constants for FrontMind Content Workflow v4.11.0."""
from __future__ import annotations

from types import MappingProxyType


RELEASE_VERSION = "4.11.0"
WORKFLOW_VERSION = "4.11"
CONTENT_JOB_VERSION = "4.11"
CONTROLLER_PROVIDER_VERSION = "4"
REFERENCE_PACK_VERSION = "4.1"
TITLE_MAP_VERSION = "4.11"
TITLE_CONTRACT_VERSION = "4.11-natural-title-1"

ACTIVE_PATTERN_IDS = frozenset({"P00", "P01", "P02", "P03", "P04", "P05", "P06"})
QUESTION_PATTERN_IDS = frozenset({"P01", "P02", "P03", "P04", "P05", "P06"})
QUESTION_POSITIONING_PATTERNS = frozenset({"P01", "P02"})

USER_PAUSE_STATUSES = frozenset({
    "awaiting_reference_pack_route",
    "awaiting_reference_pack_input",
    "awaiting_question_research_inputs",
    "awaiting_competitor_selection",
    "awaiting_core_positioning_direction",
    "awaiting_core_positioning_confirmation",
    "awaiting_p0_route",
    "awaiting_p0_example_confirmation",
    "awaiting_p0_blueprint_confirmation",
    "awaiting_response_brief",
    "awaiting_pattern_confirmation",
    "awaiting_example_confirmation",
    "awaiting_question_positioning_confirmation",
    "awaiting_blueprint_confirmation",
})

INTERNAL_STATUSES = frozenset({
    "running_reference_material_intake",
    "running_positioning_market_research",
    "running_positioning_value_synthesis",
    "running_positioning_competitive_tiering",
    "running_positioning_brand_placement",
    "running_positioning_positioning_polish",
    "running_positioning_choice_map",
    "running_positioning_direction_generation",
    "running_positioning_direction_critique",
    "running_core_positioning_synthesis",
    "running_core_positioning_critique",
    "running_reference_pack_assembly",
    "running_p0_example_discovery",
    "running_p0_blueprint",
    "running_p0_production",
    "running_reference_pack_p0_commit",
    "running_answer_analysis",
    "running_question_positioning",
    "running_article_blueprint",
    "running_article_production",
})

TERMINAL_STATUSES = frozenset({"positioning_ready", "p0_ready", "completed"})
ACTIVE_JOB_STATUSES = USER_PAUSE_STATUSES | INTERNAL_STATUSES | TERMINAL_STATUSES

CONTRACT_VERSIONS = MappingProxyType({
    "workflow": WORKFLOW_VERSION,
    "content_job": CONTENT_JOB_VERSION,
    "controller_provider": CONTROLLER_PROVIDER_VERSION,
    "reference_pack": REFERENCE_PACK_VERSION,
    "title_map": TITLE_MAP_VERSION,
    "title_contract": TITLE_CONTRACT_VERSION,
})


def require_contract_version(name: str, value: object) -> str:
    if name not in CONTRACT_VERSIONS:
        raise ValueError("contract_version_name_unknown")
    expected = CONTRACT_VERSIONS[name]
    if str(value or "").strip() != expected:
        raise ValueError(f"contract_version_mismatch:{name}:{expected}")
    return expected


__all__ = [name for name in globals() if name.isupper()] + ["require_contract_version"]
