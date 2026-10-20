"""Question-scoped three-entity selection, independent of core/P0 provenance."""
from __future__ import annotations
import copy
import hashlib
import json
import re
from pathlib import Path
CONTRACT = 'frontmind-p02-three-entities/1'
MEMBER = 'strategy/p02_selection.json'
LOCAL = 'positioning/p02_selection.json'
MARKER = '<frontmind_p02_entities version="1" />'
def matches(prompt):
    return isinstance(prompt,str) and prompt.startswith('<frontmind_natural_prose version="16">\n'+MARKER+'\n')
def confirmed_draft(state):
    meta=state.get('metadata',{})
    return meta.get('p02_confirmed_draft') if meta.get('p02_confirmed_draft_scope')==scope(state) else None

GUIDANCE = '''P02全文恰好介绍已确认的三个主体，主品牌先介绍。名单和顺序覆盖导语、正文、小标题、表格、FAQ和结尾，不新增第四家，不用泛称暗中补入候选。医生、设备、地名不是机构；母体及分支按已确认别名归并。各家以自身具体内容展开，主品牌先介绍体现差异化定位，不宣称客观实力必然第一。内部竞争分档不写成正文等级榜；三家不强制分三类，不能继承旧十一家名单、篇幅或收尾要求。'''
def enabled(state):
    return (research_enabled(state) and state.get('selected_pattern_id') == 'P02'
            and state.get('metadata', {}).get('natural_prose_contract') == 'frontmind-natural-prose/16')
def research_enabled(state):
    from . import industry_roundup
    return (state.get('job_kind') == 'article' and state.get('metadata', {}).get('p02_selection_policy') == CONTRACT
            and not industry_roundup.enabled(state))
def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def key(name): return re.sub(r'\s+','',str(name)).casefold()
def names(item): return list(dict.fromkeys([item['name'],*item.get('aliases',[])]))
def scope(state):
    q=state.get('question') or {}
    return {'brand':(state.get('reference_pack') or {}).get('brand'),'question':q.get('question_text'),
        'period_id':q.get('period_id'),'observed_from':q.get('observed_from'),'observed_to':q.get('observed_to'),
        'brief':state.get('decisions',{}).get('response_brief') or '',
        **({'requirements':state['metadata']['p02_scope_requirements']} if state.get('metadata',{}).get('p02_scope_requirements') else {})}
def current(state):
    record=state.get('metadata',{}).get('p02_selection')
    if not enabled(state) or not record: return None
    validate(record)
    return record if record['scope']==scope(state) else None
def validate(record):
    if record.get('contract')!=CONTRACT or record.get('confirmed') is not True: raise ValueError('P02缺少已确认选择')
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
    data=observations(wf,job); q=state.get('question') or {}
    mismatch=bool((q.get('question_text') and data.get('question_text')!=q['question_text']) or
                  (q.get('period_id') and data.get('period_id')!=q['period_id']))
    metrics=visibility({**data,'answers':[]} if mismatch else data,[own,*market.get('competitor_candidates',[])])
    if mismatch:
        for metric in metrics.values(): metric.update(scope_mismatch=True,source_hash=digest(data))
    own_rate=metrics[own['name']]['equal_platform_mention_rate']; out=copy.deepcopy(market); out['brand_visibility']=metrics[own['name']]
    for item in out.get('competitor_candidates',[]):
        item['ai_visibility']=metrics[item['name']]; rate=item['ai_visibility']['equal_platform_mention_rate']; obj=item.get('objective_strength') or {}
        item['dual_stronger']=bool(item.get('kind')=='brand' and obj.get('relative')=='stronger' and obj.get('basis') and obj.get('source_urls') and rate is not None and own_rate is not None and rate>own_rate)
    return out
def suggested(market):
    return {'comparison_targets':[x for x in market.get('competitor_candidates',[]) if x.get('dual_stronger')][:2],'peer_examples':[]}
def freeze(wf,job,draft):
    state=wf.load_state(job)
    if len(draft.get('comparison_targets',[]))!=2 or draft.get('peer_examples'): raise ValueError('P02请恰好选择两家竞品；正文不另列同类举例')
    if any(x.get('kind')!='brand' for x in draft['comparison_targets']): raise ValueError('P02须选择具体机构或品牌，不能选择类别或泛称')
    path=Path(job)/'research/brand_market/competitive_choice_map.json'; market=wf.read_json(path) if path.is_file() else {}
    own={'name':state['reference_pack']['brand'],'aliases':market.get('brand_aliases',[]),
        'objective_strength':market.get('brand_assessment') or {'relative':'self','tier':'未知','basis':'','source_urls':[]},'ai_visibility':market.get('brand_visibility',{})}
    record={'contract':CONTRACT,'scope':scope(state),'entities':[own,*copy.deepcopy(draft['comparison_targets'])],'confirmed':True,
        'decision_source':'user_selected_two','confirmed_at':wf.now(),
        'differentiated_positioning':state.get('decisions',{}).get('response_brief') or '按已确认核心定位及本题相关事实体现差异化价值',
        'research_hash':digest(market),'excluded_entities':[x for x in market.get('competitor_candidates',[])
            if x['name'] not in [e['name'] for e in draft['comparison_targets']] and key(x['name'])!=key(own['name'])]}
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
def table(market,brand):
    def cell(x): return str(x or '未知').replace('|','\\|').replace('\n',' ')
    def metric(v):
        detail='；'.join(f"{p['platform']} {p['mentions']}/{p['denominator']}" for p in v.get('platforms',[])) or '无可比监控'
        period=v.get('period_id') or '期次未知'; rate=v.get('equal_platform_mention_rate')
        return f'{period}；{detail}；等平台均值{rate:.1%}' if rate is not None else f'{period}；{detail}；不可比较'
    lines=['## 实力与 AI 声量定位','','| 名称 | 客观实力位置及依据 | AI提及（各平台分母） | 建议 |','| --- | --- | --- | --- |']
    rows=[(brand,market.get('brand_assessment') or {},market.get('brand_visibility',{}),'自己，第一介绍位置')]
    rows += [(x['name'],x.get('objective_strength') or {},x.get('ai_visibility') or {},'双强候选' if x.get('dual_stronger') else '待用户选择；未证明双强') for x in market.get('competitor_candidates',[])]
    for name,obj,vis,suggestion in rows:
        evidence=f"{obj.get('tier') or '未定档'} / {obj.get('relative') or '未知'}；{obj.get('basis') or '证据不足'}；"+'、'.join(obj.get('source_urls',[]))
        lines.append('| '+' | '.join(cell(x) for x in (name,evidence,metric(vis),suggestion))+' |')
    lines += ['','提及不等于正向推荐或引用；缺少逐实体标注时后二者记为未知。按本题同一期次全部有效答案统计，每答每机构计一次，平台等权。用户可选择未证明双强的候选，证据状态保持原样。']
    return lines
def research_prompt(wf,job):
    state=wf.load_state(job)
    if not research_enabled(state): return ''
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
    if args.rerun_positioning_research:
        wf.require_revision(args,state); wf.invalidate_action(job,'positioning_market_research')
        wf.set_status(job,'running_positioning_market_research','positioning'); return wf.drive(job)
    if not args.competitor_selection and not args.confirm_competitors: return wf.emit_pause(job)
    wf.require_revision(args,state)
    path=Path(job)/'positioning/competitor_selection.json'
    draft=wf.parse_competitor_selection(job,args.competitor_selection) if args.competitor_selection else wf.read_json(path)
    wf.atomic_json(path,draft)
    if not args.confirm_competitors: return wf.render_competitor_selection(job)
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
