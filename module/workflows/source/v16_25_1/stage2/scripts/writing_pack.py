"""Three-file Reference Pack and direct, versioned Markdown knowledge input."""
from pathlib import Path, PurePosixPath
import io
import re
import shutil
import zipfile

CONTRACT = 'frontmind-knowledge-source/16.21'
IMPORTED = 'frontmind-confirmed-three-item-pack/16.21'
DIRECT = 'frontmind-knowledge-positioning/16.21'
PACK_FILES = ('定位.md', '核心差异化优势.md', '知识库.zip')


def _zip_members(path):
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP文件损坏')
        infos = z.infolist()
        if len({i.filename for i in infos}) != len(infos):
            raise ValueError('ZIP成员路径重复')
        for info in infos:
            q = PurePosixPath(info.filename)
            if q.is_absolute() or '..' in q.parts or any(':' in part for part in q.parts) or '\\' in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('ZIP含不安全路径或软链接')
        if sum(i.file_size for i in infos) > 500 * 1024 * 1024:
            raise ValueError('知识库超过500MB')
        return [i.filename for i in infos if not i.is_dir()]


def _knowledge_members(path):
    names = _zip_members(path)
    if not any(n.lower().endswith('.md') for n in names):
        raise ValueError('请提供包含完整Markdown知识内容的知识库ZIP')
    if any(Path(n).suffix.lower() in {'.pdf', '.docx', '.pptx', '.xlsx', '.jpg', '.jpeg', '.png', '.mp4', '.rar'} for n in names):
        raise ValueError('知识库入口接收已整理的Markdown知识包；原始附件先整理为知识库')
    return names


def attach_knowledge(w, p, file):
    src = Path(file).expanduser().resolve()
    _knowledge_members(src)
    sha = w.hashfile(src)
    target = Path(p) / 'knowledge_sources' / (sha + '.zip')
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(src, target)
    w.write(Path(p) / 'knowledge_current.json', {'path': target.relative_to(p).as_posix(), 'sha256': sha})
    return target


def exists(p):
    return (Path(p) / 'knowledge_current.json').is_file()


def ensure_knowledge(w, p):
    w.require(exists(p), '请先导入完整Markdown知识库ZIP')
    pointer = w.read(Path(p) / 'knowledge_current.json')
    path = Path(p) / pointer['path']
    w.require(w.hashfile(path) == pointer['sha256'], '知识库版本已变化，请导入新版本')
    return path


def knowledge_documents(w, p, snapshot_id=None):
    if snapshot_id:
        path = Path(p) / 'knowledge_sources' / (snapshot_id + '.zip')
        w.require(path.is_file() and w.hashfile(path) == snapshot_id, '绑定的知识库版本不存在或已变化')
    else:
        path = ensure_knowledge(w, p)
    names = _knowledge_members(path)
    docs = []
    with zipfile.ZipFile(path) as z:
        for name in sorted(names):
            if name.lower().endswith('.md'):
                text = z.read(name).decode('utf-8-sig')
                if text.strip():
                    docs.append({'member': name, 'text': text})
    w.require(docs, '知识库Markdown正文为空')
    return path, docs


def snapshot(w, p, snapshot_id=None):
    path, docs = knowledge_documents(w, p, snapshot_id)
    sha = w.hashfile(path)
    # Source text is expanded into the current prompt, never rewritten into a second standing summary.
    text = '\n\n'.join('## 知识库原文 ' + d['member'] + '\n\n' + d['text'].strip() for d in docs)
    return {'contract': CONTRACT, 'snapshot_id': sha, 'knowledge_sha256': sha,
            'writing_material_markdown': text, 'directory': path.parent, 'knowledge_path': path,
            'source_members': [d['member'] for d in docs]}


def dependencies(w, p, snapshot_id=None):
    s = snapshot(w, p, snapshot_id)
    f = s['knowledge_path']
    return {f.relative_to(p).as_posix(): w.hashfile(f)}


