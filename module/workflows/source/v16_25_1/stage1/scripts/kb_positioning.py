"""Position the brand from complete knowledge, then let the user choose."""
from pathlib import Path
import copy
import re
import shutil
import writing_pack as kb

SCHEMA = {
    'category_options': [{'id': 'c1', 'label': '产品类别及必要细分', 'scope': '用途、客户及纳入范围',
                          'reason': '知识库支持的落位理由', 'fact_ids': ['k0001'],
                          'product_boundaries': [], 'scenario_tags': []}],
    'optimization_questions': [{'question_text': '适合后续优化的具体问题', 'category': '产品场景', 'category_ids': ['c1'],
                                'reason': '与品牌及定位的关系'}],
    'summary': '定位建议；等待用户选类，不自动替用户决定',
}
INSTRUCTION = '''完整阅读知识库的主题节点与原资料正文，区分品牌、具体产品、配套软件、专业服务及不同版本。
提出知识库支持的产品定位选项，通常1—3项即可，不为凑数创造类别；说明用途、客户范围、必要产品边界及理由。
知识库是企业资料入口，不先生成一份常设的资料综合底稿。不要把企业缺少某证件反推成法定产品属性。
给出后续优化问题目录，问题具体且与品牌范围有关，可属行业排名、美誉舆情、产品场景三类；category_ids标记对应定位选项，确认后只承接所选范围。
问题目录描述选题意图，不预先替第二阶段选择文章模式。P02可按用户选择作开放式多主体推荐；不拟点名横评。问题目录不冒充监测结果。
已有问题目录或监测问答可以帮助选题；无监测数据时不编造提及率、推荐率或市场排名。
不从企业知识库虚构竞品事实。这里只作企业产品定位，若用户另要求市场研究再使用真实外部来源。
输出结构化业务结果供宿主保存，类别最终由用户在A选择；不会要求用户重新确认知识库内容。'''


def folder(w, p):
    return w.stepdir(p, 2)


def confirmed_peers(w,p,file,by,note):
    """Optional inheritance of an explicitly confirmed pool, never KB inference."""
    w.require(not w.done(p,2),'定位已冻结；改变已确认同类池请在新项目版本承接，不覆盖旧依赖')
    w.require(by in ('user','explicit_prior_choice') and w.nonempty(note),'继承同类池须有用户选择或明确既有授权原话')
    source=Path(file).expanduser().resolve();text=source.read_text(encoding='utf-8-sig')
    if source.suffix.lower()=='.json':
        value=w.read(source);raw=value if isinstance(value,list) else value.get('selected_candidates',value.get('confirmed_peers',[]))
    else:raw=kb.confirmed_candidates(text)
    w.require(isinstance(raw,list) and raw,'文件须有已确认同类竞品章节或明确的selected_candidates列表，不从随意提及厂商推断确认')
    rows=[];names=set();ids=set()
    for index,item in enumerate(raw,1):
        name=item.get('display_name') or item.get('name');cid=item.get('candidate_id') or 'c'+str(index).zfill(3)
        w.require(w.nonempty(name) and name not in names and cid not in ids,'同类池名称或ID为空/重复')
        names.add(name);ids.add(cid)
        rows.append({**item,'candidate_id':cid,'display_name':name,
                     'offer_name':item.get('offer_name') or item.get('product_name') or name,
                     'intended_use':item.get('intended_use') or item.get('purpose') or '',
                     'fit_reason':item.get('fit_reason') or '',
                     'relationship':item.get('relationship') or 'direct','evidence_status':item.get('evidence_status') or 'pending',
                     'boundary_checks':item.get('boundary_checks',[]),'choice_origin':{'by':by,'note':note}})
    target=Path(p)/'inputs'/('confirmed_peer_pool_source'+(source.suffix or '.txt'))
    pool=Path(p)/'inputs/confirmed_peer_pool.json';record=Path(p)/'inputs/confirmed_peer_pool_record.json'
    if pool.exists():
        archive=Path(p)/'reference_pack/confirmed_peer_pool_history'/w.uuid.uuid4().hex[:10];archive.mkdir(parents=True)
        previous=w.read(record)
        for f in [pool,record,Path(p)/previous['source_path']]:shutil.copy2(f,archive/f.name)
    if source!=target.resolve():shutil.copy2(source,target)
    w.write(pool,{'selected_candidates':rows,'by':by,'note':note})
    w.write(record,{'source_path':target.relative_to(p).as_posix(),'source_sha256':w.hashfile(target),'pool_sha256':w.hashfile(pool),'by':by,'note':note})
    return rows


