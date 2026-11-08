#!/usr/bin/env python3
"""Application adapter for the two supplied business flows, with durable UI pauses.

job_state.json is an application projection. The supplied engines' original files,
confirmations, requests and responses remain authoritative inside this same Job.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
VERSION = '16.25.1'
PAUSES = {
    'awaiting_positioning_selection': ('选择企业定位', 'choose_positioning'),
    'awaiting_advantages_confirmation': ('确认优势与顺序', 'confirm_advantages'),
    'awaiting_question_selection': ('选择本次优化问题', 'choose_question'),
    'awaiting_question_answers': ('关联完整回答或明确暂无', 'set_question_answers'),
    'awaiting_question_sources': ('上传本题逐条信源', 'provide_question_sources'),
    'awaiting_writing_selection': ('选择问题类型与文章模式', 'choose_writing'),
    'awaiting_article_task_confirmation': ('确认本篇写作任务', 'confirm_article_task'),
    'awaiting_writing_brief_confirmation': ('确认本篇简要约稿', 'confirm_writing_brief'),
    'awaiting_reference_fulltext': ('补充参考文章完整正文', 'provide_reference_fulltext'),
}


def read(file):
    return json.loads(Path(file).read_text(encoding='utf-8'))


def write(file, value):
    file = Path(file)
    file.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    temporary = file.with_name('.' + file.name + '.' + uuid.uuid4().hex)
    temporary.write_text(text, encoding='utf-8', newline='\n')
    temporary.replace(file)


def sha(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


def engine(stage):
    # One invocation owns one phase; never mix the two engines' module globals.
    scripts = ROOT / 'v16_25_1' / stage / 'scripts'
    sys.path.insert(0, str(scripts))
    return importlib.import_module('engine')


def touch(job, state, status, stage, choices=(), body='', pending=None):
    state.update(status=status, stage=stage, updated_at=datetime.now(timezone.utc).isoformat(),
                 pending_action=pending, current_pause=None)
    if status in PAUSES:
        title, _ = PAUSES[status]
        state['current_pause'] = dict(pause_type=status, title=title,
            available_choices=list(choices), revision=state['revision'],
            requires_user_input=True, user_pause=True, must_stop=True)
        review = job / 'reviews' / f'review_{status}_r{state["revision"]}.md'
        write(review, '# ' + title + '\n\n' + body + '\n\n' + '\n'.join('- ' + x for x in choices) + '\n')
        state['current_pause']['review_markdown_path'] = str(review)
    write(job / 'job_state.json', state)
    return state


def pause(job, state, status, choices=(), body=''):
    return touch(job, state, status, status.removeprefix('awaiting_'), choices, body)


def invoke(job, state, name, callback, stage='article_production'):
    touch(job, state, 'running_' + stage, stage, pending={'action': name, 'requires_provider_action': True})
    result = callback()
    return not isinstance(result, dict) or result.get('status') != 'waiting'


def table(rows, keys, labels):
    def cell(value):
        return str(value).replace('|', '／').replace('\n', ' ')
    return '\n'.join(['| ' + ' | '.join(labels) + ' |', '| ' + ' | '.join('---' for _ in keys) + ' |'] +
        ['| ' + ' | '.join(cell(row.get(key, '')) for key in keys) + ' |' for row in rows])


def export_pack(job, state, w, project):
    delivery = job / 'deliverables'
    delivery.mkdir(exist_ok=True)
    previous = state.get('metadata', {}).get('reference_pack_delivery')
    if previous:
        output = Path(previous['portable_zip_path'])
        if not output.is_file() or 'sha256:' + sha(output) != previous['portable_zip_sha256']:
            raise ValueError('REFERENCE_PACK_DELIVERY_CHANGED')
        return output
    version=len(state['metadata'].get('reference_pack_history',[]))+1
    output = delivery / ('Reference_Pack.zip' if version==1 else f'Reference_Pack_{version}.zip')
    if output.exists():
        import zipfile
        with zipfile.ZipFile(output) as archive:
            expected={'Reference_Pack/定位.md':w.wp.positioning_md(w,project).encode('utf-8'),
                'Reference_Pack/核心差异化优势.md':w.wp.advantages_md(w,project).encode('utf-8'),
                'Reference_Pack/知识库.zip':w.wp.ensure_knowledge(w,project).read_bytes()}
            if set(archive.namelist())!=set(expected) or any(archive.read(name)!=data for name,data in expected.items()):
                raise ValueError('REFERENCE_PACK_DELIVERY_CHANGED')
    else:
        w.wp.export(w, project, output)
    digest = sha(output)
    confirmation = read(w.stepdir(project, 2) / 'confirmation.json')
    advantages = read(w.ad.folder(project) / 'confirmed.json')
    state['metadata']['reference_pack_delivery'] = {
        'status': 'created', 'format': 'frontmind-confirmed-three-item-pack/16.25.1',
        'portable_zip_path': str(output), 'portable_zip_sha256': 'sha256:' + digest,
        'brand_name': w.state(project)['brand'], 'pack_id': 'rp_' + digest[:16], 'pack_version': 1,
        'positioning_confirmed': bool(confirmation.get('note')),
        'advantages_confirmed': bool(advantages.get('note')),
        'knowledge_sha256': w.wp.snapshot(w, project)['knowledge_sha256'],
        'readiness': {'positioning_ready': True, 'p0_ready': False},
    }
    write(job / 'job_state.json', state)
    return output


def rendering_tools():
    office_names = ('libreoffice.exe', 'soffice.com', 'soffice.exe') if os.name == 'nt' else ('libreoffice', 'soffice')
    office = next((resolved for name in office_names if (resolved := shutil.which(name))), None)
    poppler = shutil.which('pdftoppm')
    if not office or not poppler:
        raise ValueError('WORD_RENDER_DEPENDENCY_MISSING')
    return office, poppler


def render_words(job, delivery):
    """Actual local rendering; model visual acceptance is a separate engine action."""
    office, poppler = rendering_tools()
    manifest=job/'working/rendered_pages.json'
    if manifest.is_file():
        old=read(manifest).get('documents',[])
        actual={p.name:sha(p) for p in delivery.glob('*.docx')}
        if old and {d['file_name']:d['docx_sha256'] for d in old}==actual:
            if not all(d.get('rendered_pages') and all(Path(p).is_file() for p in d['rendered_pages']) for d in old):
                raise ValueError('WORD_RENDER_CACHE_CHANGED')
            return manifest
    documents = []
    for docx in sorted(delivery.glob('*.docx')):
        # Each actual render gets a fresh directory, so an interrupted attempt
        # cannot contribute stale extra pages to a later visual acceptance.
        output = job / 'working' / 'rendered' / sha(docx) / uuid.uuid4().hex
        output.mkdir(parents=True, exist_ok=True)
        profile = (job / 'working' / 'libreoffice').resolve().as_uri()
        subprocess.run([office, '-env:UserInstallation=' + profile, '--headless',
            '--convert-to', 'pdf', '--outdir', str(output), str(docx)], check=True,
            timeout=180, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pdf = output / (docx.stem + '.pdf')
        if not pdf.is_file():
            raise ValueError('WORD_RENDER_FAILED')
        subprocess.run([poppler, '-png', '-r', '110', str(pdf), str(output / 'page')],
            check=True, timeout=180, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        pages = sorted(output.glob('page-*.png'), key=lambda p: int(p.stem.split('-')[-1]))
        if not pages:
            raise ValueError('WORD_RENDER_EMPTY')
        documents.append({'file_name': docx.name, 'docx_sha256': sha(docx),
                          'rendered_pages': [str(p.resolve()) for p in pages]})
    if not documents:
        raise ValueError('WORD_EXPORT_MISSING')
    manifest = job / 'working' / 'rendered_pages.json'
    write(manifest, {'documents': documents})
    return manifest


def drive_stage1(job, state, w, project):
    proposal = w.stepdir(project, 2) / 'positioning_proposal.json'
    if not w.done(project, 2) and not proposal.is_file():
        if not invoke(job, state, 'positioning', lambda: w.run_agent(project, 'positioning'), 'positioning_market_research'):
            return state
    if not w.done(project, 2):
        rows = read(proposal)['category_options']
        return pause(job, state, 'awaiting_positioning_selection',
            [row['id'] + '｜' + row['label'] for row in rows],
            table(rows, ['id', 'label', 'scope', 'reason'], ['编号', '定位', '用途范围', '依据']))
    if not (w.ad.folder(project) / 'confirmed.json').is_file():
        if not (w.ad.folder(project) / 'draft.json').is_file():
            if not invoke(job, state, 'advantages', lambda: w.run_agent(project, 'advantages'), 'positioning_value_synthesis'):
                return state
        rows = read(w.ad.folder(project) / 'draft.json')['advantages']
        return pause(job, state, 'awaiting_advantages_confirmation',
            [row['id'] + '｜' + row['title'] for row in rows],
            table(rows, ['id', 'title', 'customer_value', 'suggested_wording'], ['编号', '优势', '客户价值', '建议写法']))
    if state['goal'] == 'reference_pack':
        export_pack(job, state, w, project)
        return touch(job, state, 'positioning_ready', 'reference_pack')
    if not w.done(project, 3):
        if not (w.stepdir(project, 3) / 'candidate.json').is_file():
            invoke(job, state, 'p0_draft', lambda: w.run_writer(project, 3), 'p0_production')
        if not invoke(job, state, 'p0_check', lambda: w.run_agent(project, 'p0_check'), 'p0_production'):
            return state
        if not w.done(project, 3):
            _, current = w.candidate(project, 3, None)
            if current.get('edit_count', 0):
                raise ValueError('STYLE_NEW_VERSION_REQUIRED')
            invoke(job, state, 'p0_style_edit', lambda: w.run_writer(project, 3,
                edit_notes=w.stepdir(project, 3) / 'targeted_edit_notes.md'), 'p0_production')
            if not invoke(job, state, 'p0_check', lambda: w.run_agent(project, 'p0_check'), 'p0_production'):
                return state
            if not w.done(project, 3):
                raise ValueError('STYLE_NEW_VERSION_REQUIRED')
    delivery = project / 'deliveries' / 'P0'
    if not delivery.is_dir():
        w.export_p0(project)
    if (delivery / 'VISUAL_QA_PENDING.md').is_file():
        manifest = render_words(job, delivery)
        if not invoke(job, state, 'p0_visual_check', lambda: w.run_agent(project,
                'p0_visual_check', pages_manifest=manifest), 'p0_production'):
            return state
    if (delivery / 'VISUAL_QA_PENDING.md').is_file():
        raise ValueError('WORD_VISUAL_QA_NOT_PASSED')
    state['job_kind'] = 'p0'
    state['metadata']['delivery_directory'] = str(delivery)
    return touch(job, state, 'p0_ready', 'reference_pack')


def task_review(task):
    rows=[{'label':label,'value':task.get(key,'')} for key,label in [('category','问题类型'),('form','文章模式'),('reader','目标读者'),('focus','本篇重点'),('requirements','本篇要求')]]
    rows.append({'label':'本篇主体顺序','value':'、'.join(task.get('candidate_order',[]))})
    return table(rows,['label','value'],['项目','内容'])


def selected_article(w, project):
    pending = read(project / 'current_task.json') if (project / 'current_task.json').exists() else {}
    article = pending.get('article')
    return pending, article if article in w.state(project)['articles'] else None


def drive_stage2(job, state, w, project):
    qu = importlib.import_module('question_updates')
    wc = importlib.import_module('writing_choices')
    pending, article = selected_article(w, project)
    if not pending.get('question_id'):
        rows = qu.available(w, project)
        return pause(job, state, 'awaiting_question_selection',
            [row['id'] + '｜' + row['question_text'] for row in rows], '选择已有问题，或输入一个完整的新问题。')
    question, period = qu.resolve(w, project, pending['question_id'], pending['period_id'])
    roles=job/'inputs/initial_roles.json'
    if roles.is_file():
        original=read(roles)
        if period['answer_status']=='pending' and original.get('answers'):
            qu.attach_answers(w,project,pending['question_id'],pending['period_id'],[Path(p) for p in original['answers']])
        if not period.get('source_files') and original.get('sources'):
            qu.attach_sources(w,project,pending['question_id'],pending['period_id'],[Path(p) for p in original['sources']])
        question,period=qu.resolve(w,project,pending['question_id'],pending['period_id'])
    if period['answer_status'] == 'pending':
        return pause(job, state, 'awaiting_question_answers', body=question['question_text'])
    if not period.get('source_files'):
        return pause(job, state, 'awaiting_question_sources', body=question['question_text'])
    if not article:
        article = 'article1'
        w.select(project, article, pending['question_id'], pending['period_id'], [])
        pending['article'] = article
        write(project / 'current_task.json', pending)
    if not wc.load(w, project, article, required=False):
        report = importlib.import_module('reporting')
        body = report.render_sources(report.source_view(w, project, article))
        peers = wc.candidates(w, project)
        body += '\n\n已确认同类池：\n' + '\n'.join('- ' + x['candidate_id'] + '｜' + x['display_name'] for x in peers)
        return pause(job, state, 'awaiting_writing_selection',
            [key + '｜' + value['form'] for key, value in wc.PATTERNS.items()], body)
    if not w.done(project, 5, article):
        if not invoke(job, state, 'article_task', lambda: w.run_agent(project, 5, article)):
            return state
    if not (w.stepdir(project, 5, article) / 'confirmation.json').is_file():
        return pause(job, state, 'awaiting_article_task_confirmation', body=task_review(w.task(project, article)))
    if not w.done(project, 6, article):
        w.acquire(project, article)
        complete = []
        for row in w.body_pool(project, article):
            try:
                w.fullbody(project, article, row['raw_rank'])
                complete.append(row['raw_rank'])
            except (ValueError, KeyError, FileNotFoundError):
                pass
        if len(complete) < 2:
            return pause(job, state, 'awaiting_reference_fulltext',
                [str(row['raw_rank']) + '｜' + str(row.get('content_title') or row.get('title') or '') for row in w.body_pool(project, article)],
                '尚不足两篇不同的完整参考正文。请补充相应文章原文；题名不能替代全文。')
        if not invoke(job, state, 'article_references', lambda: w.run_agent(project, 6, article)):
            return state
    if not w.done(project, 7, article):
        if not invoke(job, state, 'article_brief', lambda: w.run_agent(project, 7, article)):
            return state
    if not (w.stepdir(project, 7, article) / 'confirmation.json').is_file():
        brief = w.result(project, 7, article)
        references = importlib.import_module('interaction')._references(w, project, article)
        body = str(brief['brief']) + '\n\n' + brief['writing_material_markdown'] + '\n\n参考文章：\n'
        body += '\n'.join('- ' + str(x.get('content_title') or x.get('title') or '') + '：' + str(x.get('reason', '')) for x in references)
        for rank in w.result(project, 6, article)['selected_ranks']:
            row=next(x for x in w.sourcepool(project, article)['articles'] if x['raw_rank']==rank)
            body+='\n\n## 完整构思参考：'+str(row.get('content_title') or row.get('title') or '')+'\n\n'+str(row.get('canonical_url',''))+'\n\n'+w.fullbody(project, article, rank)
        for name,material in brief.get('subject_materials_markdown',{}).items():
            body+='\n\n## '+name+'\n\n'+material
        return pause(job, state, 'awaiting_writing_brief_confirmation', body=body)
    if not w.done(project, 8, article):
        if not (w.stepdir(project, 8, article) / 'candidate.json').exists():
            invoke(job, state, 'article_draft', lambda: w.run_writer(project, 8, article))
        if not invoke(job, state, 'article_style_check', lambda: w.run_agent(project, 8, article)):
            return state
        if not w.done(project, 8, article):
            invoke(job, state, 'article_style_edit', lambda: w.run_writer(project, 8, article,
                edit_notes=w.stepdir(project, 8, article) / 'edit_notes.md'))
            if not invoke(job, state, 'article_style_check', lambda: w.run_agent(project, 8, article)):
                return state
            if not w.done(project, 8, article):
                raise ValueError('STYLE_NEW_VERSION_REQUIRED')
    if not w.done(project, 9, article):
        if not (w.stepdir(project, 9, article) / 'title_references.json').exists():
            if not invoke(job, state, 'title_references', lambda: w.run_agent(project, 9, article, 'refs')):
                return state
        if not (w.stepdir(project, 9, article) / 'writer_result.json').exists():
            invoke(job, state, 'ten_titles', lambda: w.run_writer(project, 9, article))
        if not invoke(job, state, 'title_check', lambda: w.run_agent(project, 9, article, 'edit')):
            return state
        if not w.done(project, 9, article):
            invoke(job, state, 'title_style_edit', lambda: w.run_writer(project, 9, article,
                edit_notes=w.stepdir(project, 9, article) / 'title_edit_notes.md'))
            if not invoke(job, state, 'title_check', lambda: w.run_agent(project, 9, article, 'edit')):
                return state
            if not w.done(project, 9, article):
                raise ValueError('TITLE_NEW_VERSION_REQUIRED')
    if not w.done(project, 10, article):
        if not invoke(job, state, 'media_recommendations', lambda: w.run_agent(project, 10, article)):
            return state
    if not w.done(project, 11, article):
        w.export(project, article)
    delivery = project / 'deliveries' / article
    if (delivery / 'VISUAL_QA_PENDING.md').exists():
        manifest = render_words(job, delivery)
        if not invoke(job, state, 'word_visual_check', lambda: w.run_agent(project, 11, article, pages_manifest=manifest)):
            return state
    if (delivery / 'VISUAL_QA_PENDING.md').exists():
        raise ValueError('WORD_VISUAL_QA_NOT_PASSED')
    state['metadata']['delivery_directory'] = str(delivery)
    return touch(job, state, 'completed', 'E10')


def apply_action(job, state, w, project, action, files):
    kind = action['kind']
    if action.get('revision') != state['revision']:
        raise ValueError('CONTENT_PRODUCTION_CONFIRMATION_CONFLICT')
    if kind == 'resume_current_execution':
        if state['current_pause'] is not None:
            raise ValueError('RESUME_CANNOT_CONFIRM_PAUSE')
        return
    status = state['status']
    expected = PAUSES.get(status, (None, None))[1]
    if kind != expected and not (status in ('awaiting_advantages_confirmation','positioning_ready') and state['phase']=='stage1' and kind=='revise_advantages'):
        raise ValueError('CONTENT_PRODUCTION_CONFIRMATION_CONFLICT')
    note = action.get('note') or '用户具体选择：' + json.dumps(action, ensure_ascii=False)
    if kind == 'choose_positioning':
        importlib.import_module('kb_positioning').confirm(w, project, action['categoryId'], 'user', note)
    elif kind == 'revise_advantages':
        w.ad.revise(w, project, action['instructions'])
        previous=state['metadata'].pop('reference_pack_delivery',None)
        if previous:state['metadata'].setdefault('reference_pack_history',[]).append(previous)
        state['goal']='reference_pack';state['job_kind']='reference_pack'
        state['metadata']['completed_phase_confirmations']=[x for x in state['metadata']['completed_phase_confirmations'] if x!='awaiting_advantages_confirmation']
        return
    elif kind == 'confirm_advantages':
        w.ad.confirm(w, project, action.get('advantageIds', []), action.get('none', False), 'user', note)
    else:
        qu = importlib.import_module('question_updates')
        ui = importlib.import_module('interaction')
        pending, article = selected_article(w, project)
        if kind == 'choose_question':
            value = action['selection'].strip().split('｜', 1)[0]
            rows = qu.available(w, project)
            chosen = next((x for x in rows if value in (x['id'], x['question_text'])), None)
            if chosen is None:
                created = qu.register_question(w, project, action['selection'].strip(), 'undated', None)
                value = created['question_id']
                period = created['period_id']
            else:
                period = action.get('periodId')
            ui.choose_question(w, project, value, period)
        elif kind == 'set_question_answers':
            if action.get('noAnswers') is True:
                if files:
                    raise ValueError('ANSWER_INPUT_CONFLICT')
                qu.skip_answers(w, project, pending['question_id'], pending['period_id'], note)
            else:
                if not files:
                    raise ValueError('COMPLETE_ANSWERS_REQUIRED')
                qu.attach_answers(w, project, pending['question_id'], pending['period_id'], files, action.get('answerDate'))
        elif kind == 'provide_question_sources':
            if not files:
                raise ValueError('QUESTION_SOURCES_REQUIRED')
            qu.attach_sources(w, project, pending['question_id'], pending['period_id'], files, action.get('sourceDate'))
        elif kind == 'choose_writing':
            importlib.import_module('writing_choices').choose(w, project, article,
                action['category'], action['pattern'], action.get('subjects', []), 'user', note)
            if action.get('requiredMedia'):
                w.require_media(project, article, action['requiredMedia'], note)
        elif kind in ('confirm_article_task', 'confirm_writing_brief'):
            step = 5 if kind == 'confirm_article_task' else 7
            w.accepted(project, step, article)
            write(w.stepdir(project, step, article) / 'confirmation.json', {
                'at': w.now(), 'by': 'user', 'note': note,
                'output_sha256': w.hashfile(w.stepdir(project, step, article) / 'result.json')})
        elif kind == 'provide_reference_fulltext':
            if len(files) != 1:
                raise ValueError('ONE_COMPLETE_REFERENCE_REQUIRED')
            w.supply_text(project, article, action['rank'], files[0])
    state['metadata']['completed_phase_confirmations'] = list(dict.fromkeys(
        state['metadata']['completed_phase_confirmations'] + [status]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['preflight', 'start', 'continue', 'status'])
    parser.add_argument('--job-dir', type=Path)
    parser.add_argument('--task', choices=['reference-pack', 'reference-pack-refresh', 'import-reference-pack', 'p0', 'article'])
    parser.add_argument('--brand')
    parser.add_argument('--knowledge', type=Path)
    parser.add_argument('--request-file', type=Path)
    parser.add_argument('--question')
    parser.add_argument('--question-id')
    parser.add_argument('--period-id')
    parser.add_argument('--answer',type=Path,action='append',default=[])
    parser.add_argument('--source',type=Path,action='append',default=[])
    parser.add_argument('--reference-pack', type=Path)
    parser.add_argument('--action-file', type=Path)
    parser.add_argument('--input', type=Path, action='append', default=[])
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'preflight':
        if not os.environ.get('FRONTMIND_CONTENT_PROVIDER_PROXY'):
            raise ValueError('CONTENT_PROVIDER_PROXY_REQUIRED')
        from urllib.request import urlopen
        with urlopen(os.environ['FRONTMIND_CONTENT_PROVIDER_PROXY'].rstrip('/') + '/status', timeout=20) as response:
            providers = json.load(response)['providers']
        if not all(providers.get(key) for key in ('xty', 'kimi')):
            raise ValueError('CONTENT_V16251_PROVIDER_CONFIGURATION_REQUIRED')
        rendering_tools()
        print(json.dumps({'ok': True, 'version': VERSION}))
        return
    if args.job_dir is None:
        raise ValueError('JOB_DIRECTORY_REQUIRED')
    job = args.job_dir.resolve()
    if args.command == 'status':
        print(json.dumps(read(job / 'job_state.json'), ensure_ascii=False))
        return
    if args.command == 'start':
        if (job / 'job_state.json').exists() or not args.task or not args.brand:
            raise ValueError('NEW_JOB_IDENTITY_REQUIRED')
        phase = 'stage2' if args.task == 'article' else 'stage1'
        w = engine(phase)
        project = job / phase
        if args.task == 'reference-pack':
            if not args.knowledge:
                raise ValueError('MARKDOWN_KNOWLEDGE_ZIP_REQUIRED')
            importlib.import_module('workflow').initialize(project, args.brand, args.knowledge)
        else:
            if not args.reference_pack:
                raise ValueError('THREE_ITEM_REFERENCE_PACK_REQUIRED')
            w.wp.import_pack(w, project, args.reference_pack, args.brand)
        if phase=='stage2':
            qu=importlib.import_module('question_updates');ui=importlib.import_module('interaction')
            if args.question_id or args.question:
                known=next((q for q in qu.available(w,project) if q['id']==args.question_id or q['question_text']==args.question),None)
                if known is None:
                    if args.question_id:raise ValueError('QUESTION_NOT_IN_CONFIRMED_PACK')
                    created=qu.register_question(w,project,args.question)
                    ui.choose_question(w,project,created['question_id'],created['period_id'])
                else:ui.choose_question(w,project,known['id'],args.period_id)
            if args.answer or args.source:
                write(job/'inputs/initial_roles.json',{'answers':[str(p.resolve()) for p in args.answer],'sources':[str(p.resolve()) for p in args.source]})
        state = dict(schema_version=VERSION, artifact_type='frontmind_content_job_state', workflow_version=VERSION,
            job_id=job.name, job_kind='article' if phase == 'stage2' else 'p0' if args.task == 'p0' else 'reference_pack',
            brand=args.brand, phase=phase, goal='article' if phase == 'stage2' else 'p0' if args.task == 'p0' else 'reference_pack',
            revision=1, updated_at=datetime.now(timezone.utc).isoformat(), stage='intake', status='running_reference_material_intake',
            current_pause=None, pending_action=None, flags={}, decisions={}, p0_route='create' if args.task == 'p0' else None,
            metadata={'completed_phase_confirmations': [], 'workflow_contract': 'frontmind-two-stage/16.25.1'})
        if args.request_file:
            request=args.request_file.read_text(encoding='utf-8')
            write(project/'inputs/initial_request.txt',request)
            write(job/'inputs/request.txt',request)
        if args.task=='reference-pack-refresh':
            if not args.request_file or not args.request_file.read_text(encoding='utf-8').strip():raise ValueError('ADVANTAGE_REVISION_REQUEST_REQUIRED')
            w.ad.revise(w,project,args.request_file.read_text(encoding='utf-8'))
        write(job / 'job_state.json', state)
    else:
        state = read(job / 'job_state.json')
        if state.get('workflow_version') != VERSION:
            raise ValueError('FROZEN_WORKFLOW_VERSION_CONFLICT')
        if not args.action_file and (state.get('current_pause') or state['status'] in ('positioning_ready','p0_ready','completed')):
            print(json.dumps(state,ensure_ascii=False));return
        w = engine(state['phase'])
        project = job / state['phase']
        if args.action_file:
            action = read(args.action_file)
            if action.get('kind')=='resume_current_execution' and action.get('revision')==state['revision'] and (state.get('current_pause') or state['status'] in ('positioning_ready','p0_ready','completed')):
                print(json.dumps(state,ensure_ascii=False));return
            apply_action(job, state, w, project, action, args.input)
            state['revision'] += 1
    try:
        result = (drive_stage1 if state['phase'] == 'stage1' else drive_stage2)(job, state, w, project)
    except Exception as exc:
        # Provider exceptions and user materials can contain private text. Keep the
        # concrete class and a controlled application code in the public projection.
        code = str(exc) if str(exc) in {'STYLE_NEW_VERSION_REQUIRED', 'TITLE_NEW_VERSION_REQUIRED',
            'WORD_RENDER_DEPENDENCY_MISSING', 'WORD_RENDER_FAILED', 'WORD_VISUAL_QA_NOT_PASSED'} else 'WORKFLOW_ACTION_FAILED'
        state['pending_action'] = {'action': state.get('pending_action', {}).get('action', 'workflow') if state.get('pending_action') else 'workflow',
            'requires_provider_action': True, 'error': {'code': code}}
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        write(job / 'job_state.json', state)
        raise ValueError(code) from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr)
        raise SystemExit(1)
