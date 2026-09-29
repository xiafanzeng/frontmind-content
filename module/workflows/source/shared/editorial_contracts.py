"""Contracts shared by the remote writer and the host's one editorial finish.

Body diffs preserve whitespace after normalizing CRLF/CR. Finalize acceptance
also tolerates one optional terminal newline (not an extra blank paragraph).
Such newline-only differences never count as a claimed editorial revision.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_VERSION = "frontmind-editorial/v4.11.5"


class EditorialContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def normalize_body(value: str) -> str:
    if not isinstance(value, str):
        raise EditorialContractError("article_type", "article_markdown 必须是字符串")
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _transport_equal(left: str, right: str) -> bool:
    """Permit a single optional file-ending newline, never extra blank lines."""
    left, right = normalize_body(left), normalize_body(right)
    if left == right:
        return True
    return ((left == right + "\n" and not right.endswith("\n"))
            or (right == left + "\n" and not left.endswith("\n")))


def body_diff(before: str, after: str) -> dict[str, Any]:
    left, right = normalize_body(before), normalize_body(after)
    return {
        "identical": left == right,
        "before_chars": len(left), "after_chars": len(right),
        "before_sha256": hashlib.sha256(left.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(right.encode()).hexdigest(),
        "unified_diff": "".join(difflib.unified_diff(
            left.splitlines(keepends=True), right.splitlines(keepends=True),
            fromfile="编辑基稿", tofile="待验读候选", n=3)),
    }


def _object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EditorialContractError("result_type", "写作结果必须是 JSON 对象")
    return dict(value)


def _article(value: dict[str, Any], *, required: bool = True) -> str:
    body = value.get("article_markdown")
    if not isinstance(body, str) or (required and not body.strip()):
        raise EditorialContractError("article_missing", "必须提交完整 article_markdown 正文")
    return body


def _notes(value: dict[str, Any]) -> list[str]:
    notes = value.get("editorial_notes")
    if not isinstance(notes, list) or any(not isinstance(item, str) or not item.strip() for item in notes):
        raise EditorialContractError("editorial_notes_type", "editorial_notes 必须是有效说明字符串数组")
    return notes


def validate_draft_result(value: Any) -> dict[str, Any]:
    result = _object(value)
    flag = result.get("requires_blueprint_reconfirmation")
    if not isinstance(flag, bool):
        raise EditorialContractError("reconfirmation_type", "必须明确是否需要蓝图重确认")
    reason = result.get("reconfirmation_reason")
    if not isinstance(reason, str) or (flag and not reason.strip()) or (not flag and reason.strip()):
        raise EditorialContractError("reconfirmation_reason", "蓝图重确认标记与原因不一致")
    _article(result, required=not flag)
    return result


def validate_edit_result(value: Any, draft: str) -> dict[str, Any]:
    result = validate_draft_result(value)
    status = result.get("edit_status")
    if status not in {"accepted", "revised", "requires_blueprint_reconfirmation"}:
        raise EditorialContractError("edit_status", "E8 必须明确 accepted、revised 或 requires_blueprint_reconfirmation")
    notes = _notes(result)
    needs_confirmation = status == "requires_blueprint_reconfirmation"
    if needs_confirmation != result["requires_blueprint_reconfirmation"]:
        raise EditorialContractError("edit_reconfirmation_mismatch", "E8 状态与蓝图重确认标记不一致")
    if needs_confirmation:
        return result
    same = normalize_body(result["article_markdown"]) == normalize_body(draft)
    if status == "accepted" and (not same or notes):
        raise EditorialContractError("accepted_body_mismatch", "原文通过必须保持正文不变且修改说明为空")
    newline_only = normalize_body(result["article_markdown"]).rstrip("\n") == normalize_body(draft).rstrip("\n")
    if status == "revised" and (newline_only or not notes):
        raise EditorialContractError("revised_body_mismatch", "声明已修改必须有实际正文变化及真实修改说明")
    return result


QUALITY_DIMENSIONS = ("opening", "development", "progression", "brand_specificity", "language", "ending")
QUALITY_EXAMPLES = ("xingyuanzhi", "gangjun")


def quality_review_schema() -> dict[str, Any]:
    """Model-facing evidence contract; semantics still require editorial review."""
    text = {"type": "string", "minLength": 1}
    quote = {"type": "string", "minLength": 12,
             "description": "从本次实际终稿连续摘录至少12字符；未通过时摘录被拒候选。不得概括、用省略号拼接或引用旧稿。"}
    evidence = {"type": "object", "properties": {"article_quote": quote, "assessment": text},
                "required": ["article_quote", "assessment"], "additionalProperties": False}
    check = {"type": "object", "properties": {
        "dimension": {"type": "string", "enum": list(QUALITY_DIMENSIONS)},
        "passed": {"type": "boolean"}, "article_quote": quote, "assessment": text},
        "required": ["dimension", "passed", "article_quote", "assessment"], "additionalProperties": False}
    comparison = {"type": "object", "properties": {
        "example_id": {"type": "string", "enum": list(QUALITY_EXAMPLES)},
        "passed": {"type": "boolean"}, "article_quote": quote, "reference_feature": text, "assessment": text},
        "required": ["example_id", "passed", "article_quote", "reference_feature", "assessment"], "additionalProperties": False}
    return {"type": "object", "properties": {
        "fact_check": {"type": "object", "properties": {
            "passed": {"type": "boolean"}, "evidence": {"type": "array", "minItems": 1, "items": evidence}},
            "required": ["passed", "evidence"], "additionalProperties": False},
        "article_quality": {"type": "object", "properties": {
            "passed": {"type": "boolean"}, "checks": {"type": "array", "minItems": 6, "maxItems": 6, "items": check}},
            "required": ["passed", "checks"], "additionalProperties": False},
        "example_comparison": {"type": "array", "minItems": 2, "maxItems": 2, "items": comparison},
        "unresolved_issues": {"type": "array", "items": text}},
        "required": ["fact_check", "article_quality", "example_comparison", "unresolved_issues"],
        "additionalProperties": False}


def quality_review_guidance() -> str:
    return """另交独立 quality_review，编辑动作 accepted/revised 不代表质量合格。先读实际正文，分别判断事实与文章质量，不能依据第三遍自评或总分宣布通过。
