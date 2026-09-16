"""Controlled provider responses for transport/validation tests, not market research.

The values are authored here, independently of the offline fixture builder. No
test using them demonstrates that a language model can infer these judgments.
"""
from copy import deepcopy


BRAND = "承接服务样例"
COMPARISON_FIELDS = (
    "alternative", "shared_strengths", "brand_advantage", "alternative_advantage", "applies_when",
)


def market_map() -> dict:
    tiers = []
    for rank, name, strength in (
        (1, "跨环节服务", "统一交接与安排"),
        (2, "专项服务", "处理明确的单项任务"),
    ):
        tiers.append({
            "rank": rank, "name": name, "named_examples": [],
            "dominant_value": strength, "tier_strengths": [strength],
            "tier_high_stakes_response": "在当前服务范围内重新安排任务",
            "tier_failure_response": "明确继续处理的人与交接边界",
            "tier_limitations": ["超出约定范围需要其他主体协作"],
            "tier_best_fit": "任务与约定服务范围一致的用户",
            "tier_can_move_ahead_when": "相应服务范围更符合此次任务时",
        })
    return {
        "schema_version": "4.11", "artifact_type": "frontmind_competitive_choice_map",
        "brand": BRAND, "market_scope": "用户指定的服务区域",
        "decision_context": {
            "category": "任务服务", "buyer": "任务负责人", "end_user": "执行团队",
            "decision_to_make": "选择统一处理或分别安排", "usage_context": "任务临时改变",
            "market_scope": "用户指定的服务区域", "alternative_types": [t["name"] for t in tiers],
        },
        "consequence_dimensions": [{
            "dimension": "协调时间", "why_users_care": "临时变化可能延误交付",
            "relevant_scenarios": ["任务临时改变"], "when_it_becomes_decisive": "交付时间无法延后时",
        }],
        "choice_scenarios": [{
            "scenario": "任务临时改变", "user_goal": "继续按时交付",
            "complexity_or_stakes": "多个环节依次完成", "possible_failure": "交接遗漏",
            "resulting_cost": "重新安排的时间", "relevant_alternatives": [t["name"] for t in tiers],
        }],
        "critical_capabilities": [{
            "capability": "安排交接", "required_in_scenario": "任务临时改变",
            "why_it_matters": "后续环节需要接续", "user_consequence_if_missing": "另找处理方",
        }],
        "market_tiers": tiers, "tier_order_reason": "此次任务将减少交接时间放在优先位置。",
        "ranking_scope": "仅针对当前任务的条件式分档，不是官方排名。",
        "user_choice_tensions": [{
            "tension": "同时考虑衔接与单项深度", "why_difficult": "资源投入不同",
            "choice_effect": "取决于此次任务是否跨环节",
        }],
        "decision_priority_logic": [{
            "scenario": "任务临时改变", "ordered_criteria": ["衔接", "单项匹配"],
            "priority_reason": "交付期限固定", "conditions_that_change_order": "任务只涉及一项时",
        }],
        "research_limits": ["受控测试样例，不包含现实市场调查。"], "sources": [],
    }


