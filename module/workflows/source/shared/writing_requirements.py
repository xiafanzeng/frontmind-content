"""Durable article requirements, independent of prose and reference lengths.

This is input state, not a quality gate. Explicit requirement changes can be
supplied with a revision; ordinary editing instructions never erase it.
"""
from __future__ import annotations
import json
from pathlib import Path

CONTRACT = 'frontmind-writing-requirements/4.13.2-final13'
MARKER = '<frontmind_natural_editor version="4.13.2-final13">'
BLUEPRINT_MATERIAL_INPUT_MODE = 'source-index-v1'
WRITING_OUTLINE_INPUT_MODE = 'suggested-outline-v1'
WRITING_MISSION_INPUT_MODE = 'editorial-mission-v1'
DEFAULT_MISSION_INPUT_MODE = 'editorial-mission-v2'
MANUSCRIPT_OUTLINE_INPUT_MODE = 'current-manuscript-v1'
LEGACY_EDITORIAL_REVIEW_SCOPE_MODE = 'actual-claims-v1'
EDITORIAL_REVIEW_SCOPE_MODE = 'actual-claims-v2'
TITLE_INPUT_MODE = 'final-body-v1'
MISSION_MARKER = '<frontmind_natural_editor version="4.13.2-editorial1">'
FIELDS = {'article_brief', 'estimated_length', 'candidate_order', 'brand_positioning_use',
          'recommendation_relationships', 'formatting', 'reference_roles', 'question', 'pattern_id'}


def enabled(state):
    from .natural_editor import enabled as natural_enabled
    return natural_enabled(state) and state.get('metadata', {}).get('writing_requirements_contract') == CONTRACT


def effective(wf, job, *, p0):
    state = wf.load_state(job)
    prefix = 'p0' if p0 else 'article'
    path = Path(job) / 'blueprints' / (prefix + '_blueprint.json')
    bp = wf.read_json(path) if path.is_file() else {}
    value = {key: bp[key] for key in sorted(FIELDS) if key in bp}
    # Revision inputs are frozen in the existing revision record. A title-only
    # turn or recovery sees the same merged requirements, not a short draft.
    value.update(state.get('metadata', {}).get('effective_writing_requirements', {}))
    if p0 and not value.get('estimated_length'):
        value['estimated_length'] = '默认3500—4200个正文可见字符；用户明确的本篇篇幅要求优先。'
    if not p0:
        value['question'] = state['question']['question_text']
        value['pattern_id'] = state['selected_pattern_id']
    return value


def read_changes(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict) or not value or set(value) - FIELDS:
        raise ValueError('写作要求须为已有要求字段组成的非空 JSON 对象')
    if {'question', 'pattern_id'} & set(value):
        raise ValueError('正式题目和 Pattern 请使用已有选题与 Pattern 入口修改，不能通过写作要求覆盖身份')
    if any(v is None or v == '' or v == [] or v == {} for v in value.values()):
        raise ValueError('写作要求不能用空值撤销原要求；请明确填写新要求')
    return value


def merge_changes(state, changes):
    current = dict(state.get('metadata', {}).get('effective_writing_requirements', {}))
    current.update(changes)
    state['metadata']['effective_writing_requirements'] = current


def mark_new_blueprint(state):
    """Opt in only at a new explicit commission, never during restoration."""
    if enabled(state):
        state.setdefault('metadata', {})['writing_outline_input_mode'] = WRITING_OUTLINE_INPUT_MODE
        state['metadata']['writing_mission_input_mode'] = DEFAULT_MISSION_INPUT_MODE
        state['metadata']['title_input_mode'] = TITLE_INPUT_MODE


def editorial_mission(state):
    return enabled(state) and state.get('metadata', {}).get('writing_mission_input_mode') == WRITING_MISSION_INPUT_MODE


EDITORIAL_CORE = '''你是受托撰写本篇文章的中文编辑。以当前写作要求确定读者、体裁、主题、主体关系、篇幅和排版，把选中的具体业务、人物、方法和服务组织成一篇完整文章。用读者关心的问题推进内容，让重点获得充分展开，次要背景简述。推荐文章通过具体特点与详略呈现推荐；解释、比较、事件与品牌介绍各自完成本篇任务。文风例文帮助把握选材和段落推进，章节构思可按内容调整。
事实按材料记录的主体、范围和时间状态使用。分别记载的项目、人员与资源保持各自归属，只有材料明确建立的联系才能写成该主体实际采用的做法。正文直接叙述已知事实，影响理解的具体条件随对应内容交代一次。材料出处、研究过程和编辑工作留在后台。成稿、编辑和返工持续使用同一明确篇幅目标，删改后补足尚未展开的相关内容，交付有内容、可直接阅读的完整文章。'''

