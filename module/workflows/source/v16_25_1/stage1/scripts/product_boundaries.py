"""Material product differences precede settings; evidence remains separate.

Signals request an assessment, never classify a product or its legal status.
The host still reads the complete answers and supplies attributable judgments.
"""
from __future__ import annotations
import re

CONTRACT = 'frontmind-product-boundaries/16.18'
KINDS = ('product_nature', 'scenario', 'attribute')
CHECKS = ('match', 'mismatch', 'unknown')
BASES = ('product_source', 'enterprise_statement', 'answer_observation', 'not_available')

REVIEW_SCHEMA = {
    'schema': CONTRACT,
    'dimensions': [{
        'id': 'd1', 'label': '改变替代关系的产品差异', 'kind': 'product_nature/scenario/attribute',
        'decisive': True, 'reason': '为什么改变或不改变产品替代关系',
        'values': [{'id': 'v1', 'label': '产品类型', 'definition': '纳入与排除边界'}],
        'answer_evidence': [{'observation_id': '实际ID', 'quote': '原句'}],
    }],
    'no_decisive_product_boundary_reason': '仅在答案确不支持产品本质分界时说明，不得用场景替代已出现的产品分界',
    'regulatory_status': {'status': 'documented/enterprise_stated/unverified/conflicting/not_applicable',
                          'statement': '自家具体产品法定属性的证据状态，与本轮商业/写作用途选择分开',
                          'sources': [{'source': '原件或URL', 'quote': '原句'}]},
}
CHECK_SCHEMA = [{
    'dimension_id': '已确认的关键产品维度', 'value_id': '候选对应值，未知null',
    'status': 'match/mismatch/unknown', 'basis': 'product_source/enterprise_statement/answer_observation/not_available',
    'evidence_role': 'product_boundary/scenario_only/uncertain',
    'source': '具体产品原件/URL或观察ID，缺失留空', 'quote': '可回查原句，缺失留空',
    'reason': '为何满足、不满足或仍未定；场景相同不能代替产品边界',
}]

INSTRUCTION = '''先区别“产品是什么”和“在哪里用”。必须审读答案中的产品本质分界，例如医疗诊疗/临床辅助与非医疗康养评估、完整多诊采集终端与单脉诊模块、硬件终端与软件/医生服务；只保留实际改变本题替代关系的维度，不为凑字段发明分类。机构/家庭/门店/社区通常是使用场景，同一产品可跨场景，不能先按场景切断同类型研究池。只有确有工作流或交付差异时，场景才成为下层的必要细分，并说明对替代关系的影响。
product_boundary_review逐项记录维度、是否关键、不同取值及完整答案证据。已由用户明确的业务用途保留为条件；与材料冲突时展示冲突，不静默置空。detected_boundary_signals仅提示必须研究的原文信号，不是产品事实判断。若触发health_intended_use信号，必须显式审查同名维度，取值至少含clinical(医疗诊疗/临床辅助)、nonclinical(非医疗康养评估)，也可含unknown或research_only；不能用机构/家庭覆盖掉医疗/非医疗分界。
类别与必要细分的boundary_values明确映射关键维度。primary_split_axis.dimension_id必须指向关键产品维度；场景和价格、形态等另列，不把不同轴硬排为一层。已选类别和细分合起来须明确全部关键维度；不确定的值应明示unknown供企业选择或补充，不能代选。自家设备法定注册/备案状态单独填regulatory_status；选择非医疗康养是本轮比较和写作边界，不等于已核验非医疗合规，更不能因未见注册证反推非医疗。
每份答案保存实际局部分类、未知与冲突。答案只谈家用/门店时，不据此断言其器械法定属性；原文未定的产品边界保留未定。完整答案本身是AI表达观察，不是产品资质证明。'''

CANDIDATE_INSTRUCTION = '''候选须逐项填写boundary_checks，对照selected_category.product_boundaries中的每个关键维度，分别标match/mismatch/unknown，并写对应具体产品依据。evidence_role区分原句是否支持产品边界(product_boundary)、只说明使用场景(scenario_only)、不清楚(uncertain)；只说明“面向药店/康养机构”不足以填关键产品边界match。面向同一门店、康养机构或同公司另一型号均不能代替产品类型匹配。医疗/非医疗比较边界核对具体产品的预期用途与服务职责，不用3C称谓或缺注册证代替用途证据；法定状态另记证据限制。
match基于answer_observation只说明同类线索，不能提升为产品事实已支持。任何关键维度unknown或仅AI观察，必须保留为待核研究候选而非已核同类；资料不完整不能被静默删除。任何关键维度mismatch的具体产品另列跨类，不进入同类可选表。若品牌有另一款符合边界的产品，应另核对应产品，不能把医疗款的一切能力移入康养款。
先展示已支持同类，再展示待核同类线索；企业可明确保留待核对象研究。可见度依产品类别的局部答案语境计算，不按机构/家庭场景先删掉同类型候选，不把整品牌或其他型号的提及当本型号表现。'''

