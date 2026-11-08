"""Assess the complete source pool and recommend 20 distinct suitable outlets."""
from collections import Counter
import csv
from pathlib import Path

PRIORITIES = ('优先推荐', '可选推荐', '待核实后考虑')
MEDIA_KINDS = ('新闻媒体', '内容平台', '视频平台', '商业发布平台', '行业资讯平台', '待核实平台')
EXCLUDED_KINDS = ('企业官网', '品牌自有站点', '政府监管资料', '医院学校科研资料', '百科论文数据库', '非发布型检索入口')
READ_LABELS = {'fulltext': '已读全文', 'title_only': '仅标题证据'}
SCOPE_LABELS = {'same': '同类用途', 'mixed': '混合用途', 'cross': '不同用途', 'undetermined': '用途待核实'}
TABLE_HEADERS = ('媒体名字', '类型', '比例', '具体文章依据')
TARGET_COUNT = 20
TOPIC_FITS = ('direct', 'related', 'weak')
FORM_FITS = ('same', 'adaptable', 'rebuild')
AUDIENCE_FITS = ('direct', 'adjacent', 'unclear')

SCHEMA = {
    'rows': [{'media': '本题媒体或平台', 'source_kind': '/'.join(MEDIA_KINDS),
              'outlet_key': '实际独立发布载体标识；同平台不同来源标签使用同一值',
              'topic_fit': '/'.join(TOPIC_FITS), 'form_fit': '/'.join(FORM_FITS),
              'audience_fit': '/'.join(AUDIENCE_FITS), 'fit_basis': '结合实际文章说明本篇用途、写法及读者适配，不能只写媒体名气',
              'selection_reason': '入选20时必填，说明相较其余候选的实际采用理由；未入选可留空',
              'priority': '/'.join(PRIORITIES), 'use_route': '本篇可采用的内容载体、角度或使用方式',
              'next_action': '需要改写、补读或核实的具体事项',
              'evidence': [{'article_id': 'a000001', 'basis': '具体被引文章与当前稿的关系',
                            'read_level': 'fulltext/title_only', 'scope_fit': 'same/mixed/cross/undetermined',
                            'scope_basis': '来源用途与本篇的实际关系'}], 'reason': '为何推荐以及限制'}],
    'excluded_sources': [{'media': '非媒体来源名称', 'source_kind': '/'.join(EXCLUDED_KINDS),
                          'reason': '依据来源身份说明剔除原因，不能用缺全文或题材不同代替',
                          'article_ids': ['该来源实际文章ID']}],
    'selection': {'selected_media': ['按推荐顺序排列的原始media键，目标20个独立载体'],
                  'required_media': ['用户明确要求纳入的本题合格media键；无此要求时为空'],
                  'required_media_note': '有指定来源时记录用户原话或已有明确授权，不由宿主编造指定',
                  'reason': '按本篇适配、具体证据、改编成本及同档引用表现择优，并说明多样性取舍；不足20如实说明'},
    'availability_note': '观察口径、完整候选覆盖范围及实际账号/栏目可购性核实情况'
}


def coverage(pool, value):
    """Every source group must have either advice or a typed identity exclusion."""
    expected = {x['media'] for x in pool['media']}
    rows = value.get('rows', [])
    excluded = value.get('excluded_sources', [])
    names = [x.get('media') for x in rows]
    removed = [x.get('media') for x in excluded]
    if len(names) != len(set(names)) or len(removed) != len(set(removed)):
        raise ValueError('媒体建议或非媒体剔除清单存在重复来源')
    if set(names) & set(removed):
        raise ValueError('同一来源不能既推荐又剔除')
    actual = set(names) | set(removed)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected, key=str)
        raise ValueError('必须覆盖本题全部来源：缺少' + '、'.join(missing) + '；未知来源' + '、'.join(map(str, unknown)))
    selection=value.get('selection', {})
    if not isinstance(selection,dict) or not isinstance(selection.get('selected_media'),list):
        raise ValueError('需提供按当前文章择优的20信源selection，旧版全表不能直接作为20个推荐')
    chosen=selection['selected_media']
    if len(chosen)!=len(set(chosen)):
        raise ValueError('推荐名单存在重复来源')
    candidates={x['media']:x for x in rows}
    eligible={name:r for name,r in candidates.items()
              if r.get('source_kind') in MEDIA_KINDS and r.get('source_kind')!='待核实平台'
              and r.get('topic_fit') in ('direct','related')}
    outlet_key=lambda r:str(r.get('outlet_key') or r['media']).strip().casefold()
    eligible_keys={outlet_key(r) for r in eligible.values()}
    required=min(TARGET_COUNT,len(eligible_keys))
    if any(name not in eligible for name in chosen):
        raise ValueError('入选信源必须来自已评估候选且身份明确、与本篇主题至少相关；企业官网、弱相关或身份未明来源不凑数')
    keys=[outlet_key(eligible[name]) for name in chosen]
    displays=[display_media(eligible[name]).strip().casefold() for name in chosen]
    if len(keys)!=len(set(keys)) or len(displays)!=len(set(displays)):
        raise ValueError('同一实际平台或其别名不能重复占推荐名额')
    if len(chosen)!=required:
        raise ValueError(f'应推荐{required}个独立合格信源（目标20个，实际合格{len(eligible_keys)}个），不得只取少量或用官网凑数')
    requested=selection.get('required_media',[])
    if not isinstance(requested,list) or len(requested)!=len(set(requested)):
        raise ValueError('用户指定信源required_media须为不重复的本题来源列表')
    if any(name not in eligible for name in requested):
        raise ValueError('用户指定来源须在本题有真实依据且身份/主题合格，不能以指定名义加入官网或池外来源')
    if any(outlet_key(eligible[name]) not in set(keys) for name in requested):
        raise ValueError('用户明确指定的合格信源必须纳入20个推荐，不能留作备选')
    return {'source_count': len(expected), 'candidate_source_group_count':len(names),
            'eligible_distinct_outlet_count':len(eligible_keys),'target_count':TARGET_COUNT,
            'recommended_source_count': len(chosen), 'reserve_source_group_count':len(names)-len(chosen),
            'excluded_source_count': len(removed), 'article_count': pool['article_count'],
            'citation_count': pool['citation_count'], 'complete': True,
            'priority_counts':dict(Counter(candidates[name].get('priority') for name in chosen)),
            'candidate_priority_counts': dict(Counter(x.get('priority') for x in rows))}


