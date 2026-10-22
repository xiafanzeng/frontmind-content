"""Question-scoped three-entity selection, independent of core/P0 provenance."""
from __future__ import annotations
import copy
import hashlib
import json
import re
import uuid
from pathlib import Path
CONTRACT = 'frontmind-p02-three-entities/1'
AUTO_CONTRACT = 'frontmind-p02-auto-dual-strength/2'
MEMBER = 'strategy/p02_selection.json'
LOCAL = 'positioning/p02_selection.json'
MARKER = '<frontmind_p02_entities version="1" />'
def matches(prompt):
    return isinstance(prompt,str) and prompt.startswith(tuple(prefix+MARKER+'\n' for prefix in ('<frontmind_natural_prose version="16">\n', '<frontmind_natural_prose version="16.5">\n')))
def confirmed_draft(state):
    meta=state.get('metadata',{})
    return meta.get('p02_confirmed_draft') if meta.get('p02_confirmed_draft_scope')==scope(state) else None

GUIDANCE = '''P02全文恰好介绍已确认的三个主体，主品牌先介绍。名单和顺序覆盖导语、正文、小标题、表格、FAQ和结尾，不新增第四家，不用泛称暗中补入候选。医生、设备、地名不是机构；母体及分支按已确认别名归并。各家以自身具体内容展开，主品牌先介绍体现差异化定位，不宣称客观实力必然第一。内部竞争分档不写成正文等级榜；三家不强制分三类，不能继承旧十一家名单、篇幅或收尾要求。'''
AUTO_GUIDANCE = '''P02围绕本篇选定的三家展开，主品牌先介绍，并充分讲出它的产品特点和使用内容。随后两家按各自最有内容的产品与用途展开，详略和段落长短可以不同。名称及别名对应同一家，推荐对象保持这三家；主品牌的介绍顺序体现本篇重心。'''
def enabled(state):
    return (research_enabled(state) and state.get('selected_pattern_id') == 'P02'
            and state.get('metadata', {}).get('natural_prose_contract') in {'frontmind-natural-prose/16', 'frontmind-natural-prose/16.5'})
def research_enabled(state):
    from . import industry_roundup
    if industry_roundup.enabled(state): return False
    policy = state.get('metadata', {}).get('p02_selection_policy')
    return state.get('job_kind') == 'article' and (policy == CONTRACT or
        (policy == AUTO_CONTRACT and state.get('selected_pattern_id') == 'P02'))
def automatic(state):
    return research_enabled(state) and state.get('metadata', {}).get('p02_selection_policy') == AUTO_CONTRACT
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def key(name): return re.sub(r'\s+','',str(name)).casefold()
def names(item): return list(dict.fromkeys([item['name'],*item.get('aliases',[])]))
def scope(state):
    q=state.get('question') or {}
    return {'brand':(state.get('reference_pack') or {}).get('brand'),'question':q.get('question_text'),
        'period_id':q.get('period_id'),'observed_from':q.get('observed_from'),'observed_to':q.get('observed_to'),
        'brief':state.get('decisions',{}).get('response_brief') or '',
        **({'selection_policy': AUTO_CONTRACT} if automatic(state) else {}),
        **({'requirements':state['metadata']['p02_scope_requirements']} if state.get('metadata',{}).get('p02_scope_requirements') else {})}
def current(state):
    record=state.get('metadata',{}).get('p02_selection')
    if not enabled(state) or not record: return None
    validate(record)
    return record if record['scope']==scope(state) else None
