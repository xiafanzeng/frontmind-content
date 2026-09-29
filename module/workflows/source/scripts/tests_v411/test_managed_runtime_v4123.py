"""Official Managed Agents wire-shape simulation; never evidence of live access."""
from __future__ import annotations
import copy,json,tempfile,unittest
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch
from shared import model_runtime as rt, managed_runtime as managed
from scripts.tests_v411.test_model_runtime import FakeTools,valid

# 作者档位跟随本包 config/deepseek.json 的显式覆盖（用户2026-09-22定为high；缺省默认max）。
# 断言验证配置一致性，而不是钉死某一档位。
import json as _json
from pathlib import Path as _Path
try:
    _cfgf = _Path(__file__).resolve().parents[2] / 'config' / 'deepseek.json'
    _WRITER_EFFORT = (_json.loads(_cfgf.read_text()).get('reasoning_effort') or 'max') if _cfgf.exists() else 'max'
except Exception:
    _WRITER_EFFORT = 'max'


class ManagedServer:
    """Stateful fake server: platform chooses calls; client only resolves tools."""
    def __init__(self, result=None, *, read_first=True, fault=None):
        self.result=result if result is not None else {'ok':True}
        self.read_first=read_first;self.fault=fault;self.calls=[];self.events=[];self.resources={};self.failed=False
    def event(self,typ,**fields):
        row={'id':'evt_%03d'%(len(self.events)+1),'type':typ,'processed_at':'2026-09-17T00:00:%02dZ'%(len(self.events)%60),**fields}
        self.events.append(row);return row
    def tool(self,name,arguments):
        self.event('session.status_running')
        e=self.event('agent.custom_tool_use',name=name,input=arguments)
        self.event('span.model_request_end',model='glm-5.3',model_usage={'input_tokens':25,'output_tokens':10})
        self.event('session.status_idle',stop_reason={'type':'requires_action','event_ids':[e['id']]})
    def request(self,method,path,body=None):
        self.calls.append((method,path,copy.deepcopy(body)))
        if self.fault=='authentication' and not self.resources:
            raise rt.ProviderActionError('managed_authentication_failed','synthetic denied')
        base=urlsplit(path).path
        if method=='POST' and base=='/v1/agents':
            self.resources['agent']={'id':'agent_fixture','version':1,**copy.deepcopy(body)}
            if self.fault=='wrong_model':self.resources['agent']['model']['id']='glm-other'
            if self.fault=='unexpected_tool':self.resources['agent']['tools'].append({'type':'agent_toolset_20260601'})
            if self.fault=='unknown_create' and not self.failed:
                self.failed=True;raise rt.ProviderActionError('managed_write_outcome_unknown','synthetic ack loss')
            return copy.deepcopy(self.resources['agent'])
        if method=='POST' and base=='/v1/environments':
            self.resources['environment']={'id':'env_fixture',**copy.deepcopy(body)}
            if self.fault=='open_network':self.resources['environment']['config']['networking']['type']='unrestricted'
            return copy.deepcopy(self.resources['environment'])
        if method=='POST' and base=='/v1/sessions':
            self.resources['session']={'id':'sess_fixture','environment_id':body['environment_id'], 'agent':copy.deepcopy(self.resources['agent']), 'usage':{'input_tokens':50,'output_tokens':20}}
            return copy.deepcopy(self.resources['session'])
        if method=='GET' and base=='/v1/sessions/sess_fixture':return copy.deepcopy(self.resources['session'])
        if method=='GET' and base.endswith('/events'):
            # Boundary rows are deliberately replayed. Real cursor handling is tested below.
            return {'data':copy.deepcopy(self.events),'has_more':False}
        if method=='POST' and base.endswith('/events'):
            for incoming in body['events']:
                e=copy.deepcopy(incoming);typ=e.pop('type');self.event(typ,**e)
                if typ=='user.message':
                    if self.fault=='no_submission':self.event('session.status_idle',stop_reason={'type':'end_turn'})
                    elif self.read_first:self.tool('read_material',{'artifact_id':'one'})
                    else:self.tool('submit_result',{'result':self.result})
                elif typ=='user.custom_tool_result':
                    src=next(e for e in self.events if e['id']==incoming['custom_tool_use_id'])
                    if src['name']=='read_material':
                        if self.fault=='missing_ids':self.event('session.status_idle',stop_reason={'type':'requires_action','event_ids':['unknown']})
                        else:self.tool('submit_result',{'result':self.result})
                    else:
                        if self.fault=='tool_after_submit':self.event('agent.custom_tool_use',name='read_material',input={'artifact_id':'one'})
                        self.event('session.status_idle',stop_reason={'type':'end_turn'})
                    if self.fault=='resolution_ack_lost' and not self.failed:
                        self.failed=True;raise rt.ProviderActionError('managed_write_outcome_unknown','synthetic result ack loss')
            return {'accepted':True}
        raise AssertionError((method,path))

