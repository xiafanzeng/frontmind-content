#!/usr/bin/env python3
"""Flow 1 only: complete knowledge -> positioning -> advantages -> Pack and P0."""
from pathlib import Path
import argparse
import json
import shutil
import sys
import engine as w
import kb_positioning as kp

VERSION = '16.25.1'


def emit(value, output_format='markdown'):
    if output_format == 'json':
        print(w.dump(value)); return
    if not isinstance(value, dict):
        print(value if isinstance(value, str) else '\n'.join(str(x.get('statement', x.get('title', ''))) for x in value)); return
    print('第一流程 · 定位与差异化优势及P0\n')
    if value.get('brand'): print('企业：' + value['brand'] + '\n')
    states = {'awaiting_knowledge': '等待知识库', 'ready_positioning': '可整理定位',
              'awaiting_positioning_choice': 'A 等待选择定位', 'ready_advantages': '可整理优势',
              'awaiting_advantage_confirmation': 'C 等待确认优势', 'ready_p0': '可写P0并导出资料包',
              'awaiting_p0_review': '待文风核对或原文字问题确认', 'p0_needs_targeted_edit':'待一次文风轻润色',
              'p0_requires_resolution':'剩余文字问题待用户新要求', 'waiting':'Kimi仍在执行',
              'awaiting_visual_qa': '待自动排版检查', 'complete': '第一流程完成'}
    if value.get('status'): print('当前状态：' + states.get(value['status'], value['status']) + '\n')
    if value.get('instruction'): print(value['instruction'] + '\n')
    agent=value.get('agent_run',value if value.get('session_id') else {})
    if agent.get('session_id'):
        print('分析执行：kimi-k3.1-pro / high；Session：'+str(agent['session_id'])+'\n')
    if agent.get('edit_notes_file'):print('定向修改清单：'+str(agent['edit_notes_file'])+'\n')
    def cell(x): return str(x).replace('|', '／').replace('\n', ' ')
    if value.get('category_options'):
        print('| 编号 | 定位建议 | 用途范围 | 依据 |\n|---|---|---|---|')
        for row in value['category_options']:
            print('| ' + ' | '.join(cell(row.get(k, '')) for k in ['id', 'label', 'scope', 'reason']) + ' |')
        print()
    if value.get('advantages'):
        print('| 编号 | 优势 | 客户价值 | 建议表述 |\n|---|---|---|---|')
        for row in value['advantages']:
            print('| ' + ' | '.join(cell(row.get(k, '')) for k in ['id', 'title', 'customer_value', 'suggested_wording']) + ' |')
        print()
    if value.get('questions'):
        print('| 编号 | 优化问题 | 类型 |\n|---|---|---|')
        for row in value['questions']:
            print('| ' + ' | '.join(cell(row.get(k, '')) for k in ['id', 'question_text', 'category']) + ' |')
        print()
    if value.get('question_text'): print('已登记问题：' + value['question_text'] + '\n')
    if value.get('next'):
        labels = {'run-agent --action positioning': 'Kimi整理定位建议', 'confirm-positioning': '选择定位编号',
                  'run-agent --action advantages': 'Kimi整理差异化优势', 'add-advantage': '补充优势',
                  'revise-advantages': '修改优势草案', 'confirm-advantages': '确认优势与顺序',
                  'export-pack': '导出三项Reference Pack', 'prepare --step 3': '准备P0写作Prompt',
                  'run-writer --step 3': 'Gemini写作P0', 'run-agent --action p0_check': 'Kimi核对当前P0文风', 'visual-qa': '完成Word逐页检查'}
        print('下一步：' + '；'.join(labels.get(x, x) for x in value['next']))


def initialize(project, brand, knowledge, aliases=()):
    p = Path(project).resolve()
    w.require(not (p / 'state.json').exists(), '项目已存在，请使用新目录保留旧版本')
    w.wp._knowledge_members(Path(knowledge).expanduser().resolve())
    p.mkdir(parents=True, exist_ok=True)
    w.save(p, {'schema': 'frontmind/16.25.1', 'flow': 'positioning_and_p0', 'brand': brand,
               'aliases': list(aliases), 'articles': {}, 'created_at': w.now(),
               'model_policy': {'research':'kimi-k3.1-pro','research_transport':'kimi_hosted_agents_rest',
                                'session_scope':'one_per_project','writer':'gemini-4-argon',
                                'writer_provider':'xty_http','effort':'high','max_targeted_edits':1}})
    w.wp.attach_knowledge(w, p, knowledge)
    w.write(p / 'inputs/all_answers.json', [])
    w.write(p / 'inputs/question_catalog.json', [])
    w.wp.bind_knowledge_facts(w, p)
    return screen(p)