def validate(record):
    if record.get('contract') not in {CONTRACT, AUTO_CONTRACT} or record.get('confirmed') is not True: raise ValueError('P02缺少已选定名单')
    entities=record.get('entities')
    if not isinstance(entities,list) or len(entities)!=3: raise ValueError('P02必须恰好包含主品牌及两家竞品')
    seen=set()
    for e in entities:
        if not isinstance(e,dict) or not isinstance(e.get('name'),str) or not e['name'].strip(): raise ValueError('P02主体需要名称')
        if not isinstance(e.get('aliases',[]),list) or any(not isinstance(x,str) or not x.strip() for x in e.get('aliases',[])): raise ValueError('P02别名须为名称列表')
        aliases={key(x) for x in names(e)}
        if aliases & seen: raise ValueError('P02主体及其别名不能重复或重叠')
        seen |= aliases
    if key(record.get('scope',{}).get('brand')) not in {key(x) for x in names(entities[0])}: raise ValueError('P02第一家必须是主品牌')
    if record.get('selection_hash')!=digest({k:v for k,v in record.items() if k!='selection_hash'}): raise ValueError('P02选择记录摘要不一致')
    return record
def observations(wf,job):
    p=Path(job)/'inputs/question_observations.json'
    return wf.read_json(p) if p.is_file() else {}
def visibility(data,entities):
    from .question_bank_import import UNKNOWN_PLATFORMS,platform_key
    groups={}; seen=set()
    for index,r in enumerate(data.get('answers',[])):
        platform=platform_key(r.get('platform') or ''); text=r.get('answer_text')
        if platform in UNKNOWN_PLATFORMS or not platform or not isinstance(text,str) or not text.strip(): continue
        if r.get('period_id') and data.get('period_id') and r['period_id']!=data['period_id']: continue
        if r.get('question_text') and r['question_text']!=data.get('question_text'): continue
        identity=(platform,r.get('answer_id') or ('row',index))
        if identity in seen: continue
        seen.add(identity); groups.setdefault(platform,[]).append(r)
    comparable=bool(groups and (data.get('period_id') or (data.get('observed_from') and data.get('observed_to'))))
    output={}
    for e in entities:
        aliases={key(x) for x in names(e)}; per=[]
        for platform,rows in sorted(groups.items()):
            mentions=sum(any(a in key(r['answer_text']) for a in aliases) for r in rows)
            def annotated(field):
                if not all(isinstance(r.get(field),list) for r in rows): return None
                return sum(bool({key(x) for x in r[field]} & aliases) for r in rows)
            per.append({'platform':platform,'denominator':len(rows),'mentions':mentions,'mention_rate':mentions/len(rows),
                'positive_recommendations':annotated('recommended_entities'),'attributed_citations':annotated('cited_entities')})
        output[e['name']]={'comparable':comparable,'equal_platform_mention_rate':sum(p['mention_rate'] for p in per)/len(per) if comparable else None,
            'platforms':per,'period_id':data.get('period_id'),'observed_from':data.get('observed_from'),'observed_to':data.get('observed_to'),
            'question':data.get('question_text'),'source_hash':digest(data)}
    return output
def enrich(wf,job,market):
    state=wf.load_state(job); own={'name':state['reference_pack']['brand'],'aliases':market.get('brand_aliases',[])}
    out=copy.deepcopy(market)
    if automatic(state):
        # Resolve explicit alias links to the main brand before calculating its
        # baseline; a duplicate name must not overwrite that metric in the map.
        remaining=list(out.get('competitor_candidates',[]))
        while True:
            own_names={key(n) for n in names(own)}
            duplicates=[x for x in remaining if {key(n) for n in names(x)} & own_names]
            if not duplicates: break
            own['aliases']=list(dict.fromkeys([*own['aliases'],*[n for x in duplicates for n in names(x)
                if key(n)!=key(own['name'])]]))
            remaining=[x for x in remaining if x not in duplicates]
        out['brand_aliases']=own['aliases']
        out['competitor_candidates']=remaining
    data=observations(wf,job); q=state.get('question') or {}
    mismatch=bool((q.get('question_text') and data.get('question_text')!=q['question_text']) or
                  (q.get('period_id') and data.get('period_id')!=q['period_id']))
    metrics=visibility({**data,'answers':[]} if mismatch else data,[own,*out.get('competitor_candidates',[])])
    if mismatch:
        for metric in metrics.values(): metric.update(scope_mismatch=True,source_hash=digest(data))
    own_rate=metrics[own['name']]['equal_platform_mention_rate']; out['brand_visibility']=metrics[own['name']]
    for item in out.get('competitor_candidates',[]):
        item['ai_visibility']=metrics[item['name']]; rate=item['ai_visibility']['equal_platform_mention_rate']; obj=item.get('objective_strength') or {}
        clear = not automatic(state) or obj.get('advantage_level') == 'clear'
        item['dual_stronger']=bool(item.get('kind')=='brand' and clear and obj.get('relative')=='stronger' and obj.get('basis') and obj.get('source_urls') and rate is not None and own_rate is not None and rate>own_rate)
    return out
