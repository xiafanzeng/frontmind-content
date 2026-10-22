"""Reader-facing writing for new P01--P06 commissions.

The v16 builders remain unchanged for frozen historical requests. Editorial
resources are local text, not detectors, external scripts or extra model calls.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import writing_requirements as requirements
from .editorial_contracts import edit_base_input
from .writing_context import _blueprint

CONTRACT = 'frontmind-natural-prose/16.5'
PRODUCT_SOURCE_CONTRACT = 'frontmind-product-sources/16.6'
PRODUCT_SOURCE_MARKER = '<frontmind_product_sources version="16.6" />'
MARKER = '<frontmind_natural_prose version="16.5">'
PATTERNS = frozenset({'P01', 'P02', 'P03', 'P04', 'P05', 'P06'})
RESOURCE_DIR = Path(__file__).resolve().parents[1] / 'resources' / 'natural_editorial_v165'

PATTERN_GUIDANCE = {
    'P01': '单主体推荐：围绕正式问题，介绍一家主体的产品、业务、做法与特点。推荐意味可以鲜明，让具体内容和使用场景自然呈现它的吸引力。',
    'P02': '多主体推荐：按已确认的三家及顺序介绍，主品牌先。各家从自身最有内容的特点展开，详略与段落形式可以不同；分类只在当前委托需要时使用。',
    'P03': '场景解决方案：从读者遇到的一件具体事情进入，把相关做法、产品或服务过程讲清。只展开本题实际需要的步骤、价格、条件或风险。',
    'P04': '事件新闻：围绕这次事件、参与者、发生时间和实际进展报道，必要背景随叙述交代。重点留给正在发生的事。',
    'P05': '明确对象对比：保留题目点名的对象，围绕读者关心的差异比较。按相关的共同维度讲清各自特点和适合的需要，写法随内容安排。',
    'P06': '口碑与可信度：直接回应本题对一个主体的疑问，组织相关业务、资质、体验、口碑或事件内容。已经知道什么就清楚讲什么，保持解释与评价的自然语气。',
}
CASE_TYPES = {
    'P01': '两篇完整的单主体推荐或产品、业务介绍稿，观察怎样引出一家主体、展开特点与场景。',
    'P02': '两篇完整的多主体推荐稿，观察怎样切入同类需求、选择各家的特点、安排不同详略。',
    'P03': '两篇围绕具体场景讲清做法或解决方案的完整文章，观察问题怎样进入、步骤与产品怎样融入叙述。',
    'P04': '两篇有明确事件、参与者、时间和进展的完整新闻，观察导语、事件推进与背景交代。',
    'P05': '两篇比较明确对象的完整文章，观察共同维度、关键差异与自然的比较展开。',
    'P06': '两篇回应单主体体验、口碑或可信度疑问的完整文章，观察怎样直接回答疑问、展开相关内容。',
}

MATERIAL_GUIDANCE = ('素材帮助理解对象与事件，提供可展开的具体内容。原有措辞和排列顺序由作者重新组织；'
                     '重点写充分，辅助内容简述。正常的场景、用途解释、价值表达和适度修辞都可以使用。'
                     '保持已知产品、业务与事件的含义，人物、经历、数字与引语使用本篇已有内容。')
CATEGORY_GUIDANCE = ('多主体稿保留当前确认的主体与顺序；确有分类时用业务、服务或需求特点表达。'
                     '分类名称使用“第一类、第二类”等称谓，推荐关系自然体现在介绍中。')
LENGTH_GUIDANCE = ('篇幅由本题需要和可展开的内容决定，写充分后自然结束。预计篇幅和例文长度用于参考。'
                   '只有明确的硬性字数范围才按范围校准；删除重复无需等量补回。')
STYLE_GUIDANCE = ('用自然的中文直接写给读者。允许轻微口语、长短句交错、正常转折、有限重复和一点未经精雕细琢的新闻稿感觉。'
                  '保留有感染力的表达，稿件可以不那么工整，读起来顺、意思清楚即可。')

PREPARATION = '''你是这篇文章的策划编辑。先理解正式问题、当前委托、体裁与读者需要，再选取有用的产品、业务或事件内容。
实际搜索并取得两篇适合当前体裁的已发布文章，分段读到正文结尾。研究它们怎样进入主题、展开具体内容、安排详略与衔接；这些文章只提供写法启发。
读取本篇相关原始材料，整理成能让作者理解对象的自然段落：产品是什么、做什么，业务怎样开展，事件有什么进展，有哪些值得展开的细节。丰富内容成组保留，重复信息合并一次，次要背景简述。
先从企业原件整理内容。已有P0和定位帮助理解介绍重点，原件里的产品、功能、业务与事件构成本篇选用内容。素材的每个自然段都在介绍对象；技术段讲实际处理方式，机构段讲接口、系统连接和部署。
输出分为作者内容和后台备注。writing_material_markdown是作者可直接讲述的内容；blueprint_suggestions只安排这些内容的主次。material_adjustments存放取用提醒、采购核对和历史定位中的审读意见。比如报告段写“图文报告展示舌象和脉搏波形，工作人员可以结合生活情况逐项讲解”，部署段写“API用于连接机构系统，私有化部署面向自有服务器或私有云”。关于结果不能证明什么、哪些信息还要确认、采用前需要做什么的意见，都写入后台备注。整理完后从头读两份作者内容，移动混入其中的工作意见；保持内容本身完整，不用另一句委婉提醒替代。
已有的阶段、时间、收费或服务条件有助理解时，和对应内容放在一起。例如已公布的服务地区、费用与截止时间是内容；一串待核对的模块、字段和责任归属是工作备注。构思建议写具体进入方式、展开重点和自然结束的位置。
完成后交付选用内容、少量构思建议与实际读取的来源记录，供下一步形成蓝图。'''

MATERIAL_FIELD_DESCRIPTION = ('直接介绍本篇对象的完整素材段落：产品是什么、功能怎样使用、报告怎样呈现、业务怎样开展。'
    '素材每段以对象和内容为主语，技术段写处理方式，机构段写系统连接与部署。'
    '已知服务条件随内容交代；作者提醒、结果不能证明什么、采用前应核对什么只存后台material_adjustments。'
    '这里交付产品与业务内容，写法建议另存blueprint_suggestions。')

ROLES = {
    'preparation': PREPARATION,
    'blueprint': '''你是文章策划编辑。根据当前委托、选用内容与例文，安排一篇能顺着读下去的文章。
导语从本题相关的需求、产品或事件自然进入；章节围绕不同的具体内容推进。小标题直接指向内容，各节任务只说明写什么、哪些细节适合展开及相对主次。写法、句子与段落节奏留给作者。
用正向的内容描述安排全文。文章写到最后一项实质内容便可结束。''',
    'draft': '''你是中文新闻与品宣稿作者。按当前体裁写成完整初稿，让读者直接进入对象或事件。
蓝图帮助把握内容主次，措辞、导语、衔接与段落由你组织。借鉴完整例文的叙述姿态、信息展开与节奏，让产品、业务、场景或进展随着叙述出现。重点写充分，次要背景简洁交代。
先把文章写顺，再连起来读一遍。直接交付可阅读的正文。''',
    'edit': '''你是负责发布稿的全文编辑。通读初稿，结合本篇任务和完整文风例文，把全文编辑成自然、好读的成稿。
导语、小标题、整段、整节与结尾都可以重写、合并、删除或调整次序。遇到一整段都在审读资料、解释作者如何谨慎，先想清它要介绍的业务，再用中文重新讲一遍。
已经自然的表达留下。生动的介绍、合理场景、正常用途与价值表达可以展开。修改同类问题时通读全篇，编辑实际完成在正文里。''',
    'repair': '''你是负责完整成稿的编辑。以当前失败候选为基稿，根据具体阅读问题重新编辑全文。
保留已经写好的内容，改掉相关段落及全篇同类问题。先想清有问题的整段到底要告诉读者什么，再重新讲述；工序、参数或功能不必逐项保留，选择能把意思讲清的细节。后文写新增内容，讲完最后一件实质内容就可以停住。必要时重新起草导语或整节，把稿件写顺后交付完整修订稿。当前意见帮助定位问题，具体写法由你决定。''',
    'finalize': '''你是发布稿的文风验读编辑。只通读当前完整候选，判断普通读者能否自然读下去、它是否已经像一篇可发布的稿件。
先作为本题读者连着读完，判断这篇普通待发稿能否一遍读懂并完成它的任务。返工针对使阅读明显停下来、叙述身份跑偏或大段空转的问题；只是还能再精细一点的稿件直接通过，不把可优化之处逐条变成整改任务。
重点看作者是否在介绍对象或事件，导语和段落是否顺畅，是否仍有资料审阅、假想质疑下的自辩、连续的空泛总结或整齐模板感。看全文的阅读效果，按句子的实际用途判断。
按当前读者看专业信息的展开。技术细节是题目重点时可以充分讲；面向业务读者的介绍中，连续罗列工序、指标或术语而让使用主线停下来的整段，需要重新讲述。读到后半篇时也看它是否在讲新增内容，还是把前文的功能又汇总一遍；自然的呼应可以保留，重复总结拖慢结束时指出具体段落。
允许口语、有限重复、不完全工整的段落和正常品宣润色；这些本身不构成返工理由。专业词、正常列举、前后呼应和一句点题也不单独构成问题，看它们是否帮助当前读者理解内容。已经成立的稿件直接通过。需要再编辑时，只写少量实际影响发布阅读的具体段落问题与重写方向。
本轮不改写正文、不重新检索、不回查原件、不做事实审计、评分或逐项验收报告。''',
}
ROLES['polish'] = ROLES['finalize']
POLISH_REVISION_SCOPE = '只判断当前完整稿的发布阅读效果；有具体问题交给全文编辑，无问题保留当前稿。'

BLUEPRINT_FIELDS_DESCRIPTIONS = {
    'article_brief': '用一两句正向说明本篇读者、体裁、对象范围与重点；明确用户要求继续保留。',
    'brand_positioning_use': '本篇推荐主体、产品与业务重点，直接说明介绍重心。',
    'answer_use': '正向说明本篇怎样回应正式问题，呈现什么内容和推荐理由。',
    'materials': '蓝图页展示的简短内容概述。',
    'writing_material_markdown': '由准备阶段继承的具体内容，作者自主取舍与组织。',
    'opening': '从什么具体需求、产品或事件进入主题，简短说明即可。',
    'sections': '各部分的具体内容与相对详略；小标题自然指向内容。',
    'ending': '最后一项具体内容怎样完成，按需要自然收住。',
    'estimated_length': '按内容估计的展开长度；没有明确硬性范围时标明仅供参考。',
    'material_adjustments': '后台使用备注，不作为章节任务或正文内容。',
    'writing_material_sources': '准备阶段已经采用的原始来源记录。',
    'example_use': '简短说明例文的叙述姿态、展开与衔接启发；文章池仅用于构思。',
    'style_source': '本篇的读者距离、说话方式、展开节奏与详略。',
}
SECTION_TASK = ('像给读者介绍接下来会读到什么，正向说明本节的具体内容、代表性细节、承接关系与相对详略。'
                '内容安排写清即可结束；作者谨慎取用、避免推断或结果解释的提醒属于后台工作备注。')


def enabled(state, *, p0=False):
    return (not p0 and state.get('selected_pattern_id') in PATTERNS
            and state.get('metadata', {}).get('natural_prose_contract') == CONTRACT)


def matches(prompt):
    return isinstance(prompt, str) and prompt.startswith(MARKER + '\n')


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2)


def skill_body():
    text = (RESOURCE_DIR / 'SKILL.md').read_text(encoding='utf-8')
    if text.startswith('---\n'):
        _, boundary, text = text[4:].partition('\n---\n')
        if not boundary:
            raise ValueError('缺少完整的16.5自然编辑资源')
    return text.strip()


def hard_length_range(wf, job):
    """Only an explicit input range is hard; model estimates stay informational."""
    meta = wf.load_state(job).get('metadata', {})
    value = meta.get('article_hard_length_range')
    if value is None:
        value = meta.get('effective_writing_requirements', {}).get('body_character_range')
    if value is None:
        return None
    if (not isinstance(value, dict) or set(value) != {'minimum', 'maximum'}
            or any(type(value[k]) is not int for k in value)
            or not 0 < value['minimum'] <= value['maximum']):
        raise ValueError('显式硬性篇幅须为有效的minimum/maximum范围')
    return dict(value)


def wrap(text, *, writer=False):
    from .writer_measure import MARKER as COUNT_MARKER
    return MARKER + '\n' + ((COUNT_MARKER + '\n') if writer else '') + text


def wrap_for(wf, job, text, *, writer=False):
    from . import p01_expression, p02_selection
    state = wf.load_state(job)
    result = wrap(text, writer=writer and hard_length_range(wf, job) is not None)
    if p02_selection.enabled(state):
        result = result.replace(MARKER + '\n', MARKER + '\n' + p02_selection.MARKER + '\n', 1)
    if p01_expression.enabled(state):
        result = result.replace(MARKER + '\n', MARKER + '\n' + p01_expression.MARKER + '\n', 1)
    return result


def system(action, prompt=''):
    if action in {'article_titles', 'article_title_review'}:
        from .writing_context_v14 import system as title_system
        return title_system(action, prompt)
    stage = 'preparation' if action == 'article_editorial_preparation' else action.rsplit('_', 1)[-1]
    parts = [ROLES[stage]]
    if stage in {'draft', 'edit', 'repair'}:
        parts += [skill_body(), MATERIAL_GUIDANCE, LENGTH_GUIDANCE]
        from .writer_measure import MARKER as COUNT_MARKER
        if COUNT_MARKER in prompt.split('\n')[:4]:
            parts.append('完成正文后调用count_article记录实际字符数，并按当前明确硬性范围调整有内容的展开。')
    elif stage == 'blueprint':
        parts += [MATERIAL_GUIDANCE, LENGTH_GUIDANCE, STYLE_GUIDANCE]
    elif stage in {'finalize', 'polish'}:
        parts.append(STYLE_GUIDANCE)
    if stage == 'draft':
        parts.append('本动作的返回对象包含三个字段：article_markdown（完整正文）、requires_blueprint_reconfirmation（正常写作为false）、reconfirmation_reason（正常写作为空字符串）。三个字段一起返回。')
    elif stage == 'edit':
        parts.append('本动作同时返回edit_status、article_markdown、editorial_notes、requires_blueprint_reconfirmation、reconfirmation_reason。正文是完整编辑稿，其他字段只记录动作状态与实际修改。')
    parts.append('最后单独调用submit_result提交结果，成功后只回复{"submitted":true}。'
                 if stage in {'preparation', 'blueprint', 'finalize', 'polish'}
                 else '只返回当前动作要求的JSON对象和完整正文，不加代码围栏。')
    return '\n\n'.join(parts)


def _pattern(wf, job):
    pattern = wf.load_state(job).get('selected_pattern_id')
    if pattern not in PATTERNS:
        raise ValueError('16.5写作仅适用于P01至P06')
    return pattern


def commission(wf, job, *, editor=False, planning=False):
    from .manuscript_revision import current_revision
    from . import p02_selection, question_positioning_handoff
    state = wf.load_state(job)
    brief = dict(requirements.effective(wf, job, p0=False))
    if state.get('metadata', {}).get('product_source_policy') == PRODUCT_SOURCE_CONTRACT:
        brief.pop('material_input_note', None)
    if planning and question_positioning_handoff.context(wf, job):
        explicit = state.get('metadata', {}).get('effective_writing_requirements', {})
        for field in ('brand_positioning_use', 'recommendation_relationships'):
            if field not in explicit:
                brief.pop(field, None)
        if 'candidate_order' not in explicit and not p02_selection.enabled(state):
            brief.pop('candidate_order', None)
        if 'article_brief' not in explicit and state.get('decisions', {}).get('response_brief'):
            brief['article_brief'] = state['decisions']['response_brief']
    if editor:
        for field in ('reference_roles', 'brand_positioning_use', 'answer_use'):
            brief.pop(field, None)
    length = hard_length_range(wf, job)
    if length:
        brief['body_character_range'] = length
        brief['estimated_length'] = f"明确硬性范围：{length['minimum']}—{length['maximum']}个正文可见字符。"
    else:
        estimate = brief.get('estimated_length')
        brief['estimated_length'] = ((str(estimate) + '（建议篇幅，仅供参考，按有效内容展开。）')
                                     if estimate else '按本题内容充分展开，预计长度仅供参考。')
    from . import article_focus
    parts = ['<current_commission>', _json(brief), article_focus.context(state), PATTERN_GUIDANCE[_pattern(wf, job)], STYLE_GUIDANCE,
             '正文采用第三人称，首行保留一个H1。字符数包含小标题、标点、数字与英文，排除主标题、空白及Markdown标记。']
    if brief.get('recommendation_relationships'):
        parts.append(CATEGORY_GUIDANCE)
    if state.get('metadata', {}).get('pattern_example_note'):
        parts.append(state['metadata']['pattern_example_note'])
    revision = current_revision(wf, job, p0=False)
    if revision:
        parts.append('本轮用户修改要求：\n' + revision['edits_markdown'])
    if p02_selection.enabled(state):
        parts.append(p02_selection.context(state))
    return '\n\n'.join(parts + ['</current_commission>'])


def preparation_commission(wf, job):
    from . import p02_selection
    state = wf.load_state(job)
    brief = dict(state.get('metadata', {}).get('effective_writing_requirements', {}))
    brief.setdefault('article_brief', state.get('decisions', {}).get('response_brief', ''))
    brief['question'] = state.get('question', {}).get('question_text', '')
    brief['pattern_id'] = _pattern(wf, job)
    brief = p02_selection.project(state, brief)
    parts = ['<current_commission>', _json(brief), PATTERN_GUIDANCE[brief['pattern_id']], LENGTH_GUIDANCE]
    current = state.get('metadata', {}).get('pattern_example_note')
    if current:
        parts.append(current)
    if p02_selection.enabled(state):
        parts.append(p02_selection.context(state))
    return '\n\n'.join(parts + ['</current_commission>'])


def preparation(wf, job):
    from .editorial_preparation import load
    return load(job)


def _planning_references(wf, job):
    from . import article_pool, question_positioning_handoff
    return [value for value in (question_positioning_handoff.context(wf, job),
                               article_pool.prompt_references(wf, job)) if value]


def prompt_preparation(wf, job):
    state = wf.load_state(job)
    parts = ['# 案例研究与写作准备', preparation_commission(wf, job),
             '本轮案例体裁：\n' + CASE_TYPES[_pattern(wf, job)],
             *_planning_references(wf, job),
             '已确认定位提供对象、主次与内容方向；其中历史核对意见仅供后台理解，构思与素材用产品、业务和事件的正向内容描述。文章池只借鉴构思，独立例文继续决定文风。',
             '研究线索：\n' + _json(state.get('metadata', {}).get('editorial_research_hints', {})),
             '已有例文索引：\n' + _json(wf.load_examples(job, 'question')),
             '原始材料目录：\n' + _json(state.get('metadata', {}).get('blueprint_material_roots', [])),
             '材料索引：\n' + str(wf.user_material_index(job, 'question') or ''),
             '本轮另外搜索并读取两个匹配体裁的完整案例，与已有例文不同；体裁优先，必要时放宽行业细分词。web_read取得文章后用read_material分段读到正文结尾。随后按本篇需要读原始材料。',
             '通过submit_result提交writing_material_markdown（直接介绍对象或事件的自然素材段落）、blueprint_suggestions（简短安排内容如何进入、展开、承接和结束）、reference_cases（恰好两项，每项source_ref/title/url/insight）、writing_material_sources（实际采用原件的source_ref/use）、material_adjustments（后台工作备注，可为空）。作者内容呈现产品与业务本身，结果解释、取用提醒和采购核对留在material_adjustments。提交前连着读素材和构思建议，把工作意见移到后台；来源与备注随结果保存。']
    if state.get('metadata', {}).get('product_source_policy') == PRODUCT_SOURCE_CONTRACT:
        parts.insert(0, PRODUCT_SOURCE_MARKER)
    return wrap_for(wf, job, '\n\n'.join(parts))


def prompt_blueprint(wf, job, *, p0=False):
    from .writing_context_v14 import examples
    from . import article_pool
    prep = preparation(wf, job)
    # Confirmed positioning enters preparation. Pass its selected content
    # forward rather than reintroducing historical review prose here.
    parts = ['# 本篇写作蓝图', commission(wf, job, planning=True), article_pool.prompt_references(wf, job),
             '选用内容：\n' + prep['writing_material_markdown'],
             '构思建议：\n' + prep['blueprint_suggestions'],
             examples(wf, job, p0=False, stage='blueprint'),
             '以上准备已经提供所需内容，本轮直接安排文章。定位中的后台核对要求不安排成导语、章节任务或结尾。各节以产品、业务、事件、差异或做法为主线，用正向描述写明内容。',
             'task可以这样说明内容：“介绍蛋形终端在服务台面的使用形态，接着讲采集信息怎样进入报告。报告部分重点展开查看、保存、打印和现场讲解，让后续记录自然接上来。”这只是语言尺度示范，具体内容随本题安排。各节的取用提醒保存在后台备注，task只讲文章将呈现的内容。',
             '字段说明：\n' + _json(BLUEPRINT_FIELDS_DESCRIPTIONS), 'sections.task：' + SECTION_TASK,
             '通过submit_result提交kind=article、question、pattern_id、article_brief、candidate_order、brand_positioning_use、answer_use、opening、sections、ending、materials、estimated_length、style_source、example_use。素材、来源、后台备注由程序继承。']
    edits = wf.load_state(job).get('decisions', {}).get('blueprint_edits')
    if edits:
        parts.append('当前用户构思要求：\n' + str(edits))
    return wrap_for(wf, job, '\n\n'.join(parts))


def references(wf, job, *, outline=False):
    from .writing_materials import selected
    from .manuscript_revision import current_revision
    from .writing_context_v14 import examples
    bp = _blueprint(job, p0=False)
    material = selected(current_revision(wf, job, p0=False), bp)
    parts = [MATERIAL_GUIDANCE, '本篇选用内容：\n' + material['writing_material_markdown']]
    if outline:
        parts.append('可调整的内容构思：\n' + _json({k: bp[k] for k in ('opening', 'sections', 'ending') if k in bp}))
        parts.append('构思帮助把握主次。作者自主完成措辞、段落与衔接，历史审读安排不成为正文叙述。')
    parts.append(examples(wf, job, p0=False, stage='draft', include_blueprint_guidance=False))
    parts.append('完整例文用于体会读者姿态、导语、具体展开与节奏，事实留在各自原文；已有文章池参考只用于构思。')
    return '<reference_data>\n' + '\n\n'.join(parts) + '\n</reference_data>'


def length_note(body):
    from .natural_editor import character_count
    return '当前正文可见字符数：' + str(character_count(body)) + '；此数字只记录长度。'


def prompt_article(wf, job, *, p0=False):
    return wrap_for(wf, job, '# 写成完整初稿\n\n' + commission(wf, job)
                    + '\n\n' + references(wf, job, outline=True)
                    + '\n\n' + STYLE_GUIDANCE + '\n' + LENGTH_GUIDANCE
                    + '\n提交完整JSON：{"article_markdown":"完整正文","requires_blueprint_reconfirmation":false,"reconfirmation_reason":""}。三个字段一起写齐；正常写作取舍直接完成。', writer=True)


def prompt_edit(wf, job, *, p0=False):
    body = edit_base_input(wf, job, p0=False)['article_markdown']
    return wrap_for(wf, job, '# 全文发布编辑\n\n完整基稿：\n' + body + '\n\n' + length_note(body)
                    + '\n\n' + commission(wf, job, editor=True) + '\n\n' + references(wf, job)
                    + '\n\n先按读者阅读顺序重新想清各段要讲的事情，再编辑整篇稿件。技术、专业和系统交付内容围绕本题读者需要展开，把代表性细节接回对象的使用或业务过程。后文讲新增内容，前文讲清的功能顺势承接即可。把已经自然的表达留下；读着别扭的整段重新组织，段落按意思自然分开。完成后连起来读，交付正文中的实际修改。'
                    + '\n提交完整JSON：{"edit_status":"revised","article_markdown":"完整正文","editorial_notes":["实际完成的简短修改"],"requires_blueprint_reconfirmation":false,"reconfirmation_reason":""}。全文自然无需改动时用accepted，正文原样保留且editorial_notes=[]。', writer=True)


def prompt_finish(wf, job, *, after_repair=True):
    from .natural_editorial_v165 import input_body
    body = input_body(wf, job, after_repair=after_repair)
    return wrap_for(wf, job, '# 通读当前完整发布稿\n\n' + commission(wf, job, editor=True)
                    + '\n\n唯一待验读候选：\n' + body
                    + '\n\n只提交needs_revision与comments。能自然发布时为false与[]；存在实际阅读问题时为true，comments简短指出原句或段落与重写方向。'
                    '通读全文再判断，已经解决的上轮问题不再沿用；不提供局部替换、不写评分或事实检查结果。')


def prompt_finalize(wf, job, *, p0=False):
    return prompt_finish(wf, job, after_repair=False)


def prompt_repair(wf, job, *, p0=False):
    from .natural_editorial_v165 import repair_context
    context = repair_context(wf, job)
    body = context['article_markdown']
    return wrap_for(wf, job, '# 重新编辑当前完整稿\n\n完整失败候选：\n' + body
                    + '\n\n本轮阅读意见：\n' + _json(context['comments'])
                    + '\n\n' + commission(wf, job, editor=True) + '\n\n' + references(wf, job)
                    + '\n\n意见用于定位阅读问题。围绕相关内容重写，处理整篇同类问题；保持已经自然的段落。直接返回JSON，仅含article_markdown（完整修订正文）。', writer=True)