def bind_knowledge_facts(w, p):
    path, docs = knowledge_documents(w, p)
    extracted = Path(p) / 'knowledge_sources' / 'extracted' / w.hashfile(path)
    entries, facts = [], []
    for i, d in enumerate(docs, 1):
        target = extracted / d['member']
        w.write(target, d['text'])
        relative = target.relative_to(p).as_posix()
        entries.append({'path': relative, 'text_path': relative, 'file_name': d['member'],
                        'sha256': w.hashfile(target), 'status': 'knowledge_original_text'})
        facts.append({'id': 'k' + str(i).zfill(4), 'statement': d['text'], 'source': relative,
                      'quote': d['text'], 'status': 'imported_source_text', 'conditions': '保留原文范围，导入不等于独立核验'})
    w.write(Path(p) / 'inputs/materials.json', entries)
    w.bind(p, 1, None, {'brand': w.state(p)['brand'], 'knowledge': facts,
                        'overview': '完整知识库原文索引；没有新编综合底稿或伪造事实核验。'},
           {'executor': 'deterministic_complete_knowledge_import; no AI call'}, dependencies(w, p))


def _line(text, label):
    m = re.search(r'^' + re.escape(label) + r'[：:][ \t]*(.*?)[ \t]*$', text, re.M)
    return m[1].strip() if m else ''


def confirmed_candidates(text):
    """Restore only the confirmed section; never infer candidates from answers."""
    section=re.search(r'^## 已确认同类竞品\s*\n(.*?)(?=^## |\Z)',text,re.M|re.S)
    if not section:
        return []
    rows=[]
    for i,m in enumerate(re.finditer(r'^###[ \t]+([^\n]+)\n(.*?)(?=^###[ \t]+|\Z)',section[1],re.M|re.S),1):
        rows.append({'candidate_id':'c'+str(i).zfill(3),'display_name':m[1].strip(),
                     'product_name':_line(m[2],'对应产品') or m[1].strip(),
                     'purpose':_line(m[2],'用途'),'confirmed_description':m[2].strip(),
                     'source':'imported_pack/定位.md#'+m[1].strip(),'origin':'inherited_user_confirmed_pool'})
    return rows










