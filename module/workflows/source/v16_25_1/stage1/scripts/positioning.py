"""Guided positioning: answer-derived categories -> user choice -> visible
same-category candidates -> user choice -> frozen downstream scope.

All visibility figures are computed from supplied answer bodies and attributed
local spans. Visibility is an observation, not a product/registration fact.
"""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import copy
import re
import shutil
import uuid
import product_boundaries as pb
import writing_pack as wp

CONTRACT='frontmind-guided-positioning/16.18'
PHASES=('categories','candidates','candidate_review','decision')
CHOICE_BY=('user','explicit_prior_choice')
RELATIONS=('direct','adjacent','cross_category','undetermined')
EVIDENCE=('supported','pending','conflicting')

CATEGORY_SCHEMA={
 'product_boundary_review':pb.REVIEW_SCHEMA,
 'primary_split_axis':{'id':'purpose','dimension_id':'关键产品维度ID','label':'产品本质与用途边界','reason':'从答案和本产品看，为什么这条分界影响实际选择'},
 'categories':[{'id':'c1','label':'答案支持的产品大类','scope':'纳入与排除的用途边界','axis_id':'purpose',
   'boundary_values':{'关键产品维度ID':'取值ID'},'scenario_tags':['同类产品可跨机构/家庭场景，不据场景判产品属性'],
   'answer_evidence':[{'observation_id':'q000001:p000001:0001','quote':'答案原句'}],
   'brand_fit':{'assessment':'recommended/possible/unlikely','reason':'本企业具体产品为什么适配','fact_ids':['k001']},
   'segments':[{'id':'s1','label':'必要的细分','scope':'实际影响替代关系的细分','axis_id':'product_detail','boundary_values':{}}]}],
 'entities':[{'id':'e1','name':'实际品牌或产品名','aliases':['确有对应关系的名称'],'company':'主体，未知留空','entity_level':'brand/product/solution','is_own_brand':False}],
 'answer_analyses':[{'observation_id':'q000001:p000001:0001',
   'category_contexts':[{'category_id':'c1','segment_id':'s1或null','quote':'支持此答案涉及该类的原句'}],
   'placements':[{'entity_id':'e1','category_id':'c1或null','segment_id':'s1或null','mention_kind':'recommended/neutral/excluded/background/unclassified','quote':'包含实体名称且支持局部分类的连续原文'}],
   'conflicts':[],'note':'此份答案怎样分类；没有明确分类时如实说明'}],
 'attributes':{'form_factor':[],'commercial_options':[],'geography_versions':[],'supporting_claims':[]},
 'unresolved':[]
}
CANDIDATE_SCHEMA={
 'additional_entities':[],
 'additional_placements':[],
 'candidates':[{'candidate_id':'p1','entity_id':'e1','display_name':'主体／对应产品或方案','offer_name':'具体产品，未知明确待核',
   'category_id':'已选category_id','segment_id':'已选segment_id或null','relationship':'direct/adjacent/cross_category/undetermined',
   'evidence_status':'supported/pending/conflicting','intended_use':'对应用途','fit_reason':'和自家产品的客户任务与替代关系',
   'boundary_checks':pb.CHECK_SCHEMA,
   'discovery_observations':['q000001:p000001:0001'],
   'sources':[{'source':'原件路径或URL','quote':'可回查原句，AI观察不当产品事实'}],
   'scope_evidence':[{'category_id':'已选大类','segment_id':None,'source':'具体产品用途的独立来源','quote':'原句'}],'unknowns':[]}],
 'not_comparable_entities':[{'entity_id':'e2','reason':'软件/模块/背景实体或其他不适合直接比较的原因'}],
 'conflicts':[],
 'selection_note':'展示统计，用户决定范围；不按可见度自动选最高两家'
}
DECISION_SCHEMA={
 'taxonomy':[{'id':'primary','overall_category':'已选大类名称','subcategory':'已选细分或大类名称',
  'product_use_customer':'当前产品×已选用途×客户','brand_fit':'依据本品牌事实的适配说明','evidence_ids':['k001'],
  'answer_evidence':[{'question_id':'q000001','period_id':'p000001','answer_index':0,'quote':'原文摘录'}],
  'competitors':[{'candidate_id':'用户选定ID','name':'选定对象名称','company':'对应主体','source':'来源或待核','fit_reason':'同类关系'}]}],
 'question_map':[{'question_id':'q000001','category':'行业排名/美誉舆情/产品场景','branch_ids':['primary'],'fit':'direct/adjacent/out_of_scope','reason':'题目对当前已选用途的适配'}],
 'excluded_questions':[],'uncertainties':[],
 'proposed_primary_positioning':'保持用户已选类别及用途，不能扩大到其他赛道',
 'attributes':{'form_factor':[],'commercial_options':[],'geography_versions':[],'supporting_claims':[]}
}