def suggested(market):
    return {'comparison_targets':[x for x in market.get('competitor_candidates',[]) if x.get('dual_stronger')][:2],'peer_examples':[]}
def freeze(wf,job,draft, *, decision_source='user_selected_two', automatic_basis=None):
    state=wf.load_state(job)
    if len(draft.get('comparison_targets',[]))!=2 or draft.get('peer_examples'): raise ValueError('P02请恰好选择两家竞品；正文不另列同类举例')
    if any(x.get('kind')!='brand' for x in draft['comparison_targets']): raise ValueError('P02须选择具体机构或品牌，不能选择类别或泛称')
    path=Path(job)/'research/brand_market/competitive_choice_map.json'; market=wf.read_json(path) if path.is_file() else {}
    own={'name':state['reference_pack']['brand'],'aliases':market.get('brand_aliases',[]),
        'objective_strength':market.get('brand_assessment') or {'relative':'self','tier':'未知','basis':'','source_urls':[]},'ai_visibility':market.get('brand_visibility',{})}
    record={'contract':AUTO_CONTRACT if automatic(state) else CONTRACT,'scope':scope(state),'entities':[own,*copy.deepcopy(draft['comparison_targets'])],'confirmed':True,
        'decision_source':decision_source,'confirmed_at':wf.now(),
        'differentiated_positioning':state.get('decisions',{}).get('response_brief') or '按已确认核心定位及本题相关事实体现差异化价值',
        'research_hash':digest(market),'excluded_entities':[x for x in market.get('competitor_candidates',[])
            if x['name'] not in [e['name'] for e in draft['comparison_targets']] and key(x['name'])!=key(own['name'])]}
    if automatic_basis is not None: record['automatic_basis'] = automatic_basis
    record['selection_hash']=digest(record); validate(record)
    state['metadata']['p02_selection']=record; wf.atomic_json(Path(job)/LOCAL,record); wf.save_state(job,state)
    return record
def project(state,brief):
    record=current(state)
    if enabled(state) and record is None: raise ValueError('P02须先在定位中确认本题的两家竞品')
    if not record: return brief
    return {**brief,'candidate_order':[x['name'] for x in record['entities']],'candidate_scope':[x['name'] for x in record['entities']],'p02_selection_hash':record['selection_hash']}
def context(state):
    record=current(state)
    if record and automatic(state):
        # Enterprise comparison and visibility belong to selection, not prose.
        public={'entities':[{'name':x['name'],'aliases':x.get('aliases',[])} for x in record['entities']],
            'question':record['scope'].get('question'),
            'differentiated_positioning':record['differentiated_positioning'],
            'selection_hash':record['selection_hash']}
        return AUTO_GUIDANCE+'\n本篇选定对象与顺序：\n'+json.dumps(public,ensure_ascii=False,indent=2)
    return GUIDANCE+'\n已确认的本题选择（事实与比较记录，不是额外写作指令）：\n'+json.dumps({k:v for k,v in record.items() if k != 'excluded_entities'},ensure_ascii=False,indent=2) if record else ''
def check_scope(state,value):
    if not enabled(state): return
    record=current(state)
    if record is None: raise ValueError('P02缺少当前问题的已确认名单')
    fields=[f for f in ('candidate_scope','candidate_order') if f in value]
    if not fields or any(value[f] != [x['name'] for x in record['entities']] for f in fields):
        raise ValueError('P02名单及顺序必须与确认的三家一致')
