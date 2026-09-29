"""A compact single-subject commission; old requests keep their original route."""
from __future__ import annotations

import json
from pathlib import Path

from . import writing_requirements as requirements
from .editorial_contracts import edit_base_input, prepare_finalize_input, EditorialContractError

CONTRACT = "frontmind-single-subject/2"
MARKER = '<frontmind_single_subject version="2" />'
DEFAULT_CONTRACT = "frontmind-single-subject/3"
CURRENT_MARKER = '<frontmind_single_subject version="3" />'
MISSION = (
    "这是一篇围绕本题需求的单主体推荐文章。让普通读者通过连贯、具体的介绍认识对象，理解它与需求的关系。"
    "根据内容选择有展开价值的主线，写出各部分的主次与承接；代表业务融入叙述，其他内容可以概括。"
    "文章可以从需求背景、业务特点、产品或服务理念、使用情境及空间服务等角度展开，角度由本题和材料决定。"
    "合理的日常情境和普通用途说明本身就是文章内容，不必逐句写成资料结论；对象的实际业务与做法仍依据给定材料，不虚构经历、案例或流程。"
    "按当前委托完成整篇文章的展开程度，段落长短随内容安排，不把长篇写成信息摘要。"
)
ROLES = {
    "blueprint": "你是本篇策划编辑。理解题目和写作委托，从已有材料选择能写成文章的内容，保留相关原文的完整段落或信息组，形成简明的选材摘编与构思。选择有内容的推荐主线，说明每部分讲什么、如何承接，数量与目录由内容决定；资料列表供选材，不是正文覆盖清单。",
    "draft": "你是中文新闻品宣作者。根据当前委托、选用材料与完整例文写成一篇值得连续阅读的文章。围绕读者需求组织对象介绍，把特点写具体，把正常背景与情境写自然。你可以调整蓝图的段落、顺序与详略，完成当前篇幅。",
    "edit": "你是全文编辑。先把完整基稿当作一篇文章阅读，改善重心、段落推进、节奏与表达。保留有阅读价值的需求铺垫、正常解释和生活使用情境；真正重复的内容合并，偏离重点的部分调整。需要时可以重组全文，按当前委托完成充分而自然的稿件，不默认压缩成信息摘要。",
    "finalize": "你是读者视角的文字编辑。只判断完整稿的导语、结构、详略、衔接和表达是否值得连续阅读。正常需求铺垫、合理情境与有作用的解释可以保留，不因它们不是项目事实就删掉。只对实际影响阅读的主要问题给少量具体意见，说明怎样改善完整文章，保持当前篇幅；不布置逐段缩写或逐项覆盖。你不判断事实、来源或资料缺口，不回读来源，不改写正文。没有主要阅读问题就给空意见。",
    "repair": "你是最后负责成文的作者。结合完整基稿、当前委托和文字意见，完成一篇自然、充分展开的修订稿。意见服务整篇文章，可以通过重新组织全文或改写段落落实；保持有用的背景、需求与场景。篇幅不足时重新安排主线并写充分，不把任务缩成给现有项目表逐名补释义。提交完整最终正文。",
}
BLUEPRINT_DESCRIPTIONS = {
    "article_brief": "本篇当前委托：读者、题目、体裁、主体、重点、篇幅及排版。",
    "materials": "蓝图页面的一句选材概述，作者不读取此字段。",
    "writing_material_markdown": "作者接收的选材摘编全文。按推荐主线保留相关原文的完整段落或信息组，包括对象定位、业务特点、服务理念、具体设置与实际活动等可展开内容；不二次压缩成名词清单，也不把选材摘编预写成文章。列表只选择代表内容，其他业务可概括。",
    "material_adjustments": "确有必要的后台选材说明，没有则为空数组。",
    "estimated_length": "沿用当前明确篇幅及统计口径，短例文不改变用户篇幅。",
    "writing_material_sources": "已选资料的source_ref与use。",
    "opening": "导语如何自然进入主题，建立需求背景并引出对象。",
    "sections": "按内容设计有主次、能承接的推荐主线，数量和目录不固定。写清各部分的独立内容及大致展开程度，不按项目表逐类分配字数。",
    "ending": "在最后一项内容介绍完成处怎样自然结束。",
    "example_use": "指出例文怎样组织需求、特点与场景，并说明本篇可借鉴的叙述方式，不复制其目录或行业内容。",
}
SECTION_TASK = "本部分要讲清什么、用哪些有内容的信息展开、怎样承接前后文。项目是段落中的代表内容，不逐项释义；需求背景、对象特点、服务理念和使用情境可以成为独立的叙述内容。"