INSTRUCTIONS={
 'categories':'''这是定位暂停A之前的分类研究，不写品牌文章，也不选择最终竞品。连续阅读全部完整答案，对每份保存分类轴、类别上下文、品牌/产品所在的局部段落和矛盾。先从答案中归纳几个能影响采购替代关系的产品大类，通常2—6类；证据只有一个类别时说明，不编造多类。同级分类用同一轴；便携、租赁、地域和背书单列属性，不替代关键用途分界。必要的更小类放segments，按客户任务或产品范围细分。
给每个类别提供原答案摘录及本企业具体产品适配依据，推荐落位只作建议，等待企业选择。用户已明确的目标作为预选和条件保留，不能自动跳过类别确认；若本轮已有对同一类别的明确选择，可用explicit_prior_choice记录原话。
entities提取所有实际品牌/产品/方案及用户必研究候选，自家品牌也要进入，不能只留名气最大或容易找到官网的企业。aliases只用于明确同名关系，不把同公司所有型号能力合并。对每份答案中的实体出现逐一记录placements；不能判定类别的用null并说明。局部quote必须连续包含实体名称；不要因为全文前面写“医疗”就把后面所有品牌都标医疗。不同答案冲突保留，两种用途可以分别出现，不按多数投票消除。category_contexts记录每个答案实际涉及的类和细分，并给原句。全部原文只是AI观察，不证明资质或性能。输出后必须停在类别选择页，不能直接进入竞品研究。''',
 'candidates':'''这是定位暂停B之前的同类竞品研究，必须先读取category_selection，不能更改其类别/细分。只在用户选定的用途与客户任务内提出可比较的产品/方案；同公司不同用途分别判断。用户指定候选和全部在已选类中出现的实体均须交代：入候选表，或列not_comparable_entities及原因，不能因缺官网静默消失。跨类可以留内部说明，但不得进入可选直接竞品。
每个候选记录具体产品/方案、类别、用途、客户任务与替代理由。relationship分direct/adjacent/cross_category/undetermined，证据成熟度独立分supported/pending/conflicting；“型号待核”不等于跨类，用户指定也不等于性能事实核验完成。有同类AI上下文或本轮用户指定但资料不足时，可保留待核候选，注明缺口；未核实参数不要写成事实。发现某品牌跨多个用途时只对齐本次对应产品。
可见度由程序计算，不填写、改写或推算统计数字。程序展示全样本正文提及n/N、已选同类语境提及n/M、同类推荐提及、平台端覆盖及逐问题/日期分组。候选没有出现时如实0，数据不足时不以官网数量冒充可见度。可见度帮助企业选择，不代表推荐贡献、产品能力或市场排名。输出后必须停在同类竞品选择页，不能自动取最高两家。''',
 'decision':'''类别和竞品范围已有两次具体用户选择。依据这两份选择整理最终定位；不得更改所选类别、细分或增删竞品。只保留一个当前主产品落位，其他产品、版本、形态、租赁、地域、合作与背书放独立属性。给所有已导入问题作行业排名/美誉舆情/产品场景映射；宽问题不能扩大主产品用途。某问题明确跨类可记out_of_scope。
taxonomy的competitors须逐项带选定candidate_id，实际名称保持候选记录。候选池与单篇P02最终主体名单分开，后续可从本池选子集，不固定两家。产品事实待核的字段保留，不从AI答案转成事实。提交后程序根据两份具体选择冻结定位并继续，不新增第三个整版定位确认，也不得用泛化“同范围自动完成”代替前两次选择。'''
}
INSTRUCTIONS['candidates']+='\n用户在暂停B新增对象时，不必重选已确定类别：additional_entities每项含id、name、aliases、entity_level、discovery_note；additional_placements逐条含observation_id、entity_id、category_id或null、segment_id或null、mention_kind、连续quote。新对象在每份答案实际出现均须补局部归类或明确未定；程序据此重算，不能因原台账没有就假报0。读取user_revision_request.required_candidates并逐一覆盖。补充对象仍不能创建未确认的新类别。'
INSTRUCTIONS['categories']+='\n'+pb.INSTRUCTION
INSTRUCTIONS['candidates']+='\n'+pb.CANDIDATE_INSTRUCTION
INSTRUCTIONS['decision']+='\n最终定位必须继承selected_category.product_boundaries与regulatory_status，产品类型、场景、监管证据状态分开；不能把待核研究对象变成已证实同类。'
INSTRUCTIONS['candidate_review']=pb.REVIEW_INSTRUCTION

def d(w,p):return w.stepdir(p,2)
def path(w,p,name):return d(w,p)/(name+'.json')
def exists(w,p,name):return path(w,p,name).is_file()
def brief(w,p):
    f=Path(p)/'inputs/business_brief.json'
    return w.read(f) if f.exists() else {'target_scope':None,'required_candidates':[],'excluded_direct_scopes':[],'note':'未提供先验范围；先展示答案分类供企业选择'}

def set_brief(w,p,value):
    w.require(not exists(w,p,'category_analysis') and not w.done(p,2),'分类研究已使用业务范围，调整请先修订类别或建立新版本')
    w.require(isinstance(value,dict),'业务范围须为JSON对象')
    for key in ['required_candidates','excluded_direct_scopes','expected_questions']:
        w.require(isinstance(value.get(key,[]),list) and all(w.nonempty(x) for x in value.get(key,[])),'业务范围列表须为字符串：'+key)
    w.write(Path(p)/'inputs/business_brief.json',value)

def progress(w,p):
    if w.done(p,2):
        if w.result(p,2).get('positioning_contract')==wp.IMPORTED:return 'confirmed_portable_pack'
        return 'frozen_after_two_choices' if w.result(p,2).get('positioning_contract')==CONTRACT else 'legacy_positioning_requires_new_branch'
    if not (Path(p)/'inputs/all_answers.json').exists():return 'awaiting_all_answers'
    if exists(w,p,'category_analysis') and w.read(path(w,p,'category_analysis')).get('product_boundary_review',{}).get('schema')!=pb.CONTRACT:return 'legacy_positioning_requires_new_branch'
    if not exists(w,p,'category_analysis'):return 'ready_category_research'
    if not exists(w,p,'category_selection'):return 'awaiting_segment_selection' if exists(w,p,'category_pending') else 'awaiting_category_selection'
    if not exists(w,p,'candidate_analysis'):return 'ready_same_category_candidate_research'
    if not exists(w,p,'candidate_boundary_review'):return 'ready_candidate_boundary_review'
    if not w.read(path(w,p,'candidate_boundary_review')).get('overall_pass'):return 'candidate_boundary_review_needs_revision'
    if not exists(w,p,'competitor_selection'):return 'awaiting_competitor_selection'
    return 'ready_positioning_decision'

def observations(w,p):
    rows=[]
    for g in w.read(Path(p)/'inputs/all_answers.json'):
        for i,a in enumerate(g['answers']):
            rows.append({'observation_id':f"{g['question_id']}:{g['period_id']}:{i+1:04d}",'question_id':g['question_id'],
              'period_id':g['period_id'],'question_text':g['question_text'],'date':g.get('date'),
              'answer_index':i,'platform':a.get('platform') or '未提供端信息','source_record':a.get('source_record'),
              'answer_text':a['answer_text']})
    return rows