def validate(w, p, article, value):
    pool = w.sourcepool(p, article)
    w.require(isinstance(value.get('rows'), list), '需逐项评估全部第三方媒体/平台候选；全为非媒体来源时可为空')
    w.require(isinstance(value.get('excluded_sources'), list), '需明确非媒体剔除清单，可为空；不能默默漏行')
    summary = coverage(pool, value)
    lookup = {x['article_id']: x for x in pool['articles']}
    groups = {x['media']: x for x in pool['media']}
    for row in value['rows']:
        w.require(w.nonempty(row.get('outlet_key')),'需识别实际发布载体outlet_key，同平台别名不能占多个推荐名额')
        w.require(row.get('topic_fit') in TOPIC_FITS and row.get('form_fit') in FORM_FITS
                  and row.get('audience_fit') in AUDIENCE_FITS and w.nonempty(row.get('fit_basis')),
                  '每个候选需结合文章证据分析主题、写法及读者适配')
        if 'platform_name' in row:
            w.require(w.nonempty(row['platform_name']), '实际载体名称须有URL/来源身份依据，不能空填')
        w.require(row.get('source_kind') in MEDIA_KINDS, '企业官网及资料入口不进入媒体建议表；媒体类型需明确')
        w.require(row.get('priority') in PRIORITIES, '媒体建议用优先推荐/可选推荐/待核实后考虑，不用空白或未列入')
        w.require(all(w.nonempty(row.get(k)) for k in ('use_route', 'next_action', 'reason')),
                  '每家媒体需具体使用方式、下一步和理由；不能只留名称与引用量')
        ev = row.get('evidence', [])
        w.require(isinstance(ev, list) and ev, '每家媒体须有该媒体实际被引文章依据')
        ids = [e.get('article_id') for e in ev]
        w.require(len(ids) == len(set(ids)), '同一媒体证据文章不能重复计数')
        for e in ev:
            item = lookup.get(e.get('article_id'))
            w.require(item and item['media'] == row['media'], '证据文章须属于该媒体及本题实际信源')
            w.require(w.nonempty(e.get('basis')) and w.nonempty(e.get('scope_basis')), '需具体文章关系及用途说明')
            w.require(e.get('read_level') in READ_LABELS and e.get('scope_fit') in SCOPE_LABELS,
                      '如实区分全文/题名和来源用途；未知或跨用途不作为媒体漏行理由')
            if e['read_level'] == 'fulltext':
                w.fullbody(p, article, item['raw_rank'])
            e.update(title=item['content_title'], url=item['canonical_url'], citation_count=item['citation_count'])
        row.update(article_count=groups[row['media']]['article_count'], citation_count=groups[row['media']]['citation_count'],
                   evidence_article_count=len(ids), evidence_citation_count=sum(lookup[i]['citation_count'] for i in ids))
        if row['media'] in value['selection']['selected_media']:
            w.require(w.nonempty(row.get('selection_reason')),'每个入选信源须有针对当前稿的择优理由，不能按引用量机械截前20')
    for entry in value['excluded_sources']:
        w.require(entry.get('source_kind') in EXCLUDED_KINDS and w.nonempty(entry.get('reason')),
                  '只按企业自有站点或非发布资料入口身份剔除；不得因低引用/缺全文/医疗题材/文体不同剔除媒体')
        ids = entry.get('article_ids', [])
        w.require(isinstance(ids, list) and ids and len(ids) == len(set(ids)), '非媒体剔除须列实际文章ID')
        w.require(all(i in lookup and lookup[i]['media'] == entry['media'] for i in ids), '剔除依据须来自该来源的实际条目')
        entry.update(article_count=groups[entry['media']]['article_count'], citation_count=groups[entry['media']]['citation_count'])
    w.require(w.nonempty(value.get('availability_note')), '需说明统计口径与实际资源核实情况')
    w.require(w.nonempty(value['selection'].get('reason')),'需说明20信源的整体取舍及不足20时的实际原因')
    if value['selection'].get('required_media'):
        w.require(w.nonempty(value['selection'].get('required_media_note')),'指定信源须记录用户原话或明确授权，不能由宿主自行编造')
    value.update(coverage=summary, article_sha256=w.digest(w.finalbody(p, 8, article)), scope=w.selected(p, article))
    return value