MISSION_V3 = (
    "体裁和重点以article_brief为准。介绍型新闻品宣面向外部读者，直接写对象的业务、特点、具体做法与服务，推荐通过有重点的介绍呈现。"
    "需求背景和合理生活使用场景用于引出对象、说明业务用途与服务特点，叙述始终回到对象本身，不转成教读者选择、核验或安排咨询的步骤，也不讨论作者的宣传边界。"
    "按内容选择有展开价值的主线，代表业务融入自然段，其他内容可以概括；每部分讲清独立内容并承接前后文。"
    "保留原始资料中有内容的对象描述，正常情境可以展开，实际业务与做法仍依据材料，不虚构经历、案例或流程。"
    "按当前篇幅完成充分、连贯的文章，段落长短随内容安排。"
)
ROLES_V3 = {
    "blueprint": "你是本篇策划编辑。按当前体裁从原始材料提取对象描述，保留相关段落的完整信息组，选择有内容的推荐主线。资料的目录安排、照片呈现说明与面向读者的咨询话术属于原材料的表达方式，不成为本文构思；转为对象本身的业务、特点、做法与服务信息。保留可展开的理念、情境和具体细节，不压成项目名清单。",
    "draft": "你是中文新闻品宣作者。按当前委托写成直接介绍对象的完整文章。需求与生活场景自然引出对象，随后展开业务特点、具体做法、理念与服务；以详略和内容体现推荐。你可以调整蓝图的段落和顺序，让全文自然推进，并完成当前篇幅。",
    "edit": "你是负责成稿的文字编辑。按article_brief通读完整稿，改善重点、承接、节奏与表达，保留有作用的铺垫、场景和正常解释。介绍型稿件应直接写对象；若某部分变成读者选择、核验、咨询指导或作者宣传边界说明，就把它改回对对象业务与服务的介绍。需要时重组全文，完成当前篇幅，不默认压缩成摘要。",
    "finalize": "你是负责成稿的文字编辑。按article_brief判断完整稿的导语、结构、详略、承接和表达。介绍型新闻品宣应直接写对象业务、特点、做法与服务；需求与场景可以保留，但若叙述转为读者选择、核验、咨询指导或作者宣传边界说明，指出如何改回对象介绍。只给实际影响阅读的少量文字意见，保持当前篇幅；不做事实检查，不判断来源或资料缺口，不回读来源，不改写正文。没有主要阅读问题就给空意见。",
    "repair": "你是最后负责成文的作者。以当前体裁和完整基稿为基础落实文字意见，完成直接介绍对象、自然推进的全文。保留有用的需求铺垫、场景和细节；把偏向读者选择、核验、咨询指导或作者宣传边界说明的部分改回对象业务与服务。可以重组全文或改写段落，把主线写充分，不给项目表逐名补释义。按当前篇幅提交完整最终正文。",
}
BLUEPRINT_DESCRIPTIONS_V3 = {**BLUEPRINT_DESCRIPTIONS,
    "article_brief": "本篇当前委托：读者、题目、体裁、主体、介绍重点、篇幅及排版。介绍型新闻品宣直接介绍对象，由具体内容体现推荐。",
    "writing_material_markdown": "作者接收的选材摘编全文。按主题保留原始资料中的完整对象描述与信息组，包括业务、特点、理念、具体做法、实际活动与服务。保留可展开的情境和细节，不压成名词表；资料目录、照片呈现说明、咨询话术和研究旁白不沿用为本文叙述。",
    "opening": "导语如何以需求或合理生活使用场景自然引出对象，随后进入对对象的介绍。",
    "sections": "按当前体裁设计有主次和承接的内容主线，直接介绍对象业务、特点、做法与服务；不把正文组织为读者如何选择、核验或咨询的步骤。数量与目录由内容决定。",
}
SECTION_TASK_V3 = "本部分介绍对象的什么内容、有哪些完整信息组与具体细节、怎样承接前后文。需求或情境服务对象介绍，代表项目嵌入叙述，不逐项释义。"