def coverage(w,p):
    groups=w.read(Path(p)/'inputs/all_answers.json');qs=w.catalog(p)
    expected=brief(w,p).get('expected_questions',[]);known={x['question_text'] for x in qs}
    return {'question_count':len(qs),'full_answer_count':sum(len(x['answers']) for x in groups),
      'periods':[{'question_id':g['question_id'],'question':g['question_text'],'period_id':g['period_id'],'date':g.get('date'),'answers':len(g['answers'])} for g in groups],
      'expected_questions':expected,'missing_declared_questions':[x for x in expected if x not in known],
      'completeness':'declared_catalog_covered' if expected and set(expected)<=known else 'declared_catalog_incomplete' if expected else 'not_declared',
      'note':'只说明已收到的范围；未提供预期目录时不假设还有哪些题，不把多期汇总当单期推荐率。'}

def phase_file(phase):return {'categories':'category_analysis','candidates':'candidate_analysis'}[phase]
def phase_result(w,p,phase):
    f=path(w,p,phase_file(phase));r=w.read(f.with_name(f.stem+'_record.json'))
    w.require(w.hashfile(f)==r['sha256'],'定位研究结果已被改动')
    for name,h in r['dependencies'].items():w.require((Path(p)/name).is_file() and w.hashfile(Path(p)/name)==h,'定位上游输入变化，请重新修订定位：'+name)
    value=w.read(f)
    if phase=='categories':w.require(value.get('product_boundary_review',{}).get('schema')==pb.CONTRACT,'旧分类缺少产品本质边界审查；请保留事实输入，用新版重新定位，不沿用场景分类')
    return value

def choice(w,p,name):
    f=path(w,p,name);w.require(f.is_file(),'先完成具体选择：'+name)
    v=w.read(f);w.require(v['by'] in CHOICE_BY and w.nonempty(v.get('note')),'具体选择须记录用户原话或明确选择')
    analysis='categories' if name=='category_selection' else 'candidates'
    phase_result(w,p,analysis)
    w.require(v['analysis_sha256']==w.hashfile(path(w,p,phase_file(analysis))),'用户选择不对应当前研究版本')
    if name=='competitor_selection':w.require(v['category_selection_sha256']==w.hashfile(path(w,p,'category_selection')),'竞品选择不对应当前类别')
    return v

def selected_category(w,p):
    ch=choice(w,p,'category_selection');data=phase_result(w,p,'categories')
    c=next(x for x in data['categories'] if x['id']==ch['category_id'])
    seg=next((x for x in c.get('segments',[]) if x['id']==ch.get('segment_id')),None)
    return {'category_id':c['id'],'category_label':c['label'],'category_scope':c['scope'],
            'segment_id':seg['id'] if seg else None,'segment_label':seg['label'] if seg else None,'scope':seg['scope'] if seg else c['scope'],
            'product_boundaries':pb.selected(data,c,seg),'scenario_tags':c.get('scenario_tags',[]),
            'regulatory_status':data['product_boundary_review']['regulatory_status'],
            'choice_origin':{'by':ch['by'],'note':ch['note']}}

def phase_dependencies(w,p,phase):
    deps=w.stage_deps(p,2,None)
    def add(name):
        f=path(w,p,name);deps[f.relative_to(p).as_posix()]=w.hashfile(f)
    f=Path(p)/'inputs/business_brief.json'
    if f.exists():deps[f.relative_to(p).as_posix()]=w.hashfile(f)
    for name in ['category_revision_request']+(['candidate_revision_request'] if phase!='categories' else []):
        if exists(w,p,name):add(name)
    if phase in ('candidates','candidate_review','decision'):
        choice(w,p,'category_selection');add('category_analysis');add('category_selection')
    if phase=='candidate_review':
        phase_result(w,p,'candidates');add('candidate_analysis');add('candidate_visibility')
    if phase=='decision':
        accepted_boundary_review(w,p);add('candidate_boundary_review')
        choice(w,p,'competitor_selection');add('candidate_analysis');add('competitor_selection');add('candidate_visibility')
    return deps

def inputs(w,p,phase):
    w.require(phase in PHASES,'步骤2阶段应为categories、candidates、decision')
    w.accepted(p,1);w.require((Path(p)/'inputs/all_answers.json').exists(),'分类前先导入完整问答')
    data={'step':2,'phase':phase,'contract':CONTRACT,'brand':w.state(p)['brand'],'aliases':w.state(p)['aliases'],
      'business_brief':brief(w,p),'coverage':coverage(w,p),'brand_facts':w.accepted(p,1),'question_catalog':w.catalog(p),
      'full_answer_observations':observations(w,p),'instruction':INSTRUCTIONS[phase]}
    focus=w.state(p)['brand']+' '+w.dump(w.catalog(p))+' '+w.dump(data['brand_facts'])
    data['detected_boundary_signals']=pb.signals(data['full_answer_observations'],focus)
    w.require(data['coverage']['completeness']!='declared_catalog_incomplete','已声明的问题目录尚缺完整答案，请先补齐或明确调整本轮范围')
    revision='category_revision_request' if phase=='categories' else 'candidate_revision_request'
    if exists(w,p,revision):data['user_revision_request']=w.read(path(w,p,revision))
    if phase!='categories':
        data['category_analysis']=phase_result(w,p,'categories');data['category_selection']=selected_category(w,p)
    if phase=='candidate_review':
        data['candidate_analysis']=phase_result(w,p,'candidates')
        data['candidate_analysis_sha256']=w.hashfile(path(w,p,'candidate_analysis'))
        data['instruction']=pb.REVIEW_INSTRUCTION
    if phase=='decision':
        data['candidate_analysis']=phase_result(w,p,'candidates');data['competitor_selection']=choice(w,p,'competitor_selection')
        data['visibility']=w.read(path(w,p,'candidate_visibility'))
    skill=w.ROOT/'skills/frontmind-market-positioning/SKILL.md'
    if skill.exists():data['positioning_skill']=skill.read_text(encoding='utf-8')
    if phase=='candidate_review':
        # The critic receives evidence and selected scope, not a copy of the
        # classification author's full explanation as an instruction.
        data={k:data[k] for k in ['step','phase','contract','brand','aliases','brand_facts','category_selection','candidate_analysis','candidate_analysis_sha256','instruction']}
    return data