def cell(value):
    return str(value).replace('|', '／').replace('\n', ' ').strip()


def sentence(value):
    return str(value or '').strip().rstrip('。；;')


def evidence_text(e):
    basis=sentence(e['basis']);scope=sentence(e['scope_basis'])
    relation='' if basis==scope else '。用途关系：'+scope
    return (f"[{e['title']}]({e['url']})（{e['citation_count']}次，{READ_LABELS[e['read_level']]}，"
            f"{SCOPE_LABELS[e['scope_fit']]}）：{basis}{relation}")


def display_media(row):
    return row.get('platform_name') or row['media']


def table_values(row):
    evidence='；'.join(evidence_text(e) for e in row['evidence'])
    if display_media(row)!=row['media']:
        evidence='原来源标签：'+row['media']+'。'+evidence
    return [display_media(row), row['source_kind'],
            f"{row['article_count']}篇／{row['citation_count']}次", evidence]


def visible_rows(value,selected_only=True):
    if not selected_only:return value['rows']
    if not isinstance(value.get('selection',{}).get('selected_media'),list):
        raise ValueError('该媒体表尚未完成20信源优选，不能机械截取旧表前20行')
    lookup={r['media']:r for r in value['rows']}
    return [lookup[name] for name in value['selection']['selected_media']]


def render_lines(value,selected_only=True):
    count = value.get('coverage', {})
    shown=visible_rows(value,selected_only)
    heading=f"本表推荐{len(shown)}个独立信源，目标20个" if selected_only else f"本表为全部{len(shown)}组媒体候选，不等于全部入选推荐"
    if selected_only and len(shown)<TARGET_COUNT:
        heading+='；本题身份明确且具备相关证据的独立载体不足20个，按实际数量推荐'
    lines = [f"覆盖核对：本题{count.get('source_count', '待核')}组来源；评估媒体候选{len(value['rows'])}组；{heading}；"
             f"剔除企业官网等非媒体来源{len(value.get('excluded_sources', []))}组。", '',
             '比例列为选中原始来源组的本题去重文章篇数／引用次数，不表示百分比；未把别名组统计擅自相加。具体文章的引用数与阅读状态在依据中单列。', '',
             '| ' + ' | '.join(TABLE_HEADERS) + ' |', '|---|---|---:|---|']
    for row in shown:
        lines.append('| ' + ' | '.join(cell(x) for x in table_values(row)) + ' |')
    return lines + ['', value.get('availability_note', '')]


def render_report(value, method,selected_only=True):
    scope = value['scope']
    date = scope.get('source_observed_from') or scope.get('observed_from') or '未提供'
    title='# 本篇优选媒体信源（目标20个）' if selected_only else '# 本题全部媒体候选清单'
    return '\n'.join([title, '',
                     f"问题：{scope['question_text']}。回答观察日期：{scope.get('observed_from') or '未提供'}；信源日期：{date}。对应当前完整终稿。",
                     '', method, '', *render_lines(value,selected_only)]) + '\n'


def write_csv(value, path,selected_only=True):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(TABLE_HEADERS)
        for row in visible_rows(value,selected_only):
            writer.writerow(table_values(row))


def exclusion_report(value, pool):
    lookup = {x['article_id']: x for x in pool['articles']}
    lines = ['# 非媒体来源剔除清单', '', '仅按来源身份剔除企业官网及资料入口；本清单不进入媒体推荐表。', '',
             '| 来源 | 类型 | 本题篇／引用 | 剔除原因与实际条目 |', '|---|---|---:|---|']
    for row in value.get('excluded_sources', []):
        articles = '；'.join(f"[{lookup[i]['content_title']}]({lookup[i]['canonical_url']})" for i in row['article_ids'])
        lines.append('| ' + ' | '.join(cell(x) for x in [row['media'], row['source_kind'],
                     f"{row['article_count']}／{row['citation_count']}", sentence(row['reason']) + '。' + articles]) + ' |')
    return '\n'.join(lines) + '\n'
