#!/usr/bin/env python3
"""Explicit read-only provider probes; never claim a prose or generation pass.

Default: local configuration only. --live reads XTY and DeepSeek model lists.
--legacy-managed additionally reads the legacy Managed Agent list.
--interrupt-session ID additionally sends exactly one user.interrupt event; it
never retries that write. This does not delete a session or any history.
"""
from __future__ import annotations
import argparse,json,re,sys,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from shared.workflow_versions import RELEASE_VERSION
from shared import model_runtime as rt,managed_runtime as managed
from scripts.probe_agents_gateway import check_models


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='perform authenticated read-only API requests')
    parser.add_argument('--legacy-managed',action='store_true',help='also read the legacy Managed Agent list; never create resources')
    parser.add_argument('--output',type=Path,help='write a non-secret JSON report')
    parser.add_argument('--interrupt-session',help='explicitly interrupt one known Managed Agents session; requires --live')
    args=parser.parse_args(argv)
    if args.interrupt_session and (not args.live or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',args.interrupt_session)):
        parser.error('--interrupt-session requires --live and a valid opaque session ID')
    report={'release_version':RELEASE_VERSION,'checked_at':rt.utcnow(),'mode':'live_read_only' if args.live else 'local_configuration',
            'configuration':rt.configuration_status(ROOT),'generation_verified':False,'content_quality_verified':False,'checks':[]}
    if args.live:
        try:
            report['checks'].append({'provider':'xty', **check_models(ROOT)})
        except Exception as exc:
            report['checks'].append({'provider':'xty','status':'unverified','error_code':getattr(exc,'code',type(exc).__name__),
                'message':'XTY模型列表请求未完成；不代表鉴权或生成通过。'})
        if args.legacy_managed or args.interrupt_session:
            try:
                cfg=rt.load_configuration(ROOT,'zhipu')
                client=managed.ManagedClient(cfg['api_key'],timeout=30)
                data=client.request('GET','/v1/agents?limit=1')
                report['checks'].append({'provider':'zhipu','operation':'list_agents','status':'pass',
                    'scope':'Authenticated Managed Agents list access only; not session/tool execution.'})
                if args.interrupt_session:
                    # Resolve the exact session first. Never infer a session from a title.
                    session=client.request('GET','/v1/sessions/'+args.interrupt_session)
                    if session.get('id')!=args.interrupt_session:raise ValueError('session identity mismatch')
                    client.request('POST','/v1/sessions/'+args.interrupt_session+'/events',{'events':[{'type':'user.interrupt'}]})
                    report['checks'].append({'provider':'zhipu','operation':'user.interrupt','session_id':args.interrupt_session,'status':'request_acknowledged',
                        'scope':'One interrupt event acknowledged; poll the session history to establish the final stop state.'})
            except Exception as exc:
                report['checks'].append({'provider':'zhipu','status':'unverified','error_code':getattr(exc,'code',type(exc).__name__),
                    'message':'Managed Agents request did not complete successfully; no fallback or automatic write retry.'})
        try:
            cfg=rt.load_configuration(ROOT,'deepseek')
            request=urllib.request.Request('https://api.deepseek.com/models',headers={'Authorization':'Bearer '+cfg['api_key'],'Accept':'application/json'})
            with urllib.request.build_opener(rt._NoRedirect()).open(request,timeout=30) as response:
                data=json.loads(response.read(1024*1024).decode('utf-8'))
            ids=[row.get('id') for row in data.get('data',[]) if isinstance(row,dict)]
            expected=rt.profile_for('p0_draft')['model']
            report['checks'].append({'provider':'deepseek','operation':'list_models','status':'pass' if expected in ids else 'model_not_listed',
                'expected_model':expected,'available_model_ids':ids,'scope':'Model-list access only; not a generation test.'})
        except Exception as exc:
            report['checks'].append({'provider':'deepseek','status':'unverified','error_code':getattr(exc,'code',type(exc).__name__),
                'message':'Official DeepSeek model-list request did not complete successfully.'})
    report['status']='configuration_only' if not args.live else ('read_access_verified' if all(x['status'] in {'pass','request_acknowledged'} for x in report['checks']) else 'live_verification_incomplete')
    text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    print(text,end='')
    return 1 if report['status']=='live_verification_incomplete' else 0

if __name__=='__main__':raise SystemExit(main())
