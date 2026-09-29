#!/usr/bin/env python3
"""Inspect/backup local Job sessions, or explicitly reconcile an uncertain tool.
No API calls; never archive/delete remote resources. RunState stays server-side.
"""
from __future__ import annotations
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from shared import model_runtime as rt,agents_runtime as ar
from scripts.frontmind_workflow import job_execution_lock

READ_TOOLS={'read_material','list_materials','search_materials','extract_document','web_search','web_read','ocr'}

def inspect_job(job):
    actions=[]
    for p in sorted((job/'provider').glob('*/runtime/latest.json')):
        action=p.parent.parent.name;r=rt.action_record(job,action)
        actions.append({k:r.get(k) for k in ('action','status','attempt_id','session_id','sdk_version','started_at','resumed_at','model_calls','tool_calls','error')})
        actions[-1]['wire_api']=r.get('requested_configuration',{}).get('wire_api')
    state=rt._read_json(job/'job_state.json',{})
    return {'job_dir':str(job),'business_status':state.get('status'),'revision':state.get('revision'),'actions':actions,
            'automatic_expiry':False,'remote_resource_mutation':False,'note':'日期旧不会自动清理；续跑需要完整Job及兼容SDK、工具和模型配置。'}


def reconcile(job,action,call_id,reason,ack):
    if not ack or not reason.strip():raise ValueError('必须说明核对结果，并显式接受可能重复的读取费用。')
    r=rt.action_record(job,action)
    if r.get('requested_configuration',{}).get('wire_api')!=ar.WIRE_API or r.get('status')!='failed':raise ValueError('仅处理失败SDK动作。')
    attempt_id=r.get('attempt_id','')
    if Path(attempt_id).name!=attempt_id or not attempt_id:raise ValueError('无效动作标识')
    directory=job/'provider'/action/'runtime/attempts'/attempt_id
    path=directory/('tool_'+hashlib.sha256(call_id.encode()).hexdigest()+'.json');row=rt._read_json(path,{})
    if row.get('call_id')!=call_id or row.get('status')!='started' or row.get('name') not in READ_TOOLS:raise ValueError('只允许核对未收到回执的已登记读取工具，不处理已完成提交或写入工具。')
    report={'operation':'explicit_allow_tool_retry','reason':reason,'acknowledge_possible_duplicate_cost':True,'reconciled_at':rt.utcnow(),'original_receipt':row}
    target=path.with_name('reconciled_'+path.name)
    if target.exists():raise ValueError('该工具已存在核对记录；请保留历史并人工检查，不覆盖。')
    ar._write(target,report);path.unlink()
    return {'status':'retry_authorized_not_executed','action':action,'call_id':call_id,'note':'尚未调用API或工具；使用continue --retry-current-action恢复。'}


def backup(job,target):
    job=job.resolve();target=target.resolve()
    if target==job or job in target.parents:raise ValueError('备份输出必须放在Job目录之外。')
    if target.exists():raise ValueError('不覆盖已有备份。')
    paths=list(job.rglob('*'))
    if any(p.is_symlink() for p in paths):raise ValueError('任务含符号链接，拒绝跟随打包；请先检查。')
    target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in paths:
            if p.is_file():z.write(p,Path(job.name)/p.relative_to(job))
    target.chmod(0o600)
    return {'status':'backed_up','path':str(target),'files':sum(p.is_file() for p in paths),'sha256':rt._hash_file(target),
            'note':'包含业务状态、材料、历史和SQLite相关文件；须同时保留匹配程序与模型配置。备份前已锁定CLI与SDK宿主。'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--job-dir',required=True,type=Path)
    sub=p.add_subparsers(dest='operation',required=True);sub.add_parser('inspect')
    b=sub.add_parser('backup');b.add_argument('--output',required=True,type=Path)
    q=sub.add_parser('allow-tool-retry');q.add_argument('--action',required=True,choices=sorted(rt.HOST_ACTIONS));q.add_argument('--call-id',required=True)
    q.add_argument('--reason',required=True);q.add_argument('--acknowledge-possible-duplicate-cost',action='store_true')
    a=p.parse_args(argv)
    if a.job_dir.is_symlink() or not a.job_dir.is_dir():p.error('需要一个已存在的普通Job目录。')
    try:
        with job_execution_lock(a.job_dir),rt.action_lock(a.job_dir/'provider/agents_job_lock'):
            result=inspect_job(a.job_dir) if a.operation=='inspect' else backup(a.job_dir,a.output) if a.operation=='backup' else reconcile(a.job_dir,a.action,a.call_id,a.reason,a.acknowledge_possible_duplicate_cost)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as exc:
        print(json.dumps({'status':'error','message':rt.redact(str(exc))},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