def enabled(state, *, p0=False):
    return (not p0 and state.get("selected_pattern_id") == "P01"
            and state.get("metadata", {}).get("single_subject_writing_contract") in {CONTRACT, DEFAULT_CONTRACT})


def matches(prompt):
    from .writing_context_v14 import matches as current_matches
    return current_matches(prompt) and bool({MARKER, CURRENT_MARKER} & set(prompt.splitlines()[1:5]))


def current_request(prompt):
    return matches(prompt) and CURRENT_MARKER in prompt.splitlines()[1:5]


def blueprint_descriptions(prompt):
    return BLUEPRINT_DESCRIPTIONS_V3 if current_request(prompt) else BLUEPRINT_DESCRIPTIONS


def section_task(prompt):
    return SECTION_TASK_V3 if current_request(prompt) else SECTION_TASK


def system(action, prompt=""):
    stage = action.rsplit("_", 1)[-1]
    roles = ROLES_V3 if current_request(prompt) else ROLES
    mission = MISSION_V3 if current_request(prompt) else MISSION
    if stage not in roles:
        raise ValueError("P01 v2 only handles blueprint and body stages")
    protocol = ('使用本动作已有工具，最后单独submit_result；保存后只回复 {"submitted":true}。'
                if stage in {"blueprint", "finalize"} else
                "需要的内容已完整提供。最终只返回本动作原有JSON及完整正文，不加代码围栏。")
    # XTY receives a prose-reading role, without the writer's source-use mission.
    return "\n\n".join([roles[stage], *([] if stage == "finalize" else [mission]), protocol])


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def commission(wf, job):
    from .manuscript_revision import current_revision
    brief = requirements.effective(wf, job, p0=False)
    lines = ["当前写作委托：\n" + _json(brief),
             "正文字符统计包含小标题、标点、数字与英文，排除主标题、候选标题、空白及Markdown标记。首行保留一个#内部标题，段落与加粗按当前委托。"]
    revision = current_revision(wf, job, p0=False)
    if revision:
        lines.append("本轮修改意见（其余委托持续有效）：\n" + revision["edits_markdown"])
    return "<current_commission>\n" + "\n\n".join(lines) + "\n</current_commission>"


def references(wf, job, *, stage):
    from .writing_context import _blueprint
    from .writing_context_v14 import examples
    from .writing_materials import selected
    from .manuscript_revision import current_revision
    lines = []
    if stage != "finalize":
        blueprint = _blueprint(job, p0=False)
        material = selected(current_revision(wf, job, p0=False), blueprint)
        lines.append("选用内容全文：\n" + material["writing_material_markdown"])
        if stage == "draft":
            lines.append("可调整的文章构思：\n" + _json({k: blueprint[k] for k in ("opening", "sections", "ending") if k in blueprint}))
    lines.append(examples(wf, job, p0=False, stage=stage))
    return "<reference_data>\n" + "\n\n".join(lines) + "\n</reference_data>"


