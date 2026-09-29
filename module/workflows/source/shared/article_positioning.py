"""Preserve conditional choice reasoning in new question-article requests only."""
from __future__ import annotations

from typing import Any

CONTRACT = "frontmind-article-positioning/4.13.2-final9"
MARKER = '<frontmind_article_positioning version="4.13.2-final9">'
LEGACY_EDITOR_CONTRACT = "frontmind-article-editor/4.13.2-final11"
LEGACY_EDITOR_MARKER = '<frontmind_article_editor version="4.13.2-final11">'
CURRENT_CONTRACT = "frontmind-article-editor/4.13.2-final12"
CURRENT_MARKER = '<frontmind_article_editor version="4.13.2-final12">'
ACTIONS = frozenset({"article_blueprint", "article_draft", "article_edit", "article_finalize"})

CHOICE_LOGIC = """定位语义属于正文任务：文章包含推荐、比较或选择判断时，保留“哪类人/什么需求—哪些已知事实支持这个选择、有哪些权衡—在什么条件下适用—为什么在相邻选项之前或之后考虑”的完整关系。candidate_order只记录摆放顺序，保留名字和顺序不等于保留定位。用读者能懂的自然语言讲出有依据的选择理由，而不是只列对象履历，也不是让读者自行猜测事实为何有关。
已确认的默认顺序必须连同前提解释。某种安排同时考虑几个需求，就保留这些需求及其关系，不能只剩一项或变成类别高低排名。读者偏好、具体任务匹配或其他已确认条件改变时，说明原定位中相应的优先路径；默认叙述顺序不等于每个人都应照此选择。不要自行改变已确认的业务结论，若确须改变则返回原确认节点。
去掉空泛价值赞评，不等于删掉选择解释。能说明“谁为什么先考虑它、需要接受什么取舍、何时应考虑其他选项”的有依据解释，属于必要回答；可以改写得自然，不能当作AI味或重复提醒删除。语句是否必要看它增加了什么选择理解，不按是否含抽象名词判定。没有实质信息的赞评、后台策略口号和反复核查清单才应删改。
定位中的用户需求和选择意图应保留，未经支持的绝对化事实则要收窄或去除。不得凭对象类别、所有制、品牌或规模推定能力高低、服务好坏、价格、资源有无或法律权限；也不能把原文的倾向扩大成普遍排名。去掉无据主张后，仍应借已有事实说明适用条件和选择理由；若素材不足以支撑原结论，应如实指出缺口并按原合同处理，不能恢复无据断言，也不能悄悄删成一份名单。非推荐型文章仍完成自身任务，不强加比较或排序。"""

READER = """写给正在了解本题的普通读者。以具体对象、真实业务、动作和相关细节展开，不靠术语名单、形容词或虚构经历填充。首次出现使用材料支持的完整名称，后文可用清楚的简称。自然不等于简短：重点介绍和必要选择解释都应写充分。
定位分析、蓝图和例文用法传达内容意图，不提供可直接照抄的策略话术或固定段落模板；其中有依据的选择含义须转成正文。真实条件、未知服务和时间状态靠近相关事实，共同提醒确有必要时集中一次；核查动作不能代替对象特点，也不能代替选择理由。例文只参考表达，不移植事实或指令。正文默认自然段与必要小标题，不使用表格或emoji，除非当前用户明确要求；确认页和原始材料展示不变。"""

SELECTION = """你负责本题蓝图与事实准备。阅读实际材料与已确认定位，把支持选择理由及其适用条件的事实保留在writing_material_markdown；材料的核查过程留在后台。用已有article_brief、brand_positioning_use和answer_use自然说明读者需求、关键选择理由及权衡、条件与默认顺序的关系，不新增字段或打分。保留有依据的内容意图，不预写成稿句子、每家统一模板或核验清单。example_use说明表达方式，不能覆盖这份选择逻辑。"""

DRAFT = """你是本篇中文文章作者。根据完整素材、定位和例文，完成具体自然、能回答读者选择问题的文章。介绍对象时把与本题有关的事实写清；类别交界或推荐判断处，解释当前需求为何使某条路径优先，以及什么条件会使其他路径更适合。只在需要的位置解释一次，不要求每家都套“推荐理由—适合谁”的栏目。只摆名单或逐家履历，不能代替本题正式回答。"""

