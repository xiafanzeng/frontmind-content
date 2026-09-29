"""Project a confirmed per-article commission for an independent remote writer.

The host owns original-material reading and selection. These helpers never walk
the reference pack or inject all raw sources into the writer's prompt.
"""
from __future__ import annotations

from .brand_prose import refine_prompt as _refine_p0_prompt

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from shared.editorial_contracts import EditorialContractError, prepare_finalize_input, edit_base_input, quality_review_guidance
from shared import p0_style, brand_stage, article_reader, article_positioning

CONTEXT_CONTRACT_VERSION = "frontmind-writing-context/v4.11.8"
DEEP_P0_PROMPT_PREFIX = '<frontmind_p0_contract version="4.12.2">\n'

PATTERN_GUIDANCE = {
    "P00": "围绕本篇委托介绍品牌自身，让读者理解其业务与特点。身份、产品或服务、人员、技术、工作方法、真实项目等仅是可选内容维度，根据材料和本篇重点取舍，不固定开篇、章节数量或顺序，不要求每篇都有案例、流程或成果。产品或服务的作用通过具体事实及其关系体现，不通过外部服务与客户自行完成的比较来论证。不写具名或类别竞品对照、采购筛选、验真指南、市场排名，也不以抽象的资质效力或法律权威组织全篇。",
    "P01": "围绕正式问题讲清主推荐对象的具体理由和适用条件，保留已经确认的本题选择逻辑。",
    "P02": "完整回答本题的多主体推荐，写出各对象各自的事实和适用条件，保持已确认的分层及顺序，避免每家机构套同一介绍段。",
    "P03": "直接解释当前场景的具体问题、方法、过程和适用条件，只使用与问题有关的企业信息。",
    "P04": "围绕事件、参与者、时间和实际进展组织叙述，不把新闻写成企业通史。",
    "P05": "围绕题目点名对象，在共同且相关的维度上解释有材料支持的差异，保留各方必要事实与适用条件。",
    "P06": "用本题相关的业务事实回答资质、体验、口碑或可信度疑问，直接解释读者关心的事情，不写材料审阅报告。",
}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() and not path.is_symlink() else ""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def natural_writing_guidance(pattern: str, *, manuscript: bool = False) -> str:
    return PATTERN_GUIDANCE.get(pattern, PATTERN_GUIDANCE["P03"]) + "\n" + source_and_structure_guidance() + """
企业事实直接陈述，来源、历史修改与核验过程留在后台，必要日期和服务条件保留。可以解释材料中已记载动作的直接用途和衔接关系，不要求来源逐字写出同一句解释；不得虚构客户经历、量化收益、实际成效或保证结果，也不把具体资质和服务范围扩大为普遍效力，过强时收窄表达。素材不要求把其中每项都搬进正文。例文只参考写法，不移植事实，也不要求套用其开头句式。只制作文字，不选择或插入图片，不输出图片占位。"""


def source_and_structure_guidance() -> str:
    return """原始材料提供事实及其适用条件，不规定文章必须沿用其标题、字段、排列顺序和结论格式。根据当前文章任务选择有用内容，重新组织为适合读者的叙述；未采用的细目保留在后台，不要求全部写入正文。已采用事实的关键单位、范围、条件和时间状态不能丢失。原件没有案例、人物或结果，不补造这些内容。解释可以说明给定事实之间的直接关系，但不新增该主体未记载的属性、操作细节、对话、经历或保证；通常合理的做法不等于这家主体已经采用或承诺采用。
通用规范只规定写作与编辑方法，文章类型决定要完成的任务，本篇委托和所选例文决定具体表达方向。开篇、章节、案例和结尾依本篇需要安排，不强制介绍团队、流程、资质或周期，也不让原件最后一句自动成为文章最后一句。
计划、进行中和已完成的状态在开篇或对应叙述处自然交代，并贯穿相关动作的时态；不能先写成已经发生，再靠末尾说明修正。素材中没有某项信息时，省略未支持的说法，不把资料有无、选材过程、不能推导的提醒或删改理由写进正文。必要范围直接附着在相关事实与条件上，不另设材料边界说明段。
在本篇任务已经完成、读者所需信息已经交代清楚的位置结束。是否需要结果、判断、建议或下一步，取决于文章类型和现有事实，不机械追加，也不一律删除。"""


def manuscript_composition_guidance(pattern: str) -> str:
    genre = ("写一篇让读者逐步了解这家企业的深度介绍。" if pattern == "P00" else
             "写一篇围绕本次事件及实际进展展开的新闻。" if pattern == "P04" else
             "写一篇直接回答本题、让读者理解判断理由的文章。")
    return genre + """将给定事实组织成符合本篇体裁、值得连续阅读的文章。依据 article_brief 确定重心，参考 example_use 与完整例文安排详略：重点内容充分展开，辅助信息简要交代，让读者随着叙述理解主体的业务、特点或本题判断。文章的吸引力来自观察角度、具体内容和叙述推进，不靠形容词、口号或虚构情节。
具体事实可以承担介绍、解释、展开或印证的作用，不必逐项改写为业务定义。让背景、事实、动作和解释自然承接，前后句有实际关系，术语随理解需要使用。小标题已经交代的主题不必在段首再宣布，相邻章节各有分工。必要解释写充分，已经讲清的内容就停下，不再点评其价值。问题文章直接回答问题的结论、真实比较和必要步骤、建议也应保留。
素材是事实准备，不是文章底稿；素材段落无需对应文章段落，其句子和排列顺序不约束成稿。可取舍、换序、合并并重新组织整段或整节，不必保留原来的句子、段落数量或枚举，不以轮换主语和连接词代替重组。自然精练不等于把材料压成摘要，不以缩短篇幅代替写清楚。
句子长短与段落详略随内容安排，不要求每段采用“总说—列举—总结”。例文用于理解实际写法，不提供固定开头或收尾公式。不为段落长短整齐、凑字数或显得有深度而扩写，也不以全篇重写或长句数量证明文采。"""


def focused_editorial_guidance() -> str:
    return """按以下顺序编辑实际候选稿，不重新接受从素材成篇的任务：
一、整体阅读。对照本篇委托与 article_brief 判断是否完成体裁任务，有无明确重心、必要展开和阅读推进；即使事实正确、结构齐全、能够读懂，仍像业务目录或材料汇编也不能判为通过。检查章节分工及重点内容是否得到足够说明，保留必要步骤、直接回答和共同维度比较，不把问题文章或事件新闻改成企业介绍。
二、段落编辑。检查段首、段末和全文结尾，是否反复宣布主题、连续枚举术语或只将事实并排摆放。需要时在既定主题内重组整段或整节，不能只轮换主语、连接词或近义词。保留有理解增量的解释、必要的回答和建议、事实条件以及有依据的比较，不一律删除总结或因果句。前文已经足以理解时，不再概括它们的共同作用；普通动作不需再用近义词解释一遍。
三、句子与事实复核。在上下文中检查措辞、术语、范围、日期和时态，也核对事实之间的关系：材料明示的是并列、时间、条件还是状态，就保持相应含义；叙述承接不能把并列信息变成先后依赖，把计划或待定状态变成必将发生的承诺，或新增因果、排他说法及结果保证。各项事实成立，不等于结合后的结果已经得到支持；材料未提及，也不等于主体不提供。把本次新增句、标题及定义句同样放回全文检查，提交前再核对自己的连接句和新增限定。删除无据内容后直接组织剩余事实，不用后台资料缺口说明、抽象归纳或赞评填补删句。
已经完成体裁任务且自然准确的内容保留；短段落本身不是缺陷。删句后检查衔接，不用套话补位，不为整齐或目标字数扩写。篇幅、点名句消失或编辑说明声称已修改都不能替代通读。结尾由本篇任务和现有事实决定，不固定案例或原件结论收尾，也不自动追加展望、判断或建议。"""


def editorial_authority_guidance() -> str:
    return """写作与编辑权限：保留核心定位含义、正式回答、对象范围、章节主题及其确认顺序，不改变推荐对象的先后。标题措辞和段落组织由作者决定。可以直接重拟标题、合并段落、删去非必要枚举与案例细节；事实细目不是强制覆盖项。这些是正常写作编辑，无须重新确认蓝图。只有必须改变上述业务决定，或用户明确要求原样保留的内容时，才说明原因并返回原确认节点。"""


def writing_material_contract_guidance(*, pattern: str | None = None) -> str:
    scope = (article_reader.material_scope(pattern) if pattern else
             "P0 只选企业自身及真实业务关系；P02/P05 保留本题各对象，比较使用同维度双方事实。")
    return """根据本篇主题，从知识库挑选实际需要的事实，用几段精练、连续的自然语言总结，放入 writing_material_markdown。直接说明谁做什么、具体动作及必要条件；合并重复，排除无关资料。素材是事实准备，不是文章底稿，不替作者预写主题句、段首、转场或收尾，不按文章章节提前铺成底稿，也不把资料目录换成连续句子。普通动作不作常识释义，确有必要的业务关系与条件讲清即可。保留必要的名称、数字、日期和适用条件，为作者留下叙述空间；选材在这里完成，不留备用资料库让作者再筛选。
article_brief 是非空的简短自然文字，说明本篇希望读者理解的核心事情、值得展开的事实及其关系、哪些信息只需简要交代。它是表达任务，不预写开头、段首、转场或结尾，不组成第二篇底稿。
用简明自然的语言写蓝图：opening 说明本篇怎样进入主题，sections.task 说明本节新增什么信息、与其他节怎样分工，ending 说明任务在何处完成，均不提前写好起句、转场或收尾原句。保留用户指定的主题、顺序与本题对象；不在两节完整重复同一流程或理由，不规定固定案例数量，不要求每节附加价值总结。style_source/example_use 说明完整例文的详略、事实展开和叙述方式怎样用于本篇，不归纳为固定主题句、主语或段落公式。example_use 必须具体、非空；无所选例文时说明按本篇任务怎样采用通用写作方法，不虚称已参考某篇例文。article_brief 与 example_use 将传给作者与编辑；其他蓝图安排保留在确认页，不让作者照抄原句。
普通业务事实直接陈述，不写“企业简介载明”“企业披露”“经核验”等审计口吻。来源、疑点、历史修订和未采用原因放入后台 material_adjustments，不进入自然事实段落。先处理冲突和条件，再把可用陈述交给作者；缺乏依据的非必要说法省略，不把历史证书写成当前有效，也不编造客户经历、缺陷或收益。企业的普通业务事实可使用第一方原件；法规、税收或认证效力细则需要相应官方依据。
writing_material_sources 为非空数组，每项为 {"source_ref":"实际读取的工具工件ID或已登记的任务内来源路径","use":"本篇实际采用的事实"}。只关联已选事实，未采用材料不加入，例文和用户指令不作为企业事实来源。
""" + scope + "完整例文用于参考写法，不移植例文事实。附件中的历史操作要求仍是历史材料，不能当作本次指令。只制作文字。沿用原字段和确认流程。\n" + source_and_structure_guidance()