def inherited_peers(w,p):
    pool=Path(p)/'inputs/confirmed_peer_pool.json'
    if not pool.exists():return []
    record=w.read(Path(p)/'inputs/confirmed_peer_pool_record.json')
    w.require(record['pool_sha256']==w.hashfile(pool) and record['source_sha256']==w.hashfile(Path(p)/record['source_path']),'已确认同类池输入已改变，请按用户当前要求重新登记')
    return w.read(pool)['selected_candidates']


def prepare(w, p):
    w.accepted(p, 1)
    w.require(not w.done(p, 2), '定位已确认；保持既有定位，明确要求改动时再建立新版本')
    source = kb.snapshot(w, p)
    data = {'brand': w.state(p)['brand'], 'complete_knowledge_markdown': source['writing_material_markdown'],
            'source_index': [{'id': x['id'], 'source': x['source']} for x in w.accepted(p, 1)['knowledge']],
            'existing_questions': w.catalog(p),
            'monitoring_answers': w.read(Path(p) / 'inputs/all_answers.json'),
            'inherited_user_confirmed_peers':inherited_peers(w,p),'instruction': INSTRUCTION}
    request=Path(p)/'inputs/initial_request.txt'
    if request.is_file():data['user_requirements']=request.read_text(encoding='utf-8')
    d = folder(w, p) / 'prompts' / 'positioning'
    w.write(d / 'system.md', w.HOST_SYSTEM+'依据完整知识库提出类别与问题目录，等用户选择；保留明确已确认同类池，不从知识库新增竞品确认。')
    w.write(d / 'user.md', w.dump(data) + '\n\n输出合同\n' + w.dump(SCHEMA))
    w.write(d / 'manifest.json', {'knowledge_sha256': source['knowledge_sha256'],
            'system_sha256': w.hashfile(d / 'system.md'), 'user_sha256': w.hashfile(d / 'user.md')})
    return d


def submit(w, p, file, model):
    w.require(w.nonempty(model), '如实记录当前宿主模型')
    w.require(not w.done(p, 2), '已确认定位不覆盖')
    d = folder(w, p) / 'prompts' / 'positioning'
    manifest = w.read(d / 'manifest.json')
    w.require(manifest['knowledge_sha256'] == kb.snapshot(w, p)['knowledge_sha256'], '知识库版本改变，请重新prepare')
    for role in ('system', 'user'):
        w.require(manifest[role + '_sha256'] == w.hashfile(d / (role + '.md')), '定位Prompt已改变')
    value = copy.deepcopy(w.read(file))
    rows = value.get('category_options', [])
    w.require(rows and len({x.get('id') for x in rows}) == len(rows), '需实际类别建议且ID唯一')
    known = {x['id'] for x in w.accepted(p, 1)['knowledge']}
    for x in rows:
        w.require(all(w.nonempty(x.get(k)) for k in ('id', 'label', 'scope', 'reason')), '类别需名称、范围及依据')
        w.require(x.get('fact_ids') and set(x['fact_ids']) <= known, '类别须引用当前知识库条目')
    questions = value.get('optimization_questions', [])
    w.require(isinstance(questions, list), '优化问题目录须为列表')
    w.require(questions or w.catalog(p), '请整理至少一个与定位有关的优化问题，或使用已有目录')
    for x in questions:
        w.require(w.nonempty(x.get('question_text')) and '\n' not in x['question_text'], '优化问题须为单行完整文字')
        w.require(x.get('category') in w.CATEGORIES, '问题类型须为行业排名、美誉舆情或产品场景')
        if x.get('category_ids'):
            w.require(isinstance(x['category_ids'], list) and set(x['category_ids']) <= {r['id'] for r in rows}, '问题引用未知定位选项')
    w.write(folder(w, p) / 'positioning_proposal.json', value)
    w.write(folder(w, p) / 'proposal_record.json', {'actual_model': model,
            'knowledge_sha256': manifest['knowledge_sha256'], 'proposal_sha256': w.hashfile(folder(w, p) / 'positioning_proposal.json')})
    return value