def schema(phase):return {'categories':CATEGORY_SCHEMA,'candidates':CANDIDATE_SCHEMA,'candidate_review':pb.REVIEW_SCHEMA_CANDIDATES,'decision':DECISION_SCHEMA}[phase]

def aliases(e):return list(dict.fromkeys([e['name'],*e.get('aliases',[])]))
def mentions(body,e):return any(x in body for x in aliases(e))
def scope_match(entry,selection,include_segment=True):
    return entry.get('category_id')==selection['category_id'] and (not include_segment or not selection.get('segment_id') or entry.get('segment_id')==selection['segment_id'])

def valid_ref(w,ref,obs):
    o=obs.get(ref.get('observation_id'));w.require(o and w.nonempty(ref.get('quote')) and ref['quote'] in o['answer_text'],'定位引文必须逐字存在于指定完整答案')

def normalize_entities(w,p,v):
    ownnames=[w.state(p)['brand'],*w.state(p)['aliases']];seenown=False
    for e in v.get('entities',[]):
        w.require(w.nonempty(e.get('id')) and w.nonempty(e.get('name')),'实体需ID和实际名称')
        w.require(isinstance(e.get('aliases',[]),list) and all(w.nonempty(x) for x in e.get('aliases',[])),'实体别名须为明确字符串')
        if set(aliases(e)) & set(ownnames):e['is_own_brand']=True;seenown=True;e['aliases']=list(dict.fromkeys([*e.get('aliases',[]),*ownnames]))
    if not seenown:
        eid='own_brand';used={x['id'] for x in v.get('entities',[])}
        while eid in used:eid+='_'
        v.setdefault('entities',[]).append({'id':eid,'name':ownnames[0],'aliases':ownnames[1:],'entity_level':'brand','is_own_brand':True})

def validate_categories(w,p,v):
    w.require(isinstance(v,dict),'分类研究须JSON对象');normalize_entities(w,p,v)
    cats=v.get('categories',[]);w.require(cats,'应展示答案支持的产品类别；不能空类别')
    axis=v.get('primary_split_axis',{});w.require(all(w.nonempty(axis.get(k)) for k in ['id','label','reason']),'需明确本层产品分类轴及理由')
    ids=[x.get('id') for x in cats];w.require(len(set(ids))==len(ids) and all(w.nonempty(x) for x in ids),'类别ID重复或为空')
    entities=v['entities'];eids=[x['id'] for x in entities];w.require(len(set(eids))==len(eids),'实体ID重复')
    obs={x['observation_id']:x for x in observations(w,p)};facts={x['id'] for x in w.accepted(p,1)['knowledge']};segments={}
    focus=w.state(p)['brand']+' '+w.dump(w.catalog(p))+' '+w.dump(w.accepted(p,1))
    pb.validate_review(w,v,obs,pb.signals(list(obs.values()),focus))
    for c in cats:
        w.require(c.get('axis_id')==axis['id'] and w.nonempty(c.get('label')) and w.nonempty(c.get('scope')),'平级类别必须采用同一分类轴，并有用途纳入/排除范围')
        w.require(c.get('answer_evidence'),'每个类别须有实际答案依据，不可凭空造类别')
        for ref in c['answer_evidence']:valid_ref(w,ref,obs)
        fit=c.get('brand_fit',{});w.require(fit.get('assessment') in ['recommended','possible','unlikely'] and w.nonempty(fit.get('reason')),'每类需展示本品牌适配判断与理由')
        w.require(set(fit.get('fact_ids',[]))<=facts,'品牌适配引用未知事实')
        segment_axes=set()
        for s in c.get('segments',[]):
            w.require(w.nonempty(s.get('id')) and s['id'] not in segments and w.nonempty(s.get('label')) and w.nonempty(s.get('scope')) and w.nonempty(s.get('axis_id')),'细分类别需唯一ID、定义和分类轴')
            segments[s['id']]=c['id'];segment_axes.add(s['axis_id'])
        w.require(len(segment_axes)<=1,'同一大类下的平级细分不能混用分类轴')
    aa=v.get('answer_analyses',[]);aids=[x.get('observation_id') for x in aa]
    w.require(len(aids)==len(obs) and set(aids)==set(obs),'必须逐份提炼所有实际答案，不能只挑几句支撑定位')
    lookup={x['id']:x for x in entities}
    for row in aa:
        o=obs[row['observation_id']];contexts=row.get('category_contexts',[])
        for c in contexts:
            w.require(c.get('category_id') in ids,'类别上下文引用未知类别')
            if c.get('segment_id'):w.require(segments.get(c['segment_id'])==c['category_id'],'细分须属于该大类')
            valid_ref(w,{'observation_id':row['observation_id'],'quote':c.get('quote')},obs)
        ps=row.get('placements',[])
        for e in ps:
            w.require(e.get('entity_id') in lookup and e.get('mention_kind') in ['recommended','neutral','excluded','background','unclassified'],'实体归类或提及角色无效')
            w.require(e.get('category_id') is None or e['category_id'] in ids,'实体归类引用未知类别')
            if e.get('segment_id'):w.require(segments.get(e['segment_id'])==e.get('category_id'),'实体细分与大类不一致')
            valid_ref(w,{'observation_id':row['observation_id'],'quote':e.get('quote')},obs)
            w.require(mentions(e['quote'],lookup[e['entity_id']]),'归类引文必须连续包含对应实体名称，不能只引无关的医疗/康养词')
            if e.get('category_id'):
                w.require(any(x['category_id']==e['category_id'] and (not e.get('segment_id') or x.get('segment_id')==e['segment_id']) for x in contexts),'实体归类需要同答案对应的类别上下文')
        # Coverage concerns every discovered/required entity, without claiming
        # that a deterministic matcher can discover all unknown proper names.
        for e in entities:
            if mentions(o['answer_text'],e):w.require(any(x['entity_id']==e['id'] for x in ps),'已发现实体在此答案出现但无局部归类/未定记录：'+e['name']+' / '+row['observation_id'])
        w.require(w.nonempty(row.get('note')),'每份答案需分类或未分类说明')
    for seed in brief(w,p).get('required_candidates',[]):
        w.require(any(seed in aliases(e) for e in entities),'用户指定候选必须入实体台账：'+seed)
    return v