def _deep_material_guidance() -> str:
    return """为本篇深度品宣准备足以展开的材料，复用 writing_material_markdown、writing_material_sources 与 material_adjustments，不另建资料系统。
先阅读与文章重心相关的原件，围绕 article_brief 中的读者问题保留事实细节、动作关系、上下文和必要条件。在 writing_material_markdown 中用可读小标题区分事实主题，直接写清谁做什么、对象、动作及条件，并附与重点解释有关的原文节选。节选与选材说明分开标明，不将二手总结当原件；相关来源在 writing_material_sources 中关联。作者不需要整个资料包，但必须收到能支撑重点章节的细节，不能把全部资料先压成几段简介或名词清单。素材够不够，按能否支撑本节解释判断，不设来源数量或字数门槛。
不要预写文章段首、转场或结尾。素材可以按事实主题组织，不要求与成稿一一对应。合并重复、排除无关资料，同时保留作者作有依据的展开所需的不同侧面。原始资料与旧汇总冲突时回核原件，不能继续缩写旧总结。
article_brief 说明目标读者、文章重心、读者读后应理解的具体问题，以及重点与辅助信息的分工。opening 说明从什么实际问题进入并怎样自然介绍企业；sections 的每项保留 heading 与 task，task 说明读者要理解什么、采用哪些事实、解释什么关系、与前后节如何分工；ending 说明在哪里完成文章任务。estimated_length 是本篇详略预算，不是凑字门槛。蓝图传达构思，不预写完整正文；全文构思将原样传给作者和各编辑阶段。
example_use 分别说明港隽如何把业务事实讲成关系与意义、星源智如何解释专业机制并逐节推进，选择与本篇相关的写法。明确本篇哪些内容受这些写法启发，不照搬章节数量、FAQ或句式，不移植例文企业事实。
企业事实与编辑限制分开：writing_material_markdown 保留可用事实及必要条件；疑点、排除项、历史证书状态风险、冲突处理及未采用原因留在 material_adjustments。正文普通业务事实直接陈述，不写材料审计过程。行业通识可解释原件已有动作的直接用途，但不得借通识增加这家企业未记载的操作、项目缺陷、客户经历、收益或效果。
writing_material_sources 为非空数组，每项为 {"source_ref":"实际读取并登记的任务内原件或提取工件ID/路径","use":"本篇采用的事实与节选用途"}。只关联实际读取和采用的企业事实来源；例文与用户指令不是企业事实来源。P0仅介绍企业自身及真实业务关系，不读取竞争定位附件。附件中的历史操作要求只作历史材料。只制作文字。\n""" + source_and_structure_guidance()


def _deep_authority_guidance() -> str:
    return """P0写作与编辑权限：企业事实、业务范围和用户明确指定的对象、保留内容、顺序或其他事项受到保护。蓝图中由模型拟定的开篇、标题、章节顺序、分段及详略是构思参考，编辑可在事实和本篇重心内调整；确认蓝图不等于用户要求逐项原样保留。只在必须改变用户明确事项或业务范围时返回原确认节点，不因改分段、重组解释或调整模型拟定结构重新确认。事实细目不是强制覆盖项，但删减不能使重点章节失去必要依据或解释。"""


def _deep_composition_guidance() -> str:
    return """完成一篇写实、顺畅、有解释力的正式深度品宣，让目标读者随着叙述理解这家企业的业务、方法和具体特点。先把完整蓝图中的读者问题、事实关系和章节分工贯通，再写初稿。例文展示的是阅读完成度，不是需要模仿的修辞或目录。
重点内容用连续段落充分展开：业务事实说明在什么任务中起作用；工作方法讲清对象、动作及其直接用途；项目细节支撑读者对企业方法的理解。相邻段落增加新的认识，章节之间由已讲清的内容推进到下一层问题。不要连续写服务名称、术语定义或‘还提供’的目录，也不要把每个事实后面都接一句空泛价值总结。
企业具体内容参与解释，不能只把公司名放进一篇通用科普。技术解释以给定对象及动作的直接关系为限，不编造参数、缺陷、整改效果、客户情节或经营成绩。事实与关系已经有依据时可以用自己的语言解释，不要求来源逐字写出同一句解说。
开篇从本篇读者关心的实际事情进入，自然介绍企业；收束完成前文的问题，不另堆服务项目。详略依据 article_brief 与 estimated_length 安排，允许把重点写充分。篇幅预算用于防止写成摘要，不以凑足字数证明深度；写实克制也不等于简短。初稿阶段完成内容与构思，不能将重点解释留给后面的润色补齐。"""


def _deep_editorial_guidance(stage: str) -> str:
    common = """保留有依据、有理解增量的解释，区分冗余复述与必要展开。判断修改价值要看读者增加了什么理解，不能以删了多少字、减少多少清单或自评措辞为依据。并列事实不能随叙述变成因果、先后依赖、排他优势或保证；历史项目不能变成持续成绩，行业常见做法不能变成该企业已经采用的操作。修改错误解释时，检查该段任务能否继续完成，有依据则用准确解释替换，不把整节删成简介。不得在正文暴露审阅过程、缺少材料或‘不能据此推断’等后台提醒。"""
    responsibilities = {
        "e8": "E8职责：检查事实关系、内容缺口与章节逻辑。对照原稿、完整构思和素材确认重点是否讲充分；修复不成立的关系、主体错误、重复覆盖和跳步，有充分事实依据时补足解释。保留已经准确且有展开的段落，不把整篇重做成业务摘要。缺陷集中在内容时先处理内容，不用反复改标题与词语掩盖。",
        "style": "第三遍职责：专门改善段落展开、专业解释、章际推进、句子节奏和详略。以E8候选为对象，对照两篇全文与段落拆解，找出事实只并排摆放、说明停在术语释义、章节没有递进的位置，重组或补足有依据的解释。可以调整模型拟定的结构，不必每节使用同一种段落公式。重要解释已清楚时保留，不追求全篇改写，也不把修饰退化为换词、改标题、删句。",
        "finalize": "最终验读职责：独立阅读修饰后的实际全文，对照事实与两篇例文分别判断。先判断整篇是否达到本篇深度及表达目标，再做一次必要的局部修正；不默认压缩，不再次代替作者重写全篇。若需重新选材、改变构思或补写多个重点才能成立，返回 incomplete，说明应返回蓝图/素材、初稿、E8或修饰的具体问题；不能剪成简介后通过。模型自评和上阶段accepted/revised仅说明编辑动作，不证明质量。",
    }
    return responsibilities[stage] + "\n" + common


def validate_article_brief(value: Any) -> dict[str, Any]:
    """Require the expression task on new blueprint results, not legacy reads."""
    if not isinstance(value, dict) or not _text(value.get("article_brief")).strip():
        raise EditorialContractError("article_brief_missing", "新蓝图缺少本篇表达任务 article_brief")
    if not _text(value.get("example_use")).strip():
        raise EditorialContractError("example_use_missing", "新蓝图缺少本篇具体例文用法 example_use")
    return value