REVIEW_SCHEMA_CANDIDATES = {
    'candidate_analysis_sha256': '当前candidate_analysis.json文件sha256',
    'review_origin': 'separate_context/same_host_second_pass',
    'verdicts': [{'candidate_id': '逐项覆盖所有候选',
                  'checks': [{'dimension_id': '关键产品维度', 'verdict': 'supported/insufficient/conflicting',
                              'source': '被复核的原来源', 'quote': '被复核的原引文，未知可留空',
                              'reason': '原句是否证明具体产品本质，还是仅同场景/别的型号/AI陈述'}]}],
    'overall_pass': True,
    'notes': '待核线索可保持未知；复核不替代外站取证或法定资质核验',
}
REVIEW_INSTRUCTION = '''对已保存的候选研究作第二次证据审读，不写正文，不代企业选竞品，也不把待核项补成已核。逐个candidate_id和关键产品维度读具体产品、原文与来源，独立判断该引文是否蕴含对应产品本质：supported、insufficient、conflicting。不要复制作者自填的evidence_role/status当结论；“适合连锁药店、养生馆、康养机构”只证明场景，不能同时证明非医疗用途、多诊模块齐备、硬件交付。“报告仅供参考”也可能出现在医疗辅助设备；3C或未见医械证不是法定分类证明。
每条verdict复制当前被复核来源与引文，并说明为什么足够或不足。对应多个维度时分别核对，不能一条场景引文一概判三项match。任何拟列supported同类的候选有一个关键维度insufficient/conflicting，overall_pass必须false，返回修改候选关系/证据状态或补产品用途来源。已经诚实标pending/unknown的线索可保留研究，复核无需因其仍未知而全局失败。所有候选均需覆盖。具备子代理能力时用不带作者结论偏好的新上下文审读；否则如实标same_host_second_pass，不伪称独立模型。复核是自动研究环节，不新增用户暂停点。'''

def validate_candidate_review(w, review, analysis, analysis_sha):
    w.require(review.get('candidate_analysis_sha256') == analysis_sha, '证据复核必须绑定当前候选版本')
    w.require(review.get('review_origin') in ['separate_context', 'same_host_second_pass'], '如实记录新上下文复核或同宿主第二遍，不伪称独立模型')
    verdicts=review.get('verdicts',[]);ids=[x.get('candidate_id') for x in verdicts]
    candidates={x['candidate_id']:x for x in analysis['candidates']}
    w.require(len(ids)==len(set(ids)) and set(ids)==set(candidates), '证据复核须逐候选覆盖，不能只看最高可见度对象')
    inconsistent=[]
    for row in verdicts:
        candidate=candidates[row['candidate_id']];checks={x['dimension_id']:x for x in candidate['boundary_checks']}
        judgments=row.get('checks',[]);keys=[x.get('dimension_id') for x in judgments]
        w.require(len(keys)==len(set(keys)) and set(keys)==set(checks), '复核须覆盖每条关键产品边界')
        for judgment in judgments:
            original=checks[judgment['dimension_id']]
            w.require(judgment.get('verdict') in ['supported','insufficient','conflicting'] and w.nonempty(judgment.get('reason')), '复核须解释引文是否支持具体产品本质')
            w.require(judgment.get('source','')==original.get('source','') and judgment.get('quote','')==original.get('quote',''), '复核不能偷换原候选的来源/引文，补来源须先修订候选')
            if candidate['evidence_status']=='supported' and candidate['relationship']!='cross_category' and judgment['verdict']!='supported':inconsistent.append(candidate['candidate_id'])
    w.require(isinstance(review.get('overall_pass'),bool), '复核须明确能否继续')
    w.require(not inconsistent or not review['overall_pass'], '复核发现已支持候选的关键边界无依据，不能仍放行同类选择页')
    return review

