"""Source excerpts for title editors; extraction is neither verification nor a gate.

Keep each hook beside its original sentence and origin.  The compatibility
lists are an index, not facts that can be assembled into a new claim.
"""
from __future__ import annotations

import re

_SENTENCES = re.compile(r"[。！？!?；;\n]+")
_NUMBER = re.compile(
    r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?\s*(?:%|％|分钟|秒|小时|通道|毫秒|毫米|厘米|公斤|克|千克|"
    r"英寸|寸|万元|亿元|元|万|亿|项|种|家|条|款|个|年|次|人|台|套|度|天|个月|月)(?![A-Za-z])"
)
_PATENT = re.compile(r"(?<![A-Za-z0-9])ZL\s*\d{6,}(?:\.\d+|[Xx])?(?![A-Za-z0-9])", re.I)
_STANDARD = re.compile(r"(?<![A-Za-z])(?:GB(?:\s*/\s*T)?|ISO|IEC)\s*\d+(?:[.\-/]\d+)*(?![A-Za-z0-9])", re.I)
_ORG = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9·&.\- ]{2,50}?(?:大学|学院|协会|集团|公司|实验室|研究院|研究所|医院|中心|委员会)"
    r"(?:[（(][^（）()\n]{1,15}[）)])?"
)
_ORG_BOUNDARY = re.compile(
    r"(?:联合研发|联合成立|共同成立|战略合作|开展合作|进行合作|产品由|设备由|终端由|"
    r"携手|到访|莅临|签约|合作|推出|发布|代表|来自|包括|例如|目前|此前|这是|"
    r"以及|及其|与|由|同|在|向|和|及|的)"
)
_CHANNELS = ("中医馆", "药店", "健康管理中心", "康养机构", "社区", "门店", "家庭", "企业", "医院", "诊所")
_EVENT = re.compile(r"合作|到访|签约|发布|上市|莅临|洽谈|出海|成立|推出")
_PRODUCT_CONTEXT = re.compile(
    r"检测|采集|通道|设备|终端|机器人|产品|屏幕|电池|续航|测量|分辨率|传感|功能|"
    r"技术|服务|门店|用户|客户|机构|销售|售价|价格|重量|尺寸|上市|发布|成立|合作|到访|专利|标准"
)
_AUTHOR_NUMBER = re.compile(
    r"(?:字数|字符|篇幅|标题|候选|正式组|场景组|段落|章节|Prompt|prompt|提示词|"
    r"返工|迭代|轮次|第[一二三四五六七八九十\d]+轮|例文|文章池|推荐问题)"
)


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n。；;，,:：")


def _compact(value):
    return re.sub(r"\s+", "", value or "")


def _sentences(text):
    return [_clean(part) for part in _SENTENCES.split(text or "") if _clean(part)]


def _org_name(raw):
    # Sentence/relationship text to the left of a name is not part of the name.
    name = _ORG_BOUNDARY.split(_clean(raw))[-1].strip()
    name = re.sub(r"^(?:本次|此次|近日|该产品|该设备|该终端|本产品|本设备|本终端|双方|一所|一家|一所位于)", "", name)
    if len(name) < 3 or name in _CHANNELS or name in {"集团", "公司", "实验室", "研究院", "研究所", "大学", "学院", "协会", "委员会"}:
        return ""
    return name


def _number_is_content(sentence, match, origin):
    # Writing counts are not product hooks, even if a product is named nearby.
    before = sentence[max(0, match.start() - 14):match.start()]
    after = sentence[match.end():match.end() + 10]
    if _AUTHOR_NUMBER.search(before[-8:] + after):
        return False
    if origin != "body":
        clause_start = max(sentence.rfind(p, 0, match.start()) for p in ("，", ",", "：", ":")) + 1
        positions = [sentence.find(p, match.end()) for p in ("，", ",", "：", ":")]
        clause_end = min((p for p in positions if p >= 0), default=len(sentence))
        return bool(_PRODUCT_CONTEXT.search(sentence[clause_start:clause_end]))
    return True