def validate_candidates(w,p,v):
    selection=selected_category(w,p);cats=phase_result(w,p,'categories');obs={x['observation_id']:x for x in observations(w,p)}
    baseids={x['id'] for x in cats['entities']};extras=v.get('additional_entities',[])
    w.require(isinstance(extras,list) and isinstance(v.get('additional_placements',[]),list),'补充实体与局部归类须为数组')
    extraids=[e.get('id') for e in extras]
    w.require(len(extraids)==len(set(extraids)) and not (set(extraids)&baseids),'补充实体ID不能重复或覆盖原分类实体')
    for e in extras:
        w.require(w.nonempty(e.get('id')) and w.nonempty(e.get('name')) and w.nonempty(e.get('discovery_note')),'补充实体需名称、ID和用户/研究发现说明')
        w.require(isinstance(e.get('aliases',[]),list) and all(w.nonempty(a) for a in e.get('aliases',[])),'补充实体别名格式无效')
        w.require(not e.get('is_own_brand') and not(set(aliases(e))&set([w.state(p)['brand'],*w.state(p)['aliases']])),'不能把自家作为补充竞品')
    entities,analyses=expanded_view(w,p,v);rows=v.get('candidates',[])
    segs={s['id']:c['id'] for c in cats['categories'] for s in c.get('segments',[])};catids={c['id'] for c in cats['categories']}
    for x in v.get('additional_placements',[]):
        w.require(x.get('entity_id') in extraids and x.get('observation_id') in obs,'补充局部归类只适用于新实体及实际答案')
        w.require(x.get('mention_kind') in ['recommended','neutral','excluded','background','unclassified'],'补充提及角色无效')
        w.require(x.get('category_id') is None or x['category_id'] in catids,'补充实体不能创建未确认的新类别')
        if x.get('segment_id'):w.require(segs.get(x['segment_id'])==x.get('category_id'),'补充细分与大类不符')
        valid_ref(w,x,obs);w.require(mentions(x['quote'],entities[x['entity_id']]),'补充原句必须包含对应新实体')
    for e in extras:
        for oid,o in obs.items():
            if mentions(o['answer_text'],e):w.require(any(x.get('entity_id')==e['id'] and x.get('observation_id')==oid for x in v.get('additional_placements',[])),'新实体在答案出现，须补局部归类或明确未定，不能假报0可见度')
    w.require(isinstance(rows,list) and isinstance(v.get('not_comparable_entities',[]),list),'需候选与未纳入对象台账')
    ids=[x.get('candidate_id') for x in rows];w.require(len(ids)==len(set(ids)) and all(w.nonempty(x) for x in ids),'候选产品ID重复或为空')
    covered=set()
    for c in rows:
        e=entities.get(c.get('entity_id'));w.require(e and not e.get('is_own_brand'),'候选须是已发现的外部实体，不能将自家列竞品')
        covered.add(e['id']);w.require(c.get('relationship') in RELATIONS and c.get('evidence_status') in EVIDENCE,'竞品关系与证据状态须独立填写')
        pb.validate_candidate(w,c,selection)
        w.require(all(w.nonempty(c.get(k)) for k in ['display_name','offer_name','intended_use','fit_reason']),'候选需对应产品/方案、用途和替代理由')
        w.require(not (set(c)&{'visibility','all_hits','all_total','same_scope_hits','same_scope_total','mention_count','recommendation_rate','score','rank'}),'候选分析不得填写统计/评分数字，可见度由程序计算')
        if c['relationship']=='direct':
            w.require(scope_match(c,selection),'明确跨类或跨细分的产品不能标为直接竞品')
            placements=[x for row in analyses for x in row.get('placements',[]) if x['entity_id']==e['id']]
            local=any(scope_match(x,selection) for x in placements)
            scopes={x.get('category_id') for x in placements if x.get('category_id')}
            if len(scopes)>1 and e.get('entity_level')=='brand':
                local=c['offer_name'] not in aliases(e) and any(scope_match(x,selection) and c['offer_name'] in x['quote'] for x in placements)
            scoped_sources=c.get('scope_evidence',[])
            independent=any(scope_match(x,selection) and w.nonempty(x.get('source')) and w.nonempty(x.get('quote')) for x in scoped_sources)
            w.require(local or independent,'直接同类关系须有本类局部语境或具体产品的独立用途来源，不能只改category_id')
        for oid in c.get('discovery_observations',[]):
            w.require(oid in obs and mentions(obs[oid]['answer_text'],e),'候选发现记录必须含对应实体')
        if c['evidence_status']=='supported':w.require(c.get('sources') and all(w.nonempty(x.get('source')) and w.nonempty(x.get('quote')) for x in c['sources']),'已支持的产品事实需原件/公开来源及摘录')
        if c['evidence_status']!='supported':w.require(c.get('unknowns'),'待核或冲突候选须列实际缺口，不作事实已核验展示')
    excluded=v.get('not_comparable_entities',[])
    for e in excluded:
        w.require(e.get('entity_id') in entities and w.nonempty(e.get('reason')),'未纳入对象须有实体与具体原因')
        w.require(e['entity_id'] not in covered,'同一实体不能既入候选又整体排除');covered.add(e['entity_id'])
    required={x['entity_id'] for r in analyses for x in r.get('placements',[]) if scope_match(x,selection) and not entities[x['entity_id']].get('is_own_brand')}
    for seed in brief(w,p).get('required_candidates',[]):required.update(e['id'] for e in entities.values() if seed in aliases(e))
    if exists(w,p,'candidate_revision_request'):
        for name in w.read(path(w,p,'candidate_revision_request')).get('required_candidates',[]):
            found=[e['id'] for e in entities.values() if name in aliases(e)];w.require(found,'用户补充候选未进入实体台账：'+name);required.update(found)
    w.require(required<=covered,'同类语境实体或用户指定候选未逐一处理，不能静默遗漏：'+','.join(sorted(required-covered)))
    return v