class ManagedRuntimeTests(unittest.TestCase):
    def setUp(self):
        from shared.model_runtime import legacy_managed_routes
        legacy = legacy_managed_routes(); legacy.__enter__(); self.addCleanup(legacy.__exit__, None, None, None)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.pkg=Path(self.tmp.name)/'pkg';self.pkg.mkdir();self.job=Path(self.tmp.name)/'job';self.job.mkdir()
    def run_server(self,server,*,tools=None,retry=False,action='p0_blueprint',validator=valid,prompt='only current input'):
        return rt.run_action(self.pkg,self.job,action,prompt,validator,retry=retry,host_tools=tools or FakeTools(),transport=server,offline=True)
    def attempt(self,action='p0_blueprint'):
        record=rt.action_record(self.job,action)
        return self.job/'provider'/action/'runtime/attempts'/record['attempt_id'],record
    def test_current_routes_are_managed_max_and_pro_max_without_aliases(self):
        for action in rt.HOST_ACTIONS:
            p=rt.profile_for(action);self.assertEqual((p['provider'],p['wire_api'],p['model'],p['effort']),('zhipu','zhipu_managed_agents','glm-5.3','max'))
            plan=rt.build_payload(action,'complete input')
            self.assertNotIn('messages',plan);self.assertEqual(plan['agent']['model'],{'id':'glm-5.3','effort':'max'})
            self.assertFalse({'thinking','speed','max_tokens','temperature'}&plan['agent'].keys())
            self.assertTrue(all(t['type']=='custom' for t in plan['agent']['tools']))
        for action in rt.DEEPSEEK_ACTIONS:
            p=rt.build_payload(action,'complete input');self.assertEqual(p['model'],'deepseek-v4-pro');self.assertEqual(p['reasoning_effort'],_WRITER_EFFORT)
    def test_platform_tool_events_complete_and_original_events_validate(self):
        s=ManagedServer();t=FakeTools();self.assertEqual(self.run_server(s,tools=t),{'ok':True});self.assertTrue(t.read)
        attempt,r=self.attempt();self.assertEqual(r['execution_mode'],'offline_simulated');self.assertEqual(r['status'],'succeeded')
        self.assertEqual(managed.restore_result(attempt,r,FakeTools(),valid),{'ok':True})
        sessionpost=next(b for m,p,b in s.calls if p=='/v1/sessions')
        self.assertEqual(sessionpost['agent'],{'type':'agent','id':'agent_fixture','version':1})
        self.assertFalse(any('/chat/completions' in p or '/responses' in p for _,p,_ in s.calls))
    def test_all_eleven_host_actions_use_managed_protocol(self):
        for action in rt.HOST_ACTIONS:
            with self.subTest(action=action):self.assertEqual(self.run_server(ManagedServer(),action=action),{'ok':True})
    def test_cached_completed_result_never_contacts_server(self):
        s=ManagedServer();self.run_server(s);n=len(s.calls);self.run_server(s);self.assertEqual(n,len(s.calls))
    def test_non_simulated_override_is_rejected_before_network(self):
        with self.assertRaises(rt.ProviderActionError) as e:rt.run_action(self.pkg,self.job,'p0_blueprint','task',valid,transport=ManagedServer())
        self.assertEqual(e.exception.code,'production_transport_override')
    def test_missing_managed_key_does_not_fallback_to_xty(self):
        (self.pkg/'config').mkdir();(self.pkg/'config/xty.json').write_text('{"api_key":"fixture-old-gateway"}')
        with self.assertRaises(rt.ProviderActionError) as e:rt.run_action(self.pkg,self.job,'p0_blueprint','task',valid)
        self.assertEqual(e.exception.code,'missing_api_key')
    def test_model_configuration_mismatch_stops_before_session(self):
        s=ManagedServer(fault='wrong_model')
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(s)
        self.assertEqual(e.exception.code,'managed_model_mismatch');self.assertNotIn('session',s.resources)
    def test_builtin_tools_are_rejected(self):
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(ManagedServer(fault='unexpected_tool'))
        self.assertEqual(e.exception.code,'managed_configuration_mismatch')
    def test_open_network_environment_rejected(self):
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(ManagedServer(fault='open_network'))
        self.assertEqual(e.exception.code,'managed_environment_mismatch')
    def test_final_submission_without_reading_is_rejected(self):
        with self.assertRaises(rt.ProviderActionError):self.run_server(ManagedServer(read_first=False))
        _,record=self.attempt();self.assertEqual(record['status'],'failed')
    def test_rejected_business_submission_does_not_start_second_edit(self):
        s=ManagedServer(result={'ok':False})
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(s)
        self.assertEqual(e.exception.code,'invalid_result_contract');n=len(s.calls)
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(s,retry=True)
        self.assertEqual(e.exception.code,'saved_submission_not_recoverable');self.assertEqual(n,len(s.calls))
    def test_end_turn_without_submission_is_not_success(self):
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(ManagedServer(fault='no_submission'))
        self.assertEqual(e.exception.code,'managed_missing_submission')
    def test_unknown_action_ids_fail_closed(self):
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(ManagedServer(fault='missing_ids'))
        self.assertEqual(e.exception.code,'managed_unexpected_approval')
    def test_post_submission_tool_hidden_before_end_turn_rejected(self):
        with self.assertRaises(rt.ProviderActionError):self.run_server(ManagedServer(fault='tool_after_submit'))
        _,record=self.attempt();self.assertEqual(record['status'],'failed')
    def test_explicit_retry_reuses_session_and_reconciles_ack_loss(self):
        s=ManagedServer(fault='resolution_ack_lost');t=FakeTools()
        with self.assertRaises(rt.ProviderActionError):self.run_server(s,tools=t)
        before=len(s.calls)
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(s)
        self.assertEqual(e.exception.code,'managed_explicit_retry_required');self.assertEqual(before,len(s.calls))
        self.assertEqual(self.run_server(s,retry=True),{'ok':True})
        self.assertEqual(sum(m=='POST' and p=='/v1/sessions' for m,p,b in s.calls),1)
        resolutions=[b['events'][0]['custom_tool_use_id'] for m,p,b in s.calls if m=='POST' and p.endswith('/events') and b['events'][0]['type']=='user.custom_tool_result']
        self.assertEqual(len(resolutions),len(set(resolutions)))
        attempt,record=self.attempt();self.assertTrue((attempt/'resume_001_previous_execution.json').is_file())
    def test_unknown_create_ack_never_creates_second_agent(self):
        s=ManagedServer(fault='unknown_create')
        with self.assertRaises(rt.ProviderActionError):self.run_server(s)
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(s,retry=True)
        self.assertEqual(e.exception.code,'managed_write_outcome_unknown')
        self.assertEqual(sum(p=='/v1/agents' for _,p,_ in s.calls),1)
    def test_auth_error_is_not_business_reconfirmation(self):
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(ManagedServer(fault='authentication'))
        self.assertEqual(e.exception.code,'managed_authentication_failed')
    def test_event_evidence_tampering_invalidates_completed_cache(self):
        s=ManagedServer();self.run_server(s);a,_=self.attempt();(a/'events.json').write_text('[]');n=len(s.calls)
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(s)
        self.assertEqual(e.exception.code,'cached_result_invalid');self.assertEqual(n,len(s.calls))
    def test_changed_input_creates_distinct_attempt(self):
        self.run_server(ManagedServer(),prompt='one');self.run_server(ManagedServer(),prompt='two')
        self.assertEqual(len(list((self.job/'provider/p0_blueprint/runtime/attempts').iterdir())),2)
    def test_resource_session_version_is_checked(self):
        s=ManagedServer();self.run_server(s);a,r=self.attempt();state=rt._read_json(a/'managed_state.json');plan=rt._read_json(a/'request_plan.json')
        session=copy.deepcopy(s.resources['session']);session['agent']['version']=2
        with self.assertRaises(rt.ProviderActionError):managed.validate_session_echo(session,state,plan)
    def test_pagination_replays_ids_and_uses_returned_cursor(self):
        e1={'id':'evt_1','type':'session.status_running','processed_at':'2026-09-17T00:00:00Z'}
        e2={'id':'evt_2','type':'session.status_idle','processed_at':'2026-09-17T00:00:01Z'}
        class Pages:
            def request(self,method,path,body=None):
                q=parse_qs(urlsplit(path).query)
                if 'page' not in q:return {'data':[e1],'next_page':'cursor_2'}
                if q['page']!=['cursor_2']:raise AssertionError(q)
                return {'data':[e1,e2],'has_more':False}
        self.assertEqual(managed.read_history(Pages(),'session_id',[]),[e1,e2])
    def test_page_cursor_and_explicit_null_end_are_consumed(self):
        e1={'id':'p1','processed_at':'t1','type':'session.status_running'}
        e2={'id':'p2','processed_at':'t2','type':'session.status_idle'}
        class Pages:
            def request(self,method,path):
                return {'data':[e2],'page':None} if 'page=cursor2' in path else {'data':[e1],'page':'cursor2'}
        self.assertEqual(managed.read_history(Pages(),'session_id',[]),[e1,e2])
    def test_full_page_without_end_or_continuation_is_not_silently_complete(self):
        rows=[{'id':'e'+str(i),'processed_at':'t'+str(i),'type':'session.status_running'} for i in range(100)]
        class Pages:
            def request(self,*args):return {'data':rows}
        with self.assertRaises(rt.ProviderActionError) as e:managed.read_history(Pages(),'session_id',[])
        self.assertEqual(e.exception.code,'managed_pagination_missing')
    def test_missing_pagination_cursor_is_not_silent_truncation(self):
        class Pages:
            def request(self,*a):return {'data':[],'has_more':True}
        with self.assertRaises(rt.ProviderActionError) as e:managed.read_history(Pages(),'s',[])
        self.assertEqual(e.exception.code,'managed_pagination_missing')
    def test_changed_duplicate_event_is_rejected(self):
        e={'id':'e','processed_at':'t','type':'session.status_running'}
        class Pages:
            def request(self,*a):return {'data':[{**e,'type':'session.deleted'}]}
        with self.assertRaises(rt.ProviderActionError):managed.read_history(Pages(),'s',[e])
    def test_credentials_do_not_enter_prompt_or_network(self):
        (self.pkg/'config').mkdir();(self.pkg/'config/zhipu.json').write_text('{"api_key":"synthetic-private-key-12345"}')
        s=ManagedServer()
        with self.assertRaises(rt.ProviderActionError) as e:self.run_server(s,prompt='synthetic-private-key-12345')
        self.assertEqual(e.exception.code,'credential_in_prompt');self.assertEqual(s.calls,[])
    def test_client_headers_and_fixed_endpoint(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return b'{"data":[]}'
        with patch.object(managed.urllib.request,'build_opener') as opener:
            opener.return_value.open.return_value=Response()
            client=managed.ManagedClient('synthetic-key');client.request('GET','/v1/agents')
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,managed.BASE_URL+'/v1/agents')
            h={k.lower():v for k,v in request.header_items()};self.assertEqual(h['zai-version'],managed.API_VERSION);self.assertEqual(h['zai-beta'],managed.BETA_VERSION)
            with self.assertRaises(rt.ProviderActionError):client.request('POST','https://wrong.example')

if __name__=='__main__':unittest.main()
