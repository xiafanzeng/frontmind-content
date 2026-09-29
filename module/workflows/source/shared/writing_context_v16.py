"""Editorial preparation, open prose composition and bounded final editing.

Only new P01/P02 commissions use this contract. Earlier prompt builders remain
unchanged so frozen requests retain their original writing instructions.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import writing_requirements as requirements
from .editorial_contracts import edit_base_input, prepare_finalize_input
from .writing_context import _blueprint

CONTRACT = 'frontmind-natural-prose/16'
MARKER = '<frontmind_natural_prose version="16">'

CATEGORY_GUIDANCE = '多主体文章按业务、服务或需求特点分类。分组标题使用“第一类、第二类、第三类”等类别称谓，过渡使用“这一类、该类”等表述；正文和候选标题均不用“第一档、第二档、第三档”“第一梯队”等档位或等级排名称谓。保持本篇已确认的分类重点、主体归属、顺序与详略，不在正文另加分类或排序的辩解。'

MATERIAL_GUIDANCE = """事实段落用于帮助理解介绍对象，提供内容基础和写作方向。它的原有措辞、排列顺序和段落形式不约束最终文章，也不要求逐项写入。
请根据本篇体裁和读者需要，自主取舍、组织和展开内容，在保持核心含义的基础上充分润色、美化。可以使用自然的衔接、贴切的解释和适度的修辞，让文章具有清楚的重点、舒展的表达和有变化的节奏。润色时保持主体业务与具体内容的含义，不凭空添加企业经历、案例或效果承诺。
首要目标是写出一篇漂亮、自然、让人愿意继续读下去的完整文章。"""

PREPARATION = """你是本篇文章的策划编辑，负责案例研究和写作材料整理。先理解读者、介绍对象、体裁、重点和篇幅：article_brief决定介绍范围，question提供选题入口，成文应服务于这份委托。
实际使用web_search搜索、web_read取得两篇同行业、同体裁的已发布文章，再用read_material读完每篇正文。两篇均须符合本次指定的案例类型，彼此不同，也不同于本任务已有例文。优先研究媒体发布的完整机构品宣、业务介绍或推荐文章；价格表、资料卡、病例日记和咨询问答拼接页不算成文案例。搜索不合适时可放宽地域或项目关键词，保持体裁相近；搜索摘要不能代替全文。
研究案例怎样引出对象、用哪些具体内容展开、怎样安排详略和结束。区分文章正文与导航、咨询组件、相关推荐、页尾声明，借鉴适合本篇的组织与表达。案例只帮助理解写法，企业事实仍来自本次原始资料。
随后阅读企业原始材料，按委托选取相关业务、具体特点和必要背景。保留原件中有内容的信息组，包括项目与用途、特点、条件之间的明确对应；重复出现的同一信息合并一次。主体业务按实际内容整理，母体与行业背景按委托简述，网页咨询话术和通用提醒按本篇用途取舍。
将这些信息整理成连贯、简洁、自然的事实段落，供作者理解对象并充分展开。原件有具体描述，就保留其内容；只提供名称和用途，就按这个信息粒度交代。整理不是摘要，也不需要把信息包装成业务关联或综合优势。不同对象各按自身内容组织，材料只谈对象本身；关于文章怎样写、哪些值得多写的判断留给蓝图建议。
另给少量与本篇材料对应的取舍建议：哪些内容最有特点、哪些细节足以展开、哪些适合合并或简述。说明判断依据，供蓝图编辑采用或调整，不提前编排章节、逐节任务或字数配额。
通过正式结果交付自然事实段落、蓝图建议及实际案例和企业来源记录。本轮完成研究与整理，正式蓝图和正文分别由后续步骤完成。"""

ROLES = {
    'preparation': PREPARATION,
    'blueprint': """你是本篇文章的蓝图编辑。结合当前委托、自然事实段落和前置建议，设计一篇读起来顺畅、有重点的文章。前置建议可调整，事实材料可取舍、合并，组织顺序由内容决定。
