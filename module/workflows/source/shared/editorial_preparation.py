"""Frozen editorial preparation for v16; raw sources belong to this action only."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

CONTRACT = "frontmind-natural-prose/16"
MARKER = '<frontmind_natural_prose version="16">'
ACTION = "article_editorial_preparation"
PATH = "editorial/article_preparation.json"
SOURCE_PATH = "editorial/article_preparation_source.json"
FIELDS = ("writing_material_markdown", "writing_material_sources", "material_adjustments", "blueprint_suggestions")


def enabled(state, *, p0=False):
    return (not p0 and state.get("metadata", {}).get("natural_prose_contract") == CONTRACT
            and state.get("selected_pattern_id") in {"P01", "P02"})


def matches(prompt):
    return isinstance(prompt, str) and prompt.startswith(MARKER + "\n")


def validate(value):
    from .writing_context import validate_writing_material
    validate_writing_material(value)
    if not isinstance(value.get("blueprint_suggestions"), str) or not value["blueprint_suggestions"].strip():
        raise ValueError("编辑准备须提交自然事实段落和蓝图建议")
    cases = value.get("reference_cases")
    if not isinstance(cases, list) or len(cases) != 2:
        raise ValueError("编辑准备须实际搜索并完整阅读两篇同类案例")
    for item in cases:
        if not isinstance(item, dict) or set(item) != {"source_ref", "title", "url", "insight"} or any(
                not isinstance(v, str) or not v.strip() for v in item.values()):
            raise ValueError("案例须包含source_ref、title、url和具体写法启发insight")
    if len({item["source_ref"] for item in cases}) != 2 or len({item["url"].rstrip("/") for item in cases}) != 2:
        raise ValueError("两篇案例须为不同的已读文章")
    adjustments = value.get("material_adjustments", [])
    if not isinstance(adjustments, list) or any(not isinstance(item, str) for item in adjustments):
        raise ValueError("material_adjustments须为文字数组")
    return {**value, "material_adjustments": adjustments}


def schema():
    return {"type": "object", "properties": {
        "writing_material_markdown": {"type": "string", "minLength": 1, "description": "经过取舍、可供充分展开的自然事实段落，不是摘要。保留已选业务有用的具体描述及项目、用途、特点的对应关系，不压成多个名称加一句综合概括；后续作者仍可自由取舍与润色。本字段只介绍对象，写法与取舍建议放blueprint_suggestions。"},
        "blueprint_suggestions": {"type": "string", "minLength": 1, "description": "基于两篇同体裁实际案例和编辑经验的构思建议。所有关于文章怎样写、材料如何取用的判断放在这里；正式蓝图由下一轮完成。"},
        "writing_material_sources": {"type": "array", "minItems": 1, "items": {"anyOf": [
            {"type": "string", "minLength": 1}, {"type": "object", "properties": {
                "source_ref": {"type": "string", "minLength": 1}, "use": {"type": "string", "minLength": 1}},
                "required": ["source_ref", "use"], "additionalProperties": True}]}},
        "material_adjustments": {"type": "array", "items": {"type": "string"}},
        "reference_cases": {"type": "array", "minItems": 2, "maxItems": 2, "items": {
            "type": "object", "properties": {key: {"type": "string", "minLength": 1} for key in ("source_ref", "title", "url", "insight")},
            "required": ["source_ref", "title", "url", "insight"], "additionalProperties": False}}},
        "required": ["writing_material_markdown", "blueprint_suggestions", "writing_material_sources", "reference_cases"],
        "additionalProperties": False}


def freeze(wf, job, value):
    value = validate(value)
    target = Path(job) / PATH
    wf.atomic_json(target, value)
    wf.atomic_json(Path(job) / SOURCE_PATH, {"contract": CONTRACT, "action": ACTION,
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest()})
    return value


def load(job):
    root = Path(job)
    path, source = root / PATH, root / SOURCE_PATH
    if path.is_symlink() or source.is_symlink() or not path.is_file() or not source.is_file():
        raise ValueError("缺少已冻结的v16编辑准备结果")
    provenance = json.loads(source.read_text(encoding="utf-8"))
    if provenance != {"contract": CONTRACT, "action": ACTION, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}:
        raise ValueError("编辑准备结果与冻结来源不一致")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def bind_blueprint(job, value):
    prepared = load(job)
    # The model owns the formal outline, never a second selection of facts.
    return {**value, **{key: prepared[key] for key in FIELDS}}


def fixture():
    return {"writing_material_markdown": "合成品牌提供需求沟通、服务实施与交付跟进。本段仅用于离线流程验证。",
        "blueprint_suggestions": "围绕实际业务特点自然组织文章，按内容安排详略。", "material_adjustments": [],
        "writing_material_sources": ["offline_fixture"],
        "reference_cases": [{"source_ref": f"offline_case_{n}", "title": f"离线案例{n}",
            "url": f"https://example.com/offline/{n}", "insight": "从具体业务进入主题，按阅读重点组织内容。"} for n in (1, 2)]}