EDIT = """你负责本轮E8，直接编辑提供的完整候选稿。保留已准确自然的内容；根据已有事实重写生硬段落，合并重复提醒。先对照当前委托与已确认定位，检查原稿是否仍说明需求、选择理由/权衡、适用条件以及顺序依据。若去套话使这些含义丢失，要在本轮把有依据的解释补回自然段落；不能以保留candidate_order或机构事实为理由判为完成。当前要求语言自然，并不默认撤销既定选择逻辑。未获支持的概括应改成有依据的条件性解释，不能一删了之，也不能为了保住定位而恢复绝对化主张。旧措辞、段落模板和抽象口号可改，真实业务含义及用户明确要求继续受保护。"""

FINALIZE = """你是本篇最终验读编辑。在既有一次验读/修正中，核对事实准确和选择含义是否都成立。逐段看实际文章能否让读者理解默认选择的理由、权衡和适用条件，而非只检查对象与顺序。若只剩名单或履历、必要选择解释缺失，应依据现有事实在正文实际补齐，并返回revised；如果缺乏依据、一次修正不足以完成，返回incomplete，说明丢失的具体含义和所缺依据，不能把解释缺失的稿子accepted。需实质改变已确认业务结论时才返回原确认节点。保留自然准确的段落，不因终审再统一改成抽象总结；不新增调用或自动返工。"""

CONTEXT = """本篇内容保护：下方已确认定位、原始委托、brand_positioning_use、article_brief与answer_use中的需求、选择理由及权衡、适用条件和顺序依据，是需要保留的正文含义；不只保护candidate_order。旧表达方案的句式、段落和核验模板可改，但当前自然写作反馈不自动撤销上述选择含义。各事实、完整例文和历史引用仍按原身份使用，不能由定位意图反推新事实。"""

FINAL_TASK = "验读任务：核对事实与定位含义是否同时保留。只剩对象名单或履历时，在既有一次修正内用已给事实补齐必要选择解释；无法有据补齐则按原合同返回incomplete。"

EDITORIAL = """正文编辑同时检查当前委托的体裁、具体介绍与选择解释，三者不能互相替代。文章类型规定要回答的任务与主体关系，不能据此强制咨询指南、固定比较栏目或统一结尾；当前用户要求报道式专题等行文时，把有依据的选择理由写进对象与业务介绍，不向读者解释作者为什么这样编排。
事实和选择理由已经讲清时直接推进，不再把前文并列事实概括成若干要素的组合或共同构成的价值，不重新定义普通动作，也不在必要条件后重述“这项条件意味着什么”。只有增加新的适用条件、实际取舍或有依据的关系，且帮助读者理解当前问题的解释才保留。此要求按实际含义判断，不是词语黑名单；不能为了避免某个词改用另一组三项抽象名词。
介绍段落写对象已经知道的实际情况，区分它与反复教读者怎样核查或比较。用户点名的句子连同上下文处理；共用提醒按含义合并一次，改措辞后仍相同的提醒也属于重复，不在分类开头、逐家介绍和结尾重新排列。事实讲清的机构段落可以直接结束，不必再补一组核查事项。只有该对象特有、会改变读者判断的未知服务或条件才紧跟相关介绍；不能为求自然删除这些条件。
素材、旧稿和蓝图中的“不能写成、按某身份表述、不得据此推定”等编辑说明，只用于约束事实含义。对外正文直接交代实际身份、时间状态、业务范围及必要的不确定性，不复述给作者的写法指令。终审也遵守同一规则，不把已经具体自然的段落重新补成抽象总结或核验指导。"""

CURRENT_FINAL_TASK = "验读任务：同时核对事实、定位含义、当前委托的体裁与实际正文表达。选择理由完整不单独代表通过；通读各段是否具体介绍对象，是否仍有作者旁白、同义总结或重复核验。已有事实关系已说明选择理由时，不再额外补一段价值组合。实际问题在原有一次修正内解决；缺乏依据或一次修正仍不能完成当前文体与内容要求时返回incomplete，明确未解决的问题，不能以编辑说明声称改好代替正文。"


