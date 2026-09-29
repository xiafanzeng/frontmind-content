"""Current recommendation writing; v12 builders remain immutable for recovery."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from .writing_context import (_text, _read, _json, _blueprint, _reference_key, _is_same_reference,
    reference_is_ai_answer, reference_is_content_background)
from .editorial_contracts import EditorialContractError, prepare_finalize_input, edit_base_input
from . import writing_requirements as requirements

def _natural_wrap(prompt: str) -> str:
    from .writing_requirements import MARKER
    return MARKER + "\n" + prompt


def _natural_wrap_for(wf: Any, job_root: Path, prompt: str) -> str:
    if requirements.editorial_mission(wf.load_state(job_root)):
        return requirements.MISSION_MARKER + "\n" + prompt
    return _natural_wrap(prompt)


NATURAL_PATTERN_GUIDANCE = {
    "P00": "品牌深度特写：围绕品牌自身的业务、方法、团队与特点建立整体认识，不承担具体问题的推荐或竞品比较任务。",
    "P01": "单主体推荐：围绕正式问题，选择与眼前需求直接相关的业务、人员、方法和服务，具体说明为什么值得考虑主对象。推荐依据融入介绍，不写成品牌通史或每段末尾的推荐总结；不默认追加竞品、替代路径或短板章节。",
    "P02": "多主体推荐：保留本题已确认的推荐分档、重点、主体角色及顺序，通过导语、分档标题和具体特点完成推荐任务，不能只剩名录。分档不是无据的质量、安全或效果等级；不向读者辩解排序，也不追加统一核查清单。",
    "P03": "解释本题的具体问题、方法或过程，相关主体信息为解释服务。",
    "P04": "报道本次事件的参与者、时间与实际进展。",
    "P05": "围绕题目点名的对象，以相关、可比的事实说明差异；比较方式服从本篇表达任务。",
    "P06": "用相关业务事实回答本题关于资质、体验、口碑或可信度的疑问。",
}


def _reference_key(text: str) -> str:
    # Identity normalization is only for duplicate reference texts. It is not a
    # lexical classifier or a prose quality test.
    return re.sub(r"[\s#*_`]+", "", text)


def _is_same_reference(text: str, others: list[str]) -> bool:
    key = _reference_key(text)
    return bool(key) and any(key == other or (min(len(key), len(other)) >= 200 and
                                            (key in other or other in key))
                             for other in (_reference_key(item) for item in others))


def reference_is_ai_answer(example: dict[str, Any], body: str, answers: list[str] = ()) -> bool:
    """Use recorded identity and duplicate bodies, never prose-word heuristics."""
    origin = " ".join(str(example.get(key) or "") for key in
                      ("source_type", "source", "origin", "obtained_via", "title"))
    return (bool(re.search(r"ai[_ -]?answer|model[_ -]?answer|AI\s*(?:答案|回答)|原回答|千问.*回答|ChatGPT.*回答|DeepSeek.*回答", origin, re.I))
            or _is_same_reference(body, list(answers)))


def reference_is_content_background(example: dict[str, Any], body: str, answers: list[str] = ()) -> bool:
    role = example.get("reference_role") or example.get("role")
    return role in {"内容背景", "content_background", "content", "background"} or reference_is_ai_answer(example, body, answers)


def _natural_reference_sets(wf: Any, job_root: Path, *, p0: bool) -> dict[str, list[dict[str, str]]]:
    """Assign roles once from recorded provenance; never reuse AI prose as style.

    Explicit fact/source reading remains the blueprint's job. These are writing
    references, not sources from which an author may invent institution facts.
    """
    state = wf.load_state(job_root)
    answers = [] if p0 else list(wf.answer_texts(job_root))
    content = []
    for index, body in enumerate(answers, 1):
        if body.strip() and not _is_same_reference(body, [x["text"] for x in content]):
            content.append({"title": f"AI 回答 {index}", "text": body})
    style, length = [], []
    route = state.get("selected_example_route")
    if route not in {"A", "top20"}:
        return {"content": content, "style": style, "length": length}
    for example in wf.load_examples(job_root, "p0" if p0 else "question"):
        raw = example.get("path") or example.get("body_path")
        if not raw:
            raise EditorialContractError("selected_example_missing", "所选例文缺少正文路径")
        path = Path(str(raw))
        path = path if path.is_absolute() else Path(job_root) / path
        body = _read(path)
        if not body.strip():
            raise EditorialContractError("selected_example_missing", "所选例文缺少完整正文")
        title = str(example.get("title") or "写作参考")
        role = str(example.get("reference_role") or example.get("role") or "")
        record = {"title": title, "text": body}
        if reference_is_content_background(example, body, answers):
            if not _is_same_reference(body, [x["text"] for x in content]):
                content.append(record)
            continue
        if role in {"篇幅参考", "篇幅样本", "length", "length_only", "style_and_length"}:
            if not _is_same_reference(body, [x["text"] for x in length]):
                length.append(record)
        if role not in {"篇幅参考", "篇幅样本", "length", "length_only", "事实来源", "fact"}:
            record["guidance"] = str(example.get("style_analysis") or "")
            if not _is_same_reference(body, [x["text"] for x in style]):
                style.append(record)
    return {"content": content, "style": style, "length": length}


def _natural_examples(wf: Any, job_root: Path, *, p0: bool) -> str:
    if p0:
        return "P0 完整文风例文只在第三遍使用。"
    rows = _natural_reference_sets(wf, job_root, p0=False)["style"]
    return "\n\n".join("### 文风例文：" + row["title"] + "\n用法：" + row.get("guidance", "") + "\n\n" + row["text"] for row in rows) or "没有独立的文风例文；按本篇体裁与自然写作要求完成。"


def reference_length_budget(wf: Any, job_root: Path, *, p0: bool) -> dict[str, Any]:
    from .natural_editor import character_count
    rows = _natural_reference_sets(wf, job_root, p0=p0)["length"]
    samples = [{"title": row["title"], "characters": character_count(row["text"])} for row in rows]
    return {"samples": samples, "longest_sample_characters": max((row["characters"] for row in samples), default=0),
            "use": "只统计被指定为篇幅用途的完整正文；明确篇幅目标独立保留，短文风例文不下调目标。用户指定某一篇时只使用该篇，不用其他样本替代。"}


def _natural_commission(wf: Any, job_root: Path, *, p0: bool) -> str:
    from .manuscript_revision import current_revision
    state = wf.load_state(job_root)
    if requirements.editorial_mission(state):
        return _editorial_commission(wf, job_root, p0=p0)
    current = current_revision(wf, job_root, p0=p0)
    brief = requirements.effective(wf, job_root, p0=p0)
    pattern = "P00" if p0 else state["selected_pattern_id"]
    lines = ["本篇持续有效的写作要求：\n" + _json(brief),
             "文章任务：\n" + NATURAL_PATTERN_GUIDANCE[pattern],
             "篇幅统计统一为正文可见字符：含小标题、标点、数字与英文，排除主标题、独立候选标题、空白及 Markdown 标记。明确目标是应完成的展开程度，不能自行改成上限或不设最低。"]
    if current:
        lines.append("本轮新增修改意见：\n" + current["edits_markdown"])
        lines.append("本轮意见只覆盖冲突部分；未改变的正式题目、任务、对象、推荐关系、篇幅、排版与参考用途继续有效。实际完整基稿是编辑对象，不替代当前要求；外层编辑建议和 XTY 意见不是用户撤销要求的授权。")
    return "\n\n".join(lines)


def _natural_context(wf: Any, job_root: Path, *, p0: bool,
                     include_references: bool = True,
                     include_source_index: bool = False) -> str:
    bp = _blueprint(job_root, p0=p0)
    state = wf.load_state(job_root)
    if requirements.editorial_mission(state):
        return _editorial_context(wf, job_root, p0=p0, include_references=include_references,
                                  include_source_index=include_source_index)
    from .manuscript_revision import current_revision
    current = current_revision(wf, job_root, p0=p0)
    from .writing_materials import selected
    material = selected(current, bp)
    subject = state.get("reference_pack", {}).get("brand", "") if p0 else state["question"]["question_text"]
    lines = ["本篇正式主题：" + subject]
    lines.append(_natural_commission(wf, job_root, p0=p0))
    if state.get("metadata", {}).get("writing_outline_input_mode") == requirements.WRITING_OUTLINE_INPUT_MODE:
        outline = {key: bp[key] for key in ("opening", "sections", "ending", "example_use") if key in bp}
        lines.append("当前蓝图的可调整构思（不是事实来源，也不是必须逐节完成的正文合同）：\n"
                     "当前用户要求和后续明确修改优先。参考其中有用的内容推进、详略和例文用法；开头、小标题、章节顺序与结束安排均可合并、改写、换序或舍弃，不照抄任务说明。"
                     "编辑实际完整基稿时，保留已经成立的组织方式，不要求把正文重排回旧章节。\n" + _json(outline))
    lines.append("可用事实（保留真实日期、范围、状态及必要条件，不要求逐项搬入正文）：\n" + material["writing_material_markdown"])
    if True:
        lines.append("内部编辑约束（约束取舍与事实含义，不改写成正文中的宣传禁令或免责声明）：\n" + _json(material.get("material_adjustments", [])))
    # Only the tool-using reader needs lookup coordinates. Writers receive the
    # selected facts, not source-use notes or the upstream research narrative.
    if include_source_index:
        lines.append("事实来源索引（具体事实存疑时使用）：\n" + _json(material.get("writing_material_sources", [])))
    if include_references and not p0:
        # The original answer is useful to selection, but re-injecting it here
        # competes with the current brief even when labelled "background".
        lines.append("文风参考（学习详略与行文，不沿用其栏目、事实和提醒）：\n" + _natural_examples(wf, job_root, p0=False))
    lines.append("Markdown：首行一个 # 内部标题；其余排版严格按本篇要求，区分独立加粗段落与段首行内加粗。要求行内名称时写 **完整主体名称** 紧接介绍正文，名称后不换行。导出保持原结构。")
    return "\n\n".join(lines)


def _editorial_commission(wf: Any, job_root: Path, *, p0: bool) -> str:
    from .manuscript_revision import current_revision
    lines = ["当前写作要求：\n" + _json(requirements.effective(wf, job_root, p0=p0)),
             "篇幅统计：正文可见字符，含小标题、标点、数字与英文，排除主标题、候选标题、空白与 Markdown 标记。"]
    revision = current_revision(wf, job_root, p0=p0)
    if revision:
        lines.append("本轮修改要求（未变更的写作要求继续有效）：\n" + revision["edits_markdown"])
    return "\n\n".join(lines)


def _editorial_context(wf: Any, job_root: Path, *, p0: bool,
                       include_references: bool, include_source_index: bool) -> str:
    from .manuscript_revision import current_revision
    bp = _blueprint(job_root, p0=p0)
    revision = current_revision(wf, job_root, p0=p0)
    from .writing_materials import selected
    material = selected(revision, bp)
    lines = [_editorial_commission(wf, job_root, p0=p0)]
    outline = {key: bp[key] for key in ("opening", "sections", "ending", "example_use") if key in bp}
    current_manuscript = revision and revision.get("outline_input_mode") == requirements.MANUSCRIPT_OUTLINE_INPUT_MODE
    if outline and not current_manuscript:
        lines.append("可调整的内容构思（当前要求优先，编辑已有完整稿时按实际内容组织）：\n" + _json(outline))
    lines.append("选用事实：\n" + material["writing_material_markdown"])
    if material.get("material_adjustments"):
        lines.append("后台事实使用说明：\n" + _json(material["material_adjustments"]))
    if include_source_index:
        lines.append("查阅原件用的来源索引：\n" + _json(material.get("writing_material_sources", [])))
    if include_references and not p0:
        lines.append("文风参考（选材、详略与段落推进）：\n" + _natural_examples(wf, job_root, p0=False))
    lines.append("正文 Markdown 首行一个 # 内部标题，其余排版按当前要求。")
    return "\n\n".join(lines)


EDITORIAL_BLUEPRINT_FIELDS = """各字段分别承担以下工作：
article_brief：一份简短、完整的写作委托，写清读者、体裁、主题、必写主体、详略、篇幅和排版；当前要求覆盖冲突的旧构思。
writing_material_markdown：以机构、项目、人员或服务为主语，直接写选中的事实及业务状态，保留足够展开重点的具体方法和细节。项目的未知细节仅在影响本篇核心陈述时提炼为一句业务状态。文件名、表格坐标、原件怎样证明结论归入来源字段。
material_adjustments：作者确实需要、且尚未由事实状态涵盖的少量事实使用说明；每项只记录一件当前事项。研究经过保留在原任务记录。
opening、sections（heading/task）、ending：简短说明内容怎样推进，可由作者调整；事实使用说明只放 material_adjustments。
writing_material_sources：非空数组，每项含实际读取原件的 source_ref 和 use，将出处、取值位置和选中事实的依据放在这里。文风例文与写作要求保持各自身份。
brand_positioning_use、answer_use：分别简述选材重点和原回答的用途。example_use：说明例文的详略与行文怎样服务本篇。
estimated_length：完整保留当前明确目标与统计口径；未指定时参考最长有效篇幅样本。"""


def _editorial_blueprint_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    state = wf.load_state(job_root)
    pattern = "P00" if p0 else state["selected_pattern_id"]
    decisions = state.get("decisions") or {}
    current = _text(decisions.get("blueprint_edits"))
    lines = ["# 准备写作委托、事实与内容构思",
             "品牌：" + state.get("reference_pack", {}).get("brand", ""),
             "本篇内容关系：" + NATURAL_PATTERN_GUIDANCE[pattern],
             "当前修改要求：\n" + (current or "无新增修改"),
             "原始委托（继承与当前要求相容的内容）：\n" + (_text(decisions.get("response_brief")) or "按正式题目与选定内容安排"),
             _editorial_commission(wf, job_root, p0=p0),
             "使用 list_materials 定位原件，按需 read_material 或 extract_document，选取足以展开本题的具体事实。需要补料时可用现有 web_search、web_read 阅读相关原始资料，记录实际来源和日期。本轮提交选材与构思，后续作者完成文章。"]
    if not p0:
        refs = _natural_reference_sets(wf, job_root, p0=False)
        if refs["content"]:
            lines.append("理解原问题用的 AI 回答：\n\n" + "\n\n".join("### " + row["title"] + "\n\n" + row["text"] for row in refs["content"]))
        selected = requirements.effective(wf, job_root, p0=False)
        qpath = Path(job_root) / "question_positioning/question_positioning.json"
        if pattern in {"P01", "P02"} and not (selected.get("recommendation_relationships") or selected.get("brand_positioning_use")) and qpath.is_file():
            lines.append("题目定位背景（用于选材）：\n" + _read(qpath))
        lines.append("独立文风例文：\n" + _natural_examples(wf, job_root, p0=False))
        lines.append("篇幅样本统计：\n" + _json(reference_length_budget(wf, job_root, p0=False)))
    else:
        lines.append("P0 选材围绕品牌自身，完整文风例文在第三遍成文时使用。")
    extra = wf.user_material_index(job_root, "p0" if p0 else "question")
    if extra:
        lines.append("可读取的补充材料索引：\n" + extra)
    frozen_name = "p0_blueprint_edit_outline.json" if p0 else "article_blueprint_edit_outline.json"
    frozen_text = _read(Path(job_root) / "inputs" / frozen_name)
    if current and frozen_text:
        frozen = json.loads(frozen_text)
        if frozen.get("edit_sha256") == hashlib.sha256(current.encode()).hexdigest():
            prior = frozen.get("revision_candidate") or {}
            if isinstance(prior, dict):
                lines.append("旧构思定位索引：\n" + _json({"previous_section_names": frozen.get("headings", []),
                                                           "previous_subjects": prior.get("candidate_order", [])}))
    fields = "kind=p0、positioning_placement、existing_p0_edit_plan" if p0 else "kind=article、question、pattern_id、candidate_order、brand_positioning_use、answer_use"
    lines.append("提交已有字段：" + fields + "、article_brief、opening、sections、materials、material_adjustments、estimated_length、ending、style_source、example_use、writing_material_markdown、writing_material_sources。")
    lines.append(EDITORIAL_BLUEPRINT_FIELDS)
    lines.append('单独调用 submit_result 一次提交完整 JSON；保存后只回复 {"submitted":true}。')
    return _natural_wrap_for(wf, job_root, "\n\n".join(lines))


def _natural_blueprint_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    state = wf.load_state(job_root)
    if requirements.editorial_mission(state):
        return _editorial_blueprint_prompt(wf, job_root, p0=p0)
    pattern = "P00" if p0 else state["selected_pattern_id"]
    decisions = state.get("decisions") or {}
    current = _text(decisions.get("blueprint_edits"))
    original = _text(decisions.get("response_brief"))
    lines = ["# 准备本篇写作要求与事实",
             "当前动作只整理写作要求、选材与构思。委托中的成稿、标题候选和 Word 导出由后续动作完成，不放入本轮事实素材。",
             "品牌：" + state.get("reference_pack", {}).get("brand", ""),
             "主体关系：" + NATURAL_PATTERN_GUIDANCE[pattern],
             "当前蓝图修改要求（覆盖冲突的原安排）：\n" + (current or "无新增修改"),
             "原始写作委托（只继承未被当前要求覆盖的内容）：\n" + (original or "按本题及已选内容范围安排"),
             "使用 list_materials 定位原件，再 read_material 或 extract_document 阅读实际需要的内容。按原件的日期和状态选材，写入足以展开重点的具体事实。已有原件不足以完成本题时，可使用现有 web_search、web_read 补充机构官网等公开原始资料，实际阅读后记录来源与日期，不把搜索摘要当成完整事实。缺少核心项目事实时明确指出所需材料，不靠相邻业务或解释地址、科目来补长度。"]
    if not p0:
        lines.append("正式问题：" + state["question"]["question_text"])
        refs = _natural_reference_sets(wf, job_root, p0=False)
        lines.append("原 AI 答案只帮助理解题目和已有内容，不提供已确认事实，也不是新闻品宣文风：\n\n"
                     + "\n\n".join("### " + row["title"] + "\n\n" + row["text"] for row in refs["content"]))
        if pattern in {"P01", "P02"}:
            selected = requirements.effective(wf, job_root, p0=p0)
            relationships = selected.get("recommendation_relationships") or selected.get("brand_positioning_use")
            qpath = Path(job_root) / "question_positioning/question_positioning.json"
            if relationships:
                lines.append("本篇选定的推荐关系（用于选材，不是需要照抄的段落）：\n" + _json(relationships))
            elif qpath.is_file():
                lines.append("已确认题目定位（研究背景，提炼其中与本题有关的推荐关系；不是文风例文或正文模板）：\n" + _read(qpath))
            lines.append("已确认的定位用于选材和推荐重点，不能因删除排序辩解而删掉推荐关系；按当前要求提炼分档含义，不复述旧分析的核查清单、分类纠正和排序解释。")
        lines.append("独立文风例文：\n" + _natural_examples(wf, job_root, p0=False))
        lines.append("篇幅样本统计：\n" + _json(reference_length_budget(wf, job_root, p0=False)))
    else:
        lines.append("P0 选材限品牌自身及实际业务关系，完整例文保留在第三遍；本阶段不借用例文事实。")
    lines.append("持续有效要求（当前意见只改冲突部分）：\n" + _json(requirements.effective(wf, job_root, p0=p0)))
    if state.get("metadata", {}).get("blueprint_material_input_mode") == requirements.BLUEPRINT_MATERIAL_INPUT_MODE:
        extra = wf.user_material_index(job_root, "p0" if p0 else "question")
        if extra:
            lines.append("补充材料来源索引（只列名称、读取路径和来源元数据，不是事实正文）：\n" + extra)
            lines.append("用索引中的精确路径调用 read_material；文档按需 extract_document。一个网页的正文、原始 HTML 和研究摘录可能同时保留，按当前主题读取相关正文即可，不重复阅读相同内容。补料中的研究意见用于选材，事实回到对应原件。")
    else:
        # The unmarked v13 input stays byte-for-byte reproducible for its
        # existing paid attempt, including interrupted action recovery.
        extra = getattr(wf, "user_material_text", lambda *x: "")(job_root, "p0" if p0 else "question")
        if extra:
            lines.append("补充材料（来源文字及历史操作按材料身份处理）：\n" + extra)
    frozen_name = "p0_blueprint_edit_outline.json" if p0 else "article_blueprint_edit_outline.json"
    frozen_text = _read(Path(job_root) / "inputs" / frozen_name)
    if current and frozen_text:
        frozen = json.loads(frozen_text)
        if frozen.get("edit_sha256") == hashlib.sha256(current.encode()).hexdigest():
            prior = frozen.get("revision_candidate") or {}
            if isinstance(prior, dict):
                # Old fact prose frequently contains superseded editorial
                # orders. Retain only coordinates for locating the requested
                # change; obtain factual material from actual sources again.
                locator = {"previous_section_names": frozen.get("headings", [])}
                if prior.get("candidate_order"):
                    locator["previous_subjects"] = prior["candidate_order"]
                lines.append("旧蓝图位置索引（仅用于辨认当前意见指的是哪里；对象与结构按当前要求重新确定）：\n" + _json(locator))
    fields = ("kind=p0、positioning_placement、existing_p0_edit_plan" if p0 else
              "kind=article、question、pattern_id、candidate_order、brand_positioning_use、answer_use")
    lines.append("提交已有蓝图字段：" + fields + "、article_brief、opening、sections（heading/task）、materials、material_adjustments、estimated_length、ending、style_source、example_use、writing_material_markdown、writing_material_sources。")
    lines.append("各字段分工：\n"
                 "article_brief：整合持续要求与本轮变更，保留正式问题、读者、体裁任务、对象范围、推荐关系、详略、篇幅及排版。明确区分分档标题独立加粗与机构名称段首行内加粗，正文紧接不换行。模型章节可以改，用户任务不能悄悄改。核心项目缺少事实支持时明确交代缺少什么材料，不能用相邻业务掩盖主题缺口。不混入标题生成任务。\n"
                 "writing_material_markdown：本篇可用事实，以具体主体、业务、动作和实际状态展开，保留与重点有关的细节及真正影响理解的条件。从原件中提取事实，不沿用原件的核查问答、证据说明或宣传限制写法；不写‘本篇如何表述’‘作者不能推定什么’或‘哪些说法不在已确认范围’等指令，不放候选标题。未知项目若确实与主题相关，准确列出具体未知状态；是否采用及怎样表达由作者按当前要求决定。没有来源支持的非必要主张直接不选，不把每个缺口写成事实段落。\n"
                 "material_adjustments：当前仍有效的编辑约束与事实取舍，用简短数组保存；写作命令只在这里，不重复到事实段落，不累积已完成的研究经过。\n"
                 "opening、sections、ending：只说明各部分内容任务与分工，保持可调整，不预写句子；不把排除事项改成提醒章节。\n"
                 "writing_material_sources：非空数组，每项包含实际读取的 source_ref 和本篇采用的 use，只关联上述选中事实的原件。原 AI 答案、篇幅样本、文风例文和用户写作要求不列为机构事实来源。brand_positioning_use、answer_use 只概括内容选择，不规定排序辩解或类别纠正入文。\n"
                 "example_use：只说明文风例文的选材、详略与推进怎样服务本篇，不照搬固定开头、转折、收尾或原 AI 答案。estimated_length：完整保留用户已指定的目标与统计口径，不自行退成上限；按主题准备足量的相关细节，不靠常识或否定说明补齐。")
    lines.append('单独调用 submit_result 一次提交完整 JSON；工具确认保存后只回复 {"submitted":true}。')
    return _natural_wrap_for(wf, job_root, "\n\n".join(lines))


def _natural_draft_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    return _natural_wrap_for(wf, job_root, "# 按本篇要求完成初稿\n\n" + _natural_context(wf, job_root, p0=p0)
                         + '\n\n只返回 JSON：article_markdown（完整正文）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。普通选材、组织和表达直接完成；只有必须改变用户明确事项或真实业务决定才请求原节点确认。')


def _natural_edit_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    base = edit_base_input(wf, job_root, p0=p0)
    from .natural_editor import character_count
    return _natural_wrap_for(wf, job_root, "# E8：编辑实际完整候选\n\n" + _natural_context(wf, job_root, p0=p0)
                         + "\n\n程序统计的基稿正文字符数：" + str(character_count(base["article_markdown"]))
                         + "\n\n唯一编辑基稿（本轮实际候选，不是句式范本）：\n" + base["article_markdown"]
                         + '\n\n只返回 JSON：edit_status（accepted/revised/requires_blueprint_reconfirmation）、article_markdown（完整正文）、editorial_notes（实际修改说明数组）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason。accepted 保持基稿全文一致且 editorial_notes=[]；revised 返回实际改好的完整正文。只有必须改变用户明确事项或真实业务决定才重确认，普通整段重写不需要确认。')


def _natural_style_prompt(wf: Any, job_root: Path) -> str:
    from . import brand_references
    from .editorial_contracts import style_base_input
    records = brand_references.job_examples(Path(__file__).resolve().parents[1], job_root, freeze=True)
    examples = "\n\n".join("### 文风例文：" + row["title"] + "\n\n" + row["text"] for row in records)
    return _natural_wrap_for(wf, job_root, "# P0 第三遍：整理全文表达\n\n" + _natural_context(wf, job_root, p0=True, include_references=False)
                         + "\n\n两篇完整原始例文（只参考选材、详略与行文）：\n" + examples
                         + "\n\n唯一编辑基稿：E8 全文\n" + style_base_input(wf, job_root)["article_markdown"]
                         + "\n\n直接输出完整 Markdown 正文，首行一个 H1；不输出 JSON、计划、编辑说明或例文对照。")


def _review_scope(wf: Any, job_root: Path, *, p0: bool) -> str:
    from .manuscript_revision import current_revision
    revision = current_revision(wf, job_root, p0=p0)
    mode = revision.get("editorial_review_scope_mode") if revision else None
    if mode == requirements.LEGACY_EDITORIAL_REVIEW_SCOPE_MODE:
        # Historical revisions and their paid retries retain the exact text.
        return ("\n\n本轮编辑阅读原则：事实修正针对正文实际作出的断言；未作出的能力主张不新增缺失说明。"
                "篇幅意见指向原件中尚未采用的具体信息。作者可以组织已知材料，说明业务特点与读者需求的关系；"
                "具体诊疗流程、手术能力和效果陈述须有直接材料支持。")
    if mode != requirements.EDITORIAL_REVIEW_SCOPE_MODE:
        return ""
    return ("\n\n本轮编辑阅读原则：按原句实际含义提出事实意见；有依据的一般技术解释、已知业务与读者需求的关系，"
            "不等同于该主体实际采用的临床流程。事实修改针对新增的具体操作、实施分工、个体适配或效果断言，"
            "指出其缺少依据之处，保留成立的说明；已交代的必要条件不重复追加。"
            "篇幅意见关注已经采用但尚未讲清的方法、业务关系与相关细节，也可指出尚未采用的事实。")


def _natural_review_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    candidate = prepare_finalize_input(wf, job_root, p0=p0)
    from .natural_editor import character_count
    return _natural_wrap_for(wf, job_root, "# 阅读完整候选并提供编辑意见\n\n" + _natural_context(wf, job_root, p0=p0, include_references=False, include_source_index=True)
                         + _review_scope(wf, job_root, p0=p0)
                         + "\n\n唯一待阅读的实际完整候选：\n" + candidate["candidate_markdown"]
                         + "\n\n程序统计的正文字符数：" + str(character_count(candidate["candidate_markdown"]))
                         + '\n\n只提供具体编辑意见，不改稿。单独调用 submit_result 一次，result 仅含 needs_revision（布尔值）与 comments（字符串数组）。没有实际问题时 needs_revision=false、comments=[]；需要修改时 needs_revision=true，每条 comments 简要说明位置、问题与处理方向，同类问题合并。不得返回 article_markdown、评分或审核报告。编辑意见之后至多由 DeepSeek 返工一次，直接输出。保存后只回复 {"submitted":true}。')


def prompt_repair(wf: Any, job_root: Path, *, p0: bool) -> str:
    """A distinct author action so E8's actual result remains immutable."""
    if not requirements.enabled(wf.load_state(job_root)):
        raise EditorialContractError("natural_editor_not_enabled", "本任务未启用一次编辑返工")
    from .natural_editor import validate_review, character_count
    prefix = "p0" if p0 else "article"
    review = validate_review(json.loads(_read(Path(job_root) / "production" / f"{prefix}_editorial_review.json")))
    if not review["needs_revision"]:
        raise EditorialContractError("editorial_revision_not_needed", "没有编辑意见，无须调用正文返工")
    candidate = prepare_finalize_input(wf, job_root, p0=p0)
    return _natural_wrap_for(wf, job_root, "# 按具体编辑意见完成一次正文返工\n\n" + _natural_context(wf, job_root, p0=p0, include_references=False)
                         + "\n\n程序统计的基稿正文字符数：" + str(character_count(candidate["candidate_markdown"]))
                         + "\n\nXTY 编辑意见（不是新事实，也不撤销篇幅与推荐任务）：\n" + _json(review["comments"])
                         + "\n\n唯一编辑基稿：XTY 阅读过的完整候选\n" + candidate["candidate_markdown"]
                         + '\n\n直接完成上述问题及全文同类问题，保留准确自然的内容；只返回一个 JSON 对象 {"article_markdown":"完整最终正文"}。不输出计划、原因报告或新的待审稿标记。')