quality_review 字段为：fact_check={passed:boolean,evidence:[{article_quote,assessment}]}；article_quality={passed:boolean,checks:[{dimension,passed:boolean,article_quote,assessment}]}；example_comparison=[{example_id,passed:boolean,article_quote,reference_feature,assessment}]；unresolved_issues 为字符串数组。
checks 恰好包含 opening（开篇阅读方向）、development（重点关系充分展开）、progression（章节增加理解）、brand_specificity（企业事实参与解释）、language（自然有详略）、ending（收束完整）各一项。每项根据实际段落说明判断；development 应按本篇表达任务和完整蓝图检查重点关系是否充分展开，解释单元的类型与数量由本篇任务决定，不固定企业章节；本篇若明确要求三个解释单元，应逐项核对。术语释义、服务清单或价值句不能冒充解释。不能只以更简洁、无重复、事实无错判定文章通过。
example_comparison 恰好各含 xingyuanzhi、gangjun 一项。reference_feature 指明所参照的例文段落及其写法；article_quote 摘录本稿对应文字；assessment 具体比较该段是否达到关系解释或技术解释与推进的效果，说明差距，不给笼统总分。fact_check 的 evidence 应覆盖本篇关键主体、范围和历史条件。
全部 article_quote 必须从本次实际 article_markdown 连续摘录至少12字符，不添加引号、省略号或换词；如果 outcome 为 incomplete 或 requires_blueprint_reconfirmation，则摘录被拒的输入候选。每个 assessment 必须解释引文如何支持判断，不能只写已通过。程序检查引文存在不能代替人工语义复核。
仅所有 passed 为 true 且 unresolved_issues 为空时，才能提交 accepted/revised。accepted 保持候选原文，revised 提交确实改变后的完整稿和实际修改说明，quality_review 必须评估你修正后的最终文字。材料或结构缺口仍在、重点没有展开或例文差距未消除时，返回 incomplete，article_markdown 和 editorial_notes 为空，并在 reason 与 unresolved_issues 写清问题及应返回选材/蓝图/写作的哪一处；该结果会阻止标题与正式交付。不得为绕过此结果而把全文缩成业务简介。"""


def _validate_quality_review(value: Any, body: str, *, completed: bool) -> None:
    def fail(message: str):
        raise EditorialContractError("p0_quality_review_invalid", message)

    def nonempty(item: Any) -> bool:
        return isinstance(item, str) and bool(item.strip())

    def exact_keys(item: Any, keys: set[str]) -> bool:
        return isinstance(item, dict) and set(item) == keys

    def evidence(item: Any) -> None:
        quote = item.get("article_quote")
        if not nonempty(quote) or len(quote.strip()) < 12 or normalize_body(quote) not in normalize_body(body):
            fail("quality_review 的 article_quote 必须连续引用本次实际验读正文，至少12字符")
        if not nonempty(item.get("assessment")):
            fail("quality_review 必须说明实际段落如何支持判断")

    if not exact_keys(value, {"fact_check", "article_quality", "example_comparison", "unresolved_issues"}):
        fail("新版 P0 必须提交完整独立 quality_review")
    facts, quality = value["fact_check"], value["article_quality"]
    if not exact_keys(facts, {"passed", "evidence"}) or type(facts["passed"]) is not bool:
        fail("fact_check 必须明确布尔 passed 和事实证据")
    if not isinstance(facts["evidence"], list) or not facts["evidence"]:
        fail("fact_check 缺少实际正文证据")
    for item in facts["evidence"]:
        if not exact_keys(item, {"article_quote", "assessment"}):
            fail("fact_check 证据结构错误")
        evidence(item)
    if not exact_keys(quality, {"passed", "checks"}) or type(quality["passed"]) is not bool:
        fail("article_quality 必须明确布尔 passed 和六项段落检查")
    checks = quality["checks"]
    if (not isinstance(checks, list) or len(checks) != len(QUALITY_DIMENSIONS)
            or any(not exact_keys(row, {"dimension", "passed", "article_quote", "assessment"}) for row in checks)
            or any(not isinstance(row["dimension"], str) for row in checks)
            or {row["dimension"] for row in checks} != set(QUALITY_DIMENSIONS)):
        fail("article_quality 必须分别检查六个完整维度，不能重复或漏项")
    comparisons = value["example_comparison"]
    if (not isinstance(comparisons, list) or len(comparisons) != len(QUALITY_EXAMPLES)
            or any(not exact_keys(row, {"example_id", "passed", "article_quote", "reference_feature", "assessment"}) for row in comparisons)
            or any(not isinstance(row["example_id"], str) for row in comparisons)
            or {row["example_id"] for row in comparisons} != set(QUALITY_EXAMPLES)):
        fail("example_comparison 必须分别对照星源智与港隽")
    for item in checks + comparisons:
        if type(item["passed"]) is not bool:
            fail("每项质量检查必须明确布尔 passed")
        evidence(item)
    if any(not nonempty(item["reference_feature"]) for item in comparisons):
        fail("例文对照缺少对应段落与写法的具体说明")
    issues = value["unresolved_issues"]
    if not isinstance(issues, list) or any(not nonempty(item) for item in issues):
        fail("unresolved_issues 必须是有效问题字符串数组")
    if quality["passed"] != all(item["passed"] for item in checks):
        fail("article_quality.passed 与六项实际结论不一致")
    passed = facts["passed"] and quality["passed"] and all(item["passed"] for item in comparisons)
    if completed and (not passed or issues):
        fail("质量未通过时必须返回 incomplete，不能以 accepted/revised 进入正式交付")
    if not completed and not issues:
        fail("未完成或需重确认必须在 unresolved_issues 保留具体未解决问题")


def fixture_quality_review(markdown: str) -> dict[str, Any]:
    """Offline control-flow fixture only; never evidence of editorial quality."""
    quote = normalize_body(markdown).strip()[:120]
    if len(quote) < 12:
        raise ValueError("quality fixture requires a body of at least 12 characters")
    note = "离线结构夹具：仅验证质量字段与流程接线；不代表事实正确或文章达到例文质量。"
    return {"fact_check": {"passed": True, "evidence": [{"article_quote": quote, "assessment": note}]},
            "article_quality": {"passed": True, "checks": [{"dimension": dim, "passed": True, "article_quote": quote, "assessment": note} for dim in QUALITY_DIMENSIONS]},
            "example_comparison": [{"example_id": ident, "passed": True, "article_quote": quote, "reference_feature": note, "assessment": note} for ident in QUALITY_EXAMPLES],
            "unresolved_issues": []}


def validate_finalize_result(value: Any, candidate: str, *, require_quality_review: bool = False) -> dict[str, Any]:
    result = _object(value)
    outcome = result.get("outcome")
    if outcome not in {"accepted", "revised", "requires_blueprint_reconfirmation", "incomplete"}:
        raise EditorialContractError("finalize_outcome", "宿主验读结果 outcome 不合法")
    body = _article(result, required=outcome in {"accepted", "revised"})
    notes = _notes(result)
    reason = result.get("reason")
    if not isinstance(reason, str):
        raise EditorialContractError("finalize_reason_type", "reason 必须是字符串")
    if require_quality_review:
        _validate_quality_review(result.get("quality_review"), body if outcome in {"accepted", "revised"} else candidate,
                                 completed=outcome in {"accepted", "revised"})
    if outcome in {"requires_blueprint_reconfirmation", "incomplete"}:
        if body != "" or not reason.strip() or notes:
            raise EditorialContractError("finalize_unfinished_body", "未完成或需要重确认时正文及修改说明为空，并说明原因")
        return result
    same = _transport_equal(body, candidate)
    if outcome == "accepted" and (not same or notes):
        raise EditorialContractError("finalize_accepted_mismatch", "宿主原文通过必须保持候选正文不变且修改说明为空")
    newline_only = normalize_body(body).rstrip("\n") == normalize_body(candidate).rstrip("\n")
    if outcome == "revised" and (newline_only or not notes):
        raise EditorialContractError("finalize_revised_mismatch", "宿主修订必须提交实际改变的正文及真实修改说明")
    return result


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def edit_base_input(wf: Any, job_root: Path, *, p0: bool) -> dict[str, Any]:
    """Keep the original Pro draft distinct from a frozen delivered GLM final."""
    from .manuscript_revision import current_revision
    revision = current_revision(wf, job_root, p0=p0)
    if p0:
        from . import p0_rework
        repair = p0_rework.current(wf, job_root, "edit")
        if repair:
            return {"article_markdown": repair["candidate_markdown"], "source": "rejected_deepseek_style",
                    "manuscript_revision": revision}
    if revision:
        return {"article_markdown": revision["base_markdown"], "source": revision.get("base_source", "previous_glm_final"), "manuscript_revision": revision}
    prefix = "p0" if p0 else "article"
    draft = validate_draft_result(_read_object(Path(job_root) / "production" / f"{prefix}_draft.json"))
    if draft["requires_blueprint_reconfirmation"]:
        raise EditorialContractError("draft_requires_confirmation", "初稿尚需蓝图确认，不能进入编辑")
    return {"article_markdown": draft["article_markdown"], "source": "deepseek_draft", "manuscript_revision": None}


def validate_style_result(value: Any, base: str) -> dict[str, Any]:
    from .p0_style import validate_style_result as validate
    return validate(value, base)


def style_base_input(wf: Any, job_root: Path) -> dict[str, Any]:
    """A mandatory P0 style pass requires the actual, valid E8 result."""
    from .p0_style import is_enabled
    if not is_enabled(wf.load_state(job_root)):
        raise EditorialContractError("style_contract_missing", "任务未启用 P0 文采合同")
    production = Path(job_root) / "production"
    if (production / "p0_edit_failure.json").exists():
        raise EditorialContractError("style_e8_failure", "E8 尚未成功，不能以格式回退稿进入文采阶段")
    base = edit_base_input(wf, job_root, p0=True)
    edited = validate_edit_result(_read_object(production / "p0_edited.json"), base["article_markdown"])
    if edited["edit_status"] == "requires_blueprint_reconfirmation":
        raise EditorialContractError("style_e8_reconfirmation", "E8 尚需蓝图重确认，不能进入文采阶段")
    return {"article_markdown": edited["article_markdown"], "source": "deepseek_edit", "manuscript_revision": base["manuscript_revision"]}


def prepare_finalize_input(wf: Any, job_root: Path, *, p0: bool) -> dict[str, Any]:
    """Use a readable E8 candidate, otherwise the legal successful first draft.

    API failures must be rejected by the controller before entering this helper;
    the failure file describes only completed E8 responses failing the contract.
    """
    prefix = "p0" if p0 else "article"
    production = Path(job_root) / "production"
    if p0:
        from .p0_style import is_enabled
        if is_enabled(wf.load_state(job_root)):
            e8 = style_base_input(wf, job_root)
            from . import brand_stage
            style_validator = (lambda value, base: brand_stage.validate_style(value, base, state=wf.load_state(job_root))) if brand_stage.enabled(wf.load_state(job_root)) else validate_style_result
            styled = style_validator(_read_object(production / "p0_styled.json"), e8["article_markdown"])
            if styled.get("edit_status") == "requires_blueprint_reconfirmation":
                raise EditorialContractError("style_requires_confirmation", "文采稿尚需蓝图重确认，不能进入宿主验读")
            base = edit_base_input(wf, job_root, p0=True)
            draft = validate_draft_result(_read_object(production / "p0_draft.json"))
            edited = _read_object(production / "p0_edited.json")
            return {
                "draft_markdown": draft["article_markdown"], "candidate_markdown": styled["article_markdown"],
                "candidate_source": "deepseek_style", "diff": body_diff(base["article_markdown"], styled["article_markdown"]),
                "style_diff": body_diff(e8["article_markdown"], styled["article_markdown"]),
                "edit_base_markdown": base["article_markdown"], "edit_base_source": base["source"],
                "manuscript_revision": base["manuscript_revision"],
                "editorial_notes": edited["editorial_notes"], "style_notes": styled.get("editorial_notes", []),
                "style_audit": styled.get("style_audit", {}), "issues": [],
            }
    draft_result = validate_draft_result(_read_object(production / f"{prefix}_draft.json"))
    if draft_result["requires_blueprint_reconfirmation"]:
        raise EditorialContractError("draft_requires_confirmation", "初稿尚需蓝图确认，不能进入宿主验读")
    draft = draft_result["article_markdown"]
    base = edit_base_input(wf, job_root, p0=p0)
    edited = _read_object(production / f"{prefix}_edited.json")
    failure = _read_object(production / f"{prefix}_edit_failure.json")
    if not edited and not failure:
        raise EditorialContractError("edit_result_missing", "尚无 DeepSeek E8 已完成结果，不能提前进入宿主验读")
    issues: list[Any] = []
    if failure:
        issues.append({key: failure[key] for key in (
            "action", "error_code", "code", "message", "reason", "attempt_id", "stage") if key in failure})
    candidate = edited.get("article_markdown")
    source = "deepseek_edit"
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = failure.get("candidate_markdown")
        source = "deepseek_edit_format_recovery"
    if not isinstance(candidate, str) or not candidate.strip():
        candidate = base["article_markdown"]
        source = base["source"] + "_after_edit_format_error" if base["manuscript_revision"] else "deepseek_draft_after_edit_format_error"
    if edited:
        try:
            validate_edit_result(edited, base["article_markdown"])
        except EditorialContractError as exc:
            issues.append({"code": exc.code, "message": str(exc)})
    notes = edited.get("editorial_notes", [])
    return {
        "draft_markdown": draft, "candidate_markdown": candidate,
        "candidate_source": source, "diff": body_diff(base["article_markdown"], candidate),
        "edit_base_markdown": base["article_markdown"], "edit_base_source": base["source"],
        "manuscript_revision": base["manuscript_revision"],
        "editorial_notes": notes if isinstance(notes, list) else [], "issues": issues,
    }
