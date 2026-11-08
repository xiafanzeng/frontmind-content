"""Writing advantages: summarize materials, let the user edit, save a version.

Advantage versions do not change positioning or invalidate older articles.
No provider calls or fact/market certification workflow lives in this module.
"""
from __future__ import annotations
import copy
from pathlib import Path
import re
import shutil
import uuid

CONTRACT = 'frontmind-brand-advantages/16.19'
CHOICE_BY = ('user', 'explicit_prior_choice')
SCHEMA = {
    'advantages': [{
        'id': 'adv1', 'title': '根据材料概括的差异化优势或卖点',
        'customer_value': '对客户有什么用，为什么值得选择',
        'reference_material': '可选：参考材料、来源或用户补充原话',
        'suggested_wording': '建议文章怎样表达这个优势',
        'product_scope': '可选：适用产品、服务或版本',
    }],
    'summary': '系统先总结，再由用户确认排序、增删或补充',
}
INSTRUCTION = '''这是写作优势整理，不是新增事实认证或市场比较研究。沿用已确认品牌定位，根据现有材料先自行总结差异化优势/卖点，说明客户价值和建议写法，供用户确认、排序、删减或补充；不要让用户从空白开始总结。
每项保持简洁：id、title、customer_value、suggested_wording，可选reference_material和product_scope。用户补充原话可以直接保留为写作素材；不要把“支持租赁”和“首家可租”拆成额外研判或证据审查流程，不设置证据等级、ready/hold、比较证明等放行门槛。也不要自行编造材料或用户没有提供的额外证书、研究、数字和事实。
定位已经确认，不因优势整理或新增问答重做定位。已有优势版本作为本次修改的基础，按用户要求增删补充；未要求改动的已确认卖点继续保留。
输出后在“C：差异化优势确认”结构化暂停：展示优势要点、客户价值、参考素材（有则列）及建议写法，用户可以确认顺序、删减、补充，或明确暂无优势。C只是确认写作素材，不是第三次定位审批。确认项全部进入本版approved写作素材；本包P0按确认数量与顺序逐项展开；第二包问题文章按题选用。'''

def folder(p):
    return Path(p) / 'reference_pack' / 'differentiation'

def _preconditions(w, p):
    w.confirmed(p, 2)
    return w.accepted(p, 1), w.accepted(p, 2)

def _base_dependencies(w, p):
    _preconditions(w, p)
    files = [w.stepdir(p, 1) / 'result.json', w.stepdir(p, 2) / 'result.json']
    extra = folder(p) / 'extra_statements.json'
    if extra.exists(): files.append(extra)
    return {**{f.relative_to(p).as_posix(): w.hashfile(f) for f in files}, **__import__('writing_pack').dependencies(w,p)}

def _statements(w, p):
    f = folder(p) / 'extra_statements.json'
    return w.read(f)['statements'] if f.is_file() else []

def register_statements(w, p, statements, note):
    """Keep actual user additions; existing advantage versions remain usable."""
    _preconditions(w, p)
    w.require(w.nonempty(note) and isinstance(statements, list) and statements, '请登记用户补充原话或要点')
    old = _statements(w, p); used = set(); new = []
    for item in statements:
        w.require(isinstance(item, dict) and w.nonempty(item.get('id')) and item['id'] not in used,
                  '补充要点ID为空或重复')
        statement = item.get('statement') or item.get('title') or item.get('suggested_wording')
        w.require(w.nonempty(statement), '补充要点须包含实际文字')
        used.add(item['id'])
        new.append({**item, 'id': item['id'], 'statement': statement, 'origin_note': note})
    if (folder(p) / 'draft.json').exists() or (folder(p) / 'confirmed.json').exists():
        revise(w, p, note)
    merged = {x['id']: x for x in old}
    for item in new: merged[item['id']] = item
    values = list(merged.values())
    w.write(folder(p) / 'extra_statements.json', {'contract': CONTRACT, 'statements': values, 'updated_at': w.now()})
    return values