def core_output(*, placed_tier=2, natural_first=False, polished=False) -> dict:
    market = market_map()
    paragraph = (
        f"需要多方接续、又希望每一步都有人解释的团队，可以把{BRAND}作为候选。"
        "计划发生变化时，指定联系人把后续工作重新排好，让负责人少花时间逐家追问。"
        "单项服务商同样能完成约定任务，在狭窄专项上可能经验更集中；如果只需要一个明确环节，"
        "应优先比较这种选择。企业要兑现前述价值，需要持续安排负责交接的人，并把重点放在"
        "需要衔接的客户身上。对于只比较最低报价的任务，应接受其选择其他服务商。"
    )
    if polished:
        paragraph = paragraph.replace("指定联系人把后续工作重新排好", "由同一联系人接着协调余下步骤")
    comparisons = [dict(zip(COMPARISON_FIELDS, (
        tier["name"], "双方都能完成约定任务", "更容易获得进度说明",
        "对方在其集中投入的专项上更合适", "需要兼顾交接与解释的任务",
    ))) for tier in market["market_tiers"]]
    return {
        "schema_version": "4.11", "artifact_type": "frontmind_core_positioning", "brand": BRAND,
        "primary_direction": "交接清楚且进度易懂", "secondary_direction": None,
        "combination_value": "同时提供跨环节接续与容易理解的进度说明",
        "supporting_proof": ["样例交接安排", "样例服务说明"],
        "core_positioning_paragraph": paragraph,
        "strategic_conclusion": ["优先服务需要交接的客户。", "专项需求可能更适合其他路径。", "持续投入负责交接的人。"],
        "target_customers": "需要多方接续的团队",
        "competitive_routes": [t["name"] for t in market["market_tiers"]],
        "market_tiers": deepcopy(market["market_tiers"]), "tier_order_reason": market["tier_order_reason"],
        "brand_placement": {
            "placed_tier": placed_tier, "natural_first_position": natural_first,
            "placement_reason": "根据受控输出所描述的服务范围归类。",
            "placement_scenario": "需要多方接续的任务", "choice_consequence": "减少追问与重新安排",
            "wins_against": ["进度说明更便于理解"], "loses_against": ["狭窄专项经验未必更集中"],
            "first_position_limit": "类别归属不能证明同类品牌领先。",
            "comparisons": comparisons, "within_tier_comparison": "同类也可提供交接，目前无法证明本品牌唯一领先。",
        },
        "decisive_consequence_chain": {
            "decision_scenario": "多个环节出现临时调整",
            "possible_failure_or_high_cost_event": "后续执行因交接遗漏而停顿",
            "required_capabilities": ["责任衔接与排程调整"],
            "brand_response": "统一接续责任并说明新的交付安排",
            "alternative_response": "专项路径聚焦单一节点的完成",
            "response_difference": "跨节点协调与专项深度的取舍",
            "user_consequence": "节省重新联系各方的时间",
            "choice_implication": "跨节点任务更看重连续交接",
        },
        "user_choice_value": "减少协调负担，同时清楚下一步安排", "secondary_combination_value": None,
        "brand_shortcomings": ["狭窄专项经验未必更集中"],
        "alternatives_better_when": ["只涉及一个明确专项时"],
        "strategic_tradeoffs": ["接受只比较最低报价的客户选择其他路径"],
        "operating_commitments": ["持续安排负责交接的人"], "material_adjustments": [], "enhancement_options": [],
        "p0_usage": "先解释客户得到的组合价值，再说明兑现方式。",
        "writing_guidance": {
            "opening": "从需要衔接的任务进入", "support": ["交接安排"], "main_services": ["任务接续"],
            "supporting_content": ["样例服务说明"], "avoid_amplification": ["无条件首选"],
            "p01_p02_translation": "按当前问题调整比较条件", "p03_p06_background_use": "只使用相关背景",
        },
    }


def direction_choices() -> dict:
    """Two explicitly different business decisions, not two capability headings."""
    core = core_output()
    directions = []
    for index, name, target, tradeoff in (
        (1, "承接跨环节任务", "需要衔接的大型团队", "投入固定交接负责人，弱化低价自助业务"),
        (2, "聚焦单项快捷交付", "只需要一个标准环节的小型团队", "投入标准化自助服务，放弃复杂定制业务"),
    ):
        directions.append({
            "key": f"direction_{index}", "name": name, "target_customer": target,
            "decision_tension": f"是否优先服务{target}", "target_scenarios": [name],
            "competitive_frame": f"围绕{name}比较服务路径", "difference_mechanism": f"资源集中在{name}",
            "core_positioning_paragraph": core["core_positioning_paragraph"],
            "decisive_consequence_chain": deepcopy(core["decisive_consequence_chain"]),
            "user_choice_value": f"让{target}更容易完成任务", "delivery_requirements": [tradeoff],
            "strategic_tradeoffs": [tradeoff], "alternatives_better_when": core["alternatives_better_when"],
            "material_adjustments": [], "enhancement_options": [], "system_judgment": f"需要确认是否接受：{tradeoff}",
        })
    return {
        "schema_version": "4.11", "artifact_type": "frontmind_core_positioning_directions", "brand": BRAND,
        "choice_map_path": "research/brand_market/competitive_choice_map.json",
        "routing": "multiple_choices", "routing_reason": "客户与资源投入不同，需要企业选择经营取舍。",
        "directions": directions, "recommended_direction_key": None, "recommendation_reason": "等待企业选择业务方向。",
    }