def expanded_view(w,p,candidates=None):
    data=phase_result(w,p,'categories');candidate_data=candidates if candidates is not None else phase_result(w,p,'candidates') if exists(w,p,'candidate_analysis') else {}
    entities={x['id']:x for x in [*data['entities'],*candidate_data.get('additional_entities',[])]}
    aa=copy.deepcopy(data['answer_analyses']);lookup={x['observation_id']:x for x in aa}
    for x in candidate_data.get('additional_placements',[]):
        if x.get('observation_id') not in lookup:continue
        row=lookup[x['observation_id']];row['placements'].append(x)
        if x.get('category_id'):row['category_contexts'].append({'category_id':x['category_id'],'segment_id':x.get('segment_id'),'quote':x.get('quote')})
    return entities,aa

def calculate_visibility(w,p,candidates=None):
    entities,analyses=expanded_view(w,p,candidates);sel=selected_category(w,p);obs=observations(w,p);aa={x['observation_id']:x for x in analyses}
    scoperows={o['observation_id'] for o in obs if any(scope_match(c,sel) for c in aa[o['observation_id']]['category_contexts'])}
    def service(label):return re.split(r'[-—_](?:网页|手机|桌面|小程序|App|APP)',label,maxsplit=1)[0]
    def known_surface(x):return x.strip().casefold() not in {'未提供端信息','未提供','未知平台','unknown','unspecified','n/a',''}
    allsurfaces={o['platform'] for o in obs if known_surface(o['platform'])};allservices={service(x) for x in allsurfaces};rows=[]
    groups=defaultdict(list)
    for o in obs:groups[(o['question_id'],o['period_id'],o['date'])].append(o)
    for e in entities.values():
        hits={o['observation_id'] for o in obs if mentions(o['answer_text'],e)}
        local={oid for oid,r in aa.items() if any(x['entity_id']==e['id'] and scope_match(x,sel) for x in r.get('placements',[]))}
        rec={oid for oid,r in aa.items() if any(x['entity_id']==e['id'] and scope_match(x,sel) and x['mention_kind']=='recommended' for x in r.get('placements',[]))}
        surfaces=sorted({o['platform'] for o in obs if o['observation_id'] in hits and known_surface(o['platform'])});services=sorted({service(x) for x in surfaces});sub=[]
        for (qid,pid,date),gs in groups.items():
            gids={x['observation_id'] for x in gs}
            sub.append({'question_id':qid,'question':gs[0]['question_text'],'period_id':pid,'date':date,'all_hits':len(hits&gids),'all_total':len(gids),
               'same_scope_hits':len(local&gids),'same_scope_total':len(scoperows&gids),'same_scope_recommended':len(rec&gids),
               'hit_observation_ids':sorted(hits&gids),'scope_observation_ids':sorted(local&gids)})
        rows.append({'entity_id':e['id'],'name':e['name'],'entity_level':e.get('entity_level','未标明'),'is_own_brand':bool(e.get('is_own_brand')),
           'all_hits':len(hits),'all_total':len(obs),'same_scope_hits':len(local),'same_scope_total':len(scoperows),'same_scope_recommended':len(rec),
           'surface_hits':len(surfaces),'surface_total':len(allsurfaces),'surfaces':surfaces,
           'service_hits':len(services),'service_total':len(allservices),'services':services,'by_question_period':sub})
    return {'contract':CONTRACT,'selection':sel,'coverage':coverage(w,p),'rows':rows,
      'counting_rule':'全样本n/N为完整答案正文精确别名出现；同类n/M来自已审读的局部归类，M为涉及已选类别/细分的答案数；同类推荐只统计recommended角色。每份答案去重一次。',
      'limits':'不是市场份额、推荐贡献或产品能力。平台端不等于独立模型；多题多期仅汇总描述，逐题逐期记录单列。未披露名次时不补造排名率。'}

def ensure_visibility(w,p):
    f=path(w,p,'candidate_visibility')
    if not f.exists():w.write(f,calculate_visibility(w,p))
    return w.read(f)

def phase_submit(w,p,phase,v,model,deps):
    if phase=='candidate_review':
        w.require(not exists(w,p,'competitor_selection') and not exists(w,p,'candidate_boundary_review'),'复核已有结果或竞品已选；先修订候选，保留旧记录')
        analysis=phase_result(w,p,'candidates')
        v=pb.validate_candidate_review(w,v,analysis,w.hashfile(path(w,p,'candidate_analysis')))
        f=path(w,p,'candidate_boundary_review');w.write(f,v)
        w.write(path(w,p,'candidate_boundary_review_record'),{'sha256':w.hashfile(f),'dependencies':deps,'actual_model':model,'at':w.now()})
        w.write(Path(p)/'reference_pack/guided_positioning/candidate_boundary_review.json',v)
        return
    w.require(phase in ('categories','candidates'),'此函数仅提交两段研究')
    w.require(not exists(w,p,'category_selection') if phase=='categories' else not exists(w,p,'competitor_selection'),'具体选择已冻结，先用revise-positioning建立修订记录')
    v=validate_categories(w,p,v) if phase=='categories' else validate_candidates(w,p,v)
    visibility=calculate_visibility(w,p,v) if phase=='candidates' else None
    f=path(w,p,phase_file(phase))
    w.require(not f.exists(),'该阶段研究已保存；修订请使用revise-positioning，不覆盖旧结果')
    w.write(f,v);w.write(f.with_name(f.stem+'_record.json'),{'sha256':w.hashfile(f),'dependencies':deps,'actual_model':model,'at':w.now()})
    if phase=='candidates':w.write(path(w,p,'candidate_visibility'),visibility)
    pack=Path(p)/'reference_pack/guided_positioning';w.write(pack/f.name,v)
    if phase=='candidates':w.write(pack/'candidate_visibility.json',w.read(path(w,p,'candidate_visibility')))