def validate_writing_material(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not _text(value.get("writing_material_markdown")).strip():
        raise EditorialContractError("writing_material_missing", "蓝图缺少本篇自然事实段落 writing_material_markdown")
    sources = value.get("writing_material_sources")
    if not isinstance(sources, list) or not sources:
        raise EditorialContractError("writing_material_sources_missing", "蓝图缺少本篇素材来源")
    for item in sources:
        ref = item if isinstance(item, str) else item.get("source_ref") if isinstance(item, dict) else None
        if not isinstance(ref, str) or not ref.strip():
            raise EditorialContractError("writing_material_source_shape", "素材来源必须含有效 source_ref")
        if isinstance(item, dict) and not _text(item.get("use")).strip():
            raise EditorialContractError("writing_material_source_use", "素材来源需要说明本篇用途")
    return value


def validate_writing_material_sources(wf: Any, job_root: Path, value: Any, *, artifact_ids: set[str] | None = None) -> dict[str, Any]:
    validate_writing_material(value)
    root = Path(job_root).resolve()
    known = set(artifact_ids or ())
    registered: dict[str, dict[str, Any]] = {}
    registry_path = root / "artifacts/host_registry.json"
    if registry_path.is_file() and not registry_path.is_symlink():
        try:
            records = json.loads(registry_path.read_text(encoding="utf-8")).get("artifacts", {})
        except (ValueError, OSError, AttributeError):
            records = {}
        if isinstance(records, dict):
            for artifact_id, record in records.items():
                if isinstance(record, dict) and isinstance(record.get("path"), str) and record["path"]:
                    registered[artifact_id] = record
                    registered[record["path"]] = record
    fixed_examples_are_style_only = value.get("kind") == "p0" and p0_style.is_enabled(wf.load_state(job_root))
    for item in value["writing_material_sources"]:
        ref = item if isinstance(item, str) else item["source_ref"]
        if fixed_examples_are_style_only:
            source_path = Path(str(registered.get(ref, {}).get("path") or ref))
            source_path = source_path if source_path.is_absolute() else root / source_path
            try:
                source_path.resolve().relative_to(root / "inputs/p0_style_examples")
            except ValueError:
                pass
            else:
                raise EditorialContractError("p0_example_not_business_source", "星源智、港隽固定例文及写法拆解只能参考文风，不能作为本企业事实来源")
        if ref in known:
            continue
        record = registered.get(ref)
        if record is None:
            raise EditorialContractError("writing_material_source_unknown", f"素材来源尚未登记为可读工件：{ref}")
        path = Path(record["path"])
        path = path if path.is_absolute() else root / path
        try:
            path.resolve().relative_to(root)
        except ValueError:
            raise EditorialContractError("writing_material_source_unknown", f"素材来源不属于已读取的 Job 材料：{ref}") from None
        if path.is_symlink() or not path.is_file():
            raise EditorialContractError("writing_material_source_unknown", f"素材来源不存在或尚未登记：{ref}")
        if record and record.get("sha256"):
            expected = str(record["sha256"]).removeprefix("sha256:")
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise EditorialContractError("writing_material_source_changed", f"素材来源已改变，需要重新阅读并更新蓝图：{ref}")
    return value


def selected_examples_markdown(wf: Any, job_root: Path, *, p0: bool) -> str:
    if _natural_enabled(wf, job_root):
        return _natural_examples(wf, job_root, p0=p0)
    if p0 and brand_stage.enabled(wf.load_state(job_root)):
        return "本阶段不载入品宣例文；完整例文仅进入第三遍。"
    state = wf.load_state(job_root)
    fixed = p0_style.examples_markdown(Path(__file__).resolve().parents[1], job_root) if p0 and p0_style.is_enabled(state) else ""
    route = state.get("selected_example_route")
    use_examples = route in ({"top20", "A"} if p0 else {"A", "top20"})
    if not p0 and route == "B":
        return "\n\n".join(f"### 文风例文：AI 答案 {i}\n\n{text}" for i, text in enumerate(wf.answer_texts(job_root), 1))
    if not use_examples:
        return fixed or "本篇使用工作流自然写作规范。"
    examples = wf.load_examples(job_root, "p0" if p0 else "question")
    if not examples:
        raise EditorialContractError("selected_example_missing", "已选择例文，但例文正文不存在")
    parts = []
    for example in examples:
        raw = example.get("path") or example.get("body_path")
        path = Path(str(raw))
        if not path.is_absolute():
            path = Path(job_root) / path
        body = _read(path)
        if not body.strip():
            raise EditorialContractError("selected_example_missing", "已选择例文缺少完整正文")
        parts.append(f"### {example.get('title') or '文风例文'}\n\n{body}")
    return "\n\n".join(([fixed, "以下为本任务补充例文，不替代上面两篇固定例文："] if fixed else []) + parts)


def _blueprint(job_root: Path, *, p0: bool) -> dict[str, Any]:
    path = Path(job_root) / "blueprints" / ("p0_blueprint.json" if p0 else "article_blueprint.json")
    try:
        value = json.loads(_read(path))
    except ValueError:
        raise EditorialContractError("blueprint_missing", "缺少可用的已确认蓝图") from None
    return validate_writing_material(value)


def writer_blueprint(value: dict[str, Any], *, deep: bool = False) -> dict[str, Any]:
    """Keep expression intent, not prewritten openings or section-task prose."""
    scope = {key: value[key] for key in ("kind", "question", "pattern_id") if key in value}
    if value.get("kind") != "p0" and "candidate_order" in value:
        scope["candidate_order"] = value["candidate_order"]
    sections = [section for section in value.get("sections", []) if isinstance(section, dict)]
    scope["section_themes"] = [section["heading"] for section in sections if "heading" in section]
    scope["fact_use"] = "所采用事实保持准确及必要适用条件；不要求全数写入，也不固定素材或业务清单的排列。"
    notes = {key: value[key] for key in ("article_brief", "example_use", "estimated_length")
             if key in value and (key == "estimated_length" or _text(value[key]).strip())}
    if deep and value.get("kind") == "p0":
        notes.update({key: value[key] for key in ("opening", "ending") if key in value})
        notes["sections"] = [{key: section[key] for key in ("heading", "task") if key in section}
                             for section in sections]
        notes["plan_use"] = "完整蓝图传达要解释的关系与章节分工，不是预写正文；模型拟定的标题、段落和顺序可依理解需要调整。仅用户明确指定的保留内容或顺序受到保护。"
    if value.get("kind") != "p0" and "answer_use" in value:
        notes["answer_use"] = value["answer_use"]
    return {"business_scope": scope, "composition_notes": notes}


def blueprint_edit_candidate(value: Any, *, p0: bool) -> dict[str, Any] | None:
    """Project an editable prior result, never its arbitrary research attachments."""
    if not isinstance(value, dict) or not _text(value.get("writing_material_markdown")).strip():
        return None
    fields = ("article_brief", "opening", "ending", "estimated_length", "style_source", "example_use", "writing_material_markdown")
    fields += ("positioning_placement", "existing_p0_edit_plan") if p0 else ("question", "pattern_id", "brand_positioning_use", "answer_use")
    candidate = {"kind": "p0" if p0 else "article"}
    for key in fields:
        item = value.get(key)
        if isinstance(item, (str, int, float)) and not isinstance(item, bool):
            candidate[key] = item
    candidate["sections"] = [{key: section[key] for key in ("heading", "task", "level")
                              if isinstance(section.get(key), (str, int))}
                             for section in value.get("sections", []) if isinstance(section, dict)]
    for key in ("materials", "material_adjustments") + (() if p0 else ("candidate_order",)):
        items = value.get(key)
        if isinstance(items, str):
            candidate[key] = items
        elif isinstance(items, list):
            candidate[key] = [item for item in items if isinstance(item, (str, int, float)) and not isinstance(item, bool)]
    candidate["writing_material_sources"] = [
        {key: item[key] for key in ("source_ref", "use") if isinstance(item.get(key), str)} if isinstance(item, dict) else item
        for item in value.get("writing_material_sources", []) if isinstance(item, (str, dict))]
    return candidate


def prompt_blueprint(wf: Any, job_root: Path, *, p0: bool) -> str:
    from . import writing_context_v16
    if writing_context_v16.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v16.prompt_blueprint(wf, job_root, p0=p0)
    from . import writing_context_v15
    if writing_context_v15.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v15.prompt_blueprint(wf, job_root, p0=p0)
    from . import writing_context_v14
    if writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_blueprint(wf, job_root, p0=p0)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13._natural_blueprint_prompt(wf, job_root, p0=p0)
    if _natural_enabled(wf, job_root):
        return _natural_blueprint_prompt(wf, job_root, p0=p0)
    if p0 and brand_stage.enabled(wf.load_state(job_root)):
        return brand_stage.blueprint_prompt(wf, job_root)
    state = wf.load_state(job_root)
    pattern = "P00" if p0 else state["selected_pattern_id"]
    brand = state["reference_pack"]["brand"]
    lines = [f"# 生成{'P0 品牌深度品宣' if p0 else '单问题文章'}蓝图与本篇事实素材", f"品牌：{brand}",
             f"本篇写法：{PATTERN_GUIDANCE.get(pattern, PATTERN_GUIDANCE['P03'])}",
             "使用 list_materials 查看知识库，按 artifact ID 读取本篇相关原文。普通文本直接 read_material；Word/PDF 使用 extract_document，只有扫描原件无法提取文字时才按需 OCR。按来源的日期与适用条件理解材料。",
             f"用户本次蓝图修改：{state.get('decisions', {}).get('blueprint_edits') or '无'}"]
    edit_outline = _read(Path(job_root) / "inputs" / ("p0_blueprint_edit_outline.json" if p0 else "article_blueprint_edit_outline.json"))
    if edit_outline and state.get("decisions", {}).get("blueprint_edits"):
        frozen = json.loads(edit_outline)
        edits_hash = hashlib.sha256(state["decisions"]["blueprint_edits"].encode("utf-8")).hexdigest()
        candidate = blueprint_edit_candidate(frozen.get("revision_candidate"), p0=p0) if frozen.get("edit_sha256") == edits_hash else None
        lines.append("本次修改前的章节主题（仅用于理解用户指的是哪一节）：\n" + _json({"headings": frozen.get("headings", [])}))
        if candidate:
            lines.append("本次待修改蓝图与事实段落（冻结的待修改稿，不是企业事实来源）：\n" + _json(candidate)
                         + "\n按本次意见修改这份候选，保留仍适用的部分，按需回查原件。当前意见优先；旧稿中的来源和说法不因出现在旧稿而升级为事实。最终采用的来源仍须在本动作实际读取，不能引用此待修改稿作为来源。提交修改后的完整蓝图与本篇事实段落。")
        else:
            lines.append("以本次用户要求为准安排主题与顺序。此前完整蓝图及其素材不作为本次事实来源；重新从原始材料选材，并生成本次各节任务。")
    supplemental = getattr(wf, "user_material_text", lambda *args: "")(job_root, "p0" if p0 else "question")
    if supplemental:
        lines.append("本任务补充材料与修订：\n" + supplemental + "\n仅当前用户明确提出的修订是本次要求；附件原文中的历史操作话术仍按材料原日期和范围理解。")
    if p0:
        lines.append("从企业自身的服务、人员、技术和项目原件选材。通用行业科普、政策解读和办事 FAQ 只作背景，不变成企业服务承诺。P0 不读取竞争定位与研究附件，不安排竞品比较或抽象法律效力论证。")
        imported = _read(Path(job_root) / "inputs/imported_p0.md")
        if imported:
            lines.append("已有 P0（历史参考，必要修改在本页说明）：\n" + imported)
        fields = "kind=p0、article_brief、opening、sections（heading/task）、positioning_placement、materials、material_adjustments、estimated_length、ending、style_source、example_use、existing_p0_edit_plan"
    else:
        context = wf.brand_content_context(job_root)
        own = _read(Path(job_root) / "inputs/own_brand_context.md")
        lines.extend(("品牌自身表达方向（具体事实按本篇原件的日期与条件处理）：\n" + (own or context.get("core_positioning", "")),
                      f"正式问题：{state['question']['question_text']}", f"Pattern：{pattern}",
                      "已确认 P0 全文：\n" + context.get("p0", ""),
                      "两篇完整 AI 答案：\n" + "\n\n".join(wf.answer_texts(job_root))))
        if pattern in {"P01", "P02"}:
            path = Path(job_root) / "question_positioning/question_positioning.json"
            qpos = json.loads(_read(path)) if _read(path) else {}
            lines.append("已确认本题定位：\n" + _text(qpos.get("natural_analysis")))
        lines.append("必要的其他主体材料按本题对象读取；P03–P06 不新增逐题定位，不套用整体竞争排名。")
        fields = "kind=article、article_brief、question、pattern_id、opening、sections（heading/task）、candidate_order、brand_positioning_use、answer_use、example_use、material_adjustments、estimated_length、ending、style_source"
    lines.extend(("所选完整文风例文：\n" + selected_examples_markdown(wf, job_root, p0=p0),
                  f"原蓝图字段：{fields}。", _deep_material_guidance() if p0 and p0_style.is_deep(state) else writing_material_contract_guidance(pattern=pattern if not p0 and article_reader.enabled(state) else None)))
    if p0 and p0_style.is_enabled(state):
        lines.append("本篇固定文风目标：写实、顺畅、有解释力，稍有文采。通过具体事实、必要解释和章节推进表现品牌特点。不要套用例文章节或强制FAQ；example_use分别说明星源智与港隽写法怎样服务本篇。")
    prompt = _prose_projection(((DEEP_P0_PROMPT_PREFIX if p0 and p0_style.is_deep(state) else "") + "\n\n".join(lines)), "blueprint", p0 and p0_style.is_prose(wf.load_state(job_root)))
    return article_reader.wrap(prompt, state, p0=p0)



def _p0_revision_instructions(decisions: dict[str, Any], revision: dict[str, Any], *, deep: bool = False) -> list[str]:
    """Keep durable user constraints while separating completed stage actions."""
    parts = []
    inherited = _text(decisions.get("response_brief"))
    if inherited.strip():
        parts.append("继承的原始内容要求（完整原文）：以下对象、内容和限制在未被本轮意见覆盖时继续有效；当前精修意见优先，其中已经完成的上游阶段动作不重新执行。\n<inherited_content_requirements>\n" + inherited + "\n</inherited_content_requirements>")
    historical = _text(decisions.get("blueprint_edits"))
    if historical.strip():
        historical_label = ("历史蓝图委托引用（完整原文）：研究、选材、生成蓝图等阶段动作已经完成，不重复执行；其中未被本轮意见覆盖的读者目标、深度要求、例文用法、篇幅意图、事实范围与明确保留事项继续有效。新意见仅覆盖与其冲突的部分；要求删重复或修改开篇，不等于撤销整篇深度要求。这里的‘本轮’指当时阶段，不改变当前候选稿的身份。" if deep else
                            "历史蓝图委托引用（完整原文，不是本轮动作指令）：只继承其中未被当前精修覆盖的对象、内容与限制，如明确不写的事项、明确保留的段落或业务条件。不再执行其研究、重新选材、生成蓝图或另一次整篇重写动作；旧篇幅目标和旧详略命令也不自动恢复。下面引用里的‘本轮’等时间话术只指当时的历史阶段，不改变下方实际E8为待编辑稿的身份。")
        parts.append(historical_label + "\n<historical_blueprint_request>\n" + historical + "\n</historical_blueprint_request>")
    parts.append("本轮唯一当前修改委托（完整原文；与继承内容要求冲突时以本轮为准）：\n" + revision["edits_markdown"])
    return parts

def natural_author_context(wf: Any, job_root: Path, *, p0: bool, finalizing: bool = False, editing: bool = False) -> str:
    if _natural_enabled(wf, job_root):
        return _natural_context(wf, job_root, p0=p0, include_references=not finalizing)
    if p0 and brand_stage.enabled(wf.load_state(job_root)):
        return brand_stage.context(wf, job_root)
    state = wf.load_state(job_root)
    deep = p0 and p0_style.is_deep(state)
    blueprint = _blueprint(job_root, p0=p0)
    projected_blueprint = writer_blueprint(blueprint, deep=deep)
    pattern = "P00" if p0 else state["selected_pattern_id"]
    decisions = state.get("decisions") or {}
    editing = editing or finalizing
    reader_editing = not p0 and editing and article_reader.enabled(state)
    active_article_revision = None
    if reader_editing:
        from shared.manuscript_revision import current_revision
        active_article_revision = current_revision(wf, job_root, p0=False)
    active_p0_revision = None
    if p0 and editing and p0_style.is_enabled(state):
        from shared.manuscript_revision import current_revision
        active_p0_revision = current_revision(wf, job_root, p0=True)
    user_instructions = []
    if active_p0_revision:
        user_instructions = _p0_revision_instructions(decisions, active_p0_revision, deep=deep)
        if deep:
            projected_blueprint["composition_notes"]["revision_use"] = "以上原表达目标与构思在未被本轮意见覆盖时持续有效；精修不重跑历史阶段动作，也不因进入精修而清空深度、重点和例文用法。当前意见仅覆盖冲突部分。"
        else:
            projected_blueprint["composition_notes"] = {
            "history_status": "原蓝图的表达说明、篇幅意图及此前蓝图修改/整篇重写指令属于已完成的上游历史，原文保留在Job中；本轮不重新执行，也不恢复其旧详略安排。",
            "current_scope": "本轮以完整当前精修意见决定表达重心和修改范围；已确认业务主题、顺序、受保护决定及完整事实条件继续有效。",
            }
    elif active_article_revision:
        for key, label in (
            ("response_brief", "原始文章委托（完整原文）：正式问题、业务回答及未被当前意见覆盖的内容要求继续有效"),
            ("blueprint_edits", "历史蓝图阶段修订（完整原文）：研究和蓝图动作已经完成；其中明确对象、顺序、事实范围与必要条件继续有效，但旧表达方法、段落模板及详略安排可按本轮意见改写，不恢复上游动作"),
        ):
            instruction = _text(decisions.get(key))
            if instruction.strip():
                user_instructions.append(label + "：\n" + instruction)
        user_instructions.append("本轮唯一当前正文修改委托（用户原句与意见完整保留；与历史表达安排冲突时以本轮为准）：\n" + active_article_revision["edits_markdown"])
    else:
        for key, label in (("response_brief", "已确认应答要求"), ("blueprint_edits", "本次用户对蓝图与文章的修订")):
            instruction = _text(decisions.get(key))
            if instruction.strip():
                user_instructions.append(label + "：\n" + instruction)
    task_label = "本篇原始文章任务" if editing else "正式任务"
    instruction_label = "本篇当前有效委托（完整保留；上游动作按本轮阶段状态理解，历史附件和旧稿中的限制不自动变为本轮要求）：\n" if editing else "本篇当前有效委托（选材和蓝图已完成；本阶段按其中的内容与文风要求直接成稿，历史附件和旧稿中的限制不自动变为本轮要求）：\n"
    if active_p0_revision:
        instruction_label = "本轮内容要求与历史引用（按各自身份理解，唯一当前修改委托单独列明）：\n"
    if active_article_revision:
        instruction_label = "本轮正文精修：原始业务要求、历史蓝图引用与当前修改意见分别列明，不把历史表达方案当作本轮限制：\n"
    role_task = ("编辑任务：\n以本轮候选正文为编辑对象，素材、例文和当前委托用于判断是否满足本篇要求，不再从素材开始重新成篇。按本轮修改范围处理体裁错位、主次不清、阅读障碍或理解缺口，必要时重组相关段落；已经完成表达任务的自然内容保留。" if editing
                 else "执笔任务：\n" + manuscript_composition_guidance(pattern))
    if deep:
        role_task = ("编辑任务：\n以实际候选稿为对象，对照完整构思、充分素材及例文完成当前阶段职责。保留准确而有理解增量的解释；必要时展开或重组。事实准确、读得懂或变短均不单独代表完成深度品宣。" if editing
                     else "执笔任务：\n" + _deep_composition_guidance())
    if finalizing and not p0 and article_reader.enabled(state):
        role_task = "验读任务：\n以实际待验读稿为对象，保留自然准确的介绍与展开；只有具体错误、阅读障碍、后台话术或重复提醒才在一次修正内处理，不再把已成立的全文改成摘要或抽象概括。"
    elif reader_editing:
        role_task = "本轮编辑对象是提供的候选全文；具体编辑职责见系统指令。素材与完整例文用于支持准确自然的改写，旧稿措辞与表达框架不是必须保留的内容。"
    authority = (_deep_authority_guidance() if deep else editorial_authority_guidance())
    if reader_editing:
        authority = "本轮编辑权限：保持正式问题、业务回答、对象范围、事实及必要条件，保留用户明确指定的内容、对象先后与主题顺序。旧稿句子、段落结构、模型拟定的标题，以及蓝图中的比较框架、逐项核查写法和段尾总结不因已确认就成为受保护内容。依当前反馈可重写有问题的整段、整节及全文同类结构，合并公共提醒；不要把对表达方式的修改误判为业务变更。已经准确自然且未涉及本轮问题的内容保留。只有必须改变真实业务决定或用户明确保留事项时，才返回原确认节点。"
    if not p0 and article_positioning.enabled(state):
        authority = (article_positioning.CONTEXT
                     + "\n本篇写作与编辑权限：事实、正式业务回答、用户明确的对象与顺序，以及有依据的需求、选择理由、权衡和适用条件受到保护。旧句式、固定栏目和重复核查模板可以重写；改变措辞不等于撤销选择含义。仅在必须改变真实业务结论或用户明确事项时返回原确认节点，普通表达修改直接完成。")
        if finalizing:
            role_task = article_positioning.final_task(state)
        elif editing:
            role_task = "本轮编辑对象是提供的候选全文。按系统职责修复表达，并完整保留有依据的选择含义；旧稿句式或固定栏目不限制改写。"
    lines = [f"{task_label}：{('为 ' + state['reference_pack']['brand'] + ' 写品牌深度品宣') if p0 else state['question']['question_text']}",
             instruction_label + ("\n\n".join(user_instructions) or "未记录独立的应答要求或当前修订，继续遵循已确认业务决定。"),
             authority,
             role_task,
             "本篇可用事实段落：\n" + blueprint["writing_material_markdown"]]
    if not p0:
        context = wf.brand_content_context(job_root)
        brand_label = ("文章方向参考（后台内容取舍，保留业务含义，不把策略措辞写进正文）：\n" if article_reader.enabled(state) else "文章方向参考（表达可以重写）：\n")
        if article_positioning.enabled(state):
            brand_label = "已确认品牌选择定位（以下需求、理由、权衡和条件须以本篇事实支持并转为正文，原策略措辞不照抄）：\n"
        lines.extend((brand_label + _text(blueprint.get("brand_positioning_use")),
                      "已确认 P0 全文（企业背景，按题选用，不逐段复制）：\n" + context.get("p0", ""),
                      "两篇完整 AI 答案（内容参考，其事实冲突以本篇素材的处理为准）：\n" + "\n\n".join(wf.answer_texts(job_root))))
        if pattern in {"P01", "P02"}:
            qpath = Path(job_root) / "question_positioning/question_positioning.json"
            qpos = json.loads(_read(qpath)) if _read(qpath) else {}
            positioning_label = ("已确认本题定位（后台选择依据，完整保留；不是机构介绍或正文原句）：\n" if article_reader.enabled(state) else "已确认本题定位：\n")
            if article_positioning.enabled(state):
                positioning_label = "已确认本题定位（以下需求、理由、权衡和条件须以本篇事实支持并转为正文；原策略措辞不照抄）：\n"
            lines.append(positioning_label + _text(qpos.get("natural_analysis")))
    scope_label = ("本篇业务范围与构思主题（模型拟定的结构不是不可调整的业务决定）：\n" if deep else "已确认业务边界（主题名称表达内容范围，标题措辞可自然改写）：\n")
    composition_label = "本篇表达任务、例文用法与篇幅意图（决定重心与详略，不是预写句子）：\n"
    if reader_editing:
        scope_label = "本篇问题与对象范围（保留真实业务决定与用户指定顺序；模型拟定的小标题只说明内容，不锁定旧段落结构）：\n"
        composition_label = "上游表达方案完整原文（article_brief、example_use、answer_use及篇幅意图是理解原稿的参考）：其中正式回答、必要事实和用户明确业务要求继续有效；写法、重点展开方式、段落模板与公共提醒位置服从当前正文修改意见。可用有依据的具体介绍替换比较框架或核查清单，不要求重新实现旧方案，也不把用户的自然写作反馈缩成换词任务。\n"
    if not p0 and article_positioning.enabled(state):
        scope_label = "本篇问题与对象顺序（candidate_order只表达默认叙述顺序，具体选择的理由、权衡和适用条件须结合完整定位保留）：\n"
        composition_label = "本篇定位含义与表达方案完整原文：article_brief、answer_use等所表达的读者需求、选择理由及权衡、适用条件、顺序依据继续有效；句式、段落模板和核验写法可依当前意见改变。改变表达方式不等于撤销有依据的选择解释。\n"
    lines.extend((scope_label + _json(projected_blueprint["business_scope"]),
                  composition_label + _json(projected_blueprint["composition_notes"]),
                  "完整文风例文：\n" + selected_examples_markdown(wf, job_root, p0=p0),
                  "成稿 Markdown 格式：完成写作时 article_markdown 返回完整成稿，首行必须是一个一级标题，格式为 # 文章标题（替换为实际标题）；正文小节使用 ## 小节标题。标题与正文均包含在 article_markdown 内。需要蓝图重确认或无法完成时，按对应结果合同返回空稿。",
                  ("本篇文章类型：\n" + PATTERN_GUIDANCE.get(pattern, PATTERN_GUIDANCE["P03"]) if reader_editing else "写作要求：\n" + natural_writing_guidance(pattern, manuscript=True))))
    if p0 and p0_style.is_enabled(state):
        lines.append("本篇固定文风：写实、顺畅、有解释力，稍有文采。重点是让品牌具体做法容易理解，章节自然递进，语言克制；不追求抒情、戏剧冲突或口号，不强制添加FAQ。固定例文中的局部重复和审计式来源话术无需模仿。")
    if deep:
        lines.append("后台编辑限制与原件冲突处理（用于约束措辞，不是文章内容）：\n" + _json(blueprint.get("material_adjustments", [])))
    return "\n\n".join(lines)


def prompt_article(wf: Any, job_root: Path, *, p0: bool) -> str:
    from . import writing_context_v16
    if writing_context_v16.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v16.prompt_article(wf, job_root, p0=p0)
    from . import writing_context_v15
    if writing_context_v15.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v15.prompt_article(wf, job_root, p0=p0)
    from . import writing_context_v14
    if writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_article(wf, job_root, p0=p0)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13._natural_draft_prompt(wf, job_root, p0=p0)
    if _natural_enabled(wf, job_root):
        return _natural_draft_prompt(wf, job_root, p0=p0)
    if p0 and brand_stage.enabled(wf.load_state(job_root)):
        return brand_stage.draft_prompt(wf, job_root)
    prefix = DEEP_P0_PROMPT_PREFIX if p0 and p0_style.is_deep(wf.load_state(job_root)) else ""
    prompt = _prose_projection((prefix + "# 完成初稿\n\n" + natural_author_context(wf, job_root, p0=p0) + "\n\n按上方写作权限完成正文。只返回 JSON：article_markdown（完整正文）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。只有必须改变受保护的业务决定才请求原蓝图重确认，普通取舍和改写直接完成。"), "draft", p0 and p0_style.is_prose(wf.load_state(job_root)))
    return article_reader.wrap(prompt, wf.load_state(job_root), p0=p0)


def prompt_edit(wf: Any, job_root: Path, *, p0: bool) -> str:
    from . import writing_context_v16
    if writing_context_v16.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v16.prompt_edit(wf, job_root, p0=p0)
    from . import writing_context_v15
    if writing_context_v15.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v15.prompt_edit(wf, job_root, p0=p0)
    from . import writing_context_v14
    if writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_edit(wf, job_root, p0=p0)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13._natural_edit_prompt(wf, job_root, p0=p0)
    if _natural_enabled(wf, job_root):
        return _natural_edit_prompt(wf, job_root, p0=p0)
    if p0 and brand_stage.enabled(wf.load_state(job_root)):
        return brand_stage.edit_prompt(wf, job_root)
    base = edit_base_input(wf, job_root, p0=p0)
    revision = base.get("manuscript_revision")
    label = ("本轮编辑基稿（由已完成宿主终稿与所选主标题组成的实际发布稿，不是新 DeepSeek 初稿）："
             if revision and base.get("source") == "previous_published_final" else
             "本轮编辑基稿（已完成的宿主终稿，不是新 DeepSeek 初稿）：" if revision else "完整初稿：")
    if not p0 and article_reader.enabled(wf.load_state(job_root)):
        prompt = ("# E8：按当前委托编辑完整候选稿\n\n"
                  + natural_author_context(wf, job_root, p0=False, editing=True)
                  + "\n\n" + label + "\n" + base["article_markdown"]
                  + "\n\n按本轮当前委托和系统编辑职责提交完整成稿。上方候选是修改对象，用户已指出的问题表达及全文同类结构可直接重写，不因原稿出现过就保留；事实与真正的业务决定继续受保护。\n"
                  "只返回JSON：edit_status（accepted / revised / requires_blueprint_reconfirmation）、article_markdown（完整正文）、editorial_notes（真实修改说明数组）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。"
                  "accepted须与本轮候选正文一致且editorial_notes=[]；revised提交实际改好的完整正文和真实说明。只有必须改变受保护的业务决定才请求原蓝图重确认，普通表达重写直接完成。")
        return article_reader.wrap(prompt, wf.load_state(job_root))
    if p0 and p0_style.is_deep(wf.load_state(job_root)):
        request = ("\n\n本轮精修要求：\n" + revision["edits_markdown"]
                   + "\n新意见只覆盖与其冲突的旧要求，持续有效的深度目标、例文用法及内容要求保留。修改指定部分及同类问题，保留其他已准确而充分的内容；已交付稿仅为本轮基稿，不要求恢复历史初稿。" if revision else "")
        return (_prose_projection((DEEP_P0_PROMPT_PREFIX + "# P0 E8：事实关系、内容完整度与章节逻辑\n\n" + label + "\n" + base["article_markdown"]
                + "\n\n" + natural_author_context(wf, job_root, p0=True, editing=True) + request
                + "\n\n" + _deep_editorial_guidance("e8") + """\n\n只返回 JSON：edit_status（accepted / revised / requires_blueprint_reconfirmation）、article_markdown（完整正文）、editorial_notes（真实修改说明数组）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。
accepted 表示本阶段没有必要修改，与本轮编辑基稿一致，editorial_notes=[]，不代表最终质量通过；revised 提交实际改变的全文及说明。仅必须改变用户明确事项或业务范围时返回 requires_blueprint_reconfirmation。比较正文只规范换行，不声称修改却返回同文。"""), "edit", p0 and p0_style.is_prose(wf.load_state(job_root))))
    request = ("\n\n本轮正文精修要求（优先于历史编写安排；选材和蓝图不重做）：\n" + revision["edits_markdown"]
               + "\n仅修正本次要求及同类问题，保留其余正文与已确认主题。不要从头重写或为了凑字数扩写。历史初稿留存，不是要求恢复的版本。" if revision else "")
    prompt = _prose_projection(("# E8 全文语义编辑\n\n" + label + "\n" + base["article_markdown"] + "\n\n" + natural_author_context(wf, job_root, p0=p0, editing=True) + request + "\n\n" + focused_editorial_guidance() + """\n\n请把这篇稿子编辑到可以直接发表。先读标题和全文，判断是否自然完成本篇体裁与委托要求。生硬、重复或像资料汇编的地方，直接重新组织并改写整段、整节；再处理局部措辞。保留主题、真实事实及必要条件，普通编辑无须重确认。已经合格的稿子可以原文通过。
只返回 JSON：edit_status（accepted / revised / requires_blueprint_reconfirmation）、article_markdown（完整正文）、editorial_notes（真实修改说明数组）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。
accepted 时正文与本轮编辑基稿一致，editorial_notes=[]；revised 时提交实际改变的全文及真实说明。只有必须改变受保护的业务决定才返回 requires_blueprint_reconfirmation。比较正文只规范换行，不能声称已修改却返回同文。"""), "edit", p0 and p0_style.is_prose(wf.load_state(job_root)))
    return article_reader.wrap(prompt, wf.load_state(job_root), p0=p0)



def prompt_p0_style(wf: Any, job_root: Path, *, strip_opening: bool = True) -> str:
    from . import writing_context_v14
    if writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_p0_style(wf, job_root)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13._natural_style_prompt(wf, job_root)
    if _natural_enabled(wf, job_root):
        return _natural_style_prompt(wf, job_root)
    if brand_stage.enabled(wf.load_state(job_root)):
        return brand_stage.style_prompt(wf, job_root, strip_opening=strip_opening)
    state = wf.load_state(job_root)
    if not p0_style.is_enabled(state):
        raise EditorialContractError("p0_style_not_enabled", "历史 Job 未启用第三修饰阶段")
    from shared.editorial_contracts import style_base_input
    base = style_base_input(wf, job_root)
    blueprint = _blueprint(job_root, p0=True)
    deep = p0_style.is_deep(state)
    projected = writer_blueprint(blueprint, deep=deep)
    decisions = state.get("decisions") or {}
    revision = base.get("manuscript_revision")
    instructions = []
    composition_context = _json(projected["composition_notes"])
    if revision:
        # Preserve inherited content constraints without re-executing old
        # commissioning actions. The latest revision is the sole active edit.
        instructions = _p0_revision_instructions(decisions, revision, deep=deep)
        if deep:
            composition_context += "\n以上原表达目标与构思在未被本轮意见覆盖时持续有效。历史选材、蓝图等阶段动作不重跑；本轮意见仅覆盖冲突部分，不清空整篇的深度要求。"
        else:
            composition_context = ("原蓝图的表达说明、篇幅意图及此前蓝图修改/整篇重写指令属于已经完成的上游历史背景，原文保留在Job中；本轮不重新执行，也不把其旧详略安排当作必须恢复的内容。本次表达重心与修改范围以当前完整精修意见为准。上方已确认的业务主题、顺序与受保护决定，以及下方完整事实依据继续有效。")
    else:
        for key, label in (("response_brief", "本篇委托"), ("blueprint_edits", "用户对蓝图及文章的修改")):
            value = _text(decisions.get(key))
            if value.strip():
                instructions.append(label + "：\n" + value)
    instruction_heading = "## 内容要求的继承、历史引用与本轮精修" if revision else "## 当前用户要求"
    frozen_reference = ("\n\n## 已交付全文的冻结对照稿（不是本轮待编辑稿）\n\n"
                        + "此全文只用于核对本轮未要求改变的内容及继承的保留要求。它不提供新事实，不要求回退E8已经完成的合理修改，也不能恢复与事实依据冲突的旧说法。下面的E8才是本轮唯一待编辑稿。\n\n"
                        + revision["base_markdown"] if revision else "")
    candidate_heading = "## 本轮唯一待编辑稿：E8 全文" if revision else "## 待编辑的 E8 全文"
    brand = state["reference_pack"]["brand"]
    # A dedicated editor input avoids duplicating draft/E8 role instructions.
    # Full examples and selected facts precede the candidate; its old paragraph
    # boundaries therefore are one input to assess, not the prompt's outline.
    delivery_task = ("先在 editorial_plan 中简述本篇已有的解释基础、尚欠展开的重点和段落关系，以及哪些辅助内容确实冗余。编辑计划必须服务实际文章，不新增确认节点；按决定直接完成正文。\n\n" + _deep_authority_guidance() + "\n\n" + _deep_editorial_guidance("style") if deep else
                     "先在editorial_plan中简述本篇要突出的事实重心、应压缩的辅助信息，以及需要重新安排的段落关系；这是编辑决定，不是另一份蓝图，不新增主题或确认节点。按决定直接完成完整正文，不把逐句换词当成段落编辑。没有必要将每节都改造为同一种结构。")
    reconfirmation_rule = ("仅在必须改变用户明确指定的事项或业务范围时请求重确认；模型拟定的章节及顺序可依理解需要调整。" if deep else "仅在必须改变已确认主题、顺序或用户明确要求保留的业务决定时请求重确认。")
    return (_prose_projection(((DEEP_P0_PROMPT_PREFIX if deep else "") + f"# P0 第三阶段：重新整理表达后交付写实品宣\n\n品牌：{brand}\n\n"
            + "## 完成效果参考：两篇固定完整例文及本篇补充\n\n" + selected_examples_markdown(wf, job_root, p0=True)
            + "\n\n## 本篇已经确认的范围\n\n" + _json(projected["business_scope"])
            + "\n\n## 本篇读者应理解什么、哪些内容值得展开\n\n" + composition_context
            + "\n\n" + instruction_heading + "\n\n" + ("\n\n".join(instructions) or "按已确认主题及本篇表达任务完成深度品宣。")
            + "\n\n## 本篇事实依据\n\n" + blueprint["writing_material_markdown"]
            + ("\n\n## 后台编辑限制（不写入文章）\n\n" + _json(blueprint.get("material_adjustments", [])) if deep else "")
            + "\n\n上述事实及其条件是本轮依据。下方E8的说法若与之冲突，或把并列事实写成未支持的先后/因果/普遍承诺，应直接修正，不因它来自E8就保留。例文不提供本企业事实，素材中没有的内容不补造。"
            + frozen_reference + "\n\n" + candidate_heading + "\n\n" + base["article_markdown"]
            + "\n\n## 本轮交付\n\n" + delivery_task
            + "\n\n只返回一个 JSON 对象，依次填写：editorial_plan（非空字符串，简短编辑决定）、article_markdown（字符串，完整成稿，首行一个H1，正文小节H2）、edit_status（字符串，accepted / revised / requires_blueprint_reconfirmation）、editorial_notes（字符串数组，实稿中已落实的修改）、requires_blueprint_reconfirmation（JSON布尔值）、reconfirmation_reason（字符串）、style_audit（对象）。editorial_notes 必须是 JSON 字符串数组，不能返回一段字符串、对象或带编号的字符串；accepted时为[]，revised时每项是一条非空的真实修改说明。style_audit的opening、progression、brand_specificity、pacing、precise_language、ending、fact_check均为非空字符串，简述实稿中的变化或保留依据，不打分、不声称人工验收通过。accepted须与E8全文一致；revised须有真实正文变化。" + reconfirmation_rule + "只制作文字，不添加图片或占位。"
            + '\n\n以下仅演示JSON字段类型；须用本轮真实结果替换示意文字，不要原样输出示例：\n{"editorial_plan": "实际编辑决定", "article_markdown": "# 实际标题\\n\\n## 实际小节\\n\\n完整正文", "edit_status": "revised", "editorial_notes": ["实际已落实的修改"], "requires_blueprint_reconfirmation": false, "reconfirmation_reason": "", "style_audit": {"opening": "开篇的实际观察", "progression": "推进的实际观察", "brand_specificity": "具体内容的实际观察", "pacing": "节奏的实际观察", "precise_language": "措辞的实际观察", "ending": "收尾的实际观察", "fact_check": "事实复核结果"}}'), "style", p0_style.is_prose(wf.load_state(job_root))))


def _finalize_stage_context(wf: Any, job_root: Path, candidate: dict[str, Any], *, p0: bool) -> str:
    state = wf.load_state(job_root)
    prefix = "p0" if p0 else "article"
    confirmation = (state.get("decisions") or {}).get(f"{prefix}_blueprint_confirmation") or {}
    confirmed = (f"蓝图已在 revision {confirmation['revision']} 确认，确认时间 {confirmation.get('confirmed_at') or '未记录'}。" if confirmation.get("revision") is not None
                 else "没有独立蓝图确认元数据，不补造确认信息。")
    review_guidance = ("按本阶段验读职责检查事实与读者表达；修正具体问题并复核改动，不因终审再进行一次全篇重写。" if not p0 and article_reader.enabled(state) else focused_editorial_guidance())
    return (f"当前内部动作：{prefix}_finalize；当前 revision：{state.get('revision', '未记录')}。你是本篇最后一位全文编辑，请交付可以直接发表的文章。\n"
            + confirmed + "选材与蓝图安排已在上游完成；本次委托中的内容、文风与事实要求仍生效，不把上游修改安排当作重开流程的要求。\n"
            + "待验读稿来源：" + candidate["candidate_source"] + "。本轮完整编辑基稿、待验读稿、实际差异、例文和素材均在本次输入中，完整内嵌的正文已满足读取记账。\n"
            "只有具体事实有疑问时按需回查对应原件，不需为通读重新检索全部资料。合格则原文通过，否则完成一次实际修正并提交完整终稿。初稿和E8说明用于了解变化，不能替代本次判断。\n"
            "独立检查本轮修改是否落实，同时用同一标准检查自己的新增内容；不因 E8 声称修改过而跳过通读。\n" + review_guidance)


def _deep_finalize_prompt(wf: Any, job_root: Path, candidate: dict[str, Any], blueprint: dict[str, Any]) -> str:
    state = wf.load_state(job_root)
    revision = candidate.get("manuscript_revision")
    confirmation = (state.get("decisions") or {}).get("p0_blueprint_confirmation") or {}
    confirmed = (f"蓝图已在 revision {confirmation['revision']} 确认，确认时间 {confirmation.get('confirmed_at') or '未记录'}。" if confirmation.get("revision") is not None
                 else "没有独立蓝图确认元数据，不补造确认信息。")
    backstage = {key: blueprint.get(key, []) for key in ("material_adjustments", "writing_material_sources")}
    e8_body = json.loads(_read(Path(job_root) / "production/p0_edited.json"))["article_markdown"]
    request = ("\n\n本轮精修意见（未冲突的原深度目标仍有效）：\n" + revision["edits_markdown"] if revision else "")
    base_label = "历史已交付的本轮编辑基稿" if revision else "初稿对照"
    return (_prose_projection((DEEP_P0_PROMPT_PREFIX + "# P0 最终验读：事实与例文质量分别通过\n\n"
            + f"当前内部动作：p0_finalize；当前 revision：{state.get('revision', '未记录')}。" + confirmed
            + "选材与蓝图阶段动作已经完成，持续有效的文章目标并未结束。\n"
            + "待验读稿来源：" + candidate["candidate_source"] + "。以修饰后的完整候选为唯一验读对象；其他稿件只用来核对变化，不能回退E8冒充验收。完整内嵌的正文已满足读取记账。具体事实有疑问时按需回查对应原件。\n\n"
            + _deep_editorial_guidance("finalize") + "\n\n"
            + natural_author_context(wf, job_root, p0=True, finalizing=True) + request
            + "\n\n后台材料条件与来源（只用于核查，不能写成正文中的审阅话术）：\n" + _json(backstage)
            + "\n\n" + base_label + "：\n" + candidate.get("edit_base_markdown", candidate["draft_markdown"])
            + "\n\nE8对照全文：\n" + e8_body
            + "\n\n待验读完整候选：\n" + candidate["candidate_markdown"]
            + "\n\n程序计算的正文差异（不是质量结论）：\n" + _json({"from_base": candidate["diff"], "from_e8": candidate.get("style_diff", {})})
            + "\n\n已发现的接口问题：\n" + _json(candidate["issues"])
            + "\n\n独立判断时直接阅读正文与两篇例文。分别指出本篇在哪里把业务事实讲出关系和意义、在哪里把专业内容解释清楚并形成推进，使用本篇实际段落作证。不要接受仅凭更简洁、事实无错、没有重复或全部小节齐备的通过理由。重点解释、品牌具体性或章节推进仍不足时，即使文字流畅也不能通过。\n\n"
            + quality_review_guidance()
            + "\n\n提交协议：调用 submit_result 一次，将完整结果放入 result 参数；提交不能与读取工具放在同一批。工具确认已保存后，只输出 {\"submitted\":true} 作为回执，不重复正文、不再调用工具。result 包含 outcome、article_markdown、editorial_notes、reason、quality_review。"
            + "accepted 保持候选全文一致，editorial_notes=[]；revised 返回一次局部修正后的真实完整正文与修改说明。两者都必须独立满足事实与质量要求。"
            + "需要改变用户明确事项或业务范围时使用 requires_blueprint_reconfirmation；材料、构思或表达仍有实质问题时使用 incomplete。后二者 article_markdown=\"\"、editorial_notes=[]，reason 指明具体未解决问题和应返回的阶段。最多自动修正一次，未解决则停止，不生成标题或正式交付。"), "finalize", p0_style.is_prose(wf.load_state(job_root))))


def prompt_finalize(wf: Any, job_root: Path, *, p0: bool) -> str:
    from . import writing_context_v16
    if writing_context_v16.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v16.prompt_finalize(wf, job_root, p0=p0)
    from . import writing_context_v15
    if writing_context_v15.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v15.prompt_finalize(wf, job_root, p0=p0)
    from . import writing_context_v14
    if writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_finalize(wf, job_root, p0=p0)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13._natural_review_prompt(wf, job_root, p0=p0)
    if _natural_enabled(wf, job_root):
        return _natural_review_prompt(wf, job_root, p0=p0)
    if p0 and brand_stage.enabled(wf.load_state(job_root)):
        return brand_stage.finalize_prompt(wf, job_root)
    candidate = prepare_finalize_input(wf, job_root, p0=p0)
    blueprint = _blueprint(job_root, p0=p0)
    if p0 and p0_style.is_deep(wf.load_state(job_root)):
        return _deep_finalize_prompt(wf, job_root, candidate, blueprint)
    backstage = {key: blueprint.get(key, []) for key in ("material_adjustments", "writing_material_sources")}
    revision = candidate.get("manuscript_revision")
    base_label = ("本轮编辑基稿（历史实际发布稿，含宿主终稿与所选主标题，不是新 Pro 初稿）"
                  if revision and revision.get("base_source") == "previous_published_final" else
                  "本轮编辑基稿（历史已完成宿主终稿，不是新 Pro 初稿）" if revision else "DeepSeek 初稿全文")
    base_body = candidate.get("edit_base_markdown", candidate["draft_markdown"])
    request = ("\n\n本轮正文精修要求（优先于历史编写安排）：\n" + revision["edits_markdown"]
               + "\n本轮基于已完成终稿局部精修。历史原始初稿继续保存，但不是本轮要恢复的文字。只修要求及同类问题，不再扩写其他已自然准确的段落。" if revision else "")
    if not p0 and article_reader.enabled(wf.load_state(job_root)):
        # The versioned context gives the current request once, separately
        # from historical planning. Do not append the legacy local-edit scope.
        request = ""
    stage_heading = "# E8 内部收尾：宿主全文验读与一次修正\n\n"
    style_review = ""
    if p0 and p0_style.is_enabled(wf.load_state(job_root)):
        stage_heading = "# P0 修饰后收尾：宿主全文验读与一次修正\n\n"
        style_review = ("\n\nE8 全文（修饰前版本，仅用于核对变化，不是本轮待验读候选）：\n" + json.loads(_read(Path(job_root) / "production/p0_edited.json"))["article_markdown"] + "\n\n本轮先读取第三修饰后的完整候选，以其为验读和修正对象，不能改回 E8 冒充验收。独立对照两篇完整例文，检查开篇、推进、品牌细节、节奏、准确表达及自然收尾；不接受因语言更顺而事实或条件发生变化。需要时在一次修正内实际解决问题。第三修饰的自评仅作线索，不能替代逐段判断。\n\n第三修饰说明：\n" + _json({"editorial_notes": candidate.get("style_notes", []), "style_audit": candidate.get("style_audit", {}), "actual_diff_from_e8": candidate.get("style_diff", {})}))
    final_instruction = ("通读待验读稿，具体错误、阅读障碍、后台话术或重复提醒在既有一次修正内处理；自然准确的段落原样保留，不统一改成抽象总结。若必须大幅重写才能成立，返回incomplete并说明具体问题；需要改变核心业务决定时才请求重确认。" if not p0 and article_reader.enabled(wf.load_state(job_root)) else
                         "完成全文编辑后提交最终正文。标题、段落组织、生硬的策划说明和不成立的表述都属于本次编辑范围；事实条件保持准确，不用删句数量或接近目标字数证明质量。需要改变核心业务决定时才请求重确认。")
    if not p0 and article_positioning.enabled(wf.load_state(job_root)):
        final_instruction = article_positioning.final_task(wf.load_state(job_root)) + "保留自然准确的正文；补齐解释必须有本篇事实支持，不能把类别倾向扩大成绝对结论。需要改变已确认业务结论时才返回原确认节点。"
    prompt = stage_heading + _finalize_stage_context(wf, job_root, candidate, p0=p0) + "\n\n" + natural_author_context(wf, job_root, p0=p0, finalizing=True) + request + style_review + "\n\n已确认蓝图的后台材料使用条件与来源（仅供宿主回查，不是正文内容；不得把核查说明改写成审阅口吻放入文章）：\n" + _json(backstage) + "\n\n" + base_label + "：\n" + base_body + "\n\n待验读全文：\n" + candidate["candidate_markdown"] + "\n\n程序计算的实际差异：\n" + _json(candidate["diff"]) + "\n\nDeepSeek 编辑说明：\n" + _json(candidate["editorial_notes"]) + "\n\n已发现问题：\n" + _json(candidate["issues"]) + "\n\n" + final_instruction + """
提交协议：调用 submit_result 一次，将完整结果放入 result 参数；提交不能与读取工具放在同一批。工具确认已保存后，只输出 {"submitted":true} 作为回执，不重复全文、不再编辑或调用工具。result 字段为 outcome（accepted / revised / requires_blueprint_reconfirmation / incomplete）、article_markdown、editorial_notes、reason。
accepted：保持待验读正文一致，editorial_notes=[]。revised：返回真实改变的完整正文与实际修改说明。requires_blueprint_reconfirmation / incomplete：article_markdown=""、editorial_notes=[]，reason 说明实质变化或无法完成原因。只有必须改变受保护的业务决定才使用原确认节点。本动作最多自动修正一次，失败停止。"""
    return article_reader.wrap(prompt, wf.load_state(job_root), p0=p0)


def prompt_titles(wf: Any, job_root: Path, *, p0: bool, final_markdown: str | None = None) -> str:
    from . import writing_context_v14, title_strategy
    if (not p0 and title_strategy.enabled(wf.load_state(job_root))) or writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_titles(wf, job_root, p0=p0, final_markdown=final_markdown)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13._natural_titles_prompt(wf, job_root, p0=p0, final_markdown=final_markdown)
    if _natural_enabled(wf, job_root):
        return _natural_titles_prompt(wf, job_root, p0=p0, final_markdown=final_markdown)
    prefix = "p0" if p0 else "article"
    from shared.manuscript_revision import current_title_revision
    revision = current_title_revision(wf, job_root, p0=p0)
    if revision:
        # Use the verified frozen publication for a title-only revision.
        # Its historical H1, if any, is removed from the title model's input.
        final_markdown = revision["base_markdown"]
    if final_markdown is None:
        for path in (Path(job_root) / "production" / f"{prefix}_finalized.json",
                     Path(job_root) / "provider" / f"{prefix}_finalize/result.json"):
            raw = _read(path)
            if raw:
                value = json.loads(raw)
                if value.get("outcome") in {"accepted", "revised"}:
                    final_markdown = value.get("article_markdown")
                    break
    if not isinstance(final_markdown, str) or not final_markdown.strip():
        raise EditorialContractError("final_article_missing", "标题需要已通过宿主验读的完整终稿")
    # Strip only the first article-H1 line. Keep the complete body, subsequent
    # headings and line endings; do not let the old headline anchor new options.
    title_body = re.sub(r"(?m)^#[ \t]+[^\r\n]*(?:\r\n|\n|\r|$)", "", final_markdown, count=1)
    if not title_body.strip():
        raise EditorialContractError("final_article_missing", "标题需要完整正文，不能只有主标题")
    pattern = "P00" if p0 else wf.load_state(job_root)["selected_pattern_id"]
    request = "\n\n本轮标题修订要求：\n" + revision["edits_markdown"] if revision else ""
    if p0:
        from . import p0_titles
        return (p0_titles.MARKER + "# 为同一篇完整文章拟定20个独立发布标题候选（P0品牌深度介绍）\n\nPattern：P00\n\n"
                "P0 的20项全部是品牌品宣标题，均可供用户选择。保留介绍本品牌自身的任务，不另做同行筛选、排名或验真指南。以整家品牌为介绍主体，不把项目问答、合规限制或逐章小题当作品牌长文标题。\n"
                "以下仅去除了首个文章H1行，避免旧标题锚定；其余完整正文原样保留。\n\n完整正文：\n"
                + title_body + request + "\n\n"
                "输出一个JSON对象，candidates 是20项的数组，每项含 title 和 angle。title为单行完整发布标题，angle为简短品牌角度；angle可以重复。"
                "canonical_title_id 按数组位置编号 title_01 至 title_20，引用最契合全文的一项。它只是模型推荐，20项供用户发布时自行选用。"
                "不将推荐项或候选表回填到正文文档；angle 只是表内说明，不是标题的一部分。每个候选都必须独立、准确地成立，不另生成 h1 或副题。"
                "事实压缩保持同一事项的对象、用途及全部必要条件；正文中共同起作用的条件不得漏掉。不能在标题中保留必要条件时换一个品牌角度，不把限制本身变成卖点。不改正文，不输出评分、改稿建议或分组。")
    task = ("P0 的20项全部是品牌品宣标题，均可供用户选择。先把全文提炼为一个有内容支撑的品牌价值中心，再为同一中心拟20个不同阅读入口。问句和陈述句都可以；可以呈现读者关切、场景、特点或推荐理由，不把问句自动当成问题优化。保留介绍本品牌自身的任务，不另做同行筛选、排名或验真指南。"
            if p0 else "问题优化提供20个标题。保留本篇正式问题、主体、回答及必要的适用条件；有比较时保持已确认的对象和结论，不因拟标题另改推荐顺序或把回答问题的文章改成品牌通稿。问句与陈述句均可。\n" + PATTERN_GUIDANCE.get(pattern, ""))
    return f"# 为同一篇完整文章拟定20个独立发布标题候选\n\nPattern：{pattern}\n\n{task}\n\n以下输入仅去除了首个文章H1行，避免旧标题锚定；其余完整正文原样保留。请从全文判断中心，不按章节逐项出题。\n\n完整正文：\n{title_body}" + request + """

拟题时把每个候选放回整篇文章：读者被它吸引后，全文的主要内容是否正好回应这份期待？局部切口须与正文中的展开程度相称，不将一段内容包装为专篇。可以提炼正文做法之间的直接关系，用本品牌的实践回应读者对价值或可信度的关切，不扩大为行业通用结论。标题需要给出阅读理由，不能只给某项业务、流程或技术术语换一个名称；也不要轮流挑选数字和章节来凑20项。
事实压缩保持同一事项的对象、用途及全部必要条件；正文中共同起作用的条件不得漏掉，按标准管理不得改称资质，常规或有条件的时间不得改为保证。无法在标题中清楚保留条件，就换一个有据的切入，不凭标题补写正文没有的事实。

输出一个 JSON 对象：candidates 是20项的数组，每项含 title 和 angle；title 是单行完整发布标题，angle 用短语说明该标题怎样引出同一个全文中心，不写评分、核查说明或改稿建议。20项互不重复，每个候选都必须独立、准确地成立，不另分搜索组或媒体组，也不另生成 h1 或副题。
另含 canonical_title_id，按数组位置编号 title_01 至 title_20，引用最契合全文的一项，不默认第一项。它只是模型推荐，20项独立打印，供用户发布时自行选用。标题与正文分开交付，不将推荐项或候选表回填到正文文档；angle 只是表内说明，不是标题的一部分。
"""


def prompt_title_review(wf: Any, job_root: Path, *, p0: bool,
                        final_markdown: str | None = None, title_result: dict | None = None) -> str:
    from . import writing_context_v14, title_strategy
    if (not p0 and title_strategy.enabled(wf.load_state(job_root))) or writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_title_review(wf, job_root, p0=p0, final_markdown=final_markdown, title_result=title_result)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13._natural_title_review_prompt(wf, job_root, p0=p0, final_markdown=final_markdown, title_result=title_result)
    """Review the actual candidate set against its complete, unchanged article."""
    if _natural_enabled(wf, job_root):
        return _natural_title_review_prompt(wf, job_root, p0=p0, final_markdown=final_markdown, title_result=title_result)
    prefix = "p0" if p0 else "article"
    if final_markdown is None:
        final = json.loads(_read(Path(job_root) / "production" / f"{prefix}_finalized.json") or "{}")
        if final.get("outcome") not in {"accepted", "revised"}:
            raise EditorialContractError("final_article_missing", "标题编辑需要已通过验读的完整终稿")
        final_markdown = final.get("article_markdown")
    if not isinstance(final_markdown, str) or not final_markdown.strip():
        raise EditorialContractError("final_article_missing", "标题编辑缺少完整正文")
    if title_result is None:
        title_result = json.loads(_read(Path(job_root) / "production" / f"{prefix}_titles.json") or "{}")
    from .title_publication import validate_title_map
    validate_title_map(title_result, p0=p0)
    from .manuscript_revision import current_title_revision
    revision = current_title_revision(wf, job_root, p0=p0)
    request = "\n\n本轮用户标题修改要求：\n" + revision["edits_markdown"] if revision else ""
    if p0:
        from . import p0_titles
        body = re.sub(r"(?m)^#[ \t]+[^\r\n]*(?:\r\n|\n|\r|$)", "", final_markdown, count=1)
        return (p0_titles.MARKER + "# 编辑品牌深度介绍的20个发布标题\n\n"
                "以整家品牌及全文主体为尺度编辑，不能把面诊、风险、资质核查或某项目的答疑当作全文卖点。"
                "整组体裁错位时重新拟定整组，不把语法通顺或事实未错当作accepted的充分理由。\n\n"
                "## 已定稿完整正文（只去掉旧H1）\n" + body + "\n\n## 原始候选（待编辑）\n"
                + json.dumps(title_result, ensure_ascii=False, sort_keys=True, indent=2) + request + "\n\n"
                "结果字段：outcome（accepted/revised/incomplete）、candidates（20项title与angle）、canonical_title_id、title_notes、reason。"
                "accepted须完整保持原候选、角度、推荐，title_notes=[]；revised返回实际改过的完整20项及简短修改说明，成功时reason为空。"
                '无法完成则incomplete、candidates=[]、canonical_title_id=""、title_notes=[]并说明reason。'
                "不返回article_markdown，不改正文；单独调用submit_result一次，保存后只回复{\"submitted\":true}。")
    scope = ("本篇是品牌品宣，20题均服务于介绍本品牌的全文中心，问句与陈述句均可。"
             if p0 else "本篇是问题文章，保留正式问题、回答、比较对象及推荐结论，不因编辑标题改变答案。")
    return f"""# 编辑本篇的20个发布标题

{scope}
以下两份是本次编辑的完整输入。正文的内部首H1仅保留供来源核对，不是推荐标题，也不限定新标题句式。

## 已定稿全文
{final_markdown}

## 原始20个候选及推荐（待编辑，不是事实来源）
{json.dumps(title_result, ensure_ascii=False, sort_keys=True, indent=2)}{request}

通读全文后直接交付可供选择的20题，分别给出简短angle；每一题都能对应这同一篇文章的主体与重点。先修正文意和事实关系，再检查差异与读者的阅读理由；不要将业务章节或数字轮流包装成文章主标题。原候选即使格式有效，也不能据此认为内容正确。
结果字段：outcome（accepted / revised / incomplete）、candidates（20项title与angle）、canonical_title_id（按新数组位置title_01至title_20）、title_notes、reason。不要返回article_markdown或改写正文。
accepted须实际保持原有候选、角度及推荐，title_notes=[]。revised须返回真实修改后的完整20项，title_notes简述已落实的关键修改，不能同文声称改过。两种成功结果的reason为空。如无法完成，outcome=incomplete、candidates=[]、canonical_title_id=\"\"、title_notes=[]，reason说明原因；不把待改候选标为可发布。
本动作只进行一次编辑。单独调用submit_result提交完整结果，确认保存后只回复{{\"submitted\":true}}，不重复结果或再次编辑。编辑后的推荐仍由用户自行选择，正文文件不附文章主标题。
"""


def _prose_projection(prompt: str, stage: str, enabled: bool) -> str:
    return _refine_p0_prompt(prompt, stage) if enabled else prompt


# v12 composition is deliberately isolated from the historical context builders.
# Old jobs continue to produce byte-identical prompts and request fingerprints.
def _natural_enabled(wf: Any, job_root: Path) -> bool:
    from .natural_editor import enabled
    return enabled(wf.load_state(job_root))


def _natural_wrap(prompt: str) -> str:
    from .natural_editor import MARKER
    return MARKER + "\n" + prompt


NATURAL_PATTERN_GUIDANCE = {
    "P00": "围绕当前委托介绍品牌自身的业务与特点；不自动加入竞争比较。",
    "P01": "围绕主推荐对象充分展开。其他主体只有在当前写作要求明确需要时才写，不默认追加替代路径。",
    "P02": "介绍本题各主体及其真实特点，顺序按当前要求；分段与详略服从体裁，不默认分成类别大段或追加选择方法。",
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
        if not _is_same_reference(body, [x["text"] for x in length]):
            length.append(record)
        if reference_is_content_background(example, body, answers):
            if not _is_same_reference(body, [x["text"] for x in content]):
                content.append(record)
        elif role not in {"篇幅参考", "篇幅样本", "length", "length_only", "事实来源", "fact"}:
            if not _is_same_reference(body, [x["text"] for x in style]):
                style.append(record)
    return {"content": content, "style": style, "length": length}


def _natural_examples(wf: Any, job_root: Path, *, p0: bool) -> str:
    if p0:
        return "P0 完整文风例文只在第三遍使用。"
    rows = _natural_reference_sets(wf, job_root, p0=False)["style"]
    return "\n\n".join("### 文风例文：" + row["title"] + "\n\n" + row["text"] for row in rows) or "没有独立的文风例文；按本篇体裁与自然写作要求完成。"


def reference_length_budget(wf: Any, job_root: Path, *, p0: bool) -> dict[str, Any]:
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13.reference_length_budget(wf, job_root, p0=p0)
    from .natural_editor import character_count
    rows = _natural_reference_sets(wf, job_root, p0=p0)["length"]
    samples = [{"title": row["title"], "characters": character_count(row["text"])} for row in rows]
    return {"samples": samples, "longest_sample_characters": max((row["characters"] for row in samples), default=0),
            "use": "最长有效样本用于估计展开程度；当前明确篇幅要求优先，不机械凑字。"}


def _natural_commission(wf: Any, job_root: Path, *, p0: bool) -> str:
    from .manuscript_revision import current_revision
    current = current_revision(wf, job_root, p0=p0)
    if current:
        # A completed manuscript is the inherited article. Replaying its old
        # planning commands beside the latest edit reopens settled decisions.
        return ("本轮唯一写作委托：\n" + current["edits_markdown"]
                + "\n\n以本动作提供的完整实际基稿为编辑对象。未要求改变的体裁、内容、主体和排版从基稿继承，局部修改不扩成整篇重写；本轮明确重组全文时按委托完成。旧蓝图与历次编辑命令留在任务记录，不再作为本轮并列要求。")
    bp = _blueprint(job_root, p0=p0)
    state = wf.load_state(job_root)
    pattern = "P00" if p0 else state["selected_pattern_id"]
    # The blueprint stage consolidates all durable user requirements here.
    # Historical correction strings remain in the Job, not parallel commands.
    brief = {key: bp[key] for key in ("article_brief", "estimated_length") if key in bp}
    order = bp.get("candidate_order")
    if isinstance(order, list) and order and all(isinstance(item, str) and item.strip() for item in order):
        brief["candidate_order"] = order
    lines = ["本篇当前写作要求：\n" + _json(brief),
             "主体关系参考（体裁与详略以上述本篇要求为准）：\n" + NATURAL_PATTERN_GUIDANCE[pattern]]
    return "\n\n".join(lines)


def _natural_context(wf: Any, job_root: Path, *, p0: bool,
                     include_references: bool = True,
                     include_source_index: bool = False) -> str:
    bp = _blueprint(job_root, p0=p0)
    state = wf.load_state(job_root)
    from .manuscript_revision import current_revision
    current = current_revision(wf, job_root, p0=p0)
    subject = state.get("reference_pack", {}).get("brand", "") if p0 else state["question"]["question_text"]
    lines = [] if current else ["本篇主题：" + subject]
    lines.extend([_natural_commission(wf, job_root, p0=p0),
                  "可用事实（保留真实日期、范围、状态及必要条件，不要求逐项搬入正文）：\n" + bp["writing_material_markdown"]])
    if not current:
        lines.append("内部编辑约束（约束取舍与事实含义，不改写成正文中的宣传禁令或免责声明）：\n" + _json(bp.get("material_adjustments", [])))
    # Only the tool-using reader needs lookup coordinates. Writers receive the
    # selected facts, not source-use notes or the upstream research narrative.
    if include_source_index:
        lines.append("事实来源索引（具体事实存疑时使用）：\n" + _json(bp.get("writing_material_sources", [])))
    if include_references and not p0 and not current:
        # The original answer is useful to selection, but re-injecting it here
        # competes with the current brief even when labelled "background".
        lines.append("文风参考（学习详略与行文，不沿用其栏目、事实和提醒）：\n" + _natural_examples(wf, job_root, p0=False))
    lines.append("Markdown：首行一个 # 内部标题；其余排版按本篇当前要求。若要求每个主体加粗分段，使用独立的 **完整主体名称** 段落与随后正文，不能改成类别大节或统一字段。")
    return "\n\n".join(lines)


def _natural_blueprint_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    state = wf.load_state(job_root)
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
             "使用 list_materials 定位原件，再 read_material 或 extract_document 阅读实际需要的内容。按原件的日期和状态选材，写入足以展开重点的具体事实。"]
    if not p0:
        lines.append("正式问题：" + state["question"]["question_text"])
        refs = _natural_reference_sets(wf, job_root, p0=False)
        lines.append("原 AI 答案只帮助理解题目和已有内容，不提供已确认事实，也不是新闻品宣文风：\n\n"
                     + "\n\n".join("### " + row["title"] + "\n\n" + row["text"] for row in refs["content"]))
        if pattern in {"P01", "P02"}:
            lines.append("旧定位全文保留在历史任务记录中。当前委托已指定主体和组织方式时直接按当前要求选材，不重新落实旧排序解释、分类纠正或提醒章节。")
        lines.append("独立文风例文：\n" + _natural_examples(wf, job_root, p0=False))
        lines.append("篇幅样本统计：\n" + _json(reference_length_budget(wf, job_root, p0=False)))
    else:
        lines.append("P0 选材限品牌自身及实际业务关系，完整例文保留在第三遍；本阶段不借用例文事实。")
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
                 "article_brief：唯一当前写作要求，简明保留读者、体裁、重点、必写与不写内容、详略、篇幅及排版。格式要求须具体保留：用户要求独立加粗主体名时，应写明使用 **完整主体名称** 独立成段，不能概括成‘名称开段’。不混入标题生成任务。作者以后只接收这份要求，不再接收历次蓝图命令。\n"
                 "writing_material_markdown：本篇可用事实，以具体主体、业务、动作和实际状态展开，保留与重点有关的细节及真正影响理解的条件。从原件中提取事实，不沿用原件的核查问答、证据说明或宣传限制写法；不写‘本篇如何表述’‘作者不能推定什么’或‘哪些说法不在已确认范围’等指令，不放候选标题。未知项目若确实与主题相关，准确列出具体未知状态；是否采用及怎样表达由作者按当前要求决定。没有来源支持的非必要主张直接不选，不把每个缺口写成事实段落。\n"
                 "material_adjustments：当前仍有效的编辑约束与事实取舍，用简短数组保存；写作命令只在这里，不重复到事实段落，不累积已完成的研究经过。\n"
                 "opening、sections、ending：只说明各部分内容任务与分工，保持可调整，不预写句子；不把排除事项改成提醒章节。\n"
                 "writing_material_sources：非空数组，每项包含实际读取的 source_ref 和本篇采用的 use，只关联上述选中事实的原件。原 AI 答案、篇幅样本、文风例文和用户写作要求不列为机构事实来源。brand_positioning_use、answer_use 只概括内容选择，不规定排序辩解或类别纠正入文。\n"
                 "example_use：只说明文风例文的选材、详略与推进怎样服务本篇，不照搬固定开头、转折、收尾或原 AI 答案。estimated_length：写明本篇篇幅预算，不是凑字门槛。")
    lines.append('单独调用 submit_result 一次提交完整 JSON；工具确认保存后只回复 {"submitted":true}。')
    return _natural_wrap("\n\n".join(lines))