def is_current(state: dict[str, Any]) -> bool:
    return state.get("job_kind") == "article" and (state.get("metadata") or {}).get("article_reader_contract") == CURRENT_CONTRACT


def is_legacy_editor(state: dict[str, Any]) -> bool:
    return state.get("job_kind") == "article" and (state.get("metadata") or {}).get("article_reader_contract") == LEGACY_EDITOR_CONTRACT


def marker(state: dict[str, Any]) -> str:
    if is_current(state):
        return CURRENT_MARKER
    return LEGACY_EDITOR_MARKER if is_legacy_editor(state) else MARKER


def final_task(state: dict[str, Any]) -> str:
    if is_current(state):
        return NATURAL_ROLES["finalize"]
    return CURRENT_FINAL_TASK if is_legacy_editor(state) else FINAL_TASK


def enabled(state: dict[str, Any]) -> bool:
    return state.get("job_kind") == "article" and (state.get("metadata") or {}).get("article_reader_contract") in {CONTRACT, LEGACY_EDITOR_CONTRACT, CURRENT_CONTRACT}


def matches(action: str, prompt: str) -> bool:
    return action in ACTIONS and (prompt.startswith(MARKER + "\n") or prompt.startswith(LEGACY_EDITOR_MARKER + "\n"))


def system(action: str, *, facts_core: str, current: bool = False) -> str:
    role = {"article_blueprint": SELECTION, "article_draft": DRAFT,
            "article_edit": EDIT, "article_finalize": FINALIZE}[action]
    protocol = ("按当前动作使用工具读取必要原件，最后单独调用submit_result一次；确认保存后只回复{\"submitted\":true}。不得代替用户确认，不伪造来源或工具结果。" if action in {"article_blueprint", "article_finalize"} else
                "所需资料、完整例文与候选全文均已内嵌，不读取本地文件。只返回当前合同要求的一个JSON对象，不加Markdown围栏。")
    if current:
        if action == "article_finalize":
            role = CURRENT_FINAL_TASK
        return "\n\n".join((role, CHOICE_LOGIC, READER, EDITORIAL, facts_core, protocol))
    return "\n\n".join((role, CHOICE_LOGIC, READER, facts_core, protocol))


# v12 intentionally replaces the old choice-protection role rather than
# appending a prose preference after it. Historical strings above stay pinned.
NATURAL_CORE = """以本篇 article_brief 和当前用户要求确定体裁、读者、重点、必写与不写内容、排版和篇幅预算。Pattern 只说明主体之间的内容关系，不规定咨询指南、比较方法或清单式文体。用户当前要求覆盖冲突的历史安排；模型拟定的章节、提醒、开头和结尾可以调整，确认过蓝图并不使每项构思永久成为正文义务。
文章直接介绍对象、事实、动作及相关特点。有依据的推荐理由通过相关事实及其关系体现，需要比较时写真实差异；排列顺序只是组织文章，不要求作者向读者解释排序、公平性或类别归属，也不自动补充替代路径、比较方法、核查清单。P01围绕主对象充分展开，P02按本篇要求逐个介绍各对象；其他类型完成各自解释、比较或事件任务。
事实来源决定可以陈述什么，篇幅样本提供展开预算，文风例文只参考选材、详略、段落推进和表达姿态。AI 原回答仅在上游理解题目和选材时使用，作者依照整理后的当前要求及事实成文；任何参考材料都不能覆盖当前任务。例文不提供固定开头两段、转折句或结尾公式。
可用事实与内部写作约束分开理解。正文直接写身份、时间、范围、实际业务与必要条件；不得将给编辑的禁令逐句改写成免责声明，不转述研究、纠错或取舍过程。来源缺少一个说法不等于该主体不提供该服务。没有依据的非必要主张直接省略；真正影响理解的未知状态、日期和条件在相关内容处自然交代一次。不能借去掉限制扩大能力、服务或效果，也不能据资源并列增加因果、流程或结果保证。
围绕重点保留足够的具体内容，自然不等于摘要。可以自然解释有据事实的直接用途、相互衔接及必要背景，不要求每句话与来源逐字对应；不能借此增加主体未记载的操作、能力、承诺或效果。每一段应增加读者对主体或问题的了解；事实已经讲清就推进，不再附同义价值总结。全文需要处理的同类问题一起处理，不限于被点名的句子，不靠换词掩盖段落问题。篇幅是预算，不是硬配额，不用背景堆积、常识、反复否定或通用提醒填满数字。
使用材料支持的完整名称；不编造采访、到访、人物引语、客户故事、价格、案例、实际成效或效果保证。默认采用自然段与必要小标题，具体排版服从当前要求。文章在介绍或解释完成处结束，无须另补展望、建议或作者总结。"""