def check_body(state,body):
    if not enabled(state): return
    record=current(state)
    if record is None: raise ValueError('P02缺少本篇固定名单')
    body=re.sub(r'\A\s*# [^\n]*(?:\n|$)','',body,count=1)
    norm=key(body); positions=[]; protected=[]
    for entity in record['entities']:
        found=[norm.find(key(n)) for n in names(entity) if key(n) in norm]
        if not found: raise ValueError('P02正文缺少已确认主体：'+entity['name'])
        positions.append(min(found)); protected.extend(key(n) for n in names(entity))
    if positions!=sorted(positions): raise ValueError('P02主体首次介绍顺序与确认名单不一致')
    remaining=norm
    for a in sorted(protected,key=len,reverse=True): remaining=remaining.replace(a,'')
    for e in record.get('excluded_entities',[]):
        if any(key(n) in remaining for n in names(e)): raise ValueError('P02正文出现未选的第四方：'+e['name'])
    # Unknown extra entities are also covered by the existing semantic editor.
    for line in body.splitlines():
        if re.match(r'^#{2,6}\s|^\*\*',line) and re.search(r'医院|诊所|大学|学院|事务所|有限公司|留学机构|培训机构',line):
            if not any(n in key(line) for n in protected) and not re.search(r'怎么|如何|选择|服务|推荐|项目|条件',line): raise ValueError('P02出现名单外机构标题：'+line)
def table(market,brand,*,automatic=False):
    def cell(x): return str(x or '未知').replace('|','\\|').replace('\n',' ')
    def metric(v):
        detail='；'.join(f"{p['platform']} {p['mentions']}/{p['denominator']}" for p in v.get('platforms',[])) or '无可比监控'
        period=v.get('period_id') or '期次未知'; rate=v.get('equal_platform_mention_rate')
        return f'{period}；{detail}；等平台均值{rate:.1%}' if rate is not None else f'{period}；{detail}；不可比较'
    lines=['## 实力与 AI 声量定位','','| 名称 | 客观实力位置及依据 | AI提及（各平台分母） | 建议 |','| --- | --- | --- | --- |']
    rows=[(brand,market.get('brand_assessment') or {},market.get('brand_visibility',{}),'自己，第一介绍位置')]
    rows += [(x['name'],x.get('objective_strength') or {},x.get('ai_visibility') or {},'双强候选' if x.get('dual_stronger') else ('暂未满足自动条件' if automatic else '待用户选择；未证明双强')) for x in market.get('competitor_candidates',[])]
    for name,obj,vis,suggestion in rows:
        evidence=f"{obj.get('tier') or '未定档'} / {obj.get('relative') or '未知'}；{obj.get('basis') or '证据不足'}；"+'、'.join(obj.get('source_urls',[]))
        lines.append('| '+' | '.join(cell(x) for x in (name,evidence,metric(vis),suggestion))+' |')
    lines += ['','提及不等于正向推荐或引用；缺少逐实体标注时后二者记为未知。按本题同一期次全部有效答案统计，每答每机构计一次，平台等权。'+
        ('当前尚不足两家满足自动条件；补充资料后重新选择，或采用用户明确指定的两家。' if automatic else '用户可选择未证明双强的候选，证据状态保持原样。')]
    return lines

def render_missing_input(wf,job,market,message=None):
    state=wf.load_state(job)
    wf.atomic_json(Path(job)/'positioning/competitor_selection.json',{'comparison_targets':[],'peer_examples':[]})
    lines=['# 本题自动选择还缺资料','',message or '补研后仍不足两家满足明显综合实力优势和更高AI声量的对象。',
        '', '可补充实力比较资料后重新研究，也可直接指定两家；当前没有待例行确认的名单。','',
        *table(market,state['reference_pack']['brand'],automatic=True), '',
        '补充资料使用 --positioning-supplement；重新研究使用 --rerun-positioning-research。明确指定两家时用 --competitor-selection 直接提交，无需另行确认。']
    wf.set_pause(job,'awaiting_competitor_selection','\n'.join(lines),
        choices=['补充资料后继续','直接指定两家','重新研究'],
        full_text_links=[Path(job)/'research/brand_market/competitive_choice_map.md'],
        source_links=[x['url'] for x in market.get('sources',[]) if x.get('url')],stage='positioning')
    return wf.emit_pause(job)