def _natural_final_body(wf: Any, job_root: Path, *, p0: bool,
                        final_markdown: str | None = None, title_revision: bool = False) -> tuple[str, dict[str, Any] | None]:
    from .manuscript_revision import current_title_revision
    revision = current_title_revision(wf, job_root, p0=p0)
    if title_revision and revision:
        final_markdown = revision["base_markdown"]
    if final_markdown is None:
        prefix = "p0" if p0 else "article"
        final = json.loads(_read(Path(job_root) / "production" / f"{prefix}_finalized.json") or "{}")
        if final.get("outcome") not in {"accepted", "revised"}:
            raise EditorialContractError("final_article_missing", "标题需要实际选定的最终正文")
        final_markdown = final.get("article_markdown")
    if not isinstance(final_markdown, str) or not final_markdown.strip():
        raise EditorialContractError("final_article_missing", "标题需要实际选定的完整正文")
    body = re.sub(r"(?m)^#[ \t]+[^\r\n]*(?:\r\n|\n|\r|$)", "", final_markdown, count=1)
    if not body.strip():
        raise EditorialContractError("final_article_missing", "标题需要完整正文，不能只有主标题")
    return body, revision


def _natural_title_commission(wf: Any, job_root: Path, *, p0: bool,
                              revision: dict[str, Any] | None) -> str:
    # A saved title revision takes precedence over newer defaults. Missing mode
    # means the exact legacy request, including its old manuscript-edit input.
    state = wf.load_state(job_root)
    source = revision if revision is not None else state.get("metadata", {})
    if source.get("title_input_mode") != requirements.TITLE_INPUT_MODE:
        return _natural_commission(wf, job_root, p0=p0)
    brief = (revision.get("effective_writing_requirements") if revision else None)
    if brief is None:
        brief = requirements.effective(wf, job_root, p0=p0)
    return "当前写作要求：\n" + _json(brief)