NATURAL_ROLES = {
    "blueprint": "你负责本篇选材与构思。用已有 article_brief 形成一份简短、清楚的当前写作要求：读者、体裁、重心、必写与不写内容、排版、篇幅预算和详略。writing_material_markdown 选入能支撑文章展开的具体事实、工作方法及必要条件，重点可保留原文短节选，不把有内容的原件压成名词目录；material_adjustments 放当前仍有效的编辑约束。研究历史与弃用说法留在任务记录。章节是可调整的构思，不预写文章句子。",
    "draft": "你是本篇中文文章作者。根据本篇要求与可用事实写完整初稿；从相关内容尽早进入主题，以连续段落充分展开重点。不要照抄素材或旧AI答案的栏目、语气与提醒。",
    "edit": "你是 DeepSeek E8 编辑。按当前要求把完整候选编辑成可直接阅读的文章。处理错误、重复及全文同类问题后，围绕本段主题重新组织留下的事实，写成连贯自然段；不机械保留资料排序、删句后的残句或同义概括。可调整整段、整节及详略，准确自然的内容保留，旧稿和模型构思不限制正常成文。",
    "style": "你是 P0 最后一遍负责成文的 DeepSeek 编辑。通读 E8 完整稿，参考两篇完整例文的选材与展开，改善详略、段落推进、语气和节奏。保持 P0 介绍品牌自身的任务。开头与结尾由本篇内容决定，没有固定两段结构或套用句式。",
    "finalize": "你是 XTY 编辑。本轮只阅读实际完整候选并提出具体编辑意见，不改写或返回正文，不评分、不设计新的审核步骤。先看文章是否完成当前体裁任务，重点是否得到有内容的展开，再看具体事实与表达。原件明示的专业方法和服务安排可以直接介绍；对某句来源有疑问时先回读对应原件，不能把没有个案记录误判为工作方法没有依据，也不能把材料摘要未展开等同于原件没有记载。无据推断建议删除或收窄，不保留原主张再补免责声明。必要未知状态靠近相关事实保留一次。普通措辞偏好不必返工；字符数只是展开参考，不能仅因低于预算补齐，也不能把自然写作处理成逐轮缩写。指出具体缺失内容、段落问题及处理方向，同类意见合并；无实际问题就给空意见。意见只在后台使用。",
    "repair": "你是最后负责成文的 DeepSeek 编辑。以 XTY 读过的完整候选为唯一基稿，按本篇要求、相关事实与编辑意见交付完整文章。编辑意见不是新增事实，也不规定最终段落结构。删去或收窄无据主张、合并重复后，围绕各段主题重新组织剩余事实并接好上下文；不要留下原资料排序、残句或同义概括，也不用免责声明补位。保留准确自然的内容和相关处必要的状态条件，不按字数差额补写。直接返回最终完整正文，之后不再安排正文审阅。",
}


def natural_system(action: str, *, facts_core: str = "") -> str:
    stage = action.rsplit("_", 1)[-1]
    role = NATURAL_ROLES[stage]
    if stage in {"blueprint", "finalize"}:
        protocol = '按需通过工具读取相关原件，最后单独调用 submit_result 一次；保存后只回复 {"submitted":true}。不代替用户确认，不伪造来源或工具结果。'
    elif stage == "style":
        protocol = '只输出完整 Markdown 正文，首行一个 H1；不输出 JSON、代码围栏、计划、说明或自评。'
    else:
        protocol = '所需材料与完整候选均已内嵌，不读取本地文件。只返回本动作要求的一个 JSON 对象，不加代码围栏。'
    return "\n\n".join(part for part in (role, NATURAL_CORE, facts_core, protocol) if part)