def research_prompt(wf,job):
    state=wf.load_state(job)
    if not research_enabled(state): return ''
    if automatic(state):
        return '''\n本轮P02采用自动双维选择，不等待用户确认竞品。研究本题真实可替代的具体企业或品牌，结合完整AI答案里的对象发现候选，不受旧品牌定位的举例名单限制，不自动扩地区。主品牌先写只是文章顺序。
先判断企业综合实力：结合本题相关的研发与专业积累、产品与交付能力、企业团队或规模、真实客户与应用覆盖，比较主品牌与候选。给出自然的综合理由和已读取的来源，不能把某项技术卖点、搜索热度或材料多少直接当综合实力。缺少价格、同条件测评或临床试验并不自动阻止企业实力判断；已有信息确实不能比较时如实标unknown。
返回brand_aliases、brand_assessment（relative=self，tier、basis、source_urls）。每个候选包含aliases及objective_strength：relative=stronger/peer/weaker/unknown，advantage_level=clear/modest/unknown，tier、basis、source_urls。只有综合实力明显强于主品牌才使用stronger+clear；有单项优势而综合位置不明显，使用peer或unknown。不要计算假精确的企业总分。
AI声量由程序根据同题同期全部完整答案计算，按平台等权、每答每主体一次；研究不编造声量。程序在综合实力明显更强且AI提及率高于主品牌的对象中，按本题AI声量选前两家；并列按名称稳定排序。研究应覆盖有希望入选的对象，不只沿用声量前二或旧人工范围。内部实力判断与来源备注不会作为正文写作任务。
''' + '\n本题范围：' + json.dumps(scope(state),ensure_ascii=False) + '\n监控完整观测：' + json.dumps(observations(wf,job),ensure_ascii=False) + '\n必要补研方向：' + json.dumps(state.get('metadata',{}).get('p02_auto_research_hint'),ensure_ascii=False) + '\n若用户明确另指定两家，则补这两家实际产品内容并沿用指定名单：' + json.dumps(confirmed_draft(state),ensure_ascii=False)
    return '''\n本轮补充可供P02选择的竞争定位：候选为本题范围内具体机构或品牌，可研究多于两家。分别判断客观实力和AI声量，不将提及误称引用；不自动扩地区。不预定主品牌客观实力第一。
返回可选brand_aliases、brand_assessment（relative=self，tier自身位置，basis及source_urls），每个候选补充aliases和objective_strength（relative=stronger/peer/weaker/unknown、tier、basis、source_urls）。客观实力比较使用本题相关、可核实的规模、能力、专业积累或交付事实，不凭名气或来源数量给结论。证据不足写unknown，不阻断用户选择。AI声量由程序根据完整监控计算，不由模型虚构数值。档位只用于内部选择。\n本题范围：'''+json.dumps(scope(state),ensure_ascii=False)+'\n监控完整观测：'+json.dumps(observations(wf,job),ensure_ascii=False)+'\n如有用户已确认的补研名单，仅补这两家事实，完成后直接继续，不再次要求确认：'+json.dumps(confirmed_draft(state),ensure_ascii=False)

def persist_pack(wf,job,record):
    state=wf.load_state(job)
    previous=state['metadata'].get('p02_reference_pack_delivery') or {}
    source=Path(previous.get('portable_zip_path') or state['reference_pack']['path'])
    root=wf.reference_pack_root(source)
    directory,portable=wf._pack_output_targets(job,int(root['pack_version'])+1)
    artifacts={MEMBER:json.dumps(record,ensure_ascii=False,indent=2)+'\n'}
    for name in ('competitive_choice_map.json','competitive_choice_map.md'):
        path=Path(job)/'research/brand_market'/name
        if path.is_file(): artifacts['research/p02_selection/'+name]=path
    result=wf.create_next_reference_pack_version(pack=source,output=directory,artifacts=artifacts,
        readiness_updates={},remove_members=[],portable_zip=portable)
    if result['readiness']!=root['readiness']: raise ValueError('P02选择更新不得改变资料包或P0就绪状态')
    state['metadata']['p02_reference_pack_delivery']=result
    wf.save_state(job,state)
    return result