def signals(observations, focus):
    health = re.search(r'四诊|脉诊|中医.{0,8}(?:机器人|设备|仪)|体质.{0,4}(?:仪|终端)|健康.{0,4}(?:机器人|评估设备)', focus)
    if not health:
        return []
    pattern = re.compile(r'非医疗|非诊疗|医疗器械|临床级|临床辅助|辅助诊断|医疗级')
    excerpts = []
    ids = set()
    for o in observations:
        m = pattern.search(o['answer_text'])
        if not m:
            continue
        ids.add(o['observation_id'])
        if len(excerpts) < 8:
            start = max(0, o['answer_text'].rfind('\n', 0, m.start()) + 1)
            end = o['answer_text'].find('\n', m.end())
            if end < 0: end = min(len(o['answer_text']), m.end() + 150)
            excerpts.append({'observation_id': o['observation_id'], 'quote': o['answer_text'][start:end]})
    result = [{'dimension_id': 'health_intended_use', 'label': '医疗诊疗/临床辅助与非医疗康养用途边界',
             'observation_count': len(ids), 'examples': excerpts,
             'limit': '原文触发待研究维度，不证明任何品牌的医疗器械法定属性；完整答案仍须逐份审读。'}] if ids else []
    corpus = '\n'.join(o['answer_text'] for o in observations)
    contrasts = [
        ('collection_extent', '多诊整机与单脉诊/采集模块', r'单.{0,2}脉诊|仅.{0,5}(?:切诊|脉诊)|只有.{0,5}切诊', r'四诊合一|四诊合参|舌面脉'),
        ('delivery_form', '硬件终端与模型/软件服务交付', r'API|SaaS|纯软件|软件服务', r'四诊仪|采集终端|硬件'),
    ]
    for key, label, left, right in contrasts:
        if not (re.search(left, corpus, re.I) and re.search(right, corpus, re.I)):continue
        examples=[];hits=0
        for o in observations:
            m=re.search(left,o['answer_text'],re.I)
            if not m:continue
            hits+=1
            if len(examples)>=3:continue
            start=max(0,o['answer_text'].rfind('\n',0,m.start())+1);end=o['answer_text'].find('\n',m.end())
            if end<0:end=len(o['answer_text'])
            examples.append({'observation_id':o['observation_id'],'quote':o['answer_text'][start:end]})
        result.append({'dimension_id':key,'label':label,'observation_count':hits,'examples':examples,
                       'limit':'须审查是否改变本题实际替代关系；可以有依据地记非关键，不按词语自动排除产品。'})
    return result

def dimensions(data):
    return {x['id']: x for x in data['product_boundary_review']['dimensions']}

def required(data):
    return {k: v for k, v in dimensions(data).items() if v['kind'] == 'product_nature' and v['decisive']}

def describe(data, values):
    dm = dimensions(data)
    return '；'.join(dm[k]['label']+'＝'+next(x['label'] for x in dm[k]['values'] if x['id']==v) for k,v in values.items() if k in required(data))

def validate_review(w, data, obs, detected):
    review = data.get('product_boundary_review', {})
    w.require(review.get('schema') == CONTRACT, '必须先审查产品本质分界，不能只提交场景类别（v16.18合同）')
    dims = review.get('dimensions', [])
    w.require(isinstance(dims, list) and dims, '须记录产品本质/场景/属性的维度审查及依据')
    ids = [x.get('id') for x in dims]
    w.require(all(w.nonempty(x) for x in ids) and len(ids) == len(set(ids)), '产品维度ID为空或重复')
    for dim in dims:
        w.require(dim.get('kind') in KINDS and isinstance(dim.get('decisive'), bool), '维度须区分产品本质、场景和属性，并判断是否改变替代关系')
        w.require(all(w.nonempty(dim.get(k)) for k in ['label', 'reason']), '每个维度须说明本质差异与采用理由')
        vals = dim.get('values', [])
        vi = [x.get('id') for x in vals]
        w.require(vals and all(w.nonempty(x) for x in vi) and len(vi) == len(set(vi)), '维度取值ID为空或重复')
        w.require(all(w.nonempty(x.get('label')) and w.nonempty(x.get('definition')) for x in vals), '维度每个取值需有明确纳入/排除定义')
        w.require(not dim['decisive'] or dim.get('answer_evidence'), '关键分界须有完整答案依据，不能凭空发明')
        for ref in dim.get('answer_evidence', []):
            o = obs.get(ref.get('observation_id'))
            w.require(o and w.nonempty(ref.get('quote')) and ref['quote'] in o['answer_text'], '产品分界引文须逐字存在于对应完整答案')
    dm = dimensions(data)
    for signal in detected:
        dim = dm.get(signal['dimension_id'])
        w.require(dim and dim['kind'] == 'product_nature' and dim.get('answer_evidence'), '答案出现了产品差异信号，须以原句明确采用或不采用的依据：'+signal['dimension_id'])
        if signal['dimension_id']=='health_intended_use':
            w.require(dim['decisive'], '答案已体现医疗/非医疗边界，不能以机构/家庭场景代替；须审查health_intended_use')
            w.require({'clinical', 'nonclinical'} <= {x['id'] for x in dim['values']}, '医疗用途维度至少区分clinical与nonclinical；证据不足另列unknown，不反推资质')
    req = required(data)
    if req:
        primary = data.get('primary_split_axis', {}).get('dimension_id')
        w.require(primary in req, '已有关键产品分界时，大类必须先按产品本质划分，不能先按场景分流')
        primary_values = [c.get('boundary_values', {}).get(primary) for c in data['categories']]
        w.require(all(primary_values) and len(primary_values) == len(set(primary_values)), '同一关键产品取值不能仅因机构/家庭场景不同拆成互斥大类；场景放属性或有据细分')
    else:
        w.require(w.nonempty(review.get('no_decisive_product_boundary_reason')), '没有关键产品分界须说明证据理由，不得默认忽略')
    reg = review.get('regulatory_status', {})
    w.require(reg.get('status') in ['documented', 'enterprise_stated', 'unverified', 'conflicting', 'not_applicable'] and w.nonempty(reg.get('statement')), '监管事实状态须与业务定位选择分开记录')
    if reg['status'] in ['documented', 'enterprise_stated']:
        w.require(reg.get('sources') and all(w.nonempty(x.get('source')) and w.nonempty(x.get('quote')) for x in reg['sources']), '已记录的监管事实须给来源，不由商业定位或未见证据反推')
    for c in data['categories']:
        alternatives = c.get('segments', []) or [{}]
        for segment in alternatives:
            parent = c.get('boundary_values', {})
            child = segment.get('boundary_values', {})
            w.require(all(k not in parent or parent[k] == v for k,v in child.items()), '细分不能覆盖父类已经确认的产品本质取值；需要改变时另建同轴类别')
            values = {**c.get('boundary_values', {}), **segment.get('boundary_values', {})}
            w.require(set(req) <= set(values), '类别及必要细分须明确所有关键产品边界；不允许用“无必要细分”跳过')
            for key, value in values.items():
                w.require(key in dm and value in {x['id'] for x in dm[key]['values']}, '类别产品边界含未知维度或取值')