def accepted_boundary_review(w,p):
    f=path(w,p,'candidate_boundary_review');w.require(f.is_file(),'先自动复核候选产品边界证据，再展示竞品选择页')
    r=w.read(path(w,p,'candidate_boundary_review_record'));w.require(r['sha256']==w.hashfile(f),'证据复核结果已改变')
    for name,h in r['dependencies'].items():w.require((Path(p)/name).is_file() and w.hashfile(Path(p)/name)==h,'证据复核依赖已变化，请修订候选后重新复核')
    analysis=phase_result(w,p,'candidates');v=w.read(f)
    pb.validate_candidate_review(w,v,analysis,w.hashfile(path(w,p,'candidate_analysis')))
    w.require(v['overall_pass'],'候选产品边界证据复核未通过；先修订候选或补来源，不得进入同类选择')
    return v

def choose_category(w,p,category_id,segment_id,by,note):
    w.require(by in CHOICE_BY and w.nonempty(note),'类别选择须记录用户具体选择，不接受泛化自动授权')
    w.require(not exists(w,p,'category_selection'),'类别已选；调整请先revise-positioning --scope categories')
    data=phase_result(w,p,'categories');c=next((x for x in data['categories'] if x['id']==category_id),None)
    w.require(c,'请从展示的大类中选择，新增类别先修订分类研究')
    if by=='explicit_prior_choice':w.require(c['label'] in note or c['id'] in note,'既有选择记录须引用具体类别/映射，不能只写“同范围自动完成”')
    segs=c.get('segments',[])
    if len(segs)>1 and not segment_id:
        w.write(path(w,p,'category_pending'),{'category_id':category_id,'by':by,'note':note,'analysis_sha256':w.hashfile(path(w,p,'category_analysis')),'at':w.now()});return
    if len(segs)==1 and not segment_id:segment_id=segs[0]['id']
    w.require(not segment_id or any(x['id']==segment_id for x in segs),'细分不属于所选大类')
    if by=='explicit_prior_choice' and segment_id:
        segment=next(x for x in segs if x['id']==segment_id)
        w.require(segment['label'] in note or segment_id in note,'既有选择只指明大类不能代选必要细分，请记录具体细分选择或返回暂停A')
    value={'category_id':category_id,'segment_id':segment_id,'by':by,'note':note,'at':w.now(),'analysis_sha256':w.hashfile(path(w,p,'category_analysis'))}
    if exists(w,p,'category_pending') and w.read(path(w,p,'category_pending'))['category_id']==category_id:value['broad_category_choice']=w.read(path(w,p,'category_pending'))
    w.write(path(w,p,'category_selection'),value);w.write(Path(p)/'reference_pack/guided_positioning/category_selection.json',value)
    path(w,p,'category_pending').unlink(missing_ok=True)

def choose_competitors(w,p,ids,none,by,note,ack_pending=False):
    w.require(by in CHOICE_BY and w.nonempty(note),'竞品范围须记录用户具体选择，不接受泛化自动授权')
    w.require(not exists(w,p,'competitor_selection'),'竞品已选，调整请先revise-positioning --scope competitors')
    accepted_boundary_review(w,p)
    sel=selected_category(w,p);data=phase_result(w,p,'candidates');rows={x['candidate_id']:x for x in data['candidates']}
    w.require(bool(ids)!=bool(none),'请选择候选ID或明确--none，不能同时选择')
    if none and by=='explicit_prior_choice':
        w.require(re.search(r'\bnone\b|无竞品|没有竞品|不(?:纳入|选择|选|需要|设).*竞品|竞品.*(?:为空|留空|不选)',note,re.I),'既有授权未明确空竞品范围；不能用“自动完成”代选none')
    w.require(len(ids)==len(set(ids)) and set(ids)<=set(rows),'候选ID重复或不存在')
    pending=[]
    for cid in ids:
        c=rows[cid];w.require(pb.eligibility(c,sel),'产品本质边界不符或跨类产品不能选进同类竞品池；相同场景不能替代')
        w.require(not sel.get('segment_id') or c.get('segment_id') in [None,sel['segment_id']],'明确属于其他细分的产品不能直接纳入本细分')
        if c['evidence_status']!='supported' or c['relationship']=='undetermined' or pb.candidate_state(c)=='uncertain':pending.append(cid)
        if by=='explicit_prior_choice':
            e=expanded_view(w,p)[0][c['entity_id']]
            w.require(any(x in note for x in [cid,c['display_name'],c['offer_name'],*aliases(e)]),'既有选择记录须指明每个选定对象，泛化授权不能代选')
    w.require(not pending or ack_pending,'所选对象存在待核实/冲突；如用户明确将其保留研究池，用--ack-pending并记录原话，不能冒充事实已核')
    value={'candidate_ids':ids,'none':bool(none),'by':by,'note':note,'pending_candidates_acknowledged':pending,'at':w.now(),
      'analysis_sha256':w.hashfile(path(w,p,'candidate_analysis')),'category_selection_sha256':w.hashfile(path(w,p,'category_selection')),
      'visibility_sha256':w.hashfile(path(w,p,'candidate_visibility'))}
    w.write(path(w,p,'competitor_selection'),value);w.write(Path(p)/'reference_pack/guided_positioning/competitor_selection.json',value)

def snapshot(w,p):
    accepted_boundary_review(w,p)
    s=selected_category(w,p);ch=choice(w,p,'competitor_selection');data=phase_result(w,p,'candidates')
    w.require(ch['visibility_sha256']==w.hashfile(path(w,p,'candidate_visibility')),'竞品可见度展示版本已变化')
    selected=[x for x in data['candidates'] if x['candidate_id'] in ch['candidate_ids']]
    payload={'contract':CONTRACT,'selected_category':s,'selected_candidates':selected,'candidate_boundary_review_sha256':w.hashfile(path(w,p,'candidate_boundary_review')),'competitor_choice':{'by':ch['by'],'note':ch['note']},
      'boundary_note':'名单是已选研究/比较范围，不证明未核实产品事实；P02只从此池选本篇子集，不能按全行业声量另换名单。'}
    payload['snapshot_id']=w.digest(w.dump(payload));return payload