用需求自然引出对象，随后每一节介绍不同的新内容。机构背景、业务概念和必要的整体说明附在首次出现的位置，同一特点集中讲清一次。小标题直接指向要介绍的内容。
依据具体材料安排详略：有特点、有细节的业务充分展开，只有名称和简短用途的内容并入相关介绍。多主体文章保留委托规定的名单、分组和顺序，各家选择自身最有内容的重点，不按统一模板平均铺开。篇幅用于呈现对象的业务与特点。
蓝图交代各部分写什么、为什么值得展开以及相对主次，给作者保留措辞、衔接和节奏上的发挥空间。最后一项实质内容完成后自然结束。""",
    'draft': """你是一名擅长中文新闻品宣推荐稿的作者。依据当前委托、蓝图和材料，写出可以连续阅读的完整文章。
材料帮助你理解内容，蓝图帮助你把握方向。请用自己的语言成文，根据行文需要调整表达、详略和衔接，充分发挥组织与润色能力。
写出自然的导语，让具体内容随着叙述展开。句子流畅、有节奏，段落之间承接得当，业务特点和推荐意味自然呈现。重点部分写得充实，次要内容简洁带过。
以第三人称直接介绍对象，让推荐意味来自业务与特点的呈现。正常需求和用途可以自然说明，区别在于向读者介绍对象，而不是每段都替读者判断选它有什么好处。多主体文章让各家的内容各有重心，不反复落到同一种“综合服务、方便选择”的结论。
优先考虑整篇文章的语言质感、可读性和吸引力。直接交付成熟的正文，不把资料整理过程写进文章。""",
    'edit': """你是E8全文编辑。以完整文章的阅读效果为中心，改善语言、节奏、主次和衔接。可以重写不自然的句段，合并重复内容，也可以保留作者已经写好的生动表达。不要因为成稿措辞与材料不同就改回原文，不要为了显得正式而增加抽象概括。
在委托篇幅内统筹内容安排，同时处理详略、语言和篇幅。保留并写充分有内容的业务描述，让自然的需求、用途和特点融入叙述；编辑后的文章仍应舒展、充实。需要重组时可重写导语、小标题和整段，直接形成完整稿，避免先压成概要、再逐轮添句补回。
每段用具体内容向前推进，已经交代清楚的特点不再换一种说法解释。多机构文章允许必要的并列介绍，各家按自身内容安排详略，不要求每段都另附综合优势结论。
当初稿把一串项目名称接上一句综合优势时，直接把这一段重新写成自然的机构介绍：围绕最有内容的业务展开，将项目与其具体用途、做法放在一起写，其他业务简洁带过。保留有内容的信息，调整句子的重心与长短，让段落在最后一项具体内容处收住。无需再解释前面这些业务如何共同构成体系、延伸服务或方便选择。
机构简介可以有正常的业务并列，也可以解释读者能理解的用途；编辑不应先抽掉具体业务，再用项目间关系或选择建议维持篇幅。稿中如果谈到本篇选材、公开资料多少或段落收束方式，直接改成对对象本身的介绍。""",
    'repair': """你是负责最终成文的作者。根据完整基稿和编辑意见，重新组织需要调整的内容，保留已经写好的表达。发挥组织与润色能力，改善文章的重点、节奏和衔接，提交完整修订稿。随后仍有一次最后文字编辑。""",
    'finalize': """你是最后的文字编辑。从普通读者的角度通读全文，判断文章是否自然、漂亮、重点清楚，是否值得继续阅读。少量影响阅读的句子直接局部修改；已经成立的表达保留。只有需要重组内容和多个段落时，才提出具体返工意见。
