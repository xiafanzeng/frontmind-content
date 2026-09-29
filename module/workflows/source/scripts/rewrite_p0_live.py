#!/usr/bin/env python3
"""Explicitly authorized, resumable source-article rewrite using real providers.

This is a scoped rewrite entry, not a fabricated Reference Pack/market research
history. It shares production prompts, runtimes and validators with the normal
P0 route. No article text is generated locally or by the launcher AI.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts import frontmind_workflow as wf
from shared import model_runtime as rt, brand_stage as bs, editorial_contracts as ec, writing_context as wc, title_publication as tp, natural_editor as ne


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):rt._atomic(path,value)


def prepare(source,brand,run_dir,requirements):
    source=Path(source).expanduser()
    run_dir=Path(run_dir).expanduser()
    if source.is_symlink() or run_dir.is_symlink():
        raise ValueError('输入或任务目录不能是符号链接')
    source=source.resolve()
    if source.is_symlink() or not source.is_file() or source.suffix.lower() not in {'.md','.txt','.docx'}:
        raise ValueError('输入必须是本地普通MD/TXT/DOCX文件')
    run_dir=run_dir.resolve()
    secrets=[rt.load_configuration(ROOT,p,required=False).get('api_key','') for p in ('xty','zhipu','deepseek')]
    if source.suffix.lower()=='.docx':
        from docx import Document
        source_text='\n'.join(x.text for x in Document(source).paragraphs)
    else:
        source_text=source.read_text(encoding='utf-8')
    if any(key and (key in source_text or key in requirements or key in brand) for key in secrets):
        raise rt.ProviderActionError('credential_in_source','输入正文包含凭据，未复制或发送。')
    source_hash=digest(source)
    job_file=run_dir/'job_state.json'
    request={'schema':'frontmind-scoped-rewrite/4.12.5','source_sha256':source_hash,'brand':brand,'requirements':requirements,
             'authorization':'User explicitly delegates this source-article rewrite, including fact selection and three remote writing passes. No past blueprint approval is inferred.',
             'scope':'source_article_revision_not_new_market_research','reference_policy':'third_pass_only'}
    if job_file.exists():
        if json.loads((run_dir/'rewrite_request.json').read_text())!=request:
            raise ValueError('该任务的来源或要求不同，请用新目录；不覆盖旧生成记录')
        return run_dir
    if run_dir.exists() and any(run_dir.iterdir()):raise ValueError('新任务需要空目录')
    run_dir.mkdir(parents=True,exist_ok=True)
    (run_dir/'materials').mkdir()
    target=run_dir/'materials'/('source_article'+source.suffix.lower())
    shutil.copyfile(source,target)
    state=wf.make_state('rewrite_'+uuid.uuid4().hex[:12],'p0')
    state.update(status='running_p0_blueprint',stage='source_article_rewrite',reference_pack={'brand':brand,'scope':'provided_article_only'},p0_route='scoped_rewrite')
    state['metadata'].update(scoped_source_rewrite=True,source_sha256=source_hash)
    state['decisions']['response_brief']=requirements
    state['flags'].update(offline_fixture=False)
    save(job_file,state);save(run_dir/'rewrite_request.json',request)
    return run_dir


def run(source,brand,run_dir,requirements,*,retry=False,rework=None):
    root=prepare(source,brand,run_dir,requirements)
    results=root/'production';results.mkdir(exist_ok=True)
    natural=ne.enabled(wf.load_state(root))
    actions=[('p0_blueprint',lambda:wc.prompt_blueprint(wf,root,p0=True) if natural else bs.blueprint_prompt(wf,root),root/'blueprints/p0_blueprint.json'),
             ('p0_draft',lambda:wc.prompt_article(wf,root,p0=True) if natural else bs.draft_prompt(wf,root),results/'p0_draft.json'),
             ('p0_edit',lambda:wc.prompt_edit(wf,root,p0=True) if natural else bs.edit_prompt(wf,root),results/'p0_edited.json'),
             ('p0_style',lambda:wc.prompt_p0_style(wf,root) if natural else bs.style_prompt(wf,root),results/'p0_styled.json'),
             ('p0_finalize',lambda:wc.prompt_finalize(wf,root,p0=True) if natural else bs.finalize_prompt(wf,root),results/('p0_editorial_review.json' if natural else 'p0_finalized.json')),
             *([('p0_repair',lambda:wc.prompt_repair(wf,root,p0=True),results/'p0_repaired.json')] if natural else []),
             ('p0_titles',lambda:wc.prompt_titles(wf,root,p0=True),results/'p0_titles.json'),
             ('p0_title_review',lambda:wc.prompt_title_review(wf,root,p0=True),results/'p0_title_review.json')]
    report={'schema':'frontmind-scoped-rewrite-result/4.12.5','status':'running','scope':'source_article_revision_not_new_market_research',
            'source_sha256':digest(source),'started_at':rt.utcnow(),'actions':[],'article_generated':False,
            'entry_ai_authored_body':False,'visual_qa':'not_run'}
    # Always enter runtime even on resume: it validates original API evidence,
    # fingerprints and current inputs before reusing a successful response.
    try:
        if rework:
            if retry:
                raise ValueError('返工与重试不能同时提交；返工会修改实际输入并重做指定阶段')
            from shared import p0_rework
            p0_rework.begin(wf, root, rework)
        for action,builder,destination in actions:
            if action=='p0_repair' and not ne.validate_review(wf.read_json(results/'p0_editorial_review.json'))['needs_revision']:
                ne.select_final(wf,root,p0=True)
                continue
            report['current_action']=action;save(root/'rewrite_status.json',report)
            prompt=builder()
            known_keys=[rt.load_configuration(ROOT,p,required=False).get('api_key','') for p in ('xty','zhipu','deepseek')]
            if any(k and k in prompt for k in known_keys):
                raise rt.ProviderActionError('credential_in_prompt','组装输入包含凭据，未保存或发送。')
            save(root/'requests'/f'{action}.json',{'action':action,'profile':rt.profile_for_request(action,prompt),'prompt':prompt})
            value=rt.run_action(ROOT,root,action,prompt,lambda v: wf.validate_action_result(root,action,v),retry=retry)
            if action=='p0_blueprint':
                wc.validate_writing_material(value)
                # No invented confirmation: this explicit entry is delegated rewrite.
            if value.get('requires_blueprint_reconfirmation') or value.get('edit_status')=='requires_blueprint_reconfirmation':
                raise ValueError('模型发现需要改变业务决定：'+value.get('reconfirmation_reason',''))
            if action=='p0_finalize' and not natural and value.get('outcome')!='accepted':
                save(root/'reviews/rejected_final.json',value)
                if value.get('outcome')=='incomplete':
                    state=wf.load_state(root)
                    state.update(status='running_p0_production', stage='source_article_rewrite',
                                 pending_action={'action':'p0_finalize','error':{'code':'host_incomplete','message':value['reason']}})
                    state['flags']['p0_production_step']='finalize'
                    wf.save_state(root,state)
                raise ValueError('终审未通过：'+value.get('reason',''))
            if action=='p0_title_review' and value.get('outcome')=='incomplete':
                save(root/'reviews/rejected_titles.json',value)
                raise ValueError('标题编辑未通过：'+value.get('reason',''))
            save(destination,value)
            if action=='p0_repair':
                ne.select_final(wf,root,p0=True)
            report['actions'].append({'action':action,'result_sha256':digest(destination),'profile':rt.profile_for_request(action,prompt)})
        final=json.loads((results/'p0_finalized.json').read_text())['article_markdown']
        third=json.loads((results/'p0_styled.json').read_text())['article_markdown']
        if natural:
            ne.validate_selected(wf,root,third,p0=True)
        elif final!=third:
            raise ValueError('终稿不是DeepSeek第三遍原文，禁止导出')
        # Export only the selected actual author text; formatting never rewrites.
        output=root/'deliverables';output.mkdir(exist_ok=True)
        # Body-only projection removes exactly the first H1, never rewrites prose.
        import re
        body=re.sub(r'(?m)^#[ \t]+[^\r\n]*(?:\r\n|\n|\r|$)','',final,count=1)
        (output/'article.md').write_text(body,encoding='utf-8')
        wf.write_docx(body,output/'article.docx',brand)
        (output/'article.html').write_text(wf.markdown_to_html(body,brand),encoding='utf-8')
        titles=json.loads((results/'p0_title_review.json').read_text())
        save(output/'titles.json',titles)
        (output/'titles.md').write_text('\n\n'.join(f'{i}. {r["title"]}\n{r["angle"]}' for i,r in enumerate(titles['candidates'],1))+'\n',encoding='utf-8')
        report.update(status='generated_awaiting_visual_review',article_generated=True,body_author='DeepSeek Pro',host='XTY' if natural else 'Zhipu Managed Agents',
                      internal_final_sha256=hashlib.sha256(final.encode()).hexdigest(),body_sha256=hashlib.sha256(body.encode()).hexdigest(),title_count=20,docx_sha256=digest(output/'article.docx'),
                      output_docx=str(output/'article.docx'),finished_at=rt.utcnow())
        # Word is not called visually accepted merely because export succeeded.
        save(root/'rewrite_status.json',report)
        state=wf.load_state(root);state['pending_action']=None;wf.save_state(root,state)
        return report
    except Exception as e:
        report.update(status='stopped',error_code=getattr(e,'code',type(e).__name__),message=rt.redact(str(e)),finished_at=rt.utcnow())
        save(root/'rewrite_status.json',report)
        return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--live',action='store_true',help='authorize real XTY and DeepSeek API execution')
    p.add_argument('--source',type=Path,default=ROOT/'customer_inputs/yihang/source_v4.12.2.md')
    p.add_argument('--brand',default='一航软件测评中心')
    p.add_argument('--run-dir',type=Path,default=ROOT/'runs/yihang_v4.12.8')
    p.add_argument('--requirements-file',type=Path,default=ROOT/'customer_inputs/yihang/rewrite_requirements.md')
    p.add_argument('--retry-current-action',action='store_true',help='explicit retry; successful stages must still revalidate their recorded API evidence')
    p.add_argument('--rework',choices=['style','edit'],help='历史合同的显式返工入口；新版正文自动按编辑意见返工一次后输出')
    a=p.parse_args(argv)
    if a.rework and a.retry_current_action:p.error('--rework与--retry-current-action不能同时提交')
    if not a.live:p.error('需要--live显式执行真实API；此入口没有离线成稿或当前会话代写方式')
    try:
        with wf.job_execution_lock(a.run_dir):
            result=run(a.source,a.brand,a.run_dir,a.requirements_file.read_text(encoding='utf-8'),retry=a.retry_current_action,rework=a.rework)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if result['article_generated'] else 2
    except Exception as e:
        print(json.dumps({'status':'stopped','error_code':getattr(e,'code',type(e).__name__),'message':str(e),'article_generated':False},ensure_ascii=False,indent=2))
        return 2

if __name__=='__main__':raise SystemExit(main())