def extract(article: str, requirements_text: str = "", extra: list | None = None) -> dict:
    """Collect available excerpts without upgrading supplied material to proof.

    ``requirements_text`` is explicit title material, not the full writing
    prompt.  ``extra`` accepts strings and ``{text, source}`` objects.  A hook
    not already stated in the article retains ``body_covered=False``; title-only
    generation never edits the article to accommodate it.
    """
    article = str(article or "")
    result = {"numbers": [], "orgs": [], "channels": [], "events": [], "extra": [], "items": []}
    seen = set()

    def add(kind, text, context, origin, source=""):
        text, context = _clean(text), _clean(context)
        if not text or not context:
            return
        key = (kind, text, context, origin, source)
        if key in seen:
            return
        seen.add(key)
        covered = origin == "body" or _compact(context) in _compact(article)
        item = {"kind": kind, "text": text, "context": context, "origin": origin, "body_covered": covered}
        if source:
            item["source"] = source
        result["items"].append(item)
        category = {"number": "numbers", "patent": "numbers", "standard": "numbers", "org": "orgs", "channel": "channels", "event": "events", "extra": "extra"}[kind]
        if text not in result[category]:
            result[category].append(text)

    inputs = [(article, "body", ""), (str(requirements_text or ""), "requirements", "")]
    for value in extra or []:
        if isinstance(value, dict):
            text, source = _clean(value.get("text", "")), _clean(value.get("source", ""))
        elif isinstance(value, str):
            text, source = _clean(value), ""
        else:
            continue
        if text:
            add("extra", text, text, "extra", source)
            inputs.append((text, "extra", source))

    for text, origin, source in inputs:
        for sentence in _sentences(text):
            for regex, kind in ((_PATENT, "patent"), (_STANDARD, "standard"), (_NUMBER, "number")):
                for match in regex.finditer(sentence):
                    if kind != "number" or _number_is_content(sentence, match, origin):
                        add(kind, match.group(), sentence, origin, source)
            for match in _ORG.finditer(sentence):
                name = _org_name(match.group())
                if name:
                    add("org", name, sentence, origin, source)
            for channel in _CHANNELS:
                if channel in sentence:
                    add("channel", channel, sentence, origin, source)
            # A bare action is not an event: preserve who did what, where given.
            if _EVENT.search(sentence) and len(sentence) >= 8 and not _AUTHOR_NUMBER.search(sentence):
                add("event", sentence, sentence, origin, source)
    return result


def render(ammo: dict) -> str:
    """Render original relationships, never an isolated-number shopping list."""
    items = ammo.get("items", []) if isinstance(ammo, dict) else []
    if not items:
        return "- 暂无可提取的标题素材，按全文已有内容拟题，不补造数字、专名或事件。"
    labels = {"number": "数字", "patent": "专利编号", "standard": "标准编号", "org": "机构", "channel": "使用场景", "event": "事件", "extra": "补充素材"}
    origins = {"body": "正文", "requirements": "本轮标题素材", "extra": "补充输入"}
    lines = ["以下摘录保留来源上下文，只供拟题取材；提取不等于独立核验。"]
    # One sentence may contain several indexed hooks; show its relationship once.
    groups = {}
    for row in items:
        key = (row.get("context", ""), row.get("origin", ""), row.get("source", ""), bool(row.get("body_covered")))
        groups.setdefault(key, []).append(row)
    for (context, origin, source, covered), rows in groups.items():
        kinds = list(dict.fromkeys(labels.get(row.get("kind"), "素材") for row in rows))
        status = "正文已有" if covered else "正文未覆盖，拟题时按全文主线取舍"
        provenance = origins.get(origin, origin or "输入") + (f"；来源标注：{source}" if source else "")
        lines.append(f"- {'／'.join(kinds)}｜{provenance}｜{status}：{context}")
    return "\n".join(lines)