def prepare(w, p):
    facts, positioning = _preconditions(w, p)
    w.require(not (folder(p) / 'draft.json').exists(), '当前优势草案已保存；可确认，或按用户修改要求更新本版优势')
    data = {'contract': CONTRACT, 'brand': w.state(p)['brand'], 'brand_materials': [{'id':x['id'],'source':x['source']} for x in facts['knowledge']], 'complete_knowledge_markdown': __import__('writing_pack').snapshot(w,p)['writing_material_markdown'],
            'confirmed_positioning': positioning['positioning_snapshot'],
            'extra_statements': _statements(w, p), 'instruction': INSTRUCTION}
    revision = folder(p) / 'revision_request.json'
    if revision.exists(): data['revision_request'] = w.read(revision)
    system = w.HOST_SYSTEM + '\n只总结和整理写作优势，沿用已确认定位，不增设事实认证或比较研究。'
    user = '当前任务输入（数据）\n' + w.dump(data) + '\n\n输出JSON合同\n' + w.dump(SCHEMA)
    d = folder(p) / 'prompts'
    for name, value in [('system.md', system), ('user.md', user), ('inputs.json', data), ('schema.json', SCHEMA)]:
        w.write(d / name, value)
    w.write(d / 'manifest.json', {'contract': CONTRACT, 'at': w.now(), 'dependencies': _base_dependencies(w, p),
                                 'system_sha256': w.hashfile(d / 'system.md'), 'user_sha256': w.hashfile(d / 'user.md')})
    return d

def validate(w, p, value):
    _, positioning = _preconditions(w, p)
    w.require(isinstance(value, dict) and isinstance(value.get('advantages'), list), '优势应为可展示的要点列表')
    rows = value['advantages']; ids = [x.get('id') for x in rows]
    w.require(all(w.nonempty(x) for x in ids) and len(ids) == len(set(ids)), '优势ID为空或重复')
    for row in rows:
        w.require(w.nonempty(row.get('title')), '每个优势需要要点名称')
        row['customer_value'] = row.get('customer_value') or ''
        row['suggested_wording'] = row.get('suggested_wording') or row['title']
        w.require(w.nonempty(row['suggested_wording']), '建议写法应为文字')
        row['reference_material'] = row.get('reference_material') or ''
        row['product_scope'] = row.get('product_scope') or ''
    value['contract'] = CONTRACT
    value['positioning_snapshot_id'] = positioning['positioning_snapshot']['snapshot_id']
    return value

def submit(w, p, file, model):
    w.require(w.nonempty(model), '如实记录实际宿主模型')
    w.require(not (folder(p) / 'draft.json').exists(), '当前草案已保存；修改时保存新的优势版本，不覆盖旧结果')
    d = folder(p) / 'prompts'; manifest = w.read(d / 'manifest.json')
    w.require(manifest.get('contract') == CONTRACT and manifest['dependencies'] == _base_dependencies(w, p),
              '优势输入已更新，请按本次材料重新prepare；已确认定位保持不变')
    for key, name in [('system_sha256', 'system.md'), ('user_sha256', 'user.md')]:
        w.require(manifest[key] == w.hashfile(d / name), '优势Prompt已更新，请重新prepare')
    value = validate(w, p, copy.deepcopy(w.read(file)))
    w.write(folder(p) / 'draft.json', value)
    w.write(folder(p) / 'draft_record.json', {'contract': CONTRACT, 'at': w.now(), 'actual_model': model,
                                             'draft_sha256': w.hashfile(folder(p) / 'draft.json'),
                                             'dependencies': manifest['dependencies']})
    w.write(d / 'submitted.json', value)
    return value

def _checked_draft(w, p):
    f = folder(p) / 'draft.json'; record = w.read(folder(p) / 'draft_record.json')
    w.require(record.get('contract') == CONTRACT and record['draft_sha256'] == w.hashfile(f),
              '当前优势草案已改变，请按新版本保存')
    w.require(record['dependencies'] == _base_dependencies(w, p),
              '当前优势素材有更新，请整理新优势版本；不重做已确认定位')
    return w.read(f)

