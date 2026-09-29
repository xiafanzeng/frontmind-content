"""A local, read-only character counter for explicitly opted-in writer requests."""
from __future__ import annotations

CONTRACT = "frontmind-writer-count/1"
MARKER = '<frontmind_writer_count version="1" />'
ACTIONS = frozenset({"article_draft", "article_edit", "article_repair"})
GUIDANCE = (
    "完成当前正文后，先把拟提交的完整 Markdown 交给 count_article，读取程序返回的实际正文字符数。"
    "按当前委托的篇幅安排相关内容；若仍需展开或调整，在本次写作中完成，改后可再次测量。"
    "不要靠心算或自报字数。测字只提供数字，不评价文字质量。"
    "最后仍按本动作原有 JSON 格式提交完整正文，不把工具回执或测字说明写进文章。"
)


def matches(action, prompt):
    from .writing_context_v14 import MARKER as ARTICLE_MARKER
    from .writing_context_v15 import MARKER as PROSE_MARKER
    from .editorial_preparation import MARKER as EDITORIAL_MARKER
    return (action in ACTIONS and isinstance(prompt, str)
            and prompt.startswith(tuple(m + "\n" + MARKER + "\n" for m in (ARTICLE_MARKER, PROSE_MARKER, EDITORIAL_MARKER))))


def enabled(state):
    return state.get("metadata", {}).get("writer_count_contract") == CONTRACT


def definitions():
    return [{"type": "function", "function": {
        "name": "count_article",
        "description": "统计传入完整 Markdown 正文的实际可见字符数；只计算文本，不读取文件、查询资料或评价文章。",
        "parameters": {"type": "object", "properties": {
            "article_markdown": {"type": "string", "description": "当前拟提交的完整 Markdown 正文"}},
            "required": ["article_markdown"], "additionalProperties": False}}}]


def execute(name, arguments):
    if (name != "count_article" or not isinstance(arguments, dict)
            or set(arguments) != {"article_markdown"}
            or not isinstance(arguments["article_markdown"], str)):
        raise ValueError("count_article 只接受完整 article_markdown 字符串")
    from .natural_editor import character_count
    return {"body_characters": character_count(arguments["article_markdown"])}
