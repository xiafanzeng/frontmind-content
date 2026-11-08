"""Explicit business choices; a question number never chooses an article pattern."""
from pathlib import Path

PATTERNS = {
    'P01': {'form': '单品牌推荐', 'label': '单主体品类或服务推荐', 'categories': ['行业排名']},
    'P02': {'form': '多品牌推荐', 'label': '开放式多主体推荐', 'categories': ['行业排名']},
    'P03': {'form': '场景说明', 'label': '产品或服务场景解决方案', 'categories': ['产品场景']},
    'P04': {'form': '事件新闻', 'label': '有实际事件材料的新闻稿', 'categories': ['产品场景', '美誉舆情']},
    'P06': {'form': '评价回应', 'label': '单主体口碑与可信度评估', 'categories': ['美誉舆情']},
}


def candidates(w, p):
    return w.accepted(p, 2)['positioning_snapshot'].get('selected_candidates', [])


def load(w, p, a, required=False):
    file = w.scope(p, a) / 'writing_choice.json'
    if not file.exists():
        w.require(not required, '先展示信源表与类型菜单，再由用户明确选择问题类型和文章模式；问题编号或笼统确认不能代替类型选择')
        return None
    value = w.read(file)
    w.require(value['source_pool_sha256'] == w.hashfile(w.scope(p, a) / 'source_pool.json'), '信源版本与写作选择不一致')
    w.require(value['selected_question_sha256'] == w.hashfile(w.stepdir(p, 4, a) / 'result.json'), '问题期次与写作选择不一致')
    return value


def choose(w, p, a, category, pattern, subjects, by, note):
    w.selected(p, a)
    w.require(not w.done(p, 5, a), '本篇任务已冻结；调整类型请另建文章，保留原稿和调用记录')
    w.require(category in w.CATEGORIES and pattern in PATTERNS, '请选择三类问题及P01/P02/P03/P04/P06；P05点名对比已移除')
    w.require(by in ('user', 'prior_authorization') and w.nonempty(note), '需记录用户具体类型选择或此前同范围明确选择原话')
    number=str(list(PATTERNS).index(pattern)+1)
    w.require(pattern in note or PATTERNS[pattern]['form'] in note or (by=='user' and note.strip()==number),
              '选择记录须指向具体文章选项；问题编号或笼统“确认”不能当作已有文体选择。可保留原话并注明它对应当前菜单的哪一项')
    brand = w.state(p)['brand']
    subjects = list(subjects or [])
    if subjects and subjects[0] == brand:
        subjects = subjects[1:]
    w.require(len(subjects) == len(set(subjects)) and brand not in subjects, '推荐主体不能重复')
    selected = []
    if pattern == 'P02':
        w.require(subjects, 'P02还需从已确认同类池选择至少一个其他主体；不默认全选或固定数量')
        for name in subjects:
            matches = [x for x in candidates(w, p) if name in (x['candidate_id'], x['display_name'], x.get('product_name'))]
            w.require(len(matches) == 1, '请选择定位.md已确认同类对象的名称或ID：' + name)
            selected.append(matches[0])
    else:
        w.require(not subjects, '本模式只以本品牌为主体；多个推荐主体请明确选择P02')
    value = {'category': category, 'pattern_id': pattern, 'form': PATTERNS[pattern]['form'],
             'candidate_order': [brand] + [x['display_name'] for x in selected],
             'candidate_ids': [x['candidate_id'] for x in selected], 'by': by, 'note': note,
             'at': w.now(), 'source_pool_sha256': w.hashfile(w.scope(p, a) / 'source_pool.json'),
             'selected_question_sha256': w.hashfile(w.stepdir(p, 4, a) / 'result.json')}
    w.write(w.scope(p, a) / 'writing_choice.json', value)
    return value


def validate_task(w, p, a, value):
    choice = load(w, p, a, required=True)
    for key in ('category', 'form', 'candidate_order', 'candidate_ids'):
        w.require(value.get(key, [] if key == 'candidate_ids' else None) == choice[key], '本篇任务不得改写用户的类型或主体选择：' + key)
    if value.get('pattern_id'):
        w.require(value['pattern_id'] == choice['pattern_id'], '文章模式与用户选择不一致')