def selected(data, category, segment):
    vals = {**category.get('boundary_values', {}), **(segment or {}).get('boundary_values', {})}
    rows = []
    for key, dim in required(data).items():
        v = next(x for x in dim['values'] if x['id'] == vals[key])
        rows.append({'dimension_id': key, 'label': dim['label'], 'value_id': v['id'], 'value_label': v['label'], 'definition': v['definition']})
    return rows

def candidate_state(candidate):
    checks = candidate.get('boundary_checks', [])
    if any(x['status'] == 'mismatch' for x in checks): return 'mismatch'
    if any(x['status'] == 'unknown' or x['basis'] not in ['product_source', 'enterprise_statement'] for x in checks): return 'uncertain'
    return 'matching'

def validate_candidate(w, candidate, selection):
    expected = {x['dimension_id']: x for x in selection.get('product_boundaries', [])}
    w.require(isinstance(candidate.get('boundary_checks'), list), '每个候选须显式记录boundary_checks；无关键维度时也保留空数组')
    checks = candidate.get('boundary_checks', [])
    keys = [x.get('dimension_id') for x in checks]
    w.require(len(keys) == len(set(keys)) and set(keys) == set(expected), '每个候选须逐项核对已确认产品边界；不能仅凭相同场景标同类')
    for check in checks:
        target = expected[check['dimension_id']]
        w.require(check.get('status') in CHECKS and check.get('basis') in BASES and w.nonempty(check.get('reason')), '候选边界须区分匹配/不匹配/未知和来源类型')
        w.require(check.get('evidence_role') in ['product_boundary', 'scenario_only', 'uncertain'], '候选依据须说明支持产品本质还是仅使用场景')
        if check['status'] in ['match', 'mismatch']:
            w.require(check['evidence_role'] == 'product_boundary', '仅相同场景或依据未明不能判产品边界匹配/不匹配，应保留unknown')
        if check['status'] == 'match':
            w.require(check.get('value_id') == target['value_id'] and target['value_id'] not in ['unknown', 'unresolved'], '不能将不同或未定产品类型标为已匹配')
        if check['status'] == 'mismatch':
            w.require(w.nonempty(check.get('value_id')) and check['value_id'] != target['value_id'], '不匹配须指出不同产品取值')
        if check['status'] != 'unknown':
            w.require(w.nonempty(check.get('source')) and w.nonempty(check.get('quote')), '已判断匹配/不匹配需具体产品或观察依据')
        if check['basis'] == 'not_available':
            w.require(check['status'] == 'unknown', '没有依据只能保留未知，不能当已支持同类')
    status = candidate_state(candidate)
    if status == 'mismatch':
        w.require(candidate['relationship'] == 'cross_category', '关键产品边界不匹配须列跨类，不能因都面向门店而标直接或邻近同类')
    if status == 'uncertain':
        w.require(candidate['evidence_status'] != 'supported', '产品关键边界未定或仅AI观察，不能标产品事实已支持；保留待核研究线索')
    return status

def eligibility(candidate, selection):
    return (candidate['relationship'] != 'cross_category' and candidate_state(candidate) != 'mismatch'
            and candidate['category_id'] == selection['category_id']
            and (not selection.get('segment_id') or candidate.get('segment_id') in [None, selection['segment_id']]))