def ranked_automatic_candidates(market):
    """Strength is an evidence-backed qualification, never a fabricated score."""
    eligible = [x for x in market.get('competitor_candidates', []) if x.get('dual_stronger')]
    eligible.sort(key=lambda x: (-x['ai_visibility']['equal_platform_mention_rate'], key(x['name'])))
    result=[]; used=set()
    for item in eligible:
        aliases={key(n) for n in names(item)}
        if aliases & used: continue
        result.append(item); used |= aliases
    return result

def finish_selection(wf,job,record):
    persist_pack(wf,job,record)
    state=wf.load_state(job)
    for field in ('p02_confirmed_draft','p02_confirmed_draft_scope','p02_selection_pending','p02_auto_research_hint'):
        state['metadata'].pop(field,None)
    state['decisions'].pop('question_positioning_confirmation',None)
    wf.save_state(job,state)
    for action in ('question_positioning','article_editorial_preparation','article_blueprint'):
        wf.invalidate_action(job,action)
    wf.set_status(job,'running_question_positioning','question_positioning')

def complete_automatic_research(wf,job,market):
    """Return True after selecting, False after scheduling evidence supplementation."""
    state=wf.load_state(job)
    if not automatic(state): return None
    ranked=ranked_automatic_candidates(market)
    if len(ranked) >= 2:
        draft={'comparison_targets':ranked[:2],'peer_examples':[]}
        wf.atomic_json(Path(job)/'positioning/competitor_selection.json',draft)
        basis={'rule':'clear_enterprise_strength_then_question_ai_visibility',
            'strength':'本题相关综合企业实力明显更强，有比较理由与来源',
            'visibility':'同题同期完整答案，每答每主体一次，平台等权；提及率高于主品牌',
            'ranking':'符合双维条件的对象按AI提及率降序，并列按名称稳定排序',
            'eligible_candidates':[x['name'] for x in ranked], 'user_confirmation_required':False}
        record=freeze(wf,job,draft,decision_source='automatic_dual_strength',automatic_basis=basis)
        wf.atomic_json(Path(job)/'decisions/p02_automatic_selection.json',record)
        finish_selection(wf,job,record)
        return True
    # Supplement only when the first research lacks enough usable candidates.
    # A missing peer is an input problem, not a routine approval step.
    stamp=digest(scope(state))
    if state['metadata'].get('p02_auto_supplement_scope') != stamp:
        state['metadata']['p02_auto_supplement_scope']=stamp
        state['metadata']['p02_auto_research_hint']={'eligible':[x['name'] for x in ranked],
            'task':'围绕本题AI答案中的其他相关企业及候选未知的实力资料补研，找足两家双维候选；不能因数据缺少就把unknown改成stronger。',
            'candidate_assessments':[{'name':x['name'],'objective_strength':x.get('objective_strength'),
                'ai_visibility':x.get('ai_visibility')} for x in market.get('competitor_candidates',[])]}
        wf.save_state(job,state)
        wf.invalidate_action(job,'positioning_market_research')
        wf.set_status(job,'running_positioning_market_research','positioning')
        return False
    return None