def import_pack(w, p, pack, brand=None):
    p = Path(p).resolve()
    src = Path(pack).expanduser().resolve()
    w.require(not (p / 'state.json').exists(), '导入到新项目，不覆盖既有项目')
    contents = {}
    if src.is_dir():
        for name in PACK_FILES:
            found = list(src.rglob(name))
            w.require(len(found) == 1, '三项Reference Pack缺失或重复：' + name)
            contents[name] = found[0].read_bytes()
    else:
        names = _zip_members(src)
        with zipfile.ZipFile(src) as z:
            for name in PACK_FILES:
                found = [n for n in names if Path(n).name == name]
                w.require(len(found) == 1, '请提供三项Reference Pack：' + name)
                contents[name] = z.read(found[0])
    _knowledge_members(io.BytesIO(contents['知识库.zip']))
    posmd = contents['定位.md'].decode('utf-8-sig')
    advmd = contents['核心差异化优势.md'].decode('utf-8-sig')
    name = _line(posmd, '品牌') or brand
    aliases = [s for s in re.split('[、,，]', _line(posmd, '别名')) if s]
    w.require(w.nonempty(name), '请提供品牌名称')
    if brand:
        w.require(brand in [name, *aliases], '品牌与Reference Pack不一致')
    p.mkdir(parents=True, exist_ok=True)
    d = p / 'imported_pack'
    d.mkdir()
    for key, data in contents.items():
        (d / key).write_bytes(data)
    w.save(p, {'schema': 'frontmind/16.21', 'brand': name, 'aliases': aliases, 'articles': {},
               'positioning_contract': IMPORTED, 'origin': 'confirmed_three_item_pack',
               'model_policy': {'research': 'kimi_hosted/kimi-k3.1-pro/high', 'writer': 'gemini-4-argon', 'effort': 'high'}})
    attach_knowledge(w, p, d / '知识库.zip')
    bind_knowledge_facts(w, p)
    questions = []
    section = posmd.split('## 优化问题目录', 1)[1] if '## 优化问题目录' in posmd else ''
    for i, match in enumerate(re.finditer(r'^###[ \t]+([^\n]+)\n(.*?)(?=^###[ \t]+|\Z)', section, re.M | re.S), 1):
        text = _line(match[2], '问题')
        if text:
            questions.append({'id': match[1].strip(), 'question_text': text,
                              'category': _line(match[2], '类型') or '产品场景',
                              'origin': 'part1_question_catalog',
                              'periods': [{'id': 'p000001', 'date': 'undated', 'answer_count': 0}]})
    w.write(p / 'inputs/question_catalog.json', questions)
    w.write(p / 'inputs/all_answers.json', [{'question_id': q['id'], 'period_id': 'p000001',
             'question_text': q['question_text'], 'date': 'undated', 'answers': []} for q in questions])
    own = re.split(r'^## (?:同类研究背景|已确认同类竞品|优化问题目录)', posmd, maxsplit=1, flags=re.M)[0]
    scope = own.split('## 本轮定位', 1)[1].strip() if '## 本轮定位' in own else own
    label = _line(posmd, '产品定位') or '已确认品牌定位'
    peers=confirmed_candidates(posmd)
    snap = {'contract': IMPORTED, 'selected_category': {'category_id': 'imported', 'category_label': label,
            'category_scope': scope, 'scope': scope, 'segment_id': None, 'segment_label': None,
            'product_boundaries': [], 'scenario_tags': []}, 'selected_candidates': peers,
            'boundary_note': '承接已确认定位与同类池；文章主体由用户选择。P02为开放式多主体推荐，P05点名横评不进入流程。'}
    snap['snapshot_id'] = w.digest(w.dump(snap))
    pos = {'positioning_contract': IMPORTED, 'positioning_snapshot': snap,
           'taxonomy': [{'id': 'primary', 'overall_category': label, 'subcategory': label,
                         'product_use_customer': scope, 'competitors': peers}],
           'question_map': [{'question_id': q['id'], 'category': q['category'], 'branch_ids': ['primary'],
                            'fit': 'direct', 'reason': '承接第一流程问题目录'} for q in questions],
           'origin': 'confirmed_portable_pack', 'imported_positioning_sha256': w.hashfile(d / '定位.md')}
    w.bind(p, 2, None, pos, {'executor': 'confirmed_three_item_pack_import; no AI call'}, {**dependencies(w, p), 'imported_pack/定位.md': w.hashfile(d / '定位.md')})
    w.write(w.stepdir(p, 2) / 'confirmation.json', {'by': 'imported_confirmed_pack',
            'note': '沿用第一流程已确认定位，不重做定位/优势/P0',
            'output_sha256': w.hashfile(w.stepdir(p, 2) / 'result.json')})
    import advantages
    rows = []
    for i, m in enumerate(re.finditer(r'^##[ \t]+([^\n]+)\n(.*?)(?=^##[ \t]+|\Z)', advmd, re.M | re.S), 1):
        body = m[2].strip()
        words = '\n'.join(s for s in body.splitlines() if not s.startswith(('客户价值：', '适用范围：'))).strip()
        rows.append({'id': 'adv_' + str(i).zfill(3), 'title': m[1].strip(), 'suggested_wording': words or m[1].strip(),
                     'customer_value': _line(body, '客户价值'), 'product_scope': _line(body, '适用范围'),
                     'reference_material': '核心差异化优势.md'})
    av = {'contract': advantages.CONTRACT, 'positioning_snapshot_id': snap['snapshot_id'],
          'selected_ids': [x['id'] for x in rows], 'none': not rows, 'selected': rows,
          'usable_claims': [dict(x, allowed_wording=x['suggested_wording'], wording=x['suggested_wording']) for x in rows],
          'by': 'imported_confirmed_pack', 'note': '沿用三项Reference Pack优势', 'confirmed_at': w.now()}
    av['snapshot_id'] = w.digest(w.dump(av))
    w.write(advantages.folder(p) / 'snapshots' / (av['snapshot_id'] + '.json'), av)
    w.write(advantages.folder(p) / 'confirmed.json', av)
    return {'brand': name, 'positioning': 'restored', 'advantages': len(rows), 'questions': len(questions),
            'knowledge_preserved': w.hashfile(ensure_knowledge(w, p)) == w.hashfile(d / '知识库.zip')}


def assert_imported(w, p, value):
    snap = value['positioning_snapshot']
    w.require(value.get('positioning_contract') in (IMPORTED, DIRECT), '定位来源合同不一致')
    w.require(w.digest(w.dump({k: v for k, v in snap.items() if k != 'snapshot_id'})) == snap['snapshot_id'], '定位快照已改变')
    if value.get('positioning_contract') == IMPORTED:
        w.require(w.hashfile(Path(p) / 'imported_pack/定位.md') == value['imported_positioning_sha256'], '导入定位已改变')
    else:
        confirmation = w.read(w.stepdir(p, 2) / 'confirmation.json')
        w.require(confirmation['proposal_sha256'] == w.hashfile(w.stepdir(p, 2) / 'positioning_proposal.json'), '定位选择与草案版本不一致')