def _natural_titles_prompt(wf: Any, job_root: Path, *, p0: bool, final_markdown: str | None = None) -> str:
    body, revision = _natural_final_body(wf, job_root, p0=p0, final_markdown=final_markdown, title_revision=True)
    request = "\n\n本轮标题修改要求：\n" + revision["edits_markdown"] if revision else ""
    return _natural_wrap_for(wf, job_root, "# 为这篇最终正文拟定 20 个独立发布标题\n\n"
                         + _natural_title_commission(wf, job_root, p0=p0, revision=revision)
                         + "\n\n实际最终正文（仅去掉内部旧 H1，正文原样保留）：\n" + body + request
                         + '\n\n标题继承本篇当前体裁与全文重心，每项都是同一篇文章可独立使用的主标题。P01 保留针对正式问题的单主体推荐，P02 保留分档多主体推荐，不一律改成机构概览或信息梳理。新闻品宣专题不改成排名、核查、口径或面诊攻略；解释、比较、事件文章则保持自己的任务。标题不引入正文没有的能力、项目、价格、效果或优势，不将某一小段包装为全文主题。可以呈现不同阅读入口，保持完整名称和事实必要条件；无法简洁保留条件时换一个有据的角度。\n\n只返回 JSON：candidates 为 20 项数组，每项包含 title（单行完整标题）与 angle（简短角度）；canonical_title_id 按数组位置 title_01 至 title_20，推荐最契合全文的一项。20 项全部是这篇完整文章互相可替换的主标题。多主体文章不能按每一档、每个机构或某个项目分别出题再凑成20项；也不能把文中必要的状态限定变成核查提醒、研究信息或项目边界专题。围绕少数真正覆盖全文的角度拟不同表达。20 项供用户自行选择，不回填正文，不输出评分、改稿建议、分组或副标题。')