以当前委托规定的介绍范围判断主次；导语从某个需求切入，不意味着全文只能介绍那一项业务。编辑语言与组织，保留委托允许的业务延展，不另立更窄的选题。
需要返工时，指出具体段落、值得保留的重点和应合并或删减的内容，使作者可以直接执行；不要只给“更自然、少重复”一类总体要求。
确需校准语言时，可以选一两处原句给出简短改写示例，帮助作者理解表达尺度，不逐段代写全文。
不要求逐项覆盖素材或恢复原文措辞。正常需求、用途说明和有表现力的文字可以保留。多机构稿允许必要的业务并列，介绍范围内的业务不能仅因不是导语中的单一需求而被要求删去。需要改善项目罗列时，应指出如何组织已有具体内容，不能要求抽掉业务后另添综合优势解释。本轮只编辑文章，不回查知识库或做事实审计。""",
}
POLISH_REVISION_SCOPE = '按所需修改的性质判断：保持标题、主体顺序和各段内容重点即可修好的少量句级问题，即使散见不同章节，也用local_edits处理；只有确需重新分配内容重点或重组多个段落时，才用needs_revision提出具体返工意见。问题分布在多段本身不等于结构问题；整体仍未成立时也不能以几处改字代替返工。'
ROLES['finalize'] += '\n' + POLISH_REVISION_SCOPE
ROLES['polish'] = """你是返工后的最后文字编辑。先从普通读者角度通读当前完整稿，判断文章是否自然、漂亮、重点清楚，再完成必要的少量文字修改。已经成立的表达保留。
以当前委托规定的介绍范围判断主次，不另立更窄的选题。正常需求、用途说明和有表现力的文字可以保留，不要求逐项覆盖素材或恢复原文措辞。
""" + POLISH_REVISION_SCOPE + """
直接修通影响阅读的词语搭配、指代和语气，相邻短句重复同一用途时可合成一句。替换后连同前后句重新读一遍，确认搭配成立、意思清楚、语气自然，不为显得正式而把句子改得生硬、抽象。
修整相邻句子的重复时，可把同段内这两句作为一个局部片段一起修改。替换句应承接前文，不能再复述紧邻句已说明的用途或特点；不要为了维持片段长度而在新句后追加同义说明。删去编辑口吻后，让介绍直接成立即可。
确需结构返工时，指出具体段落、主要阅读问题及应调整的内容，不仅给出总体评价。本轮只编辑当前文章，不回查知识库或做事实审计。"""

BLUEPRINT_FIELDS_DESCRIPTIONS = {
    'article_brief': '当前委托的体裁、对象、重点、篇幅及排版。',
    'materials': '供蓝图页面展示的简短内容概述。',
    'writing_material_markdown': '由已完成的编辑准备提供，程序保存原版本；只作为内容基础和写作方向，不要求照句或逐项写入。',
    'opening': '自然进入对象的角度，不预写导语。',
    'sections': '正式内容顺序及各部分重点，给作者保留表达空间。',
    'ending': '最后一项内容怎样自然结束，不要求另作总结。',
    'estimated_length': '当前委托的正文篇幅及统计口径。',
    'material_adjustments': '必要的后台备注，不进入正文。',
    'writing_material_sources': '继承已完成编辑准备的企业材料来源，蓝图无需重新读取原件。',
    'example_use': '仅说明例文的表达与组织启发，不夹带对本篇内容范围或主次的新要求；不下传正文阶段。',
}
SECTION_TASK = '说明这一部分新增什么具体内容、哪些材料值得展开及相对详略；表达方式和段落节奏留给作者。'


def enabled(state, *, p0=False):
    return (not p0 and state.get('selected_pattern_id') in {'P01', 'P02'}
            and state.get('metadata', {}).get('natural_prose_contract') == CONTRACT)


def matches(prompt):
    return isinstance(prompt, str) and prompt.startswith(MARKER + '\n')


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def wrap(text, *, writer=False):
    from .writer_measure import MARKER as COUNT_MARKER
    return MARKER + '\n' + ((COUNT_MARKER + '\n') if writer else '') + text


def system(action, prompt=''):
    if action in {'article_titles', 'article_title_review'}:
        from .writing_context_v14 import system as title_system
        return title_system(action, '') + '\n\n' + CATEGORY_GUIDANCE
    stage = 'preparation' if action == 'article_editorial_preparation' else action.rsplit('_', 1)[-1]
    parts = [ROLES[stage], CATEGORY_GUIDANCE]
    if stage in {'blueprint', 'draft', 'edit', 'repair'}:
        parts.append(MATERIAL_GUIDANCE)
    if stage in {'draft', 'edit', 'repair'}:
        parts.append('先完成文章，再调用count_article统计完整稿并按当前篇幅范围校准；范围内即可，不追求精确目标数字，不把字数差额分摊成句尾解释。')
    parts.append('最后单独调用submit_result提交结果，成功后只回复{"submitted":true}。'
                 if stage in {'preparation', 'blueprint', 'finalize', 'polish'}
                 else '只返回当前动作要求的JSON对象和完整正文，不加代码围栏。')
    return '\n\n'.join(parts)


def commission(wf, job, *, editor=False):
    from .manuscript_revision import current_revision
    brief = dict(requirements.effective(wf, job, p0=False))
    if editor:
        brief.pop('reference_roles', None)
        brief.pop('brand_positioning_use', None)
    parts = ['<current_commission>', _json(brief),
             '正文采用第三人称。字符数包含正文小标题、标点、数字与英文，排除主标题、空白及Markdown标记。内部首行保留一个H1，发布时主标题独立交付。']
    if brief.get('recommendation_relationships'):
        parts.append('委托中的分类重点、各类主体及顺序已经确认，原样保留；类别名称采用第一类、第二类、第三类等称谓，旧称谓中的档或梯队改为类，保留名称的具体业务含义。当前分类要求优先于蓝图的改写。其他正文和小标题仍可自然润色。')
    rev = current_revision(wf, job, p0=False)
    if rev:
        parts.append('本轮正文修改要求：\n' + rev['edits_markdown'])
    return '\n\n'.join(parts + ['</current_commission>'])


def preparation_commission(wf, job):
    # A completed downstream blueprint must not change the upstream request.
    state = wf.load_state(job)
    brief = dict(state.get('metadata', {}).get('effective_writing_requirements', {}))
    if not brief.get('article_brief'):
        brief['article_brief'] = state.get('decisions', {}).get('response_brief', '')
    brief['question'] = state.get('question', {}).get('question_text', '')
    brief['pattern_id'] = state.get('selected_pattern_id', '')
    return '<current_commission>\n' + _json(brief) + '\n</current_commission>'


def preparation(wf, job):
    from .editorial_preparation import load
    return load(job)


def prompt_preparation(wf, job):
    state = wf.load_state(job)
    case_type = ('本次是单机构品宣推荐稿。两篇研究案例都应只介绍一家企业、机构或其一项业务，展示业务与特点。不要选择多机构榜单；不能以一篇单机构加一篇榜单完成本轮。可以放宽地域或具体产品关键词，优先保持企业场景与文章类型一致。'
                 if state.get('selected_pattern_id') == 'P01' else
                 '本次是多机构品宣推荐稿。两篇研究案例都应围绕同类需求介绍多家企业或机构，研究导语、各家特点的选择和详略。可以放宽地域或具体产品关键词，优先保持企业场景与文章类型一致。')
    parts = ['# 案例研究与编辑准备', '品牌：' + state.get('reference_pack', {}).get('brand', ''), preparation_commission(wf, job),
             '本次案例类型：\n' + case_type,
             '本次研究线索（如有，仅帮助定向；仍须实际搜索、获取并阅读全文，不作为企业事实或已完成的研究）：\n' + _json(state.get('metadata', {}).get('editorial_research_hints', {})),
             '使用原始企业资料，不导入旧正文、旧蓝图或历次改稿意见。已有参考例文仍按其约定用途使用；本轮另外实际搜索两个适合当前任务的具体案例。',
             '已有参考例文（本轮案例应与它们不同；需要辨认时可读取例文）：\n' + _json(wf.load_examples(job, 'question')),
             '本次原始材料目录：\n' + _json(state.get('metadata', {}).get('blueprint_material_roots', [])),
             '已有企业材料索引：\n' + str(wf.user_material_index(job, 'question') or ''),
             '先搜索、读取两个案例全文，再结合本篇需要读取原始企业材料。web_read取得案例后，必须再用read_material分段读完每篇案例的全文，直到正文结尾。',
             '通过submit_result提交：writing_material_markdown（自然事实段落）、blueprint_suggestions（有本篇针对性的蓝图建议）；后台字段reference_cases（恰好两项，每项source_ref、title、url、insight，记录实际阅读全文的案例及借鉴点）、writing_material_sources（实际采用企业原件的source_ref、use）、material_adjustments（可为空数组）。两篇案例只作为写法参考，不列为企业事实来源。不输出正式蓝图。']
    return wrap('\n\n'.join(parts))


def prompt_blueprint(wf, job, *, p0=False):
    from .writing_context_v14 import examples
    prep = preparation(wf, job)
    parts = ['# 正式文章蓝图', commission(wf, job), MATERIAL_GUIDANCE,
             '已准备的自然事实段落：\n' + prep['writing_material_markdown'],
             '前置编辑建议（供判断和调整）：\n' + prep['blueprint_suggestions'],
             examples(wf, job, p0=False, stage='blueprint'),
             '仅使用以上材料与建议形成正式蓝图，无需也不能重新读取原始知识库。选用素材与来源由程序从编辑准备结果带入，勿重新筛选或改写。',
             '蓝图字段说明：\n' + _json(BLUEPRINT_FIELDS_DESCRIPTIONS), 'sections.task：' + SECTION_TASK,
             '通过submit_result提交kind=article、question、pattern_id、article_brief、candidate_order、brand_positioning_use、answer_use、opening、sections、ending、materials、estimated_length、style_source、example_use。writing_material_markdown、writing_material_sources与material_adjustments由程序继承，不必重复提交。']
    edits = wf.load_state(job).get('decisions', {}).get('blueprint_edits')
    if edits:
        parts.append('本轮构思要求：\n' + str(edits))
    return wrap('\n\n'.join(parts))


def references(wf, job, *, outline=False):
    from .writing_materials import selected
    from .manuscript_revision import current_revision
    from .writing_context_v14 import examples
    bp = _blueprint(job, p0=False)
    material = selected(current_revision(wf, job, p0=False), bp)
    parts = [MATERIAL_GUIDANCE, '自然事实材料：\n' + material['writing_material_markdown']]
    parts.append('语言示例（虚构的跨行业表达示范，只用于理解语言尺度，不借用参数、事实或固定句式）：\n'
                 '素材：笔记本机身重1.1千克，14英寸屏幕，键盘键程1.5毫米。\n'
                 '成文：1.1千克的机身让这款笔记本便于随身携带，14英寸屏幕留出了宽裕的工作视野。键盘保留1.5毫米键程，连续输入时，按键仍有清晰的反馈。\n'
                 '具体特点和正常使用感受可以这样直接写进句子。到此即可转入下一项内容，无需再接“这些设计共同构成了兼顾便携、显示与输入的综合体验”。')
    if outline:
        parts.append('正式蓝图（供把握方向与主次，段落与措辞由作者组织）：\n' + _json({k: bp[k] for k in ('opening', 'sections', 'ending') if k in bp}))
    # Keep the agreed reference prose, not a second content brief hidden inside
    # the blueprint's free-form example_use commentary.
    parts.append(examples(wf, job, p0=False, stage='draft', include_blueprint_guidance=False))
    return '<reference_data>\n' + '\n\n'.join(parts) + '\n</reference_data>'


def length_note(body):
    from .natural_editor import character_count
    return '当前正文可见字符数：' + str(character_count(body)) + '。交付范围见当前委托，按文章整体安排详略。'


def prompt_article(wf, job, *, p0=False):
    return wrap('# 写成完整文章\n\n' + commission(wf, job) + '\n\n' + references(wf, job, outline=True)
                + '\n\n按委托篇幅写成完整初稿，充分发挥组织、润色和表达能力。正常需求、用途说明和有表现力的文字可以保留；不必把每个特点写成一段论证或在每段末尾解释意义。'
                + '\n按以下完整JSON结构提交，不省略字段：{"article_markdown":"完整正文","requires_blueprint_reconfirmation":false,"reconfirmation_reason":""}。正常写作取舍直接完成。', writer=True)


def prompt_edit(wf, job, *, p0=False):
    body = edit_base_input(wf, job, p0=False)['article_markdown']
    return wrap('# E8全文编辑\n\n' + body + '\n\n' + length_note(body) + '\n\n' + commission(wf, job)
                + '\n\n' + references(wf, job)
                + '\n\n以整篇文章的语言质感和可读性为中心完成编辑。需要改善的地方直接改好，已经写好的地方保留；修改后的正文处于委托篇幅范围即可。'
                + '\n按以下完整JSON结构提交，不省略字段：{"edit_status":"revised","article_markdown":"完整正文","editorial_notes":["简短、真实的修改说明"],"requires_blueprint_reconfirmation":false,"reconfirmation_reason":""}。有实际正文修改时用revised；全文无需改动时用accepted，原文保持不变且editorial_notes=[]。', writer=True)


def polish_focus(wf, job, body):
    """Optional editorial attention is bound only to this repaired manuscript."""
    from .natural_editor import digest
    metadata = wf.load_state(job).get('metadata', {})
    if 'article_polish_focus' not in metadata:
        return None
    focus = metadata['article_polish_focus']
    if (not isinstance(focus, dict) or set(focus) != {'base_sha256', 'issues'}
            or not isinstance(focus['base_sha256'], str)
            or not isinstance(focus['issues'], list) or not focus['issues']
            or any(not isinstance(issue, str) or not issue.strip() for issue in focus['issues'])):
        raise ValueError('article_polish_focus须包含base_sha256及非空问题字符串数组issues')
    if focus['base_sha256'] != digest(body):
        raise ValueError('article_polish_focus基稿摘要与当前返工正文不一致，请重新核对编辑关注项')
    return {'base_sha256': focus['base_sha256'], 'issues': list(focus['issues'])}


def prompt_finish(wf, job, *, after_repair=True):
    from .natural_editor import digest
    body = (wf.read_json(Path(job) / 'production/article_repaired.json')['article_markdown'] if after_repair
            else prepare_finalize_input(wf, job, p0=False)['candidate_markdown'])
    focus = polish_focus(wf, job, body) if after_repair else None
    attention = ('\n\n本轮编辑关注项（来自全文验读，只指出问题，不提供正文改写）：\n'
                 + _json(focus) + '\n请结合当前全文判断并修好，具体措辞由你决定，仍按本轮少量局部编辑的范围处理。'
                 if focus is not None else '')
    return wrap('# 最后文字编辑\n\n当前完整稿：\n' + body + '\n\n' + length_note(body)
                + '\n基稿标识：' + digest(body) + '\n\n' + commission(wf, job, editor=True)
                + attention
                + '\n\n从读者角度判断文章是否自然、漂亮、重点清楚，是否仍有材料罗列、重复解释、无关段落或生硬的衔接。正常的润色与有表现力的文字保留，不要求恢复素材措辞。主体、名单和分类是固定委托，蓝图的具体段落安排可以改善。'
                + '\n少量影响阅读的句子直接局部修改。只有需要重组内容或多个段落时才提出具体返工意见；普通病句也应认真修通，不用堆叠概括代替润色。'
                + '\n单独submit_result提交needs_revision、comments、local_edits。无需结构返工时needs_revision=false、comments=[]；少量句级微调放local_edits，每项仅original与replacement。original逐字复制当前稿中唯一的一处单段短句或片段，replacement只改该处表达；不跨段，不增删标题、不改变加粗机构名或类别名称，不重排段落。可以删去段内赘句，不能删掉整段。无需修改就local_edits=[]。需要结构返工则needs_revision=true、comments给少量具体意见、local_edits=[]。最终篇幅按应用局部修改后的正文计算。'
                + ('\n当前稿已完成过一次结构返工。仍有主要问题就如实提出，任务保留待修改，不自动循环。' if after_repair else ''))


def prompt_finalize(wf, job, *, p0=False):
    return prompt_finish(wf, job, after_repair=False)


def prompt_repair(wf, job, *, p0=False):
    body = prepare_finalize_input(wf, job, p0=False)['candidate_markdown']
    review = wf.read_json(Path(job) / 'production/article_editorial_review.json')
    return wrap('# 按编辑意见修订完整正文\n\n' + body + '\n\n' + length_note(body)
                + '\n\n本轮编辑意见：\n' + _json(review['comments']) + '\n\n' + commission(wf, job)
                + '\n\n' + references(wf, job)
                + '\n\n按意见改善受影响的内容组织和表达，保留已经写好的段落。发挥润色能力，让全文自然、顺畅、有吸引力。提交委托篇幅内的完整稿，随后还有一次最后文字编辑。'
                + '\n返回JSON，仅含article_markdown。', writer=True)