EDITORIAL_ROLES = {
    'blueprint': '你负责选材与构思。阅读相关原件，提取足以展开本题的直接事实，整理一份简短、完整的当前写作要求和可调整构思。',
    'draft': '你负责成稿。按本篇写作要求、具体事实和文风参考，完成连贯自然的完整文章。',
    'edit': '你是 DeepSeek E8 编辑。通读完整基稿，按本篇任务重组不成文的段落并补足未展开的具体内容，保留成立的表达。',
    'style': '你是 P0 最后负责成文的 DeepSeek 编辑。通读完整基稿，参考两篇例文改善详略、段落推进与节奏，完成品牌自身的介绍。',
    'finalize': '你是 XTY 编辑。阅读实际完整文章，判断内容展开、事实和表达是否完成本篇任务；事实有疑问时回读原件。只提出需要修改的具体位置与方向，同类问题合并，无实际问题就给空意见。',
    'repair': '你是最后负责成文的 DeepSeek 编辑。以提供的完整稿为基稿，结合本篇要求和具体编辑意见完成全文同类修改，交付完整文章。编辑意见不提供新事实。',
}


def editorial_system(action):
    """An independent mission, selected by a frozen request marker.

    Older paid requests keep system() below byte-for-byte, even if restored
    while a newer commission is already supported by this package.
    """
    stage = action.rsplit('_', 1)[-1]
    if stage in {'blueprint', 'finalize'}:
        protocol = '按需读取相关原件，最后单独调用 submit_result 一次；保存后只回复 {"submitted":true}。'
    elif stage == 'style':
        protocol = '只输出完整 Markdown 正文，首行一个 H1。'
    else:
        protocol = '所需材料与完整候选已内嵌，不读取本地文件。只返回本动作要求的一个 JSON 对象，不加代码围栏。'
    return '\n\n'.join((EDITORIAL_ROLES[stage], EDITORIAL_CORE, protocol))


def positioning_still_valid(state, job):
    path = Path(job) / 'question_positioning/question_positioning.json'
    if not path.is_file() or not state.get('decisions', {}).get('question_positioning_confirmation'):
        return False
    value = json.loads(path.read_text())
    return (value.get('pattern_id') == state.get('selected_pattern_id') and
            value.get('question') == state.get('question', {}).get('question_text') and
            value.get('brand') == state.get('reference_pack', {}).get('brand'))


def system(action, *, facts_core=''):
    from .article_positioning import NATURAL_CORE, NATURAL_ROLES
    stage = action.rsplit('_', 1)[-1]
    core = NATURAL_CORE.replace(
        'P01围绕主对象充分展开，P02按本篇要求逐个介绍各对象；其他类型完成各自解释、比较或事件任务。',
        'P0 建立对品牌的整体认识。P01 围绕正式推荐问题具体说明为何考虑单一主体；P02 保留已确认的分类关系、推荐重点、主体角色与顺序，不能退成名录；P03–P06 保持各自任务。推荐依据融入具体业务与事实，不追加机械总结。')
    core = core.replace('篇幅是预算，不是硬配额，不用背景堆积、常识、反复否定或通用提醒填满数字。',
        '用户明确指定的篇幅是持续有效的展开目标，不能自行改成上限或接受大幅缩写。删掉重复和错误内容后，补足与正式问题直接相关的业务细节、方法、人员与服务；不靠常识、无关背景、反复否定或通用提醒补字。核心业务事实不足须指出具体缺口，不能偷换题目。')
    core = core.replace('排列顺序只是组织文章', '排列顺序体现本篇选定的主体关系')
    core += '\n推荐关系通过选材、具体业务特点和详略体现，不要求每段解释自己为何被推荐、为何属于该档或提供哪种抽象基础。扩写应增加有依据的业务细节、方法、人员或服务安排；不要重复释义地址、科目或等级，不把资源并列推导为未记载的协同流程、使用场景、配套能力或效果。篇幅不足与事实不足需要分别处理，缺少新信息时不能用同义概括补长度。'
    role = NATURAL_ROLES[stage].replace('字符数只是展开参考，不能仅因低于预算补齐，也不能把自然写作处理成逐轮缩写。',
        '对照同一篇幅目标与程序统计，指出尚未展开的核心内容；不能把明显不足的稿件当成充分展开，也不能将自然编辑处理成逐轮缩写。')
    role = role.replace('不按字数差额补写。', '补足与本题相关而尚未展开的内容，完成持续有效的篇幅目标。')
    if stage == 'finalize':
        role += '提出扩写意见时指出已有材料中尚未采用的具体信息，必要时回读原件；不要要求作者仅凭登记项目、地址或机构类型解释优势，也不要求逐家说明归档理由。资料不足应指出具体缺口，不让作者以无据联系弥补。'
    if stage in {'blueprint', 'finalize'}:
        protocol = '按需通过工具读取相关原件，最后单独调用 submit_result 一次；保存后只回复 {"submitted":true}。不伪造来源或工具结果。'
    elif stage == 'style':
        protocol = '只输出完整 Markdown 正文，首行一个 H1；不输出 JSON、计划、说明或自评。'
    else:
        protocol = '所需材料与完整候选均已内嵌，不读取本地文件。只返回本动作要求的一个 JSON 对象，不加代码围栏。'
    return '\n\n'.join(x for x in (role, core, facts_core, protocol) if x)
