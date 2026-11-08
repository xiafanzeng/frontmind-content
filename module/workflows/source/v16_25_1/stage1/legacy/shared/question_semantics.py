#!/usr/bin/env python3
"""Shared deterministic semantics for FrontMind question routing.

The module deliberately keeps question text untouched.  Its normalized key is
only for exact equality, deduplication, and decision binding; it is never a
fuzzy-search or rewrite surface.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


INTENT_LABELS = {
    "recommendation": "推荐",
    "price": "价格",
    "comparison": "对比",
    "tutorial": "教程",
    "evaluation": "评价",
    "risk": "风险",
    "alternative": "替代方案",
}
ENTRY_LABELS = {
    "industry_ranking": "行业排名",
    "competitor_comparison": "竞品对比",
    "reputation": "美誉舆情",
    "product_scenario": "产品场景",
}

_ENTRY_ALIASES = {
    "industry_ranking": "industry_ranking",
    "industry": "industry_ranking",
    "行业排名": "industry_ranking",
    "行业排名词": "industry_ranking",
    "行业推荐": "industry_ranking",
    "竞品对比": "competitor_comparison",
    "竞品对比词": "competitor_comparison",
    "竞争对比": "competitor_comparison",
    "competitor_comparison": "competitor_comparison",
    "comparison": "competitor_comparison",
    "美誉舆情": "reputation",
    "美誉舆情词": "reputation",
    "口碑舆情": "reputation",
    "品牌口碑": "reputation",
    "reputation": "reputation",
    "产品场景": "product_scenario",
    "产品场景词": "product_scenario",
    "产品服务": "product_scenario",
    "product_scenario": "product_scenario",
    "product": "product_scenario",
}

_COMPARISON_CUES = (
    "对比", "比较", "区别", "差异", "相比", "哪个更", "哪一个更", "谁更", "谁口碑", "谁的口碑",
    "怎么选", "如何选", "选哪个", "选哪一个", "vs", " versus ",
)
_OPERATION_CUES = (
    "迁移", "接入", "预约", "挂号", "面诊", "就诊", "手术", "治疗", "复诊", "术后护理",
    "安装", "部署", "使用", "办理", "注册", "登录", "配置", "开通", "退款", "退订", "下单",
)
_OBJECTIVE_VERIFICATION_CUES = (
    "怎么核验", "如何核验", "怎样核验", "核验方法", "怎么验证", "如何验证", "怎样验证",
    "验证方法", "怎么确认", "如何确认", "怎样确认", "怎么查", "如何查", "在哪里查",
)
_OPEN_CANDIDATE_CUES = (
    "哪家", "哪些", "有哪些", "推荐几家", "推荐一家", "排行榜", "排名", "排行", "榜单",
    "top", "值得推荐", "为什么推荐", "机构推荐", "医院推荐", "品牌推荐", "公司推荐",
    "平台推荐", "产品推荐", "方案推荐",
)
_INTERNAL_RECOMMENDATION_CUES = (
    "各项目医生推荐", "项目医生推荐", "推荐哪位医生", "推荐哪个医生", "推荐什么医生",
    "哪位医生", "哪个医生", "医生怎么选", "医生如何选",
)
_REPUTATION_CUES = (
    "怎么样", "好不好", "靠谱吗", "可靠不", "可靠吗", "可信不", "可信吗", "可信度", "口碑",
    "评价", "表现如何", "体验如何", "稳定吗", "是否稳定", "安全吗", "是否安全", "值得信任",
    "有投诉吗", "投诉多吗", "价格合理", "售后好吗", "售后好不好", "售后响应好吗",
    "服务质量如何", "服务好吗",
)
_PRICE_EVALUATION_CUES = ("价格合理", "贵不贵", "划算吗", "值不值", "性价比怎么样")
_PRICE_CUES = ("价格", "费用", "多少钱", "收费", "报价", "预算", "成本", "套餐")
_RISK_CUES = ("风险", "副作用", "危害", "后遗症", "禁忌", "注意事项", "异常", "并发症", "不安全吗")
_ALTERNATIVE_CUES = ("替代", "还有什么", "别的选择", "其他选择", "其他方案", "除了", "换成")
_RECOMMENDATION_CUES = ("推荐", "哪家", "排行", "排名", "榜单", "哪个好", "哪家好")
_TUTORIAL_CUES = ("怎么", "如何", "怎样", "步骤", "流程", "教程", "准备什么", "方法", "操作")
_GENERIC_DIMENSIONS = {
    "价格", "费用", "服务", "流程", "功能", "项目", "效果", "安全", "风险", "口碑", "体验",
    "质量", "售后", "资质", "医生", "方案", "产品", "手术", "治疗", "预约",
}

_GENERIC_COMPARISON_ENTITIES = {
    "机构", "医院", "诊所", "品牌", "公司", "集团", "平台", "系统", "软件", "产品", "服务商",
}
_COMPARISON_ENTITY_SUFFIXES = tuple(sorted({
    "医疗美容门诊部", "整形美容门诊部", "医疗美容医院", "整形美容医院", "医学美容科",
    "医疗美容科", "整形美容科", "医疗美容诊所", "整形美容诊所", "美容专科医院",
    "美容医院", "医疗美容", "整形美容", "医学美容", "整形医院", "有限公司",
    "股份公司", "医院", "门诊部", "诊所", "机构", "集团", "品牌", "公司", "平台", "系统",
}, key=len, reverse=True))


def normalize_question_key(value: Any) -> str:
    """Return the exact-match key shared with E2.

    NFKC and case-fold first, then apply the existing E2 ASCII-letter/number
    and CJK rule.  Punctuation and whitespace are deliberately discarded.
    """

    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", normalized)


def comparison_entity_key(value: Any) -> str:
    """Return a punctuation-free entity surface key for exact comparison.

    This key is deliberately narrower than an alias decision: it never proves
    that two institutions are the same legal entity.
    """

    return normalize_question_key(value)


def comparison_entity_core(value: Any) -> str:
    """Return a conservative institution-name stem used only for discovery.

    Removing a generic organisation suffix lets a short formal-question
    surface such as ``甲医院`` find ``某地甲医院``.  The result is only a
    research/readiness lead; public sources must still verify aliases.
    """

    key = comparison_entity_key(value)
    changed = True
    while changed and key:
        changed = False
        for suffix in _COMPARISON_ENTITY_SUFFIXES:
            suffix_key = comparison_entity_key(suffix)
            if key.endswith(suffix_key) and len(key) > len(suffix_key) + 1:
                key = key[:-len(suffix_key)]
                changed = True
                break
    return key


def named_comparison_entities(value: Any) -> list[str]:
    """Extract the explicitly enumerated surfaces from a comparison question.

    The extraction is intentionally syntactic.  It preserves the user's
    spelling and does not resolve aliases, branches, or legal identities.
    """

    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text or not _hits(text, _COMPARISON_CUES):
        return []
    text = re.sub(r"[?？!！。\s]+$", "", text)
    tail_patterns = (
        r"(?:之间)?(?:应该)?(?:怎么|如何|怎样)(?:进行)?(?:对比|比较|选|选择|取舍).*$",
        r"(?:之间)?(?:有)?(?:什么|何)?(?:区别|差异).*$",
        r"(?:到底)?(?:哪个|哪一个|哪家|谁)(?:的)?(?:口碑|价格|服务|体验)?(?:更)?"
        r"(?:好|合适|适合|值得选|值得选择).*$",
        r"(?:怎么|如何|怎样)选(?:择)?.*$",
    )
    for pattern in tail_patterns:
        trimmed = re.sub(pattern, "", text, flags=re.I)
        if trimmed != text:
            text = trimmed
            break
    raw_segments = re.split(
        r"\s*(?:、|，|,|；|;|/|\bvs\.?\b|\bversus\b|以及|和|与|跟|同|对比|比较)\s*",
        text,
        flags=re.I,
    )
    entities: list[str] = []
    for index, raw in enumerate(raw_segments):
        entity = re.sub(r"^(?:请问|想问|我想了解|想了解|把|将)", "", raw.strip())
        entity = re.sub(
            r"等(?:这些|这几家|几家)?(?:机构|医院|诊所|品牌|公司|集团|平台|产品|服务商)?$",
            "",
            entity,
        ).strip(" ：:，,、")
        if index == len(raw_segments) - 1:
            entity = re.sub(r"(?:这几家|这些)(?:机构|医院|品牌)?$", "", entity).strip()
        key = comparison_entity_key(entity)
        if (
            len(key) < 2
            or entity in _GENERIC_COMPARISON_ENTITIES
            or entity in _GENERIC_DIMENSIONS
        ):
            continue
        if key not in {comparison_entity_key(item) for item in entities}:
            entities.append(entity)
    return entities if len(entities) >= 2 else []


def canonicalize_entry_category(value: Any) -> str | None:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    if not text:
        return None
    return _ENTRY_ALIASES.get(text) or _ENTRY_ALIASES.get(text.casefold())


def _hits(text: str, cues: tuple[str, ...]) -> list[str]:
    lowered = text.casefold()
    return [cue.strip() for cue in cues if cue.casefold() in lowered]


def _comparison_segments(text: str) -> tuple[str, str] | None:
    lowered = unicodedata.normalize("NFKC", text).casefold()
    if re.search(r"(?:^|[^a-z0-9])vs\.?\s*", lowered):
        parts = re.split(r"(?:^|[^a-z0-9])vs\.?\s*", lowered, maxsplit=1)
        if len(parts) == 2:
            return parts[0], parts[1]
    match = re.search(r"(.{2,32}?)(?:和|与|跟|同)(.{2,32})", lowered)
    if not match:
        return None
    return match.group(1), match.group(2)


def _name_like(segment: str) -> bool:
    cleaned = re.sub(r"[？?，,。.!！:：;；、\s]", "", segment)
    cleaned = re.sub(r"(?:怎么选|如何选|哪个好|哪一个好|的区别|对比|比较|差异).*$", "", cleaned)
    if not 1 <= len(cleaned) <= 28:
        return False
    if cleaned in _GENERIC_DIMENSIONS:
        return False
    if re.fullmatch(r"[a-z][a-z0-9._-]{0,15}", cleaned):
        return True
    if any(token in cleaned for token in (
        "医院", "医美", "诊所", "机构", "公司", "集团", "品牌", "平台", "系统", "软件", "中心",
        "大学", "学校", "银行", "门店", "服务商",
    )):
        return True
    # Short CJK names on either side of an explicit connector are commonly
    # brands (e.g. “甲机构和乙机构”).  Generic dimensions were rejected above.
    return bool(re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fffA-Za-z0-9]{2,12}", cleaned))


def _has_named_comparison(text: str, comparison_hits: list[str]) -> bool:
    if not comparison_hits:
        return False
    segments = _comparison_segments(text)
    return bool(segments and _name_like(segments[0]) and _name_like(segments[1]))


def _is_open_candidate_question(text: str, open_hits: list[str]) -> bool:
    lowered = text.casefold()
    if any(cue in text for cue in _INTERNAL_RECOMMENDATION_CUES):
        return False
    if any(token in lowered for token in ("排行榜", "排名", "排行", "榜单", "top")):
        return True
    if any(token in text for token in ("为什么推荐", "推荐一家", "值得推荐", "值得选吗")):
        return True
    generic_candidate = any(token in text for token in (
        "机构", "医院", "诊所", "品牌", "公司", "服务商", "服务", "平台", "产品", "方案", "学校", "银行",
    ))
    plural_or_recommend = any(token in text for token in ("哪家", "哪些", "有哪些", "推荐", "哪个好", "哪家好"))
    return bool(open_hits and generic_candidate and plural_or_recommend)


def _compound_warning(text: str) -> str | None:
    terminal_count = text.count("?") + text.count("？")
    interrogatives = re.findall(
        r"怎么样|好不好|靠谱吗|可靠吗|可信吗|哪家|哪些|多少|怎么|如何|怎样|是否|有吗|什么|谁",
        text,
    )
    clause_markers = sum(text.count(mark) for mark in ("；", ";", "。"))
    if terminal_count > 1 or (clause_markers and len(interrogatives) > 1):
        return "检测到多个问句或并列动作；保留原文，不自动拆分"
    if "、" in text and len(interrogatives) > 1:
        return "检测到并列询问；保留原文，不自动拆分"
    return None


def _intent(
    text: str,
    *,
    named_comparison: bool,
    verification_hits: list[str],
    reputation_hits: list[str],
    open_candidate: bool,
) -> str | None:
    comparison_hits = _hits(text, _COMPARISON_CUES)
    if named_comparison or comparison_hits and any(token in text for token in ("对比", "比较", "区别", "差异", "相比")):
        return "comparison"
    if verification_hits:
        return "tutorial"
    if _hits(text, _PRICE_EVALUATION_CUES):
        return "evaluation"
    if open_candidate:
        return "recommendation"
    if reputation_hits:
        return "evaluation"
    if _hits(text, _PRICE_CUES):
        return "price"
    if _hits(text, _RISK_CUES):
        return "risk"
    if _hits(text, _ALTERNATIVE_CUES):
        return "alternative"
    if _hits(text, _RECOMMENDATION_CUES):
        return "recommendation"
    if _hits(text, _TUTORIAL_CUES):
        return "tutorial"
    return None


def classify_question(value: Any) -> dict[str, Any]:
    """Classify one untouched question into seven intent tags and four entries."""

    text = str(value or "").strip()
    if not text:
        raise ValueError("question text must be non-empty")
    comparison_hits = _hits(text, _COMPARISON_CUES)
    operation_hits = _hits(text, _OPERATION_CUES)
    verification_hits = _hits(text, _OBJECTIVE_VERIFICATION_CUES)
    reputation_hits = _hits(text, _REPUTATION_CUES)
    open_hits = _hits(text, _OPEN_CANDIDATE_CUES)
    named_comparison = _has_named_comparison(text, comparison_hits)
    open_candidate = _is_open_candidate_question(text, open_hits)

    if named_comparison:
        entry = "competitor_comparison"
        rule_id = "named_entity_comparison"
        reason = "题面明确命名多个对象，并要求在共同维度下比较或取舍"
        confidence = 0.99
    elif (
        operation_hits
        or verification_hits
        or (_hits(text, _PRICE_CUES) and not reputation_hits)
        or any(cue in text for cue in _INTERNAL_RECOMMENDATION_CUES)
    ):
        entry = "product_scenario"
        rule_id = "objective_product_task"
        reason = "核心任务是操作、核验或单品牌内部项目/人员匹配，而非主观口碑判断"
        confidence = 0.97
    elif open_candidate:
        entry = "industry_ranking"
        rule_id = "open_market_candidates"
        reason = "预期答案是开放市场中的候选发现、推荐或排序"
        confidence = 0.98
    elif reputation_hits:
        entry = "reputation"
        rule_id = "single_entity_reputation"
        reason = "预期答案是对单一品牌或产品的口碑、可靠性、体验或服务质量评价"
        confidence = 0.99
    else:
        entry = "product_scenario"
        rule_id = "default_product_scenario"
        reason = "题面未出现可靠的开放候选、命名比较或主观评价信号，按客观产品/服务任务处理"
        confidence = 0.60

    primary_intent = _intent(
        text,
        named_comparison=named_comparison,
        verification_hits=verification_hits,
        reputation_hits=reputation_hits,
        open_candidate=open_candidate,
    )
    return {
        "question_key": normalize_question_key(text),
        "primary_intent_tag": primary_intent,
        "category": INTENT_LABELS.get(primary_intent, "其他"),
        "suggested_entry_category": entry,
        "classification_rule_id": rule_id,
        "classification_reason": reason,
        "classification_confidence": confidence,
        "compound_question_warning": _compound_warning(text),
        "matched_signals": {
            "named_comparison": comparison_hits if named_comparison else [],
            "operation": [*operation_hits, *verification_hits],
            "open_candidate": open_hits if open_candidate else [],
            "reputation": reputation_hits,
        },
    }


def classify_project_question(
    question_text: Any,
    supplied_category: Any = None,
    *,
    source_order: int = 1,
) -> dict[str, Any]:
    """Add upload-vs-semantic review state to one project question."""

    classified = classify_question(question_text)
    raw = str(supplied_category or "").strip() or None
    supplied = canonicalize_entry_category(raw)
    suggested = classified["suggested_entry_category"]
    if raw is None:
        status = "semantic_inferred"
        final = suggested
        origin = "semantic_rule"
    elif supplied == suggested:
        status = "aligned"
        final = suggested
        origin = "uploaded_category"
    else:
        status = "conflict_pending"
        final = None
        origin = None
    return {
        **classified,
        "source_order": source_order,
        "supplied_category_raw": raw,
        "supplied_entry_category": supplied,
        "entry_category": final,
        "entry_category_origin": origin,
        "classification_status": status,
    }


def apply_classification_decision(
    classification: dict[str, Any],
    decision: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Apply one compare-and-set S8 decision, returning a stale reason if any."""

    if classification.get("classification_status") != "conflict_pending":
        return classification, "question no longer has a pending classification conflict"
    expected_key = str(decision.get("question_key") or "")
    if expected_key != classification.get("question_key"):
        return classification, "question_key changed"
    expected_supplied = decision.get("expected_supplied_entry_category")
    expected_suggested = decision.get("expected_suggested_entry_category")
    if expected_supplied != classification.get("supplied_entry_category"):
        return classification, "uploaded category changed"
    if expected_suggested != classification.get("suggested_entry_category"):
        return classification, "semantic suggestion changed"
    action = decision.get("action")
    resolved = dict(classification)
    if action == "accept_semantic_suggestion":
        resolved["entry_category"] = classification["suggested_entry_category"]
        resolved["entry_category_origin"] = "user_confirmed_semantic"
        resolved["classification_status"] = "resolved_accept_suggestion"
    elif action == "keep_supplied_category":
        if classification.get("supplied_entry_category") not in ENTRY_LABELS:
            return classification, "unknown uploaded category cannot be retained"
        resolved["entry_category"] = classification["supplied_entry_category"]
        resolved["entry_category_origin"] = "user_confirmed_uploaded"
        resolved["classification_status"] = "resolved_keep_supplied"
    else:
        return classification, f"unsupported action: {action!r}"
    return resolved, None