def _natural_title_review_prompt(wf: Any, job_root: Path, *, p0: bool,
                                 final_markdown: str | None = None,
                                 title_result: dict | None = None) -> str:
    body, revision = _natural_final_body(wf, job_root, p0=p0, final_markdown=final_markdown)
    prefix = "p0" if p0 else "article"
    if title_result is None:
        title_result = json.loads(_read(Path(job_root) / "production" / f"{prefix}_titles.json") or "{}")
    from .title_publication import validate_title_map
    validate_title_map(title_result, p0=p0)
    request = "\n\n本轮标题修改要求：\n" + revision["edits_markdown"] if revision else ""
    return _natural_wrap_for(wf, job_root, "# 编辑这篇文章的 20 个发布标题\n\n"
                         + _natural_title_commission(wf, job_root, p0=p0, revision=revision)
                         + "\n\n实际最终正文（只去掉内部旧 H1）：\n" + body
                         + "\n\n待编辑的完整标题候选：\n" + _json(title_result) + request
                         + '\n\n逐条把每个候选放在完整正文前阅读，均应让全文内容自然成立；只对应某一档、某个机构、单个项目或必要提醒的，直接重拟为覆盖全文的标题，不保留局部专题名。各标题必须对应全文主体、重点与本篇体裁。新闻品宣标题不变成核查、排序辩解或问诊攻略；其他类型保持自身任务。若整组体裁错位可重新拟整组。只编辑标题，不改正文。\n\n单独调用 submit_result，结果为 outcome（accepted/revised/incomplete）、candidates（20 项 title 与 angle）、canonical_title_id、title_notes、reason。accepted 保持原候选与推荐，title_notes=[]；revised 返回实际改过的完整 20 项与简短修改说明。成功时 reason 为空；无法完成时 incomplete、candidates=[]、canonical_title_id=""、title_notes=[] 并说明 reason。不得返回 article_markdown。工具保存后只回复 {"submitted":true}。')