def ensure_ready(wf,job):
    state=wf.load_state(job)
    if not enabled(state): return True
    if state['metadata'].get('p02_confirmed_draft') and not confirmed_draft(state):
        wf.atomic_json(Path(job)/'positioning'/('superseded_draft_'+digest(state['metadata']['p02_confirmed_draft'])[:12]+'.json'),
            {'draft':state['metadata'].pop('p02_confirmed_draft'),'scope':state['metadata'].pop('p02_confirmed_draft_scope',None)})
        wf.save_state(job,state)
    if current(state): return True
    with wf.PackageView(Path(state['reference_pack']['path'])) as view:
        if MEMBER in view.names():
            record=view.read_json(MEMBER); validate(record)
            if record['scope']==scope(state):
                state['metadata']['p02_selection']=record
                wf.atomic_json(Path(job)/LOCAL,record); wf.save_state(job,state); return True
    # Reuse a selection actually confirmed for this exact scope, never a draft
    # or a merely suggested pair from a historical Pack.
    previous=state.get('decisions',{}).get('comparison_scope') or {}
    if (previous.get('confirmed') and state['metadata'].get('comparison_scope_question')==scope(state)
            and len(previous.get('comparison_targets',[]))==2 and not previous.get('peer_examples')
            and all(x.get('kind')=='brand' for x in previous['comparison_targets'])):
        record=freeze(wf,job,previous); persist_pack(wf,job,record); return True
    state['metadata']['p02_selection_pending']=scope(state)
    state['metadata'].pop('positioning_research_mode',None)
    wf.save_state(job,state)
    wf.invalidate_action(job,'positioning_market_research')
    path=Path(job)/'positioning/competitor_selection.json'
    if path.is_file():
        old=Path(job)/'positioning'/('competitor_selection.before_p02_'+digest(scope(state))[:12]+'.json')
        if not old.exists(): wf.atomic_bytes(old,path.read_bytes())
        path.unlink()
    wf.set_status(job,'running_positioning_market_research','positioning')
    return False

def handle_selection(wf,args,job):
    state=wf.load_state(job)
    if not state['metadata'].get('p02_selection_pending'): return None
    if automatic(state) and getattr(args,'positioning_supplement',None):
        wf.require_revision(args,state)
        wf.save_user_material(job,args.positioning_supplement,'positioning')
        state=wf.load_state(job)
        for field in ('p02_auto_supplement_scope','p02_auto_research_hint'): state['metadata'].pop(field,None)
        state.setdefault('flags',{}).setdefault('model_action_epochs',{})['positioning_market_research']=uuid.uuid4().hex
        wf.save_state(job,state); wf.invalidate_action(job,'positioning_market_research')
        if not getattr(args,'competitor_selection',None) and not getattr(args,'confirm_competitors',False):
            wf.set_status(job,'running_positioning_market_research','positioning')
            return wf.drive(job)
    if args.rerun_positioning_research:
        wf.require_revision(args,state)
        for field in ('p02_auto_supplement_scope','p02_auto_research_hint'): state['metadata'].pop(field,None)
        if automatic(state):
            state.setdefault('flags',{}).setdefault('model_action_epochs',{})['positioning_market_research']=uuid.uuid4().hex
        wf.save_state(job,state); wf.invalidate_action(job,'positioning_market_research')
        wf.set_status(job,'running_positioning_market_research','positioning'); return wf.drive(job)
    if not args.competitor_selection and not args.confirm_competitors: return wf.emit_pause(job)
    wf.require_revision(args,state)
    path=Path(job)/'positioning/competitor_selection.json'
    draft=wf.parse_competitor_selection(job,args.competitor_selection) if args.competitor_selection else wf.read_json(path)
    wf.atomic_json(path,draft)
    if not args.confirm_competitors and not automatic(state): return wf.render_competitor_selection(job)
    record=freeze(wf,job,draft)
    if any(not x.get('research_notes') or not x.get('category') for x in draft['comparison_targets']):
        state=wf.load_state(job); state['metadata']['p02_confirmed_draft']=draft; state['metadata']['p02_confirmed_draft_scope']=scope(state); wf.save_state(job,state)
        wf.invalidate_action(job,'positioning_market_research')
        wf.set_status(job,'running_positioning_market_research','positioning')
        return wf.drive(job)
    persist_pack(wf,job,record)
    state=wf.load_state(job); state['metadata'].pop('p02_selection_pending',None)
    state['decisions'].pop('question_positioning_confirmation',None); wf.save_state(job,state)
    for action in ('question_positioning','article_editorial_preparation','article_blueprint'):
        wf.invalidate_action(job,action)
    wf.set_status(job,'running_question_positioning','question_positioning')
    return wf.drive(job)