def validate_decision(w,p,v):
    snap=snapshot(w,p);s=snap['selected_category'];ts=v.get('taxonomy',[])
    w.require(len(ts)==1,'当前优化产品只保留一个已选主落位，形态/部署/海外放属性，不列成平级主类')
    t=ts[0];w.require(t.get('overall_category')==s['category_label'] and t.get('subcategory')==(s['segment_label'] or s['category_label']),'最终定位不可改写已确认的类别或细分名称')
    wanted={x['candidate_id'] for x in snap['selected_candidates']};actual=[x.get('candidate_id') for x in t.get('competitors',[])]
    w.require(len(actual)==len(wanted) and set(actual)==wanted,'最终定位不得增删用户选定竞品')
    selected={x['candidate_id']:x for x in snap['selected_candidates']};entities=expanded_view(w,p)[0]
    for item in t.get('competitors',[]):
        c=selected[item['candidate_id']];e=entities[c['entity_id']]
        w.require(item.get('name') in [c['display_name'],c['offer_name'],*aliases(e)],'最终竞品不能保留ID却偷换成另一品牌/产品名称')
        item['name']=c['display_name'];item['company']=e.get('company','');item['relationship']=c['relationship'];item['evidence_status']=c['evidence_status']
    v['positioning_contract']=CONTRACT;v['positioning_snapshot']=snap
    return v

def finalize(w,p,v):
    # Not a third user approval: faithfully assemble the two explicit choices.
    snap=v['positioning_snapshot'];w.write(path(w,p,'confirmation'),{'by':'derived_from_explicit_choices','at':w.now(),
      'note':'类别选择与竞品范围已分别具体确认；本步仅冻结同一范围，不新增用户确认。',
      'output_sha256':w.hashfile(path(w,p,'result')),'snapshot_id':snap['snapshot_id'],
      'category_selection_sha256':w.hashfile(path(w,p,'category_selection')),'competitor_selection_sha256':w.hashfile(path(w,p,'competitor_selection'))})
    w.write(Path(p)/'reference_pack/positioning_snapshot.json',snap)

def assert_final(w,p,v):
    if v.get('positioning_contract') in (wp.IMPORTED, wp.DIRECT):
        wp.assert_imported(w,p,v);return
    w.require(v.get('positioning_contract')==CONTRACT,'旧定位尚未经过新版类别及竞品两次选择；请fork-project --retain-facts建立新版本')
    snap=snapshot(w,p);w.require(v.get('positioning_snapshot',{}).get('snapshot_id')==snap['snapshot_id'],'下游定位快照与当前两次选择不一致')

def validate_task(w,p,v):
    pos=w.accepted(p,2);assert_final(w,p,pos);snap=pos['positioning_snapshot']
    allowed={x['candidate_id']:x for x in snap['selected_candidates']};ids=v.get('candidate_ids',[])
    w.require(isinstance(ids,list) and len(ids)==len(set(ids)) and set(ids)<=set(allowed),'本篇竞品ID须来自已选同类池')
    n=len(v.get('candidate_order',[]));w.require(len(ids)==max(0,n-1),'本篇主体顺序须为本品牌＋对应数量的已选候选；单品牌candidate_ids为空')
    w.require(v['candidate_order'][0] in [w.state(p)['brand'],*w.state(p)['aliases']],'本篇首主体须为当前品牌')
    for name,cid in zip(v['candidate_order'][1:],ids):
        c=allowed[cid];e={'name':c['display_name'],'aliases':[]} if pos.get('positioning_contract')==wp.IMPORTED else expanded_view(w,p)[0][c['entity_id']]
        w.require(name in [c['display_name'],c['offer_name'],*aliases(e)],'本篇竞品名称与对应已选候选不一致')
    supplied=v.get('positioning_snapshot_id');w.require(supplied==snap['snapshot_id'],'本篇必须绑定当前定位快照')

def revise(w,p,scope,note,candidate_names=()):
    w.require(w.nonempty(note),'修订须说明用户具体改动')
    w.require(not w.done(p,3) and not w.state(p)['articles'],'已有下游稿件时请fork-project --retain-facts，不修改原文章依赖')
    root=d(w,p);archive=Path(p)/'positioning_history'/(w.now().replace(':','')+'_'+uuid.uuid4().hex[:6]);archive.mkdir(parents=True)
    keep=set() if scope=='categories' else {'category_analysis.json','category_analysis_record.json','category_selection.json','category_revision_request.json'}
    for f in list(root.iterdir()) if root.exists() else []:
        if f.name in keep:continue
        if f.name=='prompts' and scope=='competitors':
            for sub in list(f.iterdir()):
                if sub.name!='categories':shutil.move(str(sub),str(archive/('prompts_'+sub.name)))
        else:shutil.move(str(f),str(archive/f.name))
    w.write(archive/'revision.json',{'scope':scope,'note':note,'at':w.now()})
    if (Path(p)/'inputs/business_brief.json').exists():shutil.copy2(Path(p)/'inputs/business_brief.json',archive/'business_brief_input.json')
    w.write(path(w,p,'category_revision_request' if scope=='categories' else 'candidate_revision_request'),{'scope':scope,'note':note,'required_candidates':list(candidate_names),'at':w.now()})
    pack=Path(p)/'reference_pack';(pack/'positioning.json').unlink(missing_ok=True);(pack/'positioning_snapshot.json').unlink(missing_ok=True)
    gp=pack/'guided_positioning'
    if gp.exists():
        target=archive/'pack_guided_positioning';shutil.move(str(gp),str(target))
        if scope=='competitors':
            for name in ['category_analysis.json','category_selection.json']:
                if (target/name).exists():w.write(gp/name,w.read(target/name))
    meta=pack/'reference_pack.json'
    if meta.exists():v=w.read(meta);v['positioning']=None;v['updated_at']=w.now();w.write(meta,v)
    return archive
