#!/usr/bin/env python3
"""XTY + official SDK probe. Default is local-only; --models is a GET;
--live-tool makes one small paid model request and checks real RunState restore.
No business article, remote Agent or remote Environment is created.
"""
from __future__ import annotations
import argparse,asyncio,json,sys,tempfile,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from shared.workflow_versions import RELEASE_VERSION
from shared import model_runtime as rt,agents_runtime as ar


def check_models(root=ROOT):
    profile=ar.public_profile(root);cfg=rt.load_configuration(root,'xty')
    ids=None
    # Local fix 2026-09-21: some gateways sit behind bot protection that rejects
    # stdlib urllib fingerprints with HTTP 403 (Cloudflare error 1010) while the
    # SDK's httpx client passes. Prefer the SDK client; keep urllib as fallback.
    try:
        ag,oa=ar._sdk()
    except Exception:
        oa=None
    if oa is not None:
        async def _list_models():
            client=oa.AsyncOpenAI(api_key=cfg['api_key'],base_url=profile['base_url'],timeout=60,max_retries=0)
            try:
                page=await client.models.list()
                return [row.id for row in page.data if isinstance(getattr(row,'id',None),str)]
            finally:
                await client.close()
        ids=asyncio.run(_list_models())
    if ids is None:
        request=urllib.request.Request(profile['base_url']+'/models',headers={'Authorization':'Bearer '+cfg['api_key'],'Accept':'application/json'})
        with urllib.request.build_opener(rt._NoRedirect()).open(request,timeout=30) as response:
            data=rt.strict_json(response.read(4*1024*1024).decode())
        ids=[row['id'] for row in data.get('data',[]) if isinstance(row,dict) and isinstance(row.get('id'),str)]
    return {'status':'pass' if profile['model'] in ids else 'model_not_listed', 'operation':'GET /models', 'configured_model':profile['model'],
            'available_model_ids':ids,'generation_verified':False,'note':'模型未列出不必然代表不能调用；不自动选择替代模型。'}


async def live_tool(root=ROOT):
    ag,oa=ar._sdk();profile=ar.public_profile(root);cfg=rt.load_configuration(root,'xty')
    # Local fix 2026-09-21: 30s was too short for reasoning-grade models on this
    # gateway; the probe itself timed out while the model was still working.
    client=oa.AsyncOpenAI(api_key=cfg['api_key'],base_url=profile['base_url'],timeout=120,max_retries=0,http_client=oa.DefaultAsyncHttpxClient(follow_redirects=False))
    executed=[]
    async def echo(ctx,text):
        args=rt.strict_json(text)
        if args!={'value':'frontmind-probe'}:raise ValueError('probe arguments differ')
        executed.append(ctx.tool_call_id);return 'frontmind-probe-ok'
    try:
        tool=ag.FunctionTool(name='frontmind_probe',description='Echo the exact probe value.',params_json_schema={'type':'object','properties':{'value':{'type':'string','enum':['frontmind-probe']}},'required':['value'],'additionalProperties':False},on_invoke_tool=echo,needs_approval=True)
        agent=ag.Agent(name='FrontMindGatewayProbe',instructions='Call frontmind_probe exactly once with value frontmind-probe. Do not return text.',
                      model=ag.OpenAIChatCompletionsModel(model=profile['model'],openai_client=client),tools=[tool],
                      model_settings=ag.ModelSettings(tool_choice='required',parallel_tool_calls=False,max_tokens=128),
                      tool_use_behavior={'stop_at_tool_names':['frontmind_probe']})
        with tempfile.TemporaryDirectory(prefix='frontmind-sdk-probe-') as work:
            session=ag.SQLiteSession('probe',str(Path(work)/'session.sqlite3'))
            try:
                result=await ag.Runner.run(agent,'Run the tool probe.',session=session,max_turns=2,run_config=ag.RunConfig(tracing_disabled=True,trace_include_sensitive_data=False))
                if len(result.interruptions)!=1:raise ValueError('expected exactly one pending tool')
                stored=result.to_state().to_json()
                # A fresh RunState and fresh database connection, no model replay.
                session.close();session=ag.SQLiteSession('probe',str(Path(work)/'session.sqlite3'))
                state=await ag.RunState.from_json(agent,json.loads(json.dumps(stored)))
                pending=state.get_interruptions()
                if len(pending)!=1 or pending[0].name!='frontmind_probe':raise ValueError('unexpected restored tool')
                state.approve(pending[0],always_approve=False)
                final=await ag.Runner.run(agent,state,session=session,max_turns=2,run_config=ag.RunConfig(tracing_disabled=True,trace_include_sensitive_data=False))
                if final.interruptions or final.final_output!='frontmind-probe-ok' or len(executed)!=1:raise ValueError('probe did not complete once')
                return {'status':'pass','operation':'real_sdk_tool_and_serialized_resume','model':profile['model'],'sdk_version':ar.SDK_VERSION,
                        'paid_model_call':True,'real_sdk_verified':True,'tool_executed_once':True,'new_database_connection_resumed':True,
                        'article_quality_verified':False,'fifteen_days_waited':False}
            finally:session.close()
    finally:await client.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models',action='store_true',help='Authenticated read-only model-list request')
    p.add_argument('--live-tool',action='store_true',help='Explicitly authorize one small paid tool-call test')
    p.add_argument('--output',type=Path)
    a=p.parse_args(argv);report={'release_version':RELEASE_VERSION,'checked_at':rt.utcnow(),'profile':ar.public_profile(ROOT),'checks':[],'status':'local_configuration_only'}
    operations=[]
    if a.models:operations.append(('models',lambda:check_models(ROOT)))
    if a.live_tool:operations.append(('live_tool',lambda:asyncio.run(live_tool(ROOT))))
    for name,fn in operations:
        try:report['checks'].append(fn())
        except Exception as exc:
            report['checks'].append({'operation':name,'status':'unverified','error_code':getattr(exc,'code',type(exc).__name__),
                                     'message':rt.redact(str(exc),[rt.load_configuration(ROOT,'xty')['api_key']])[:600]})
    if operations:report['status']='pass' if all(x['status']=='pass' for x in report['checks']) else 'verification_incomplete'
    text=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(text)
    print(text,end='');return 1 if report['status']=='verification_incomplete' else 0
if __name__=='__main__':raise SystemExit(main())