def complete_selected_research(wf,job,market):
    state=wf.load_state(job); draft=confirmed_draft(state)
    if not draft: raise ValueError('P02补研名单已不属于当前问题范围，须重新选择')
    pool=market.get('competitor_candidates',[])
    selected=[]
    for item in draft['comparison_targets']:
        found=next((x for x in pool if key(x['name'])==key(item['name'])),None)
        selected.append({**(found or item), 'name':item['name'], 'kind':'brand'})
    record=freeze(wf,job,{'comparison_targets':selected,'peer_examples':[]})
    persist_pack(wf,job,record)
    state=wf.load_state(job)
    for field in ('p02_confirmed_draft','p02_confirmed_draft_scope','p02_selection_pending'): state['metadata'].pop(field,None)
    state['decisions'].pop('question_positioning_confirmation',None); wf.save_state(job,state)
    for action in ('question_positioning','article_editorial_preparation','article_blueprint'): wf.invalidate_action(job,action)
    wf.set_status(job,'running_question_positioning','question_positioning')

REVIEW_GUIDANCE = '''本次P02最后编辑同时核验全文推荐主体。entity_mentions按首次出现顺序逐家列出当前正文中所有作为介绍或推荐对象的机构/品牌（包括名单外对象），每家提供name和quote；quote逐字摘录应用local_edits后的正文，包含对应名称。不把医生、设备、地名、资料来源单位计作推荐主体；已确认别名合并为同一家。检查导语、普通段落、小标题、表格、FAQ和结尾，不能只抽取小标题。只有确认的三家且主品牌第一才能通过。存在名单外主体时在现有needs_revision/comments里指出删除或收回额外推荐，不可隐藏它以通过校验；需要返工时记录原稿中实际出现的主体。提交字段为needs_revision、comments、local_edits、entity_mentions。'''
def review_schema():
    return {'type':'array','description':'全文实际推荐主体清单，覆盖普通段落和表格；每家逐字引文绑定应用局部编辑后的正文。',
        'items':{'type':'object','properties':{'name':{'type':'string','minLength':1},'quote':{'type':'string','minLength':1}},
                 'required':['name','quote'],'additionalProperties':False}}
def without_h1(body):
    return re.sub(r'\A\s*# [^\n]*(?:\n|$)','',body,count=1)
def validate_mentions(state,body,mentions,*,accepted):
    record=current(state)
    if record is None: raise ValueError('P02实体检查缺少当前确认名单')
    if not isinstance(mentions,list): raise ValueError('P02实体检查须为清单')
    body=without_h1(body)
    aliases={key(n):e['name'] for e in record['entities'] for n in names(e)}
    canonical=[]
    for item in mentions:
        if not isinstance(item,dict) or set(item)!={'name','quote'} or any(not isinstance(x,str) or not x.strip() for x in item.values()):
            raise ValueError('P02实体检查每项须有name及quote')
        if item['quote'] not in body or key(item['name']) not in key(item['quote']): raise ValueError('P02实体引文须来自当前实际正文并包含该名称')
        name=aliases.get(key(item['name']),item['name'])
        if name in canonical: raise ValueError('P02实体清单须将别名归并为同一家')
        canonical.append(name)
    if accepted:
        if canonical!=[e['name'] for e in record['entities']]: raise ValueError('P02通过稿实体清单必须恰好为已确认三家，不能额外推荐第四家')
        check_body(state,body)
    return mentions

def fixture_review(state,body):
    result={'needs_revision':False,'comments':[],'local_edits':[]}
    if enabled(state):
        body=without_h1(body); mentions=[]
        for e in current(state)['entities']:
            line=next((line for line in body.splitlines() if any(n in line for n in names(e))),None)
            if line is None: raise ValueError('离线夹具正文缺少确认主体')
            alias=next(n for n in names(e) if n in line)
            mentions.append({'name':alias,'quote':line})
        result['entity_mentions']=mentions
    return result