def add_question(p, text, category='产品场景'):
    w.require(w.nonempty(text) and '\n' not in text, '问题须为单行完整文字')
    rows = w.catalog(p)
    w.require(not any(q['question_text'] == text for q in rows), '问题已在目录中')
    rows.append({'id': 'q' + str(len(rows) + 1).zfill(6), 'question_text': text,
                 'category': category, 'origin': 'user_entered_question',
                 'periods': [{'id': 'p000001', 'date': 'undated', 'answer_count': 0}]})
    w.write(Path(p) / 'inputs/question_catalog.json', rows)
    return rows[-1]


def screen(project=None):
    if project is None or not (Path(project) / 'state.json').exists():
        return {'flow': 1, 'version': VERSION, 'status': 'awaiting_knowledge',
                'requires_user_input': True, 'must_stop': True,
                'instruction': '提供企业名称与完整Markdown知识库ZIP；进入定位与差异化优势流程。',
                'inputs': ['企业名称', '知识库.zip'], 'outputs': ['三项Reference Pack', 'P0正文TXT、Word及HTML'],
                'next': ['init --project 新目录 --brand 企业名称 --knowledge 知识库.zip']}
    p = Path(project)
    value = {'flow': 1, 'version': VERSION, 'brand': w.state(p)['brand'],
             'knowledge_version': w.wp.snapshot(w, p)['knowledge_sha256'], 'questions': w.catalog(p)}
    proposal = w.stepdir(p, 2) / 'positioning_proposal.json'
    if not proposal.exists():
        value.update(status='ready_positioning', instruction='Kimi Hosted Agent读取完整知识库，提出定位及优化问题目录。', next=['run-agent --action positioning'])
    elif not w.done(p, 2):
        value.update(status='awaiting_positioning_choice', instruction='A：请选择当前类别，可修改建议；记录具体选择后继续。',
                     category_options=w.read(proposal)['category_options'], next=['confirm-positioning'])
    elif not (w.ad.folder(p) / 'confirmed.json').exists():
        draft = w.ad.folder(p) / 'draft.json'
        if draft.exists():
            value.update(status='awaiting_advantage_confirmation', instruction='C：确认、排序、增删或补充优势。',
                         advantages=w.read(draft)['advantages'], next=['add-advantage', 'revise-advantages', 'confirm-advantages'])
        else:
            value.update(status='ready_advantages', instruction='Kimi直接阅读完整知识库和确认定位，整理优势与客户价值。', next=['run-agent --action advantages'])
    elif not w.done(p, 3):
        candidate = w.stepdir(p, 3) / 'candidate.json'
        value.update(status='awaiting_p0_review' if candidate.exists() else 'ready_p0',
                     instruction='已有确认定位和优势，P0按优势实际数量与顺序独立成节；Reference Pack现在即可导出。',
                     next=['export-pack', 'run-agent --action p0_check'] if candidate.exists() else ['export-pack','run-writer --step 3'])
        review_file=w.stepdir(p,3)/'latest_review.json'
        if candidate.exists() and review_file.exists():
            r=w.read(review_file);needs=not r['prose_review']['pass']
            if needs and not w.read(candidate).get('edit_count',0):
                value.update(status='p0_needs_targeted_edit',instruction='文风核对已列具体文字问题；用targeted_edit_notes.md做一次Gemini轻润色，不核验事实或重发素材与例文。',next=['run-writer --step 3 --edit-notes '+str(w.stepdir(p,3)/'targeted_edit_notes.md')])
            elif needs:
                value.update(status='p0_requires_resolution',instruction='一次轻润色后仍有文字问题。保留现稿及记录，按用户新要求处理，不自动继续文风轮。',next=[])
    else:
        pending = p / 'deliveries/P0/VISUAL_QA_PENDING.md'
        value.update(status='awaiting_visual_qa' if pending.exists() else 'complete',
                     instruction='Word渲染逐页检查后完成第一流程；三项Pack中的问题目录交给第二流程。',
                     next=['run-agent --action p0_visual_check --pages-manifest 渲染清单.json'] if pending.exists() else ['export-pack'])
    value['requires_user_input'] = value['status'] in ('awaiting_positioning_choice', 'awaiting_advantage_confirmation','p0_requires_resolution')
    value['must_stop'] = value['requires_user_input']
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description='FrontMind流程1：知识库、定位、优势、三项Reference Pack与P0')
    sub = parser.add_subparsers(dest='command')
    p = sub.add_parser('start'); p.add_argument('--project', type=Path)
    p = sub.add_parser('screen'); p.add_argument('--project', type=Path, required=True)
    p = sub.add_parser('init'); p.add_argument('--project', type=Path, required=True); p.add_argument('--brand', required=True)
    p.add_argument('--knowledge', required=True); p.add_argument('--alias', action='append', default=[])
    def cmd(name):
        q = sub.add_parser(name); q.add_argument('--project', type=Path, required=True); return q
    cmd('prepare-positioning')
    p=cmd('run-agent');p.add_argument('--action',choices=['positioning','advantages','p0_check','p0_visual_check'],required=True)
    p.add_argument('--wait-seconds',type=float,default=45)
    p.add_argument('--pages-manifest')
    p=cmd('confirmed-peers');p.add_argument('--file',required=True)
    p.add_argument('--by',choices=['user','explicit_prior_choice'],required=True);p.add_argument('--note',required=True)
    p = cmd('submit-positioning'); p.add_argument('--file', required=True); p.add_argument('--model', required=True)
    p = cmd('confirm-positioning'); p.add_argument('--category-id', required=True)
    p.add_argument('--by', choices=['user', 'explicit_prior_choice'], required=True); p.add_argument('--note', required=True)
    p = cmd('add-question'); p.add_argument('--question', required=True); p.add_argument('--category', choices=w.CATEGORIES, default='产品场景')
    cmd('prepare-advantages')
    p = cmd('submit-advantages'); p.add_argument('--file', required=True); p.add_argument('--model', required=True)
    p = cmd('add-advantage'); p.add_argument('--text', action='append', required=True); p.add_argument('--note', default='用户补充')
    p = cmd('revise-advantages'); p.add_argument('--note', required=True)
    p = cmd('confirm-advantages'); p.add_argument('--id', action='append', default=[]); p.add_argument('--none', action='store_true')
    p.add_argument('--by', choices=['user', 'explicit_prior_choice'], required=True); p.add_argument('--note', required=True)
    p = cmd('export-pack'); p.add_argument('--output', required=True)
    for name in ['prepare', 'run-writer', 'review']:
        p = cmd(name); p.add_argument('--step', type=int, choices=[3], default=3)
        if name == 'prepare': p.add_argument('--phase', choices=['writer', 'review'], default='writer')
        elif name == 'run-writer': p.add_argument('--edit-notes'); p.add_argument('--retry', action='store_true')
        else: p.add_argument('--file', required=True); p.add_argument('--model', required=True)
    p = cmd('visual-qa'); p.add_argument('--file', required=True); p.add_argument('--model', required=True)
    for command_parser in sub.choices.values():
        command_parser.add_argument('--format', choices=['markdown', 'json'], default='markdown')
    args = parser.parse_args(argv)
    command = args.command
    if command is None or command == 'start':
        result = screen(getattr(args, 'project', None))
    elif command == 'init':
        result = initialize(args.project, args.brand, args.knowledge, args.alias)
    elif command == 'screen':
        result = screen(args.project)
    else:
        p = args.project.expanduser().resolve()
        if command == 'run-agent':
            agent=w.run_agent(p,args.action,args.wait_seconds,args.pages_manifest)
            result={**screen(p),'agent_run':agent} if agent['status']=='succeeded' else agent
        elif command == 'confirmed-peers': kp.confirmed_peers(w,p,args.file,args.by,args.note);result=screen(p)
        elif command == 'prepare-positioning': result = str(kp.prepare(w, p))
        elif command == 'submit-positioning': kp.submit(w, p, args.file, args.model); result = screen(p)
        elif command == 'confirm-positioning': kp.confirm(w, p, args.category_id, args.by, args.note); result = screen(p)
        elif command == 'add-question': result = add_question(p, args.question, args.category)
        elif command == 'prepare-advantages': result = str(w.ad.prepare(w, p))
        elif command == 'submit-advantages': w.ad.submit(w, p, args.file, args.model); result = screen(p)
        elif command == 'add-advantage':
            result = w.ad.register_statements(w, p, [{'id': 'user_' + w.uuid.uuid4().hex[:10], 'statement': s} for s in args.text], args.note)
        elif command == 'revise-advantages': w.ad.revise(w, p, args.note); result = screen(p)
        elif command == 'confirm-advantages': w.ad.confirm(w, p, args.id, args.none, args.by, args.note); result = screen(p)
        elif command == 'export-pack': result = str(w.export_pack(p, args.output))
        elif command == 'prepare': result = str(w.prepare(p, 3, None, args.phase))
        elif command == 'run-writer': w.run_writer(p, 3, None, args.edit_notes, args.retry); result = screen(p)
        elif command == 'review':
            w.review(p, 3, None, args.file, args.model)
            if w.done(p, 3): shutil.copy2(w.stepdir(p, 3) / 'final.md', p / 'deliveries/P0/P0.txt')
            result = screen(p)
        elif command == 'visual-qa': w.visual_qa(p, None, args.file, args.model); result = screen(p)
        else: raise ValueError('此命令不属于第一流程')
    emit(result, getattr(args, 'format', 'markdown'))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, FileNotFoundError, KeyError) as exc:
        print('需要补充或修正输入：' + str(exc), file=sys.stderr)
        sys.exit(2)
