"""Natural prose commissions with a final, local copy edit.

Only new P01/P02 jobs opt in. Frozen v14 and other patterns keep their builders.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import writing_requirements as requirements
from .editorial_contracts import edit_base_input, prepare_finalize_input
from .writing_context import _blueprint

CONTRACT = "frontmind-natural-prose/15"
MARKER = '<frontmind_natural_prose version="15">'

PROSE = """面向普通读者介绍对象做什么、有什么具体特点、提供怎样的服务。可以自然说明需求、用途和使用感受；第三人称不等于取消读者关系。
重要内容写充分，次要内容带过，让具体内容推动段落。一个特点讲清楚后就向前推进，不必再说明它体现了什么、构成了什么，也不必在每段末尾归纳意义。段落长短由内容决定。
原始资料中的项目列表用于选择代表内容，不是正文的覆盖清单。普通解释应帮助理解具体内容，不把并列项目强行串成一套相互协同的业务机制。不虚构经历、案例或对象的具体做法。
自然展开可以交代人们为什么在意这个特点，以及具体设置带来的日常感受，不必把每句话都写成项目名和功能的配对。一般生活情境可以写；没有采访和案例时，不把情境写成这家机构真实接待过的某类人或真实发生的故事。
写作前按本阶段篇幅安排足够的独立内容，再把每个段落写完整。最终交付在委托范围内即可，不必凑到目标的精确字数；初稿按初稿阶段的篇幅安排。测字后若相差较多，重新分配全文，展开尚未使用的内容，重写相关完整段落；不要保留短稿逐句寻找可以添加的解释。"""

STYLE_EXAMPLES = """以下小例子只说明句段怎样写，不能将其事实搬进本文，也不固定句式。
材料：书店有临街展示架、靠窗座位和儿童阅读区。平日晚上九点闭店。
自然写法：临街的展示架摆着当月新书，靠窗留出了阅读座位。带孩子来的读者可以去儿童阅读区；书店平日营业到晚上九点。
说明：具体设置及读者用途可以直接写，不需要再补“这些安排共同构成完整的阅读服务体系”。
材料：一家社区图书馆开放至晚上九点；成人阅览区有独立阅读灯和插座；儿童区设低书架、软垫座位；每周末有亲子共读活动；入口有自助还书机；另有地方文献、报刊、工具书等分类。
自然写法：下班后想找个地方安静读书，不必总把时间留到周末。这家社区图书馆将开放时间延长到晚上九点，成人阅览区的座位配有独立阅读灯和插座，读到一半的书可以继续读，带来的电脑也有地方放。对习惯在晚间学习的人来说，一处方便停留的座位，比匆匆借走一本书更贴近日常需要。
儿童区则留出了另一种阅读节奏。低书架方便孩子自己挑书，选好后可以坐在软垫上翻看；周末的亲子共读活动，让大人也能参与其中。阅读之外，自助还书机设在入口，归还图书的人进门就能办理，不需要走到阅览区。
说明：第一段围绕晚间阅读展开，第二段转向儿童与家庭；每项设置在具体情境中发挥作用。没有把全部馆藏分类逐一释义，也不替馆方虚构到访人数、活动效果或实际读者故事。这是段落展开的示范，不要求本文使用这些场景、句式或段落顺序。"""

ROLES = {
    "blueprint": "你是选材编辑。先读当前article_brief，确定全文要介绍的对象与范围。正式题目提供读者进入文章的需求，不自动决定全文主次。把有限的入口信息简短交代，从材料中选择能各自展开的业务特点、具体设置、实际工作和服务内容，以足够多的独立信息完成委托篇幅。丰富的内容多写，薄的少写，同一特点只安排一次。最后再决定章节；不把入口扩成常识长文，也不把全部项目名平均分配成目录。",
    "draft": "你是中文新闻品宣作者。按当前article_brief介绍对象，题目提供进入文章的入口。先用简洁导语引出对象，随后把篇幅用在选定的独立内容上。用原始信息组中的具体描述把业务、设置、实际工作和服务写充分，不把短项目表逐名扩成定义。蓝图供安排主次，作者可以调整详略。此阶段生成可供编辑取舍的完整初稿，按交付篇幅上限再增加约一成来安排内容，不在初稿阶段主动压到交付范围。多出的内容来自尚未写入的原始描述，不来自重复解释。先把文章写完整，再用count_article了解实际长度。",
    "edit": "你是E8全文编辑，负责把初稿编辑成可以连续阅读的新闻品宣稿。先按当前article_brief重新判断主次，再编辑段落；题目是进入文章的入口，选材摘编中的旧写作安排可以调整。初稿留有取舍余地，本轮以合并、删繁、保留具体内容完成文章。先合并跨段重复的同一需求、评估、规范与服务说明，再整理各业务段内部。项目名称后再把名称拆成定义，前面列了设置后又说明这里有这种设置，都应删去，不换一种解释补回。正常用途、使用情境和有内容的好句保留。需要重分内容时直接重组对应段落，不仅修饰措辞。最后再校准交付篇幅，范围内即可；确实不足时恢复误删的有用信息或写入选材中尚未使用的完整内容，不把测量后的差额分摊给现有句子。",
    "repair": "你是负责正文的作者。以完整基稿和本轮结构意见为依据，修正需要重新分配的内容与段落，保留未受影响的好句。把具体内容讲清楚，不用新的意义总结替换旧的意义总结。提交完整稿，随后还有最后一次句子级编辑。",
    "finalize": "你是最后的文字编辑。阅读实际准备交付的全文。普通病句、重复尾句、搭配不顺和累赘连接直接做少量局部修改；成立的表达保持原样。只有需要重新分配内容或重组多个段落时才交给正文作者。不要为了显得正式而增加概括，也不要因为审阅了就必须修改。你只处理文字和阅读效果，不回查资料、不评价证据、不改变已确认的业务安排。",
    "polish": "你是最后的文字编辑。当前是作者返工后的完整稿，不能沿用对返工前稿件的判断。通读后处理少量病句、赘句或搭配，成立的表达保持原样。不改主题、内容主次和结构，不补新的项目或解释。仍需大幅结构调整就如实返回needs_revision=true，不能靠局部修改宣告完成。只判断文字阅读效果，不做事实审计。",
}

BLUEPRINT_FIELDS_DESCRIPTIONS = {
    "article_brief": "本篇当前委托，保留读者、体裁、主体、重点、篇幅和排版。",
    "materials": "供蓝图页面显示的简短选材概述。",
    "writing_material_markdown": "这是一份已经完成取舍的作者材料。选中主要业务后，把该信息组的原文完整保留，以原文短段为主，不再改写成一句摘要：保留它具体做什么、怎样开展、有关场景、方法与服务细节。多个来源描述同一项内容时，优先保留有具体描述的信息组，不能拿项目表的短名称替代完整介绍。未选项目和重复别名直接不收入此字段，不能把整个项目表复制后让作者自行删减。只有名称的业务，仅保留足以说明范围的代表例子；有具体描述的内容才作为展开材料。这里只写对象信息，详略安排放sections.task；不预写连接句、总结句、机构优势论证或资料完整度评价。",
    "opening": "用什么具体需求自然引出对象；不要在导语预列全文所有业务。",
    "sections": "按阅读顺序安排各部分独立内容与详略，同一特点只集中写一次。",
    "ending": "最后一项具体内容在哪里结束，不默认复述全文。",
    "estimated_length": "保持当前委托篇幅及统计口径，参考例文不覆盖用户目标。",
    "material_adjustments": "必要的后台说明，不进入作者正文材料。",
    "writing_material_sources": "已选材料的source_ref及用途。",
    "example_use": "说明例文的内容展开与节奏中哪些适用于本篇，不沿用整套章节或概括句。",
}
SECTION_TASK = "先写这一部分要让读者认识到的具体特点，再说明用哪组材料写充分、哪些简述。业务分类本身不等于段落中心；只有项目名称时不能安排长篇展开。不要列为必须全部写入的项目清单，也不要再次介绍前文讲清的特点。"

FINAL_READING = """先把全文作为面向普通读者的新闻品宣稿阅读，再决定是局部改字还是交回作者。
句级校对先看句子是否真正说通：主语与动作、动词与宾语是否搭配，介词和修饰成分是否接完整，同一个谓语或总称是否适用于每一个并列项。例如“讲座、咨询和自助终端等设备”把服务、活动和设备误归为同一类，应改清关系。原材料拼接的长句尤其要读清修饰关系，不能只改显眼的重复词而放过搭配不成立的句子。少量这类问题直接修通，保留原有的具体信息。只改病句、歧义和真实重复；原来只是普通完整句就保留，不能把省几个字当作编辑任务。
内容组织问题不只是章节顺序错误，也包括多段内部没有主次：如果正文主要在罗列项目再逐名释义、转述资料如何列项，或反复邀请读者咨询，句子即使通顺，也需要作者重新组织这些段落。此时返回具体结构意见，不用几处同义词替换宣告通过。
应直接介绍对象的业务、具体特点、实际工作和服务。看每段是否增加一种新的认识；正常用途和感受可以保留，已经讲清的需求或解释不再重复。结构意见指出实际哪组内容需要取舍或展开，不要求作者增加抽象总结，也不把重写要求变成项目覆盖清单。
同段或相邻段先列业务、再列症状、再列适用人群时，要看是否提供了新信息；如果只用不同称呼重列同一批内容，应合并，而不是保留三份改几个词。多处出现这种情况时交给作者集中处理，正常的一次用途说明仍保留。
把给读者的介绍和给作者的工作说明分清：说明某段篇幅较短、某项目在资料中排得靠前、资料信息是否完整的文字，不属于机构介绍，应在句级编辑中直接清理。正常项目列举可以保留，不因出现列表就要求返工；也不应把普通的需求与用途都当成重复。已经成立的段落只有一两句同义复述时，直接删改这些句子即可。
只有主次和段落推进已经成立，剩余少量病句或赘句才用local_edits完成。不要因为少量改字权限而忽略全文仍需重新组织。"""


def enabled(state, *, p0=False):
    return (not p0 and state.get("selected_pattern_id") in {"P01", "P02"}
            and state.get("metadata", {}).get("natural_prose_contract") == CONTRACT)


def matches(prompt):
    return isinstance(prompt, str) and prompt.startswith(MARKER + "\n")


def wrap(text, *, writer=False):
    from .writer_measure import MARKER as COUNT_MARKER
    return MARKER + "\n" + ((COUNT_MARKER + "\n") if writer else "") + text


def system(action, prompt=""):
    stage = action.rsplit("_", 1)[-1]
    if stage in {"titles", "review"}:
        from .writing_context_v14 import system as legacy_system
        return legacy_system(action, "")
    protocol = ('最后单独调用submit_result提交结果，成功后只回复{"submitted":true}。'
                if stage in {"blueprint", "finalize", "polish"}
                else "只返回当前动作要求的JSON对象和完整正文，不加代码围栏。")
    parts = [ROLES[stage]]
    if stage not in {"finalize", "polish"}:
        parts += [PROSE]
    if stage in {"draft", "edit", "repair"}:
        parts += ["提交前调用count_article统计完整稿。依据全文实际内容调整篇幅，范围内不必补齐目标数字；不在正文写测字说明。"]
    return "\n\n".join(parts + [protocol])


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def commission(wf, job, *, editor=False):
    from .manuscript_revision import current_revision
    brief = dict(requirements.effective(wf, job, p0=False))
    if editor:
        brief.pop("reference_roles", None)
        brief.pop("brand_positioning_use", None)
    lines = ["<current_commission>", _json(brief),
             "第三人称介绍可以说明正常需求、用途和读者感受。只有把全文组织成选择、核验或咨询步骤才偏离本篇体裁。",
             "字符数包含正文小标题、标点、数字与英文，排除主标题、空白及Markdown标记。内部首行保留一个H1，发布时主标题独立交付。"]
    revision = current_revision(wf, job, p0=False)
    if revision:
        lines.append("本轮正文修改要求：\n" + revision["edits_markdown"])
    return "\n\n".join(lines + ["</current_commission>"])


def length_note(body):
    from .natural_editor import character_count
    return "程序统计的当前正文字符数：" + str(character_count(body)) + "。篇幅范围见当前委托；删去赘述不必等量补回。"


def references(wf, job, *, outline=False):
    from .writing_materials import selected
    from .manuscript_revision import current_revision
    from .writing_context_v14 import examples
    bp = _blueprint(job, p0=False)
    material = selected(current_revision(wf, job, p0=False), bp)
    parts = ["选用的原始内容：\n" + material["writing_material_markdown"]]
    if outline:
        parts.append("可调整的内容安排（heading是编辑规划标签，成稿小标题按实际内容另拟）：\n" + _json({k: bp[k] for k in ("opening", "sections", "ending") if k in bp}))
    parts += [examples(wf, job, p0=False, stage="draft"), STYLE_EXAMPLES]
    return "<reference_data>\n" + "\n\n".join(parts) + "\n</reference_data>"


def prompt_blueprint(wf, job, *, p0=False):
    from .writing_context_v14 import examples
    state = wf.load_state(job)
    parts = ["# 选材与文章安排", "品牌：" + state.get("reference_pack", {}).get("brand", ""),
             "使用list_materials定位原始机构、业务、产品及服务资料，以read_material或extract_document读取相关内容。已确认文风例文完整理解；内容背景与篇幅样本只按各自用途使用。原有文章、旧蓝图和历次编辑意见不作为新稿材料。",
             "先形成有主次的内容选择，再安排文章。全文介绍范围由当前article_brief决定，题目中的具体需求可以只用于导语和对应业务。为主要内容保留完整描述与细节，也选择对象实际在做的工作、具体服务安排。取舍必须落实在writing_material_markdown：删除未选项目、重复别名和同一业务在不同表中的重复条目，不向作者交付全量目录。只有名称不等于信息丰富，不能因为某类项目多就安排长篇释义。先想清每部分要表达的具体特点，再挑少量代表内容；资料分类不能直接成为文章栏目。选材应支撑当前篇幅，允许用一般需求与使用情境把特点讲充分。多主体稿保留每个主体，但不要求每个主体覆盖相同项目或采用相同段落。",
             "蓝图字段说明：\n" + _json(BLUEPRINT_FIELDS_DESCRIPTIONS),
             "sections中task的用途：" + SECTION_TASK,
             examples(wf, job, p0=False, stage="blueprint"), STYLE_EXAMPLES]
    roots = state.get("metadata", {}).get("blueprint_material_roots")
    if roots:
        parts.append("本次选用的原始材料目录：\n" + _json(roots))
    index = wf.user_material_index(job, "question")
    if index:
        parts.append("已有材料索引：\n" + index)
    if state.get("decisions", {}).get("blueprint_edits"):
        parts.append("本轮构思要求：\n" + str(state["decisions"]["blueprint_edits"]))
    parts += [commission(wf, job),
              "通过submit_result提交原有蓝图字段：kind=article、question、pattern_id、article_brief、candidate_order、brand_positioning_use、answer_use、opening、sections、ending、materials、material_adjustments、estimated_length、style_source、example_use、writing_material_markdown、writing_material_sources。"]
    return wrap("\n\n".join(parts))


def prompt_article(wf, job, *, p0=False):
    return wrap("# 写成完整文章\n\n" + references(wf, job, outline=True) + "\n\n" + commission(wf, job)
                + "\n\n阶段篇幅：当前委托中的范围是最终交付范围。本次初稿按交付篇幅上限再增加约一成来安排完整内容，供E8取舍；不要在初稿阶段主动压到交付范围。这里的余量来自选中原文里的业务做法和具体描述，不来自项目词义、常识复述或咨询提醒。E8负责删改到最终交付篇幅。"
                + "\n原始材料用于介绍对象本身。网页栏目名、照片拍摄说明、给作者的编排标签不转成正文；直接写业务和空间的实际内容。"
                + '\n\n返回JSON：article_markdown、requires_blueprint_reconfirmation、reconfirmation_reason。正常写作取舍直接完成；后两字段通常为false和空字符串。', writer=True)


def prompt_edit(wf, job, *, p0=False):
    body = edit_base_input(wf, job, p0=False)["article_markdown"]
    return wrap("# 编辑当前完整稿\n\n" + body + "\n\n" + length_note(body)
                + "\n\n" + references(wf, job) + "\n\n" + commission(wf, job)
                + '\n\n返回一个JSON对象：edit_status为"accepted"或"revised"；article_markdown为完整Markdown正文字符串；editorial_notes为字符串数组（例如["合并重复背景，展开原稿未介绍的服务内容"]）；requires_blueprint_reconfirmation为false；reconfirmation_reason为空字符串。accepted时全文不变且editorial_notes=[]；修改后返回revised及实际修改说明。正文段落用JSON换行转义\\n，不把字面量反斜杠n写进正文。正常编辑不要求业务确认。', writer=True)


def prompt_finish(wf, job, *, after_repair=True):
    from .natural_editor import digest
    if after_repair:
        body = wf.read_json(Path(job) / "production/article_repaired.json")["article_markdown"]
    else:
        body = prepare_finalize_input(wf, job, p0=False)["candidate_markdown"]
    return wrap("# 最后文字编辑\n\n当前完整稿：\n" + body + "\n\n" + length_note(body)
                + "\n基稿标识：" + digest(body) + "\n\n" + commission(wf, job, editor=True)
                + "\n最终篇幅要求适用于应用局部修改后的完整稿。保留必要信息和原本通顺的表达，不为求简短而做可有可无的删改，也不用重复说明凑字。"
                + "\n\n本次全文阅读标准：\n" + FINAL_READING
                + '\n\n单独submit_result提交needs_revision、comments、local_edits。无需结构返工时needs_revision=false、comments=[]；少量句级微调放local_edits，每项仅original与replacement。original逐字复制当前稿中唯一的一处短句或句子片段，replacement只改该处表达；不跨段，不增删标题、不改变加粗机构名或档名，不重排段落。可删去段内赘句，但不删掉整段。无需修改就local_edits=[]。需要重组多个段落时needs_revision=true、comments写少量具体结构意见、local_edits=[]。正常需求与用途说明可以保留，避免再次改成抽象体系介绍。'
                + ('\n本次已经完成过一次结构返工。仍有主要问题就如实提出，流程会保留待修改状态，不再自动循环。' if after_repair else '\n仅在确有结构问题时才返工；小问题请直接局部改好。'))


def prompt_finalize(wf, job, *, p0=False):
    return prompt_finish(wf, job, after_repair=False)


def prompt_repair(wf, job, *, p0=False):
    body = prepare_finalize_input(wf, job, p0=False)["candidate_markdown"]
    review = wf.read_json(Path(job) / "production/article_editorial_review.json")
    return wrap("# 按结构意见修订正文\n\n" + body + "\n\n" + length_note(body)
                + "\n\n本轮结构意见：\n" + _json(review["comments"])
                + "\n\n" + references(wf, job) + "\n\n" + commission(wf, job)
                + "\n\n当前委托优先于审阅建议。意见用于指出文字问题，不能据此缩窄article_brief规定的全文介绍范围。当前已经认定存在结构问题，需要重新决定受影响部分的段落中心和内容选择，不是在原稿里逐句删几字。基稿中的栏目数量、段落划分和项目覆盖都可以调整；只保留确实成立的表达。需求入口简明交代，代表业务、对象实际工作和服务内容分别展开。转述资料如何列项、评价材料是否完整的文字不进入文章。先规划足够的内容再写完整段落，测字后从整体调整，不向各句末尾添加同义释义和咨询提醒。"
                + '\n\n返回JSON，仅含article_markdown完整正文。保留未受影响的表达；不要用新概括填回刚删掉的旧概括。', writer=True)