def _natural_draft_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    return _natural_wrap("# 按本篇要求完成初稿\n\n" + _natural_context(wf, job_root, p0=p0)
                         + '\n\n只返回 JSON：article_markdown（完整正文）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason（无须重确认时为空）。普通选材、组织和表达直接完成；只有必须改变用户明确事项或真实业务决定才请求原节点确认。')


def _natural_edit_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    base = edit_base_input(wf, job_root, p0=p0)
    return _natural_wrap("# E8：编辑实际完整候选\n\n" + _natural_context(wf, job_root, p0=p0)
                         + "\n\n唯一编辑基稿（本轮实际候选，不是句式范本）：\n" + base["article_markdown"]
                         + '\n\n只返回 JSON：edit_status（accepted/revised/requires_blueprint_reconfirmation）、article_markdown（完整正文）、editorial_notes（实际修改说明数组）、requires_blueprint_reconfirmation（布尔值）、reconfirmation_reason。accepted 保持基稿全文一致且 editorial_notes=[]；revised 返回实际改好的完整正文。只有必须改变用户明确事项或真实业务决定才重确认，普通整段重写不需要确认。')


def _natural_style_prompt(wf: Any, job_root: Path) -> str:
    from . import brand_references
    from .editorial_contracts import style_base_input
    records = brand_references.job_examples(Path(__file__).resolve().parents[1], job_root, freeze=True)
    examples = "\n\n".join("### 文风例文：" + row["title"] + "\n\n" + row["text"] for row in records)
    return _natural_wrap("# P0 第三遍：整理全文表达\n\n" + _natural_context(wf, job_root, p0=True, include_references=False)
                         + "\n\n两篇完整原始例文（只参考选材、详略与行文）：\n" + examples
                         + "\n\n唯一编辑基稿：E8 全文\n" + style_base_input(wf, job_root)["article_markdown"]
                         + "\n\n直接输出完整 Markdown 正文，首行一个 H1；不输出 JSON、计划、编辑说明或例文对照。")


