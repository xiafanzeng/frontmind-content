"""Reference Pack 4.1 layout helpers for FrontMind runtime 4.11.

Reference Pack 4.1 is the only persistent package used by the workflow. It
keeps source material, reusable brand-market research, confirmed positioning,
P0, and exact-question research in separate namespaces. Readiness describes
which production stages have been completed; it is never an evidence score.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = "4.1"
PROFILE = "frontmind-content-reference-pack"
CANONICAL_PATHS = {
    "materials": "materials/",
    "brand_market": "research/brand_market/",
    "question_research": "research/question_research/",
    "registries": "registries/",
    "strategy": "strategy/",
    "p0": "p0/",
}

MATERIAL_INDEX_MEMBER = "materials/index.json"
REGISTRY_MEMBERS = {
    "knowledge_registry_path": "registries/knowledge_registry.json",
    "source_registry_path": "registries/source_registry.json",
    "claim_registry_path": "registries/claim_registry.json",
    "image_registry_path": "registries/image_registry.json",
}
BRAND_MARKET_MEMBERS = {
    "competitive_choice_map": "research/brand_market/competitive_choice_map.json",
    "competitive_choice_map_markdown": "research/brand_market/competitive_choice_map.md",
    "positioning_research_review": "research/brand_market/positioning_research_review.md",
    "brand_reality": "research/brand_market/brand_reality.md",
    "audience_choice_logic": "research/brand_market/audience_choice_logic.md",
    "competitor_landscape": "research/brand_market/competitor_landscape.md",
    "market_opportunities": "research/brand_market/market_opportunities.md",
    "ai_semantic_context": "research/brand_market/ai_semantic_context.md",
    "source_index": "research/brand_market/source_index.json",
}
STRATEGY_MEMBERS = {
    "positioning_brief": "strategy/positioning_brief.md",
    "positioning_directions": "strategy/positioning_directions.json",
    "positioning_direction_decision": "strategy/positioning_direction_decision.json",
    "core_positioning": "strategy/core_positioning.md",
    "core_positioning_record": "strategy/core_positioning.json",
    "positioning_writing_guidance": "strategy/positioning_writing_guidance.md",
    "core_positioning_confirmation": "strategy/core_positioning_confirmation.json",
}
P0_MEMBERS = {
    "p0_brand_article": "p0/p0_brand_article.md",
    "p0_html": "p0/p0.html",
    "p0_docx": "p0/p0.docx",
    "p0_title_map": "p0/p0_title_map.json",
    "p0_record": "p0/p0_record.json",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_current(pack: Any) -> bool:
    return (
        isinstance(pack, dict)
        and pack.get("schema_version") == SCHEMA_VERSION
        and pack.get("profile") == PROFILE
    )


def brand_name(pack: Any) -> str:
    if not isinstance(pack, dict):
        return ""
    if pack.get("profile") == PROFILE:
        return str(pack.get("brand_name") or "").strip()
    brand = pack.get("brand") if isinstance(pack.get("brand"), dict) else {}
    return str(brand.get("canonical_name") or "").strip()


def brand_aliases(pack: Any) -> list[str]:
    if not isinstance(pack, dict):
        return []
    brand = pack.get("brand") if isinstance(pack.get("brand"), dict) else {}
    return list(dict.fromkeys(
        str(item).strip() for item in brand.get("aliases", []) if str(item).strip()
    ))


def material_index_member(pack: Any) -> str:
    del pack
    return MATERIAL_INDEX_MEMBER


def registry_members(pack: Any) -> dict[str, str]:
    del pack
    return dict(REGISTRY_MEMBERS)


def brand_market_members(pack: Any) -> dict[str, str]:
    del pack
    return dict(BRAND_MARKET_MEMBERS)


def strategy_members(pack: Any) -> dict[str, str]:
    del pack
    return dict(STRATEGY_MEMBERS)


def p0_members(pack: Any) -> dict[str, str]:
    del pack
    return dict(P0_MEMBERS)


def readiness(pack: Any) -> dict[str, Any]:
    value = pack.get("readiness") if isinstance(pack, dict) else None
    return dict(value) if isinstance(value, dict) else {}


def current_root(
    brand: str,
    *,
    pack_id: str,
    pack_version: int = 1,
    parent_pack_version: int | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
    readiness_value: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = updated_at or _now()
    return {
        "schema_version": SCHEMA_VERSION,
        "profile": PROFILE,
        "pack_id": str(pack_id).strip(),
        "pack_version": int(pack_version),
        "parent_pack_version": parent_pack_version,
        "brand_name": str(brand).strip(),
        "created_at": created_at or timestamp,
        "updated_at": timestamp,
        "readiness": readiness_value or {
            "materials_ready": False,
            "brand_market_research_ready": False,
            "positioning_ready": False,
            "p0_ready": False,
            "question_ready": {},
        },
        "canonical_paths": dict(CANONICAL_PATHS),
    }


__all__ = [
    "BRAND_MARKET_MEMBERS", "CANONICAL_PATHS", "MATERIAL_INDEX_MEMBER",
    "P0_MEMBERS", "PROFILE", "REGISTRY_MEMBERS", "SCHEMA_VERSION",
    "STRATEGY_MEMBERS", "brand_aliases", "brand_market_members", "brand_name",
    "current_root", "is_current", "material_index_member", "p0_members",
    "readiness", "registry_members", "strategy_members",
]