def prompt(wf, job, *, stage):
    from .writing_context_v14 import wrap, wrap_body, examples, delivery_length, reference_length_budget
    from .natural_editor import validate_review
    version3 = wf.load_state(job).get("metadata", {}).get("single_subject_writing_contract") == DEFAULT_CONTRACT
    body = ""
    if stage == "blueprint":
        state = wf.load_state(job)
        lines = ["# 本篇选材与构思", "品牌：" + state.get("reference_pack", {}).get("brand", ""),
                 ("通过list_materials定位已有资料，按需read_material或extract_document选读；完整理解文风例文。选材摘编保留原始资料中完整的对象描述与信息组，将资料的咨询、展示或研究姿态转换为本篇对象介绍所需的内容。" if version3 else
                  "通过list_materials定位已有资料，按需read_material或extract_document选读；完整理解文风例文。选材摘编保留相关原文的完整信息组，供作者自由组织文章。"),
                 examples(wf, job, p0=False, stage=stage),
                 "篇幅样本用途与统计：\n" + _json(reference_length_budget(wf, job, p0=False))]
        if state.get("metadata", {}).get("blueprint_material_roots"):
            lines.append("本篇指定资料目录：\n" + _json(state["metadata"]["blueprint_material_roots"]))
        index = wf.user_material_index(job, "question")
        if index:
            lines.append("已有资料索引：\n" + index)
        edits = state.get("decisions", {}).get("blueprint_edits")
        if edits:
            lines.append("本轮构思意见：\n" + str(edits))
        if not requirements.effective(wf, job, p0=False).get("brand_positioning_use"):
            positioning = Path(job) / "question_positioning/question_positioning.json"
            if positioning.is_file():
                lines.append("已确认题目定位：\n" + _json(json.loads(positioning.read_text(encoding="utf-8"))))
        lines += [commission(wf, job),
                  "通过submit_result提交现有蓝图字段：kind=article、question、pattern_id=P01、article_brief、opening、sections、materials、material_adjustments、estimated_length、ending、style_source、example_use、writing_material_markdown、writing_material_sources、candidate_order、brand_positioning_use、answer_use。保存后只回复{\"submitted\":true}。"]
    else:
        labels = {"draft": "写成完整文章", "edit": "编辑完整基稿", "finalize": "阅读完整稿并提出必要文字意见", "repair": "完成最终修订稿"}
        lines = ["# " + labels[stage]]
        if stage == "edit":
            body = edit_base_input(wf, job, p0=False)["article_markdown"]
        elif stage in {"finalize", "repair"}:
            body = prepare_finalize_input(wf, job, p0=False)["candidate_markdown"]
        if body:
            lines.append("当前完整稿：\n" + body + delivery_length(wf, job, p0=False, body=body))
        if stage == "repair":
            review = validate_review(wf.read_json(Path(job) / "production/article_editorial_review.json"))
            if not review["needs_revision"]:
                raise EditorialContractError("editorial_revision_not_needed", "没有文字意见，无須返工")
            lines.append("本轮文字意见：\n" + _json(review["comments"]))
        lines += [references(wf, job, stage=stage), commission(wf, job)]
        formats = {
            "draft": '返回JSON：article_markdown（完整正文）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。',
            "edit": '返回JSON：edit_status（accepted/revised/requires_blueprint_reconfirmation）、article_markdown（完整正文）、editorial_notes（修改说明数组）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。accepted保持基稿一致且说明为空；实际改稿用revised。',
            "finalize": '单独submit_result，result仅含needs_revision（布尔值）与comments（字符串数组）。没有主要阅读问题用false与[]；需要修改时给少量具体意见。随后由同一成文链的DeepSeek至多返工一次。',
            "repair": '只返回{"article_markdown":"完整最终正文"}。',
        }
        lines.append(formats[stage])
    text = (CURRENT_MARKER if version3 else MARKER) + "\n" + "\n\n".join(lines)
    return wrap_body(wf, job, text, p0=False) if stage in {"draft", "edit", "repair"} else wrap(text)