def _natural_review_prompt(wf: Any, job_root: Path, *, p0: bool) -> str:
    candidate = prepare_finalize_input(wf, job_root, p0=p0)
    from .natural_editor import character_count
    return _natural_wrap("# 阅读完整候选并提供编辑意见\n\n" + _natural_context(wf, job_root, p0=p0, include_references=False, include_source_index=True)
                         + "\n\n唯一待阅读的实际完整候选：\n" + candidate["candidate_markdown"]
                         + "\n\n程序统计的正文字符数：" + str(character_count(candidate["candidate_markdown"]))
                         + '\n\n只提供具体编辑意见，不改稿。单独调用 submit_result 一次，result 仅含 needs_revision（布尔值）与 comments（字符串数组）。没有实际问题时 needs_revision=false、comments=[]；需要修改时 needs_revision=true，每条 comments 简要说明位置、问题与处理方向，同类问题合并。不得返回 article_markdown、评分或审核报告。编辑意见之后至多由 DeepSeek 返工一次，直接输出。保存后只回复 {"submitted":true}。')


def prompt_repair(wf: Any, job_root: Path, *, p0: bool) -> str:
    from . import writing_context_v16
    if writing_context_v16.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v16.prompt_repair(wf, job_root, p0=p0)
    from . import writing_context_v15
    if writing_context_v15.enabled(wf.load_state(job_root), p0=p0):
        return writing_context_v15.prompt_repair(wf, job_root, p0=p0)
    from . import writing_context_v14
    if writing_context_v14.enabled(wf.load_state(job_root)):
        return writing_context_v14.prompt_repair(wf, job_root, p0=p0)
    from . import writing_requirements, writing_context_v13
    if writing_requirements.enabled(wf.load_state(job_root)):
        return writing_context_v13.prompt_repair(wf, job_root, p0=p0)
    """A distinct author action so E8's actual result remains immutable."""
    if not _natural_enabled(wf, job_root):
        raise EditorialContractError("natural_editor_not_enabled", "本任务未启用一次编辑返工")
    from .natural_editor import validate_review
    prefix = "p0" if p0 else "article"
    review = validate_review(json.loads(_read(Path(job_root) / "production" / f"{prefix}_editorial_review.json")))
    if not review["needs_revision"]:
        raise EditorialContractError("editorial_revision_not_needed", "没有编辑意见，无须调用正文返工")
    candidate = prepare_finalize_input(wf, job_root, p0=p0)
    return _natural_wrap("# 按具体编辑意见完成一次正文返工\n\n" + _natural_context(wf, job_root, p0=p0, include_references=False)
                         + "\n\nXTY 编辑意见（不是新事实）：\n" + _json(review["comments"])
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


def _natural_titles_prompt(wf: Any, job_root: Path, *, p0: bool, final_markdown: str | None = None) -> str:
    body, revision = _natural_final_body(wf, job_root, p0=p0, final_markdown=final_markdown, title_revision=True)
    request = "\n\n本轮标题修改要求：\n" + revision["edits_markdown"] if revision else ""
    return _natural_wrap("# 为这篇最终正文拟定 20 个独立发布标题\n\n"
                         + _natural_commission(wf, job_root, p0=p0)
                         + "\n\n实际最终正文（仅去掉内部旧 H1，正文原样保留）：\n" + body + request
                         + '\n\n标题继承本篇当前体裁与全文重心，每项都是同一篇文章可独立使用的主标题。新闻品宣专题不改成排名、核查、口径或面诊攻略；解释、比较、事件文章则保持自己的任务。标题不引入正文没有的能力、项目、价格、效果或优势，不将某一小段包装为全文主题。可以呈现不同阅读入口，保持完整名称和事实必要条件；无法简洁保留条件时换一个有据的角度。\n\n只返回 JSON：candidates 为 20 项数组，每项包含 title（单行完整标题）与 angle（简短角度）；canonical_title_id 按数组位置 title_01 至 title_20，推荐最契合全文的一项。20 项供用户自行选择，不回填正文，不输出评分、改稿建议、分组或副标题。')


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
    return _natural_wrap("# 编辑这篇文章的 20 个发布标题\n\n"
                         + _natural_commission(wf, job_root, p0=p0)
                         + "\n\n实际最终正文（只去掉内部旧 H1）：\n" + body
                         + "\n\n待编辑的完整标题候选：\n" + _json(title_result) + request
                         + '\n\n各标题必须对应全文主体、重点与本篇体裁。新闻品宣标题不变成核查、排序辩解或问诊攻略；其他类型保持自身任务。若整组体裁错位可重新拟整组。只编辑标题，不改正文。\n\n单独调用 submit_result，结果为 outcome（accepted/revised/incomplete）、candidates（20 项 title 与 angle）、canonical_title_id、title_notes、reason。accepted 保持原候选与推荐，title_notes=[]；revised 返回实际改过的完整 20 项与简短修改说明。成功时 reason 为空；无法完成时 incomplete、candidates=[]、canonical_title_id=""、title_notes=[] 并说明 reason。不得返回 article_markdown。工具保存后只回复 {"submitted":true}。')
