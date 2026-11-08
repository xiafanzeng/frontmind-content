#!/usr/bin/env python3
"""Public CLI for the independent single-brand question-writing package."""
from pathlib import Path
import argparse
import sys
import engine as w
import interaction as ui
import question_updates as qu
import writing_pack as wp
import writing_choices as wc
import reporting


def selected_input(p,args):
    pending=ui.current(w,p)
    qid=getattr(args,'question_id',None) or pending.get('question_id')
    pid=getattr(args,'period_id',None) or pending.get('period_id')
    w.require(qid and pid,'先choose-question或add-question；也可明确question-id和period-id')
    return qid,pid


def main(argv=None):
    ap=argparse.ArgumentParser(description='FrontMind 16.25.1 · 第二包：Kimi Hosted分析＋Gemini问题写作')
    sub=ap.add_subparsers(dest='cmd')
    def command(name,project=True):
        q=sub.add_parser(name)
        if project:q.add_argument('--project',type=Path,required=True)
        q.add_argument('--format',choices=['json','markdown'],default='markdown');return q
    q=command('start',False);q.add_argument('--project',type=Path)
    q=command('import-pack');q.add_argument('--pack',type=Path,required=True);q.add_argument('--brand')
    for name in ['screen','status']:
        q=command(name);q.add_argument('--article')
    q=command('add-question');q.add_argument('--text',required=True);q.add_argument('--date',default='undated');q.add_argument('--category',choices=w.CATEGORIES)
    q=command('choose-question');q.add_argument('--question-id',required=True);q.add_argument('--period-id');q.add_argument('--article')
    command('new-article')
    q=command('show-sources');q.add_argument('--article',required=True)
    q=command('require-media');q.add_argument('--article',required=True);q.add_argument('--source',action='append',required=True);q.add_argument('--note',required=True)
    q=command('choose-writing');q.add_argument('--article',required=True);q.add_argument('--category',choices=w.CATEGORIES,required=True);q.add_argument('--pattern',choices=list(wc.PATTERNS),required=True);q.add_argument('--subject',action='append',default=[]);q.add_argument('--by',choices=['user','prior_authorization'],required=True);q.add_argument('--note',required=True)
    for name in ['attach-answers','skip-answers','attach-sources','select']:
        q=command(name);q.add_argument('--question-id');q.add_argument('--period-id')
        if name in ['attach-answers','attach-sources']:q.add_argument('--file',type=Path,action='append',required=True)
        if name=='attach-answers':q.add_argument('--answer-date')
        if name in ['attach-sources','select']:q.add_argument('--source-date')
        if name=='skip-answers':q.add_argument('--note',required=True)
        if name=='select':q.add_argument('--article',required=True)
    for name in ['prepare','submit']:
        q=command(name);q.add_argument('--article',required=True);q.add_argument('--step',type=int,choices=[5,6,7,8,9,10],required=True);q.add_argument('--phase',choices=['main','refs','writer','review','edit'],default='main')
        if name=='submit':q.add_argument('--file',type=Path,required=True);q.add_argument('--model',required=True)
    q=command('confirm');q.add_argument('--article',required=True);q.add_argument('--step',type=int,choices=[5,7],required=True);q.add_argument('--by',choices=['user','prior_authorization'],required=True);q.add_argument('--note',required=True)
    q=command('acquire');q.add_argument('--article',required=True);q.add_argument('--timeout',type=int,default=25);q.add_argument('--retry-failed',action='store_true')
    q=command('extend-body-pool');q.add_argument('--article',required=True);q.add_argument('--rank',type=int,action='append',required=True);q.add_argument('--note',required=True)
    q=command('supply-text');q.add_argument('--article',required=True);q.add_argument('--rank',type=int,required=True);q.add_argument('--file',type=Path,required=True)
    q=command('run-writer');q.add_argument('--article',required=True);q.add_argument('--step',type=int,choices=[8,9],required=True);q.add_argument('--edit-notes',type=Path);q.add_argument('--retry',action='store_true')
    q=command('run-agent');q.add_argument('--article',required=True);q.add_argument('--step',type=int,choices=[5,6,7,8,9,10,11],required=True);q.add_argument('--phase',choices=['main','refs','review','edit'],default='main');q.add_argument('--wait-seconds',type=int,default=45);q.add_argument('--pages-manifest',type=Path)
    q=command('review');q.add_argument('--article',required=True);q.add_argument('--file',type=Path,required=True);q.add_argument('--model',required=True)
    q=command('export');q.add_argument('--article',required=True);q.add_argument('--with-support',action='store_true',help='兼容旧命令；新版完整交付默认包含标题和媒体建议')
    q=command('visual-qa');q.add_argument('--article',required=True);q.add_argument('--file',type=Path,required=True);q.add_argument('--model',required=True)
    args=ap.parse_args(argv)
    if args.cmd is None:
        print(ui.render(ui.screen(w)));return
    p=getattr(args,'project',None)
    if p:p=p.expanduser().resolve()
    output=None
    if args.cmd=='start':output=ui.screen(w,p)
    elif args.cmd=='import-pack':
        info=wp.import_pack(w,p,args.pack,args.brand);output=ui.screen(w,p);output['import_result']=info
    else:
        w.require(p and (p/'state.json').is_file(),'先导入三项Reference Pack到新项目')
        w.confirmed(p,2);w.advantage_snapshot(p)
        if args.cmd in ['screen','status']:output=ui.screen(w,p,args.article)
        elif args.cmd=='add-question':
            row=qu.register_question(w,p,args.text,args.date,args.category)
            output=ui.choose_question(w,p,row['question_id'],row['period_id']);output['registered_question']=row
        elif args.cmd=='choose-question':output=ui.choose_question(w,p,args.question_id,args.period_id,args.article)
        elif args.cmd=='new-article':w.write(p/'current_task.json',{});output=ui.screen(w,p)
        elif args.cmd=='show-sources':
            reporting.write_sources(w,p,args.article)
            if args.format=='json':output=reporting.source_view(w,p,args.article)
            else:print(reporting.render_sources(reporting.source_view(w,p,args.article)));return
        elif args.cmd=='choose-writing':wc.choose(w,p,args.article,args.category,args.pattern,args.subject,args.by,args.note)
        elif args.cmd=='require-media':w.require_media(p,args.article,args.source,args.note)
        elif args.cmd in ['attach-answers','skip-answers','attach-sources','select']:
            qid,pid=selected_input(p,args)
            if args.cmd=='attach-answers':qu.attach_answers(w,p,qid,pid,args.file,args.answer_date)
            elif args.cmd=='skip-answers':qu.skip_answers(w,p,qid,pid,args.note)
            elif args.cmd=='attach-sources':qu.attach_sources(w,p,qid,pid,args.file,args.source_date)
            else:
                w.select(p,args.article,qid,pid,[],args.source_date)
                w.write(p/'current_task.json',{'question_id':qid,'period_id':pid,'article':args.article})
            output=ui.screen(w,p)
        elif args.cmd=='prepare':output={'prompt_directory':str(w.prepare(p,args.step,args.article,args.phase))}
        elif args.cmd=='submit':w.submit(p,args.step,args.article,args.file,args.model,args.phase)
        elif args.cmd=='confirm':
            w.accepted(p,args.step,args.article);w.require(w.nonempty(args.note),'保存具体确认或已有授权')
            w.write(w.stepdir(p,args.step,args.article)/'confirmation.json',{'at':w.now(),'by':args.by,'note':args.note,'output_sha256':w.hashfile(w.stepdir(p,args.step,args.article)/'result.json')})
        elif args.cmd=='acquire':w.acquire(p,args.article,args.timeout,args.retry_failed)
        elif args.cmd=='extend-body-pool':w.extend_body_pool(p,args.article,args.rank,args.note)
        elif args.cmd=='supply-text':w.supply_text(p,args.article,args.rank,args.file)
        elif args.cmd=='run-writer':w.run_writer(p,args.step,args.article,args.edit_notes,args.retry)
        elif args.cmd=='run-agent':
            run=w.run_agent(p,args.step,args.article,args.phase,args.wait_seconds,args.pages_manifest)
            output=ui.screen(w,p,args.article)
            if run.get('status')=='waiting':output['instruction']='Kimi云端任务正在执行；再次运行同一run-agent命令续读原Session，不重新提交或重复计费。'
            elif run.get('next_action'):output['instruction']=run['next_action']
        elif args.cmd=='review':w.review(p,8,args.article,args.file,args.model)
        elif args.cmd=='export':
            w.export(p,args.article)
        elif args.cmd=='visual-qa':w.visual_qa(p,args.article,args.file,args.model)
        if output is None:output=ui.screen(w,p,getattr(args,'article',None))
    print(w.dump(output) if args.format=='json' or 'instruction' not in output else ui.render(output))


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,FileNotFoundError) as error:
        print('当前输入需要处理：'+str(error),file=sys.stderr);raise SystemExit(2)
