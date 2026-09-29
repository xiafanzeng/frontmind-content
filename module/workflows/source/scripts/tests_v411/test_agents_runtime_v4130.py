"""Offline adapter behavior only. Fabricated responses, not model-quality scores."""
import copy,json,tempfile,unittest,sqlite3,threading,subprocess,sys,os
from pathlib import Path
from unittest.mock import patch
from shared import agents_runtime as ar,model_runtime as rt
from scripts.tests_v411.agents_sdk_fake import bundle
from scripts.tests_v411.test_model_runtime import FakeTools,valid

class CountingTools(FakeTools):
    def __init__(self,fail_after=False):super().__init__();self.executions=0;self.fail_after=fail_after
    def execute(self,name,args):
        self.executions+=1
        if self.fail_after:raise OSError('simulated tool effect without receipt')
        return super().execute(name,args)

class AgentsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.pkg=Path(self.temp.name)/'pkg';self.pkg.mkdir();self.job=Path(self.temp.name)/'job';self.job.mkdir()
    def runit(self,sdk,tools=None,retry=False,**kwargs):
        return rt.run_action(self.pkg,self.job,'p0_blueprint',kwargs.get('prompt','current task'),valid,retry=retry,host_tools=tools or FakeTools(),transport=sdk,offline=True)
    def latest(self):
        r=rt.action_record(self.job,'p0_blueprint');return self.job/'provider/p0_blueprint/runtime/attempts'/r['attempt_id'],r
    def test_new_routes_are_sdk_and_writer_is_unchanged(self):
        for a in rt.HOST_ACTIONS:self.assertEqual(rt.profile_for(a)['wire_api'],ar.WIRE_API)
        self.assertEqual(rt.profile_for('p0_draft')['model'],'deepseek-v4-pro')
        # 作者档位跟随 config/deepseek.json 的显式覆盖（用户2026-09-22定为high），
        # 未配置时默认 max；测试验证配置一致性而非钉死单一档位。
        _cfg_path = Path(__file__).resolve().parents[2] / 'config' / 'deepseek.json'
        _expected = 'max'
        if _cfg_path.exists():
            _expected = json.loads(_cfg_path.read_text()).get('reasoning_effort') or 'max'
        self.assertEqual(rt.profile_for('p0_draft')['reasoning_effort'], _expected)
    def test_real_runner_surface_and_tools_commit(self):
        sdk,e=bundle();t=CountingTools();self.assertEqual(self.runit(sdk,t),{'ok':True});self.assertEqual(t.executions,1)
        p,r=self.latest();self.assertEqual(e.calls,3);self.assertEqual(r['status'],'succeeded');self.assertEqual(r['execution_mode'],'offline_simulated')
        self.assertTrue((p/'session.sqlite3').exists());self.assertEqual(ar.restore_result(p,r,FakeTools(),valid),{'ok':True})
    def test_config_is_effective_not_only_saved(self):
        (self.pkg/'config').mkdir();(self.pkg/'config/xty.json').write_text('{"api_key":"test-token","base_url":"https://example.test/v1","model":"host-test","max_tokens":4096}')
        sdk,e=bundle();self.runit(sdk)
        _,r=self.latest();self.assertEqual(r['requested_configuration']['model'],'host-test');self.assertEqual(e.client_kwargs[0]['base_url'],'https://example.test/v1')
    def test_no_implicit_http_retries_redirects_or_global_client(self):
        sdk,e=bundle();self.runit(sdk);c=e.client_kwargs[0]
        self.assertEqual(c['max_retries'],0);self.assertFalse(c['http_client'].follow_redirects);self.assertEqual(e.closed,1);self.assertEqual(e.session_closed,1)
    def test_result_cache_makes_zero_new_model_calls(self):
        sdk,e=bundle();self.runit(sdk);n=e.calls;self.runit(sdk);self.assertEqual(e.calls,n)
    def test_15_day_old_failed_checkpoint_resumes_same_session(self):
        sdk,e=bundle(fault='network_after_read');t=CountingTools()
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk,t)
        p,r=self.latest();session=r['session_id'];r['failed_at']='2026-09-01T00:00:00Z';rt._atomic(p/'execution.json',r)
        sdk2,e2=bundle();t2=CountingTools();self.assertEqual(self.runit(sdk2,t2,retry=True),{'ok':True})
        _,after=self.latest();self.assertEqual(after['session_id'],session);self.assertEqual(t.executions,1);self.assertEqual(t2.executions,0);self.assertEqual(e2.calls,2)
    def test_cross_process_resume_uses_disk_not_memory(self):
        sdk,e=bundle(fault='network_after_read')
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk)
        script='''from pathlib import Path
from shared.model_runtime import run_action
from scripts.tests_v411.agents_sdk_fake import bundle
from scripts.tests_v411.test_model_runtime import FakeTools,valid
sdk,e=bundle()
print(run_action(Path(__import__('sys').argv[1]),Path(__import__('sys').argv[2]),'p0_blueprint','current task',valid,retry=True,host_tools=FakeTools(),transport=sdk,offline=True))
print(e.calls)
'''
        result=subprocess.run([sys.executable,'-c',script,str(self.pkg),str(self.job)],cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn("'ok': True",result.stdout);self.assertTrue(result.stdout.strip().endswith('2'))
    def test_regular_continue_never_retries_failure(self):
        sdk,e=bundle(fault='network_first')
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk)
        n=e.calls
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk)
        self.assertEqual(ex.exception.code,'agents_explicit_retry_required');self.assertEqual(e.calls,n)
    def test_network_before_first_checkpoint_retries_explicitly(self):
        sdk,e=bundle(fault='network_first')
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk)
        self.assertEqual(e.calls,1);self.assertEqual(self.runit(sdk,retry=True),{'ok':True});self.assertEqual(e.calls,4)
    def test_committed_submit_recovers_without_model(self):
        sdk,e=bundle(fault='after_submit')
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk)
        sdk2,e2=bundle();self.assertEqual(self.runit(sdk2,retry=True),{'ok':True});self.assertEqual(e2.calls,0)
    def test_readonly_started_marker_is_reexecuted_on_resume(self):
        sdk,e=bundle();t=CountingTools(fail_after=True)
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk,t)
        p,before=self.latest();session=before['session_id']
        receipts=list(p.glob('tool_*.json'))
        self.assertEqual(len(receipts),1)
        self.assertEqual(rt._read_json(receipts[0])['status'],'started')
        self.assertTrue(rt._read_json(p/'checkpoint.json')['run_state'])
        t2=CountingTools()
        self.assertEqual(self.runit(sdk,t2,retry=True),{'ok':True})
        _,after=self.latest()
        receipt=rt._read_json(receipts[0])
        self.assertEqual(after['status'],'succeeded');self.assertEqual(after['session_id'],session)
        self.assertEqual(t2.executions,1);self.assertEqual(receipt['status'],'completed')
        self.assertEqual(receipt['readonly_replay_count'],1)
        self.assertTrue(receipt['host_state']['read'])
        self.assertEqual(len(list((p.parent).iterdir())),1)

    def test_toolerror_becomes_model_feedback_and_run_still_succeeds(self):
        from shared.host_tools import ToolError
        from types import SimpleNamespace
        class CorrectableTools(CountingTools):
            def execute(self,name,args):
                if self.executions==0:
                    self.executions+=1
                    raise ToolError('Unknown registered source; use the exact artifact_id.')
                return super().execute(name,args)
        sdk,e=bundle();model=sdk[0].OpenAIChatCompletionsModel
        original=model.get_response
        async def corrected(instance,**kw):
            outputs=[x for x in kw['input'] if x.get('type')=='function_call_output']
            if outputs and json.loads(outputs[-1]['output']).get('ok') is False:
                e.calls+=1
                return SimpleNamespace(output=[{'type':'function_call','name':'read_material',
                    'call_id':'read_material_corrected','id':'fixture_corrected',
                    'arguments':'{"artifact_id":"one"}'}],response_id='fixture_correction')
            return await original(instance,**kw)
        t=CorrectableTools()
        with patch.object(model,'get_response',corrected):
            self.assertEqual(self.runit(sdk,t),{'ok':True})
        p,r=self.latest();rows=[rt._read_json(x) for x in p.glob('tool_*.json')]
        errors=[row for row in rows if row['output'].get('ok') is False]
        self.assertEqual(len(errors),1);self.assertEqual(errors[0]['status'],'completed')
        self.assertEqual(errors[0]['output']['error'],'tool_error')
        self.assertEqual(r['status'],'succeeded');self.assertEqual(e.calls,4)
        self.assertEqual(t.executions,2)
        # A completed feedback receipt is part of the exact saved result.
        n=e.calls;self.runit(sdk);self.assertEqual(e.calls,n)
    def test_unread_required_source_rejected(self):
        sdk,e=bundle(fault='unread')
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk)
        self.assertEqual(ex.exception.code,'invalid_result_contract')
    def test_invalid_result_not_accepted(self):
        sdk,e=bundle(result={'ok':False})
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk)
        self.assertEqual(ex.exception.code,'invalid_result_contract')
    def test_invalid_submit_becomes_feedback_then_corrected_resubmit(self):
        # Local fix 2026-09-21: a submit that fails content validation must reach
        # the model as durable tool feedback so it corrects and resubmits inside
        # the SAME paid run (the real-world claude-sonnet-5 blueprint incident:
        # complete 12-field blueprint missing writing_material_markdown/sources).
        sdk,e=bundle(fault='invalid_final');t=CountingTools()
        self.assertEqual(self.runit(sdk,t),{'ok':True})
        p,r=self.latest();self.assertEqual(r['status'],'succeeded')
        rows=[rt._read_json(x) for x in sorted(p.glob('tool_*.json'))]
        feedback=[row for row in rows if isinstance(row.get('output'),dict) and row['output'].get('error')=='invalid_result_contract']
        self.assertEqual(len(feedback),1)
        self.assertEqual(feedback[0]['status'],'completed')
        self.assertIn('合同',feedback[0]['output']['message'])
        self.assertEqual((p/'submission.json').is_file(),True)
        self.assertEqual(rt._read_json(p/'submission.json')['result'],{'ok':True})
        # One continuous session: read, bad submit, corrected submit, final text.
        self.assertEqual(e.calls,4);self.assertEqual(len(rows),3)
        # A cached completion makes zero new model calls.
        n=e.calls;self.runit(sdk);self.assertEqual(e.calls,n)
    def test_invalid_final_cannot_start_a_second_paid_draft(self):
        sdk,e=bundle(result={'ok':False})
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk)
        n=e.calls
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk,retry=True)
        self.assertEqual(ex.exception.code,'saved_submission_not_recoverable');self.assertEqual(n,e.calls)
    def test_plain_text_is_not_business_submission(self):
        sdk,e=bundle(fault='no_submit')
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk)
        self.assertEqual(ex.exception.code,'missing_submit_result')
    def test_submit_with_other_call_is_rejected(self):
        sdk,e=bundle(fault='mixed')
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk)
        self.assertEqual(ex.exception.code,'mixed_final_submission')
    def test_unknown_tool_is_not_executed(self):
        sdk,e=bundle(fault='forbidden');t=CountingTools()
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk,t)
        self.assertEqual(ex.exception.code,'unexpected_tool');self.assertEqual(t.executions,0)
    def test_cached_response_corruption_rejected(self):
        sdk,e=bundle();self.runit(sdk);p,r=self.latest();(p/'model_0002_response.json').write_text('{}')
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk)
        self.assertEqual(ex.exception.code,'cached_result_invalid')
    def test_cached_business_result_cannot_be_replaced(self):
        sdk,e=bundle();self.runit(sdk);p,r=self.latest();rt._atomic(p/'validated_result.json',{'ok':True,'forged':True})
        with self.assertRaises(rt.ProviderActionError):self.runit(sdk)
    def test_changed_prompt_creates_new_session_without_mutating_old(self):
        sdk,e=bundle();self.runit(sdk);p,r=self.latest();old=(p/'execution.json').read_bytes()
        self.runit(sdk,prompt='new confirmed input');p2,r2=self.latest();self.assertNotEqual(r2['session_id'],r['session_id']);self.assertEqual((p/'execution.json').read_bytes(),old)
    def test_credentials_never_enter_prompt_or_session(self):
        (self.pkg/'config').mkdir();(self.pkg/'config/xty.json').write_text('{"api_key":"private-test-key"}')
        sdk,e=bundle()
        with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk,prompt='private-test-key')
        self.assertEqual(ex.exception.code,'credential_in_prompt');self.assertEqual(e.calls,0)
    def test_production_injection_rejected(self):
        sdk,e=bundle()
        with self.assertRaises(rt.ProviderActionError) as ex:rt.run_action(self.pkg,self.job,'p0_blueprint','task',valid,transport=sdk)
        self.assertEqual(ex.exception.code,'production_transport_override')
    def test_missing_sdk_fails_clearly_without_network(self):
        with patch.dict(sys.modules,{'agents':None}):
            with self.assertRaises(rt.ProviderActionError) as ex:ar._sdk()
            self.assertEqual(ex.exception.code,'agents_sdk_missing')
    def test_missing_gateway_key_does_not_use_zhipu(self):
        (self.pkg/'config').mkdir();(self.pkg/'config/zhipu.json').write_text('{"api_key":"existing"}')
        with self.assertRaises(rt.ProviderActionError) as ex:rt.run_action(self.pkg,self.job,'p0_blueprint','task',valid)
        self.assertEqual(ex.exception.code,'missing_api_key')
    def test_same_job_host_lock_prevents_second_executor(self):
        sdk,e=bundle()
        with rt.action_lock(self.job/'provider/agents_job_lock'):
            with self.assertRaises(rt.ProviderActionError) as ex:self.runit(sdk)
            self.assertEqual(ex.exception.code,'action_locked')
        self.assertEqual(e.calls,0)
    def test_different_job_lock_does_not_block(self):
        sdk,e=bundle()
        with rt.action_lock(Path(self.temp.name)/'other/provider/agents_job_lock'):self.runit(sdk)
    def test_legacy_profile_is_context_local_and_restored(self):
        with rt.legacy_managed_routes():self.assertEqual(rt.profile_for('p0_blueprint')['wire_api'],'zhipu_managed_agents')
        self.assertEqual(rt.profile_for('p0_blueprint')['wire_api'],ar.WIRE_API)
    def test_url_validation_rejects_credential_redirect_targets(self):
        (self.pkg/'config').mkdir()
        for url in ['http://example.test/v1','https://u:p@example.test/v1','https://example.test/v1?key=x','https://example.test/docs','https://example.test:8443/v1']:
            (self.pkg/'config/xty.json').write_text(json.dumps({'base_url':url}))
            with self.assertRaises(rt.ProviderActionError):ar.public_profile(self.pkg)
    def test_no_remote_resources_in_sdk_plan(self):
        plan=rt.build_payload('p0_blueprint','task',tools=FakeTools().definitions())
        self.assertEqual(plan['session_storage'],'local_sqlite');self.assertNotIn('environment',plan);self.assertNotIn('agent_id',plan)
    def test_model_settings_change_fingerprint(self):
        p=ar.request_plan('p0_blueprint',ar.public_profile(self.pkg),rt._initial_messages('p0_blueprint','task'),[])
        q=copy.deepcopy(p);q['profile']['model']='other';self.assertNotEqual(ar.fingerprint(p,'ctx',False),ar.fingerprint(q,'ctx',False))
    def test_offline_and_production_caches_are_separate(self):
        p={'x':1};self.assertNotEqual(ar.fingerprint(p,'ctx',True),ar.fingerprint(p,'ctx',False))
    def test_controller_saved_result_handles_sdk_provenance(self):
        sdk,e=bundle();self.runit(sdk);p,r=self.latest();self.assertEqual(rt._saved_result(p,r,FakeTools(),valid),{'ok':True})
