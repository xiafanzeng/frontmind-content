"""Opt-in industry-roundup contract for new article Jobs.

Pattern answers *which relationship* the question has. Genre controls the
article form. Subject scope is an explicit, ordered commission, never inferred
from the P02 three-entity recommendation policy.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

LEGACY_CONTRACT = "frontmind-industry-roundup/1"
CONTRACT = "frontmind-industry-roundup/2"
MARKER = '<frontmind_industry_roundup version="1" />'
DIMENSIONS = ("转速", "温控", "噪音", "价格")
QUANTITY = re.compile(
    r"(?<![\d.])(?P<number>\d+(?:[.,]\d+)?(?:\s*[–—~～-]\s*\d+(?:[.,]\d+)?)?)\s*"
    r"(?:万转(?:/分)?|m/s|米/秒|℃|°C|分贝|dBA?|元|W|克|g|次/秒|毫米|mm|年|分钟|秒)",
    re.IGNORECASE,
)


def configure(state: dict, genre: str, subjects: list[str] | None = None,
              *, dimensions: list[str] | None = None) -> None:
    if genre != "industry_roundup":
        if subjects or dimensions:
            raise ValueError("--subject / --dimension 仅在 --genre industry_roundup 下使用")
        return
    names = [str(name).strip() for name in (subjects or [])]
    if not 3 <= len(names) <= 12 or any(not name for name in names):
        raise ValueError("行业盘点须用 --subject 按顺序给出 3—12 个具体品牌")
    if len({name.casefold() for name in names}) != len(names):
        raise ValueError("行业盘点主体不能重复")
    requested_dimensions = [str(item).strip() for item in (dimensions or [])]
    if requested_dimensions and (not 2 <= len(requested_dimensions) <= 8
                                 or any(not item for item in requested_dimensions)
                                 or len(set(requested_dimensions)) != len(requested_dimensions)):
        raise ValueError("行业盘点须给出 2—8 个不重复的共同对比维度")
    state.setdefault("metadata", {})["article_spec"] = {
        "contract": CONTRACT if requested_dimensions else LEGACY_CONTRACT,
        "pattern": None, "genre": genre, "subject_scope": names,
        **({"comparison_dimensions": requested_dimensions} if requested_dimensions else {}),
    }


def spec(state: dict) -> dict | None:
    value = state.get("metadata", {}).get("article_spec")
    return value if isinstance(value, dict) and value.get("contract") in {CONTRACT, LEGACY_CONTRACT} else None


def dimensions(state: dict) -> tuple[str, ...]:
    value = spec(state) or {}
    return tuple(value.get("comparison_dimensions") or DIMENSIONS)


def enabled(state: dict) -> bool:
    return bool(spec(state) and spec(state).get("genre") == "industry_roundup")


def matches(prompt: str) -> bool:
    return isinstance(prompt, str) and MARKER in prompt[:200]


def commission(state: dict) -> dict:
    value = spec(state)
    if not value:
        return {}
    return {**value, "pattern": state.get("selected_pattern_id")}


def validate_scope(state: dict) -> list[str]:
    names = spec(state)["subject_scope"]
    brand = (state.get("reference_pack") or {}).get("brand") or state.get("metadata", {}).get("reference_pack_brand_hint")
    if brand and names[0].casefold() != str(brand).strip().casefold():
        raise ValueError("行业盘点第一个主体须为本次主品牌")
    if state.get("selected_pattern_id") not in (None, "P02"):
        raise ValueError("当前行业盘点合同只接入 P02；其他 Pattern 须单独接入相应写作流程")
    return names


def _source_text(job: Path, source_ref: str) -> str:
    ref = Path(source_ref)
    if ref.is_absolute() or ".." in ref.parts:
        raise ValueError("证据 source_ref 必须是 Job 内的相对路径")
    target = (job / ref).resolve()
    if not target.is_relative_to(job.resolve()) or not target.is_file():
        raise ValueError("证据原件不存在：" + source_ref)
    if target.suffix.lower() not in {".md", ".txt", ".json"}:
        raise ValueError("证据原件须为可核验文本：" + source_ref)
    return target.read_text(encoding="utf-8")


def validate_claims(job: Path, claims: object, subjects: list[str], *, strict_model: bool = False) -> list[dict]:
    if not isinstance(claims, list) or len(claims) < len(subjects):
        raise ValueError("行业盘点须为每个主体至少登记一条可核验事实")
    ids, covered = set(), set()
    for row in claims:
        if not isinstance(row, dict):
            raise ValueError("事实记录须为对象")
        for field in ("id", "subject", "model", "claim", "source_ref", "source_quote", "as_of"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("事实记录缺少 " + field)
        if not re.fullmatch(r"F\d{2,4}", row["id"]) or row["id"] in ids:
            raise ValueError("事实 id 须唯一，格式如 F01")
        ids.add(row["id"])
        if row["subject"] not in subjects:
            raise ValueError("事实主体不在本篇名单中：" + row["subject"])
        covered.add(row["subject"])
        original = _source_text(job, row["source_ref"])
        excerpt = " ".join(row["source_quote"].split())
        if excerpt not in " ".join(original.split()):
            raise ValueError("事实原文片段不在 source_ref 中：" + row["id"])
        if strict_model:
            model = re.sub(r'\s+', '', row['model']).casefold()
            located = re.sub(r'\s+', '', row['source_quote'] + ' ' + Path(row['source_ref']).stem).casefold()
            if model not in {'品牌', '品牌层级', '未指定'} and model not in located:
                raise ValueError("具体数字缺少同一原文片段中的型号标识：" + row['id'])
        literal_position = original.find(row['source_quote'])
        if literal_position >= 0:
            line_number = original.count('\n', 0, literal_position) + 1
        else:
            matching_lines = [index for index, line in enumerate(original.splitlines(), 1)
                              if excerpt in ' '.join(line.split())]
            if not matching_lines:
                raise ValueError("事实原文片段须位于同一原文行：" + row['id'])
            line_number = matching_lines[0]
        if row.get('source_line') not in (None, line_number):
            raise ValueError("事实原文行号与实际文件不符：" + row['id'])
        row['source_line'] = line_number
    if set(subjects) - covered:
        raise ValueError("缺少主体事实：" + "、".join(set(subjects) - covered))
    return claims


def validate_blueprint(state: dict, value: dict, job: Path) -> None:
    if not enabled(state):
        return
    names = validate_scope(state)
    if value.get("genre") != "industry_roundup" or value.get("subject_scope") != names:
        raise ValueError("蓝图文体或主体名单与委托不一致")
    requested_dimensions = value.get("comparison_dimensions")
    expected_dimensions = dimensions(state)
    if not isinstance(requested_dimensions, list) or requested_dimensions != list(expected_dimensions):
        raise ValueError("蓝图须按委托顺序覆盖全部共同对比维度")
    matrix = value.get("comparison_matrix")
    if not isinstance(matrix, list) or [r.get("subject") for r in matrix if isinstance(r, dict)] != names:
        raise ValueError("对比矩阵须按委托顺序逐一覆盖全部主体")
    claims = validate_claims(job, value.get("fact_claims"), names,
                             strict_model=(spec(state) or {}).get('contract') == CONTRACT)
    claim_subjects = {claim['id']: claim['subject'] for claim in claims}
    for row in matrix:
        cells = row.get("cells")
        if not isinstance(cells, dict) or set(cells) != set(expected_dimensions):
            raise ValueError("矩阵每个主体须覆盖本篇全部维度；未知值请明确写未知")
        if any(not isinstance(cells[d], str) or not cells[d].strip() for d in expected_dimensions):
            raise ValueError("矩阵单元格须有值或写未知")
        evidence = row.get('evidence_ids')
        if not isinstance(evidence, dict) or set(evidence) != set(expected_dimensions):
            raise ValueError("矩阵每个维度须有 evidence_ids，未知值填空数组")
        if (spec(state) or {}).get('contract') == CONTRACT:
            if not isinstance(row.get('model'), str) or not row['model'].strip():
                raise ValueError("新版对比矩阵每行须固定一个具体型号")
        for dimension in expected_dimensions:
            ids = evidence[dimension]
            if not isinstance(ids, list) or any(not isinstance(item, str) for item in ids):
                raise ValueError("evidence_ids 须为事实 ID 数组")
            if cells[dimension] != '未知' and not ids:
                raise ValueError("非未知矩阵值缺少事实依据：" + row['subject'] + '/' + dimension)
            if any(claim_subjects.get(item) != row['subject'] for item in ids):
                raise ValueError("矩阵事实 ID 不属于该主体：" + row['subject'] + '/' + dimension)
            if (spec(state) or {}).get('contract') == CONTRACT and any(
                next((claim['model'] for claim in claims if claim['id'] == item), None) != row['model']
                for item in ids
            ):
                raise ValueError("同一对比行混用了不同型号：" + row['subject'] + '/' + dimension)
    mapping = value.get("reader_questions")
    headings = {r["heading"] for r in value.get("sections", [])}
    from . import article_focus
    required_questions = (article_focus.spec(state) or {}).get('reader_questions', [])
    minimum = max(1, len(required_questions)) if (spec(state) or {}).get('contract') == CONTRACT else 4
    if not isinstance(mapping, list) or len(mapping) < minimum:
        raise ValueError("读者问题须映射到正文章节")
    if any(not isinstance(r, dict) or not r.get("question") or r.get("section") not in headings for r in mapping):
        raise ValueError("读者问题的 section 须指向真实 H2")
    if required_questions and not set(required_questions).issubset({r['question'] for r in mapping}):
        raise ValueError("蓝图缺少用户指定的读者问题")
    rules = value.get("selection_rules")
    minimum_rules = 1 if (spec(state) or {}).get('contract') == CONTRACT else 2
    if not isinstance(rules, list) or len(rules) < minimum_rules or any(not str(r).strip() for r in rules):
        raise ValueError("蓝图须给出有依据的按条件选型规则")


def audit_body(state: dict, blueprint: dict, body: str) -> dict:
    """Mechanical checks only; semantic equality still needs human review."""
    if not enabled(state):
        return {"contract": CONTRACT, "applicable": False, "publish_ready": True, "issues": []}
    issues = []
    names = validate_scope(state)
    for name in names:
        if name not in body:
            issues.append("正文缺少主体：" + name)
    for dimension in dimensions(state):
        if dimension not in body:
            issues.append("正文缺少对比维度：" + dimension)
    if not re.search(r"(?m)^\|[^\n]+\|\s*$", body):
        issues.append("正文缺少横向对比表")
    for row in blueprint.get("reader_questions", []):
        if row.get("section") not in body:
            issues.append("读者问题未落到章节：" + str(row.get("question")))
    claims = {r['id']: r for r in blueprint.get('fact_claims', [])}
    ids = set(claims)
    used = set(re.findall(r"\[\^?(F\d{2,4})\]", body))
    for claim_id in sorted(used - ids):
        issues.append("正文引用了未登记的事实：" + claim_id)
    by_subject = {r['subject'] for r in blueprint.get('fact_claims', []) if r['id'] in used}
    for name in names:
        if name not in by_subject:
            issues.append("正文缺少该主体的事实引用：" + name)
    rejected = set(state.get('metadata', {}).get('rejected_fact_claims', []))
    if (spec(state) or {}).get('contract') == CONTRACT:
        selected_models = {row['subject']: row['model'] for row in blueprint.get('comparison_matrix', [])}
        for claim_id in sorted(used & ids):
            claim = claims[claim_id]
            if (QUANTITY.search(claim['claim'] + ' ' + claim['source_quote'])
                    and any(dimension in claim['claim'] + ' ' + claim['source_quote']
                            for dimension in dimensions(state))
                    and claim['model'] != selected_models.get(claim['subject'])):
                issues.append('正文数值引用了本篇对比型号以外的机型：' + claim_id)
    for claim_id in sorted(used & rejected):
        issues.append("正文沿用了已否决事实：" + claim_id)
    # A marker after a sentence cannot vouch for a different number in the
    # same sentence unless that exact numeric token appears in its source span.
    for fragment in re.split(r"[。！？；\n|]", body):
        if not fragment.strip():
            continue
        cited = set(re.findall(r"\[\^?(F\d{2,4})\]", fragment)) & ids
        for match in QUANTITY.finditer(fragment):
            number = re.sub(r"\s+", "", match.group('number')).replace('–', '-').replace('—', '-')
            supported = False
            for claim_id in cited:
                quote = re.sub(r"\s+", "", claims[claim_id]['source_quote']).replace('–', '-').replace('—', '-')
                if re.search(r"(?<![\d.])" + re.escape(number) + r"(?![\d.])", quote):
                    supported = True
                    break
            if not supported:
                issues.append("具体数字缺少同句原文依据：" + match.group(0) + "｜" + fragment.strip()[:56])
    return {"contract": CONTRACT, "applicable": True,
            "publish_ready": not issues, "issues": issues,
            "claim_count": len(ids), "used_claim_count": len(used),
            "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest()}