def confirm(w, p, category_id, by, note):
    w.require(by in ('user', 'explicit_prior_choice') and w.nonempty(note), '保存用户具体选择及原话')
    w.require(not w.done(p, 2), '定位已确认，不能覆盖旧版本')
    proposal = w.read(folder(w, p) / 'positioning_proposal.json')
    record = w.read(folder(w, p) / 'proposal_record.json')
    w.require(record['knowledge_sha256'] == kb.snapshot(w, p)['knowledge_sha256'], '知识库变动，请重新整理定位建议')
    w.require(record['proposal_sha256'] == w.hashfile(folder(w, p) / 'positioning_proposal.json'), '定位草案发生变化')
    option = next((x for x in proposal['category_options'] if x['id'] == category_id), None)
    w.require(option is not None, '请选择当前类别编号')
    category = {'category_id': option['id'], 'category_label': option['label'], 'category_scope': option['scope'],
                'scope': option['scope'], 'segment_id': None, 'segment_label': None,
                'product_boundaries': option.get('product_boundaries', []), 'scenario_tags': option.get('scenario_tags', [])}
    peers=inherited_peers(w,p)
    snap = {'contract': kb.DIRECT, 'selected_category': category, 'selected_candidates': peers,
            'choice_origin': {'by': by, 'note': note}, 'boundary_note': '知识库支持的企业定位，非监管认证或市场排名。'}
    snap['snapshot_id'] = w.digest(w.dump(snap))
    catalog = w.catalog(p)
    for item in proposal.get('optimization_questions', []):
        if item.get('category_ids') and category_id not in item['category_ids']:
            continue
        if any(q['question_text'] == item['question_text'] for q in catalog):
            continue
        catalog.append({'id': 'q' + str(len(catalog) + 1).zfill(6), 'question_text': item['question_text'],
                        'category': item['category'], 'origin': 'knowledge_proposed_question',
                        'periods': [{'id': 'p000001', 'date': 'undated', 'answer_count': 0}]})
    w.write(Path(p) / 'inputs/question_catalog.json', catalog)
    groups = w.read(Path(p) / 'inputs/all_answers.json')
    for q in catalog:
        for per in q['periods']:
            if not any(g['question_id'] == q['id'] and g['period_id'] == per['id'] for g in groups):
                groups.append({'question_id': q['id'], 'period_id': per['id'], 'question_text': q['question_text'],
                               'date': per['date'], 'answers': []})
    w.write(Path(p) / 'inputs/all_answers.json', groups)
    pos = {'positioning_contract': kb.DIRECT, 'positioning_snapshot': snap,
           'taxonomy': [{'id': 'primary', 'overall_category': option['label'], 'subcategory': option['label'],
                         'product_use_customer': option['scope'], 'brand_fit': option['reason'],
                         'evidence_ids': option['fact_ids'], 'answer_evidence': [], 'competitors': peers}],
           'question_map': [{'question_id': q['id'], 'category': q.get('category', '产品场景'),
                            'branch_ids': ['primary'], 'fit': 'direct', 'reason': '当前品牌范围的优化选题'} for q in catalog]}
    dependencies={**kb.dependencies(w,p),'steps/01/result.json':w.hashfile(w.stepdir(p,1)/'result.json')}
    for f in (Path(p)/'inputs').glob('confirmed_peer_pool*'):
        if f.is_file():dependencies[f.relative_to(p).as_posix()]=w.hashfile(f)
    w.bind(p, 2, None, pos, {'executor': 'kimi_proposal_then_explicit_user_choice'},dependencies)
    w.write(folder(w, p) / 'confirmation.json', {'by': by, 'note': note, 'category_id': category_id,
            'proposal_sha256': record['proposal_sha256'], 'output_sha256': w.hashfile(folder(w, p) / 'result.json')})
    w.write(Path(p) / 'reference_pack/positioning_snapshot.json', snap)
    return pos