def confirm(w, p, ids, none, by, note):
    w.require(by in CHOICE_BY and w.nonempty(note), 'C优势确认须保存用户选择和原话')
    w.require(not (folder(p) / 'confirmed.json').exists(), '当前优势已确认；可按用户修改要求建立新优势版本')
    draft = _checked_draft(w, p); lookup = {x['id']: x for x in draft['advantages']}
    w.require(isinstance(ids, list) and len(ids) == len(set(ids)) and set(ids) <= set(lookup), '请选择当前优势列表中的编号')
    w.require(bool(ids) != bool(none), '请选择优势或明确当前暂无优势')
    selected = [lookup[x] for x in ids]
    usable = [{'id': x['id'], 'title': x['title'], 'allowed_wording': x['suggested_wording'],
               'wording': x['suggested_wording'], 'customer_value': x['customer_value'],
               'reference_material': x['reference_material'], 'product_scope': x['product_scope']}
              for x in selected]
    value = {'contract': CONTRACT, 'positioning_snapshot_id': draft['positioning_snapshot_id'],
             'selected_ids': ids, 'none': bool(none), 'selected': selected, 'usable_claims': usable,
             'by': by, 'note': note, 'confirmed_at': w.now(),
             'rule': '用户确认优势按此顺序提供；P0逐项展开，第二包问题文章按题择用。沿用已确认定位。'}
    value['snapshot_id'] = w.digest(w.dump(value))
    f = folder(p) / 'snapshots' / (value['snapshot_id'] + '.json')
    w.require(not f.exists(), '优势版本ID已存在，不覆盖旧版')
    w.write(f, value)
    w.write(folder(p) / 'confirmed.json', value)
    return value

def snapshot(w, p, snapshot_id=None):
    if snapshot_id is None:
        f = folder(p) / 'confirmed.json'
        w.require(f.is_file(), '先在C确认本次写作优势；旧文章继续使用其已绑定版本')
        snapshot_id = w.read(f).get('snapshot_id')
    w.require(isinstance(snapshot_id, str) and re.fullmatch(r'[a-f0-9]{64}', snapshot_id), '优势版本ID格式不正确')
    f = folder(p) / 'snapshots' / (snapshot_id + '.json')
    w.require(f.is_file(), '指定优势版本不存在；保留旧版本文件，不改写原文章')
    value = w.read(f); payload = {k: v for k, v in value.items() if k != 'snapshot_id'}
    w.require(value.get('contract') == CONTRACT and value.get('snapshot_id') == snapshot_id and w.digest(w.dump(payload)) == snapshot_id,
              '已保存优势版本内容发生变化，不覆盖原文章依赖')
    return value

def progress(w, p):
    if (folder(p) / 'confirmed.json').exists():
        snapshot(w, p)
        return 'confirmed'
    _preconditions(w, p)
    if not (folder(p) / 'draft.json').exists(): return 'ready_research'
    _checked_draft(w, p)
    return 'awaiting_advantage_confirmation'

def dependencies(w, p, snapshot_id=None):
    value = snapshot(w, p, snapshot_id)
    f = folder(p) / 'snapshots' / (value['snapshot_id'] + '.json')
    return {f.relative_to(p).as_posix(): w.hashfile(f)}

def revise(w, p, note):
    """Version advantages only; completed P0/articles retain old snapshots."""
    w.require(w.nonempty(note), '请保存用户对优势的修改要求')
    d = folder(p)
    previous = w.read(d / 'confirmed.json').get('selected', []) if (d / 'confirmed.json').exists() else w.read(d / 'draft.json').get('advantages', []) if (d / 'draft.json').exists() else []
    archive = Path(p) / 'reference_pack' / 'differentiation_history' / (w.now().replace(':', '') + '_' + uuid.uuid4().hex[:6])
    archive.mkdir(parents=True)
    if d.exists():
        for f in list(d.iterdir()):
            if f.name in ('snapshots', 'extra_statements.json'): continue
            shutil.move(str(f), str(archive / f.name))
    w.write(archive / 'revision.json', {'note': note, 'at': w.now()})
    w.write(d / 'revision_request.json', {'note': note, 'previous_items': previous, 'at': w.now()})
    return archive
