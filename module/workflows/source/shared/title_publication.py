"""Separate title candidates from an exact, headline-free body delivery."""
from __future__ import annotations

import hashlib
import json
import re
import copy
from typing import Any

from .workflow_versions import TITLE_CONTRACT_VERSION, WORKFLOW_VERSION

PUBLICATION_CONTRACT = "frontmind-title-publication/4.11.9"
LEGACY_PUBLICATION_CONTRACT = "frontmind-title-publication/4.11.8"
LEGACY_TITLE_CONTRACT = "4.11.8-canonical-title-2"
_H1 = re.compile(r"(?m)^#[ \t]+[^\r\n]*(?:\r(?=\n|$))?")


def text_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def payload_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _headline(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Title Map 含空标题或非法标题类型")
    if re.search(r"[\r\n\x00-\x1f\x7f]", value):
        raise ValueError("标题必须是独立的单行文字")
    if re.search(r"!\[[^\]]*\]|<[^>]+>", value):
        raise ValueError("标题只包含文字，不包含图片或 HTML 标签")
    return re.sub(r"\s+", " ", value).strip()


def _validate_expected_count(expected_count: int | None) -> None:
    if expected_count is not None and (type(expected_count) is not int or expected_count not in (10, 20)):
        raise ValueError("标题期望数量只能是 10 或 20")


def _candidate_count(candidates: Any, expected_count: int | None) -> int:
    if not isinstance(candidates, list) or len(candidates) not in (10, 20):
        raise ValueError("Title Map candidates 必须恰好包含 10 或 20 个候选标题")
    count = len(candidates)
    if expected_count is not None and count != expected_count:
        raise ValueError(f"Title Map candidates 必须恰好包含 {expected_count} 个候选标题")
    return count


def validate_title_map(value: dict[str, Any], *, p0: bool = False,
                       legacy: bool = False, expected_count: int | None = None) -> dict[str, Any]:
    """Read 10/20-title artifacts; production passes its frozen expected count."""
    _validate_expected_count(expected_count)
    if not isinstance(value, dict):
        raise ValueError("Title Map 必须是 JSON 对象")
    if "candidates" in value:
        if "families" in value:
            raise ValueError("Title Map 不能混用 candidates 与历史 families")
        candidates = value["candidates"]
        count = _candidate_count(candidates, expected_count)
        family = "publicity" if p0 else "article"
        options = []
        for index, item in enumerate(candidates, 1):
            if not isinstance(item, dict):
                raise ValueError("每个候选必须包含 title 和 angle")
            title = _headline(item.get("title"))
            if not isinstance(item.get("angle"), str) or not item["angle"].strip():
                raise ValueError("每个新候选必须提供非空 angle，说明实际切入角度")
            angle = _headline(item["angle"])
            options.append({"title_id": f"title_{index:02d}", "family": family,
                            "title_text": title, "angle": angle})
        if len({item["title_text"] for item in options}) != count:
            raise ValueError(f"Title Map 的 {count} 个标题必须互不重复")
        recommended_id = value.get("canonical_title_id")
        recommended = next((row for row in options if row["title_id"] == recommended_id), None)
        if recommended is None:
            raise ValueError(f"新 Title Map 必须提供有效 canonical_title_id（title_01 至 title_{count:02d}）；不能默认第一项")
        return {"schema_version": WORKFLOW_VERSION, "artifact_type": "frontmind_title_map",
                "title_contract_version": TITLE_CONTRACT_VERSION,
                "requested_count": count, "total_count": count,
                "families": {family: {"count": count, "options": options}},
                "options": options, "canonical_title_id": recommended_id,
                "recommended_title_id": recommended_id, "recommended_title": recommended["title_text"],
                "title_adoption_mode": "separate_candidates_no_title_adopted"}
    families = value.get("families") or {}
    if not isinstance(families, dict):
        raise ValueError("Title Map families 必须是对象")
    if set(families) & {"article", "publicity"}:
        # A title-only revision may return the exported current Title Map.
        # Reuse the candidate contract, then require its normalized fields and
        # both option copies to agree exactly; never guess between two copies.
        family = "publicity" if p0 else "article"
        group = families.get(family)
        rows = value.get("options")
        if (set(families) != {family} or not isinstance(group, dict)
                or not isinstance(rows, list)
                or any(not isinstance(row, dict) for row in rows)):
            raise ValueError("当前 Title Map 必须包含对应的 article/publicity 家族及候选列表")
        normalized = validate_title_map({
            "candidates": [{"title": row.get("title_text"), "angle": row.get("angle")} for row in rows],
            "canonical_title_id": value.get("canonical_title_id"),
        }, p0=p0, expected_count=expected_count)
        if (set(value) - set(normalized) - {"publication"}
                or any(value.get(key) != item for key, item in normalized.items())):
            raise ValueError("当前 Title Map 的顺序编号、家族副本、数量或推荐字段不一致")
        if "publication" in value and not isinstance(value["publication"], dict):
            raise ValueError("Title Map publication 必须是对象")
        # Existing publication metadata is provenance, not a new publication
        # binding; publication()/verify_publication() derive/check that binding.
        return copy.deepcopy(value)
    if expected_count is not None and expected_count != 20:
        raise ValueError("历史双家族 Title Map 固定包含 20 个标题，与本轮期望数量不符")
    options = []
    for family, stem in (("decision_search", "decision"), ("media_pr", "media")):
        rows = families.get(family)
        if not isinstance(rows, list) or len(rows) != 10:
            raise ValueError("Title Map 必须包含 10 个决策搜索标题和 10 个媒体标题")
        for index, item in enumerate(rows, 1):
            title = _headline(item.get("title") if isinstance(item, dict) else item)
            h1 = item.get("h1") if isinstance(item, dict) else None
            options.append({"title_id": f"{stem}_title_{index:02d}", "family": family,
                            "title_text": title, "h1_suggestion": _headline(h1) if h1 else title})
            if isinstance(item, dict) and item.get("angle"):
                options[-1]["angle"] = _headline(item["angle"])
    if len({item["title_text"] for item in options}) != 20:
        raise ValueError("Title Map 的 20 个标题必须互不重复")
    selected_id = value.get("canonical_title_id")
    # A reader may validate genuine pre-4.11.8 results. This never grants a
    # missing selection to a new production action, nor rewrites historical H1.
    if legacy and selected_id is None:
        selected = options[0]
    else:
        selected = next((row for row in options if row["title_id"] == selected_id), None)
        if selected is None:
            raise ValueError("Title Map 必须明确提供有效 canonical_title_id；不能默认采用第一项")
    return {"schema_version": WORKFLOW_VERSION, "artifact_type": "frontmind_title_map",
            "title_contract_version": ("4.11-natural-title-1" if legacy and selected_id is None else TITLE_CONTRACT_VERSION),
            "requested_count": 20, "total_count": 20,
            "families": {"decision_search": {"count": 10, "options": options[:10]},
                         "media_pr": {"count": 10, "options": options[10:]}},
            "options": options, "canonical_title_id": selected_id,
            "selected_title_id": selected["title_id"], "selected_title": selected["title_text"],
            "title_adoption_mode": ("legacy_unchanged_manuscript" if legacy and selected_id is None
                                    else "model_selected_canonical_h1")}


def title_review_input(title_result: dict, *, p0: bool, expected_count: int | None = None) -> dict:
    """Neutral projection of original titles for editor comparison, never saved over them."""
    source = validate_title_map(title_result, p0=p0, expected_count=expected_count)
    recommended = source.get("recommended_title_id") or source.get("canonical_title_id")
    options = source["options"]
    position = next(index for index, option in enumerate(options, 1) if option["title_id"] == recommended)
    return {"candidates": [{"title": option["title_text"], "angle": option.get("angle") or "未标注"}
                           for option in options], "canonical_title_id": f"title_{position:02d}"}


def validate_title_review_result(value: dict, title_result: dict, *, p0: bool,
                                 expected_count: int | None = None) -> dict:
    _validate_expected_count(expected_count)
    if not isinstance(value, dict):
        raise ValueError("标题编辑结果必须是对象")
    required = {"outcome", "candidates", "canonical_title_id", "title_notes", "reason"}
    if set(value) != required:
        raise ValueError("标题编辑仅返回 outcome、candidates、canonical_title_id、title_notes、reason；不能改正文")
    outcome = value["outcome"]
    notes, reason = value["title_notes"], value["reason"]
    if not isinstance(notes, list) or not all(isinstance(item, str) and item.strip() for item in notes) or not isinstance(reason, str):
        raise ValueError("标题编辑说明或原因格式无效")
    if outcome == "incomplete":
        if value["candidates"] != [] or value["canonical_title_id"] != "" or notes or not reason.strip():
            raise ValueError("未完成标题编辑须清空候选、推荐和修改说明，并说明原因")
        return value
    if outcome not in {"accepted", "revised"}:
        raise ValueError("标题编辑 outcome 无效")
    if reason:
        raise ValueError("已完成标题编辑不填写未完成原因")
    original = title_review_input(title_result, p0=p0, expected_count=expected_count)
    reviewed = title_review_input({"candidates": value["candidates"], "canonical_title_id": value["canonical_title_id"]},
                                  p0=p0, expected_count=len(original["candidates"]))
    if outcome == "accepted" and (reviewed != original or notes):
        raise ValueError("标题原文通过须保留全部候选与推荐，且修改说明为空")
    if outcome == "revised" and (reviewed == original or not notes):
        raise ValueError("标题编辑须提交实际改变的候选或推荐及真实修改说明，不能只声明已修改")
    return value


def without_first_h1(markdown: str) -> str:
    match = _H1.search(markdown)
    if not match:
        raise ValueError("正文缺少 H1，无法派生发布标题")
    # Preserve original line endings and every non-headline character.
    end = match.end() - (1 if match.group().endswith("\r") else 0)
    return markdown[:match.start()] + markdown[end:]


def body_only(markdown: str) -> str:
    """Remove the first article-H1 line, preserving all other bytes."""
    match = _H1.search(markdown)
    if not match:
        raise ValueError("正文缺少内部文章 H1，无法派生无标题交付稿")
    end = match.end()
    if markdown[end:end + 1] == "\n":
        end += 1
    return markdown[:match.start()] + markdown[end:]


def _legacy_publication(markdown: str, title_result: dict[str, Any], *, p0: bool,
                        expected_count: int | None = None) -> tuple[str, dict, dict]:
    """Read genuine 4.11.8 automatic-title publications without upgrading them."""
    if "candidates" in title_result or set(title_result.get("families", {})) & {"article", "publicity"}:
        raise ValueError("中性标题候选不能按历史自动采用标题合同发布")
    title_map = validate_title_map(title_result, p0=p0, expected_count=expected_count)
    title_map["title_contract_version"] = LEGACY_TITLE_CONTRACT
    for option in title_map["options"]:
        option.pop("angle", None)  # 4.11.8 ignored optional angle metadata.
    if p0 and not title_map["selected_title_id"].startswith("media_title_"):
        raise ValueError("历史 P0 发布主标题不属于当时允许的媒体组")
    match = _H1.search(markdown)
    if not match:
        raise ValueError("正文缺少 H1，无法派生发布标题")
    end = match.end() - (1 if match.group().endswith("\r") else 0)
    published = markdown[:match.start()] + "# " + title_map["selected_title"] + markdown[end:]
    binding = {"contract": LEGACY_PUBLICATION_CONTRACT, "transformation": "replace_first_h1_only",
               "canonical_title_id": title_map["selected_title_id"],
               "canonical_title": title_map["selected_title"],
               "host_final_markdown_sha256": text_hash(markdown),
               "title_result_sha256": payload_hash(title_result),
               "published_markdown_sha256": text_hash(published),
               "body_without_h1_sha256": text_hash(without_first_h1(markdown))}
    return published, title_map, binding


def publication(markdown: str, title_result: dict[str, Any], *, p0: bool,
                title_review: dict | None = None, expected_count: int | None = None) -> tuple[str, dict, dict]:
    if title_review is not None:
        validate_title_review_result(title_review, title_result, p0=p0, expected_count=expected_count)
        if title_review["outcome"] == "incomplete":
            raise ValueError("标题编辑未完成，不能交付原候选")
    title_map = validate_title_map(title_review if title_review is not None else title_result,
                                   p0=p0, expected_count=expected_count)
    if "selected_title_id" in title_map:  # Historical family payload, new body-only delivery.
        title_map["recommended_title_id"] = title_map.pop("selected_title_id")
        title_map["recommended_title"] = title_map.pop("selected_title")
    title_map["title_adoption_mode"] = "separate_candidates_no_title_adopted"
    published = body_only(markdown)
    binding = {"contract": PUBLICATION_CONTRACT, "transformation": "remove_first_h1_line_only",
               "host_final_markdown_sha256": text_hash(markdown),
               "title_result_sha256": payload_hash(title_result),
               "published_markdown_sha256": text_hash(published),
               "body_without_h1_sha256": text_hash(published)}
    if title_review is not None:
        binding["title_review_result_sha256"] = payload_hash(title_review)
    return published, title_map, binding


def verify_publication(markdown: str, title_result: dict, published: str,
                       binding: dict, *, p0: bool, title_review: dict | None = None,
                       expected_count: int | None = None) -> dict:
    contract = binding.get("contract")
    if contract == LEGACY_PUBLICATION_CONTRACT:
        if title_review is not None:
            raise ValueError("历史发布稿不能混入新的标题编辑结果")
        expected, title_map, expected_binding = _legacy_publication(markdown, title_result, p0=p0,
                                                                    expected_count=expected_count)
    elif contract == PUBLICATION_CONTRACT:
        expected, title_map, expected_binding = publication(markdown, title_result, p0=p0,
                                                            title_review=title_review, expected_count=expected_count)
    else:
        raise ValueError("未知发布稿绑定合同")
    allowed = set(expected_binding) | {"finalized_result_file_sha256", "titles_result_file_sha256"}
    if title_review is not None:
        allowed.add("title_review_result_file_sha256")
    if set(binding) - allowed or published != expected or any(binding.get(key) != val for key, val in expected_binding.items()):
        raise ValueError("交付正文、标题候选或来源绑定不一致")
    return title_map
