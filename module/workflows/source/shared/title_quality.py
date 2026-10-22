"""Concrete title-editing suggestions, deliberately not a publication gate.

These heuristics can point an editor toward repetition and awkward structures.
They do not determine semantic diversity, mandate numbers, or alter candidates.
"""
from __future__ import annotations

from collections import Counter
import re

_PUNCTUATION = re.compile(r"[\s\W_]+", re.UNICODE)
_OPENING_ENUM = re.compile(r"^[^、，,：:]{1,14}、[^、，,：:]{1,14}(?:、|与|和|及)[^、，,：:]{1,14}")
_FROM_TO = re.compile(r"从[^，,：:]{1,18}到[^，,：:]{1,18}")
_CAN_LIST = re.compile(r"能[^，,：:、]{1,12}(?:(?:、|，|,)(?:也|还|又)?|又|也|还|和|且)能[^，,：:、]{1,12}")
_MECHANISM = re.compile(r"(?:连接|承载|收进|融入|适配|打通)[^，,：:]{0,12}(?:采集|信息|报告|管理|场景|部署|流程|服务协同|全链路)")


def _plain(value, brand=""):
    value = str(value or "")
    if brand:
        value = value.replace(brand, "")
    return _PUNCTUATION.sub("", value)


def _near_rewrite(left, right):
    if len(left) < 10 or len(right) < 10:
        return False
    left_chars, right_chars = Counter(left), Counter(right)
    total = sum((left_chars | right_chars).values())
    overlap = sum((left_chars & right_chars).values()) / max(total, 1)
    left_pairs = {left[i:i + 2] for i in range(len(left) - 1)}
    right_pairs = {right[i:i + 2] for i in range(len(right) - 1)}
    pairs = len(left_pairs & right_pairs) / max(len(left_pairs | right_pairs), 1)
    return overlap >= .86 or pairs >= .78


def quality_feedback(candidates: list, ammo=None, pattern="P0", brand="") -> list[str]:
    """Return advisory prose for an editor, including the affected title IDs.

    Missing optional fields and sparse source material produce no gate failure.
    User instructions, long subject names and actual genre intent take priority
    over these approximate length/structure observations.
    """
    rows = [value if isinstance(value, dict) else {"title": str(value)} for value in candidates or []]
    suggestions = []
    angles, texts, from_to = {}, [], []

    def identifier(index):
        return str(rows[index].get("title_id") or rows[index].get("id") or f"title_{index + 1:02d}")

    for index, row in enumerate(rows):
        title = str(row.get("title", ""))
        if not title:
            continue
        item_id = identifier(index)
        style = row.get("style")
        low = 18 if style == "formal" else 20
        length = len(_PUNCTUATION.sub("", title))
        without_brand = len(_plain(title, brand))
        long_name_exception = bool(brand and len(_plain(brand)) >= 10 and brand in title and without_brand <= 32)
        if style in {"formal", "scenario"} and (length < low or (length > 32 and not long_name_exception)):
            suggestions.append(f"{item_id} 约{length}字；{low}—32字仅作阅读长度参考，编辑可按主体名称和当前硬性要求保留，过长时先删流程罗列。")
        opening = title.strip()
        if brand and opening.startswith(brand):
            opening = opening[len(brand):].lstrip(" ：:｜|—-，,")
        if _OPENING_ENUM.search(opening):
            suggestions.append(f"{item_id} 开头并列了至少三项内容，考虑只留一个读者最关心的入口。")
        if _MECHANISM.search(title):
            suggestions.append(f"{item_id} 用内部机制描述推进标题，编辑可把它讲成读者能理解的用途或具体动作，不机械禁用动词。")
        if _CAN_LIST.search(title):
            suggestions.append(f"{item_id} 以“能……能……”罗列功能，考虑选一个重心，避免把功能清单当主标题。")
        if _FROM_TO.search(title):
            from_to.append(item_id)
        angle = _plain(row.get("angle", ""))
        if angle:
            if angle in angles:
                suggestions.append(f"{angles[angle]} 与 {item_id} 的 angle 相同，编辑应结合全文判断两题是否提供不同阅读入口。")
            else:
                angles[angle] = item_id
        text = _plain(title, brand)
        for prior_id, prior_text in texts:
            if text == prior_text or _near_rewrite(text, prior_text):
                suggestions.append(f"{prior_id} 与 {item_id} 的选材和措辞相近，看看是否只是换语序；需要时重新选择阅读入口，不能仅凭字符串认定语义重复。")
                break
        texts.append((item_id, text))

    if len(from_to) > 1:
        suggestions.append(f"{'、'.join(from_to)} 重复使用“从……到……”展开，编辑可调整其中几题的开头与节奏。")

    # No fixed coverage quota. P01/P02 default naming rules must not be undone.
    items = ammo.get("items", []) if isinstance(ammo, dict) else []
    relevant = [row for row in items if isinstance(row, dict) and row.get("kind") in {"number", "patent", "standard", "org"} and row.get("text") and row.get("context")]
    if pattern in {"P01", "P02"}:
        relevant = [row for row in relevant if row.get("kind") == "number"]
    hooks = list(dict.fromkeys(str(row["text"]) for row in relevant))
    if len(hooks) >= 2 and not any(hook in str(row.get("title", "")) for hook in hooks for row in rows):
        label = "数字" if pattern in {"P01", "P02"} else "数字或专名"
        suggestions.append(f"已有带上下文的{label}素材尚未用于标题；若与整篇主线相关，可挑选一个作为不同入口，不必凑覆盖数量，正文未覆盖的素材仍按后台标记取舍。")
    return suggestions
