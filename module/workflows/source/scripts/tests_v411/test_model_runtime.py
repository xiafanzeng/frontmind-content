"""Behavioral regression tests for fixed embedded execution and paid-call recovery."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'shared'))
from shared import model_runtime as m


def stream(content='{"ok":true}', model='deepseek-v4-pro', finish='stop', reasoning='private thought'):
    yield {'id':'test-id','model':model,'choices':[{'index':0,'delta':{'reasoning_content':reasoning},'finish_reason':None}]}
    yield {'id':'test-id','model':model,'choices':[{'index':0,'delta':{'content':content},'finish_reason':finish}], 'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}
    yield '[DONE]'


def tool_stream(name, arguments, *, model='glm-5.3'):
    text=json.dumps(arguments)
    split=len(text)//2
    yield {'model':model,'id':'tool-id','choices':[{'index':0,'delta':{'reasoning_content':'preserved tool thought','tool_calls':[{'index':0,'id':'call-1','function':{'name':name,'arguments':text[:split]}}]},'finish_reason':None}]}
    yield {'model':model,'id':'tool-id','choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'function':{'arguments':text[split:]}}]},'finish_reason':'tool_calls'}]}
    yield '[DONE]'


def valid(value):
    if value.get('ok') is not True:
        raise ValueError('ok must be true')
    return value


class FakeTools:
    def __init__(self): self.read=False
    def definitions(self):
        return [{'type':'function','function':{'name':'read_material','description':'read','parameters':{'type':'object','properties':{'artifact_id':{'type':'string'}},'required':['artifact_id']}}}]
    def execute(self,name,args):
        if name != 'read_material' or args != {'artifact_id':'one'}: raise ValueError('tool forbidden')
        self.read=True
        return {'text':'start middle end','complete':True}
    def assert_required_reads_complete(self):
        if not self.read: raise ValueError('required material unread')
    def cache_dependencies(self): return []
    def export_state(self): return {"read":self.read}
    def restore_state(self,state): self.read=state["read"]


def legacy_profile(action):
    """Immutable v4.11.5 execution fixture; never selected by production."""
    if action in m.HOST_ACTIONS:
        return {"provider":"zhipu", "api_url":"https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "model":"glm-5.3", "thinking":{"type":"enabled","clear_thinking":False},
            "reasoning_effort":"max", "max_tokens":131072 if action.endswith('_finalize') else 65536,
            "stream":True,"tool_stream":True,"timeout_seconds":300}
    if action in m.DEEPSEEK_ACTIONS:
        return {"provider":"deepseek","api_url":"https://api.deepseek.com/chat/completions",
            "model":"deepseek-v4-pro","thinking":{"type":"enabled"},"reasoning_effort":"high",
            "max_tokens":65536,"stream":True,"response_format":{"type":"json_object"},"timeout_seconds":300}
    raise m.ProviderActionError('unsupported_action','Unsupported historical fixture action')


class LegacyRuntimeCompatibilityTests(unittest.TestCase):
    def setUp(self):
        # Keep every old recovery regression on its actual historical protocol.
        # Current XTY/Pro configuration and native integration have a separate suite.
        old_profile=patch.object(m, 'profile_for', side_effect=legacy_profile)
        old_profile.start(); self.addCleanup(old_profile.stop)
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'package';self.root.mkdir()
        self.job=Path(self.tmp.name)/'job';self.job.mkdir()

    def test_all_fifteen_historical_fixture_routes_keep_original_configuration(self):
        self.assertEqual(len(m.GLM_ACTIONS - {"article_polish", "article_editorial_preparation"}),11)
        self.assertEqual(m.DEEPSEEK_ACTIONS, {"p0_draft", "p0_edit", "p0_style", "p0_titles", "article_draft", "article_edit", "article_titles", "p0_repair", "article_repair"})
        with patch.dict(os.environ, {'FRONTMIND_DEEPSEEK_MODEL':'deepseek-flash','FRONTMIND_CONTROLLER_PROVIDER':'fake','FRONTMIND_ZHIPU_REASONING_EFFORT':'high','FRONTMIND_DEEPSEEK_REASONING_EFFORT':'max'}):
            for action in m.GLM_ACTIONS | m.DEEPSEEK_ACTIONS:
                p=m.build_payload(action,'json task')
                self.assertEqual(p['model'],'glm-5.3' if action in m.GLM_ACTIONS else 'deepseek-v4-pro')
                self.assertEqual(p['reasoning_effort'],'max' if action in m.GLM_ACTIONS else 'high');self.assertEqual(p['thinking']['type'],'enabled')
                self.assertEqual(p['max_tokens'],131072 if action in {'p0_finalize','article_finalize'} else 65536);self.assertTrue(p['stream'])
                self.assertFalse({'speed','temperature','standard'} & set(p))
                self.assertEqual(m.profile_for(action)['timeout_seconds'],300)

    def test_finalize_output_capacity_invalidates_only_finalize_request_cache(self):
        profiles={action:m.profile_for(action) for action in m.GLM_ACTIONS | m.DEEPSEEK_ACTIONS}
        current={action:m.request_fingerprint(action,'unchanged complete input') for action in profiles}
        with patch.object(m,'profile_for',side_effect=lambda action:{**profiles[action],'max_tokens':65536}):
            previous={action:m.request_fingerprint(action,'unchanged complete input') for action in profiles}
        self.assertEqual({action for action in profiles if current[action]!=previous[action]},
                         {'p0_finalize','article_finalize'})
        self.assertEqual({a:m.profile_for(a)['max_tokens'] for a in ('p0_finalize','article_finalize')},
                         {'p0_finalize':131072,'article_finalize':131072})

    def test_editor_role_changes_only_two_blueprint_requests_and_fingerprints(self):
        actions=m.GLM_ACTIONS | m.DEEPSEEK_ACTIONS
        prompt='Same current brief and complete selected example: start middle end'
        definitions=FakeTools().definitions()
        current={action:m.build_payload(action,prompt,tools=definitions) for action in actions}
        fingerprints={action:m.request_fingerprint(action,prompt,tool_definitions=definitions,
                         context_hash='unchanged-inputs') for action in actions}
        selector=m.system_prompt_for
        with patch.object(m,'system_prompt_for',side_effect=lambda action:
                          m.GLM_SYSTEM if action in {'p0_blueprint','article_blueprint'} else selector(action)):
            previous={action:m.build_payload(action,prompt,tools=definitions) for action in actions}
            old_fingerprints={action:m.request_fingerprint(action,prompt,tool_definitions=definitions,
                                 context_hash='unchanged-inputs') for action in actions}
        expected={'p0_blueprint','article_blueprint'}
        self.assertEqual({action for action in actions if current[action]!=previous[action]},expected)
        self.assertEqual({action for action in actions if fingerprints[action]!=old_fingerprints[action]},expected)
        for action in expected:
            self.assertEqual(current[action]['messages'][0],{'role':'system','content':m.GLM_BLUEPRINT_SYSTEM})
            self.assertTrue(m.GLM_BLUEPRINT_SYSTEM.endswith(m.GLM_SYSTEM))
            current[action]['messages'][0]=previous[action]['messages'][0]
            self.assertEqual(current[action],previous[action])

    def test_writer_and_editor_roles_change_only_six_historical_systems_and_fingerprints(self):
        actions=(m.GLM_ACTIONS | m.DEEPSEEK_ACTIONS) - {"p0_style"}
        prompt='Complete confirmed task, selected facts, example and manuscript'
        profiles={action:m.profile_for(action) for action in actions}
        current={action:m.build_payload(action,prompt) for action in actions}
        fingerprints={action:m.request_fingerprint(action,prompt,context_hash='same-inputs') for action in actions}
        def previous_role(action):
            if action in {'p0_blueprint','article_blueprint'}:return m.GLM_BLUEPRINT_SYSTEM
            if action in {'p0_titles','article_titles'}:return m.DEEPSEEK_TITLES_SYSTEM
            if action.endswith('_title_review'):return m.GLM_TITLE_REVIEW_SYSTEM
            return m.GLM_SYSTEM if action in m.GLM_ACTIONS else m.DEEPSEEK_SYSTEM
        with patch.object(m,'system_prompt_for',side_effect=previous_role):
            previous={action:m.build_payload(action,prompt) for action in actions}
            old_fingerprints={action:m.request_fingerprint(action,prompt,context_hash='same-inputs') for action in actions}
        expected={prefix+'_'+stage for prefix in ('p0','article') for stage in ('draft','edit','finalize')}
        self.assertEqual({a for a in actions if current[a]!=previous[a]},expected)
        self.assertEqual({a for a in actions if fingerprints[a]!=old_fingerprints[a]},expected)
        for action in actions:
            self.assertEqual(profiles[action],m.profile_for(action))
            if action in expected:
                current[action]['messages'][0]=previous[action]['messages'][0]
                self.assertEqual(current[action],previous[action])

    def test_actual_writer_and_finalize_payloads_keep_action_role_and_full_task(self):
        expected={'draft':m.DEEPSEEK_DRAFT_SYSTEM,'edit':m.DEEPSEEK_EDIT_SYSTEM,'finalize':m.GLM_FINALIZE_SYSTEM}
        for prefix in ('p0','article'):
            for stage,system in expected.items():
                action=prefix+'_'+stage
                with self.subTest(action=action):
                    payloads=[];prompt='Full task\nFact beginning middle end\nExample beginning middle end\nActual manuscript'
                    def transport(profile,key,payload):
                        payloads.append(json.loads(json.dumps(payload)))
                        if stage=='finalize':
                            if len(payloads)==1:return tool_stream('read_material',{'artifact_id':'one'})
                            if len(payloads)==2:return tool_stream('submit_result',{'result':{'ok':True}})
                            return stream(content='{"submitted":true}',model='glm-5.3')
                        return stream(model='deepseek-v4-pro')
                    result=m.run_action(self.root,self.job,action,prompt,valid,transport=transport,
                                        offline=True,host_tools=FakeTools() if stage=='finalize' else None)
                    self.assertEqual(result,{'ok':True})
                    self.assertEqual(len(payloads),3 if stage=='finalize' else 1)
                    for payload in payloads:
                        self.assertEqual(payload['messages'][:2],[{'role':'system','content':system},{'role':'user','content':prompt}])
                        self.assertEqual(sum(row['role']=='system' for row in payload['messages']),1)

    def test_blueprint_editor_system_and_complete_prompt_persist_through_tool_turns(self):
        for action in ('p0_blueprint','article_blueprint'):
            with self.subTest(action=action):
                tools=FakeTools();payloads=[]
                prompt='Current brief\nExample start\nExample middle\nExample end'
                def transport(profile,key,payload):
                    payloads.append(json.loads(json.dumps(payload)))
                    if len(payloads)==1: return tool_stream('read_material',{'artifact_id':'one'})
                    if len(payloads)==2: return tool_stream('submit_result',{'result':{'ok':True}})
                    return stream(content='{"submitted":true}',model='glm-5.3')
                result=m.run_action(self.root,self.job,action,prompt,valid,
                                    transport=transport,offline=True,host_tools=tools)
                self.assertEqual(result,{'ok':True});self.assertEqual(len(payloads),3)
                for payload in payloads:
                    self.assertEqual(payload['messages'][:2],[
                        {'role':'system','content':m.GLM_BLUEPRINT_SYSTEM},
                        {'role':'user','content':prompt}])
                    self.assertEqual(sum(message['role']=='system' for message in payload['messages']),1)
                self.assertEqual(json.loads(payloads[1]['messages'][-1]['content'])['text'],'start middle end')
                self.assertEqual(payloads[-1]['tool_choice'],'none')

    def test_blueprint_system_change_starts_fresh_and_new_success_recovers_without_call(self):
        for action in ('p0_blueprint','article_blueprint'):
            with self.subTest(action=action):
                old_calls=[]
                def interrupted(profile,key,payload):
                    old_calls.append(json.loads(json.dumps(payload)))
                    if len(old_calls)==1: return tool_stream('read_material',{'artifact_id':'one'})
                    raise OSError('offline simulated interrupted response')
                with patch.object(m,'system_prompt_for',return_value=m.GLM_SYSTEM):
                    with self.assertRaises(m.ProviderActionError):
                        m.run_action(self.root,self.job,action,'same complete input',valid,
                                     transport=interrupted,offline=True,host_tools=FakeTools())
                previous=m.action_record(self.job,action)
                previous_path=self.job/'provider'/action/'runtime/attempts'/previous['attempt_id']/'execution.json'
                original=previous_path.read_bytes()
                new_calls=[]
                def complete(profile,key,payload):
                    new_calls.append(json.loads(json.dumps(payload)))
                    if len(new_calls)==1:
                        self.assertEqual(payload['messages'],[
                            {'role':'system','content':m.GLM_BLUEPRINT_SYSTEM},
                            {'role':'user','content':'same complete input'}])
                        return tool_stream('read_material',{'artifact_id':'one'})
                    return stream(model='glm-5.3')
                result=m.run_action(self.root,self.job,action,'same complete input',valid,retry=True,
                                    transport=complete,offline=True,host_tools=FakeTools())
                current=m.action_record(self.job,action)
                self.assertNotEqual(previous['fingerprint'],current['fingerprint'])
                self.assertNotIn('resumed_tools_from_attempt',current)
                self.assertEqual(previous_path.read_bytes(),original)
                cached=m.run_action(self.root,self.job,action,'same complete input',valid,
                                    transport=complete,offline=True,host_tools=FakeTools())
                self.assertEqual(cached,result);self.assertEqual(len(new_calls),2)

    def _failed_inline_submission(self, prompt='Entire selected example', *, production=False):
        from host_tools import HostTools
        tools=HostTools(self.root,self.job,'p0_finalize')
        tools.register_text('Entire selected example','Example','example',True)
        calls=[]
        def generate(*args):
            calls.append(1)
            return tool_stream('submit_result',{'result':{'ok':True,'article_markdown':'original revised body'}})
        if production:
            (self.root/'config').mkdir(exist_ok=True)
            (self.root/'config/zhipu.json').write_text(json.dumps({'api_key':'fake-credential-for-http-boundary-test'}))
        with patch.object(tools,'record_inline_inputs',return_value={}), patch.object(m,'http_events',generate):
            with self.assertRaises(m.ProviderActionError) as error:
                m.run_action(self.root,self.job,'p0_finalize',prompt,valid,
                             **({} if production else {'transport':generate,'offline':True}),host_tools=tools)
        self.assertEqual(error.exception.code,'invalid_result_contract');self.assertEqual(len(calls),1)
        saved=m.action_record(self.job,'p0_finalize');attempt=self.job/'provider/p0_finalize/runtime/attempts'/saved['attempt_id']
        return tools,attempt,(attempt/'execution.json').read_bytes()

    def test_complete_submit_recovers_without_pending_or_network_in_both_execution_modes(self):
        import shutil
        for production in (False, True):
            with self.subTest(production=production):
                shutil.rmtree(self.job);self.job.mkdir()
                tools,old,original_record=self._failed_inline_submission(production=production)
                self.assertFalse((old/'pending_submission.json').exists())
                original_files={p.name:p.read_bytes() for p in old.iterdir() if p.is_file()}
                def no_call(*args):raise AssertionError('complete submit_result requires no new model call')
                kwargs={} if production else {'transport':no_call,'offline':True}
                with patch.object(m,'http_events',no_call):
                    with self.assertRaises(m.ProviderActionError):
                        m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,host_tools=tools,**kwargs)
                    result=m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,
                                        retry=True,host_tools=tools,**kwargs)
                    self.assertEqual(result,{'ok':True,'article_markdown':'original revised body'})
                    current=m.action_record(self.job,'p0_finalize')
                    self.assertEqual(current['recovered_from_attempt'],old.name)
                    self.assertEqual(current['model_calls'],0)
                    self.assertEqual(current['rounds'],[])
                    self.assertIn('round_01_stream.jsonl',current['source_artifacts_sha256'])
                    current_path=old.parent/current['attempt_id']/'execution.json'
                    recovery_bytes=current_path.read_bytes()
                    cached=m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,host_tools=tools,**kwargs)
                    self.assertEqual(cached,result)
                    self.assertEqual(current_path.read_bytes(),recovery_bytes)
                self.assertEqual({p.name:p.read_bytes() for p in old.iterdir() if p.is_file()},original_files)

    def test_inline_read_recovery_cannot_turn_summary_into_full_read_or_generate_again(self):
        tools,old,original_record=self._failed_inline_submission('Entire example')
        calls=[]
        def no_generation(*args):calls.append(1);return stream(model='glm-5.3')
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_finalize','Entire example',valid,retry=True,transport=no_generation,offline=True,host_tools=tools)
        self.assertEqual(error.exception.code,'saved_submission_not_recoverable');self.assertEqual(calls,[])
        self.assertEqual((old/'execution.json').read_bytes(),original_record)

    def test_recovery_does_not_trust_forged_checkpoint_read_ranges(self):
        tools,old,_=self._failed_inline_submission('Only a summary')
        checkpoint=old/'checkpoint.json';state=json.loads(checkpoint.read_text())
        artifact=next(iter(tools._required));body=tools._text(tools.resolve_artifact(artifact))
        state['host_tools']['read_ranges']={artifact:[[0,len(body)]]}
        checkpoint.write_text(json.dumps(state))
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_finalize','Only a summary',valid,retry=True,
                         transport=lambda *a:(_ for _ in ()).throw(AssertionError('no paid retry')),
                         offline=True,host_tools=tools)
        self.assertEqual(error.exception.code,'saved_submission_not_recoverable')

    def test_recovery_rebuilds_full_reads_from_real_tool_receipts(self):
        from host_tools import HostTools
        tools=HostTools(self.root,self.job,'p0_finalize')
        artifact=tools.register_text('Full example beginning middle ending','Example','example',True)
        calls=[]
        def generate(*args):
            calls.append(1)
            if len(calls)==1:return tool_stream('read_material',{'artifact_id':artifact})
            return tool_stream('submit_result',{'result':{'ok':True}})
        def old_contract(value):raise ValueError('original contract implementation rejected complete result')
        with self.assertRaises(m.ProviderActionError):
            m.run_action(self.root,self.job,'p0_finalize','Read the registered example',old_contract,
                         transport=generate,offline=True,host_tools=tools)
        def no_call(*a):raise AssertionError('must not regenerate')
        result=m.run_action(self.root,self.job,'p0_finalize','Read the registered example',valid,retry=True,
                            transport=no_call,offline=True,host_tools=tools)
        self.assertEqual(result,{'ok':True});self.assertEqual(len(calls),2)
        self.assertEqual(tools.read_ranges[artifact],[(0,len('Full example beginning middle ending'))])

    def test_complete_submit_recovery_checks_stream_request_checkpoint_and_optional_pending(self):
        import shutil
        for target in ('response','stream','request','checkpoint','pending'):
            with self.subTest(target=target):
                shutil.rmtree(self.job);self.job.mkdir()
                tools,old,original_record=self._failed_inline_submission()
                if target == 'response':
                    path=old/'round_01_response.json';value=json.loads(path.read_text())
                    value['tool_calls'][0]['function']['arguments']=json.dumps({'result':{'ok':True,'article_markdown':'changed'}})
                    path.write_text(json.dumps(value))
                elif target == 'stream':
                    path=old/'round_01_stream.jsonl'
                    path.write_text(path.read_text().replace('original revised body','changed source article'))
                elif target == 'request':
                    path=old/'round_01_request.json';value=json.loads(path.read_text())
                    value['reasoning_effort']='high';path.write_text(json.dumps(value))
                elif target == 'checkpoint':
                    path=old/'checkpoint.json';value=json.loads(path.read_text())
                    value['messages'][1]['content']='substituted request';path.write_text(json.dumps(value))
                else:
                    (old/'pending_submission.json').write_text('{"ok":true,"article_markdown":"handwritten replacement"}')
                calls=[]
                def no_generation(*args):calls.append(1);return stream(model='glm-5.3')
                with self.assertRaises(m.ProviderActionError) as error:
                    m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,retry=True,
                                 transport=no_generation,offline=True,host_tools=tools)
                self.assertEqual(error.exception.code,'saved_submission_not_recoverable')
                self.assertEqual(calls,[])
                self.assertEqual((old/'execution.json').read_bytes(),original_record)

    def test_zero_call_recovery_cache_rejects_changed_result_or_original_evidence(self):
        import shutil
        for target in ('parsed','validated','source_request','source_stream','source_checkpoint'):
            with self.subTest(target=target):
                shutil.rmtree(self.job);self.job.mkdir()
                tools,old,_=self._failed_inline_submission()
                def no_call(*a):raise AssertionError('unexpected model call')
                result=m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,
                                    retry=True,transport=no_call,offline=True,host_tools=tools)
                current=m.action_record(self.job,'p0_finalize');saved=old.parent/current['attempt_id']
                if target in {'parsed','validated'}:
                    (saved/(target+'_result.json')).write_text(json.dumps({**result,'article_markdown':'unrecorded replacement'}))
                else:
                    path=old/{'source_request':'round_01_request.json','source_stream':'round_01_stream.jsonl',
                              'source_checkpoint':'checkpoint.json'}[target]
                    path.write_text(path.read_text()+'\n')
                with self.assertRaises(m.ProviderActionError) as error:
                    m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,
                                 transport=no_call,offline=True,host_tools=tools)
                self.assertEqual(error.exception.code,'cached_result_invalid')

    def test_explicit_retry_finds_complete_submission_behind_later_network_failure(self):
        tools,old,original_record=self._failed_inline_submission(production=True)
        # A historical retry from an older runtime timed out before receiving
        # any result. Preserve both attempts; do not move or hide latest.json.
        previous=json.loads(original_record);runtime=old.parent.parent
        network=old.parent/'zz_historical_network_failure';network.mkdir()
        network_record={**previous,'attempt_id':network.name,'rounds':[],
                        'error':{'code':'network_timeout','message':'historical timeout'}}
        (network/'execution.json').write_text(json.dumps(network_record))
        m._atomic(runtime/'latest.json',{'attempt_id':network.name,'fingerprint':previous['fingerprint']})
        network_bytes=(network/'execution.json').read_bytes()
        with patch.object(m,'http_events',side_effect=AssertionError('must recover complete older submission')):
            with self.assertRaises(m.ProviderActionError) as error:
                m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,host_tools=tools)
            self.assertEqual(error.exception.code,'network_timeout')
            result=m.run_action(self.root,self.job,'p0_finalize','Entire selected example',valid,retry=True,host_tools=tools)
        self.assertEqual(result['article_markdown'],'original revised body')
        recovered=m.action_record(self.job,'p0_finalize')
        self.assertEqual(recovered['recovered_from_attempt'],old.name)
        self.assertEqual(recovered['model_calls'],0)
        self.assertEqual((old/'execution.json').read_bytes(),original_record)
        self.assertEqual((network/'execution.json').read_bytes(),network_bytes)

    def test_stream_separates_reasoning_and_usage(self):
        r=m.collect_stream(stream(), 'deepseek-v4-pro')
        self.assertEqual(r['content'],'{"ok":true}')
        self.assertEqual(r['reasoning_content'],'private thought')
        self.assertEqual(r['usage']['total_tokens'],15)

    def test_tool_arguments_assembled_before_execution(self):
        r=m.collect_stream(tool_stream('read_material',{'artifact_id':'one'}),'glm-5.3')
        self.assertEqual(json.loads(r['tool_calls'][0]['function']['arguments']),{'artifact_id':'one'})
        self.assertEqual(r['finish_reason'],'tool_calls')

    def test_incomplete_and_wrong_identity_never_complete(self):
        cases=[(list(stream())[:-1],'incomplete_stream'),(stream(model='deepseek-flash'),'model_mismatch'),(stream(finish='length'),'incomplete_response')]
        for events, code in cases:
            with self.assertRaises(m.ProviderActionError) as error: m.collect_stream(events,'deepseek-v4-pro')
            self.assertEqual(error.exception.code,code)

    def test_length_failure_keeps_actual_stream_metadata_without_a_success_cache(self):
        for action in ('p0_finalize','p0_edit'):
            with self.subTest(action=action):
                calls=[];tools=FakeTools();tools.read=True
                model='glm-5.3' if action=='p0_finalize' else 'deepseek-v4-pro'
                usage={'prompt_tokens':20745,'completion_tokens':65536,'total_tokens':86281,
                       'completion_tokens_details':{'reasoning_tokens':65455}}
                def truncated(*args):
                    calls.append(1)
                    events=list(stream(content='{"ok":true}',model=model,finish='length',reasoning='private text stays in original raw stream only'))
                    events[-2]['usage']=usage
                    return events
                with self.assertRaises(m.ProviderActionError) as error:
                    m.run_action(self.root,self.job,action,'task',valid,transport=truncated,offline=True,host_tools=tools if action.endswith('finalize') else None)
                self.assertEqual(error.exception.code,'incomplete_response')
                self.assertFalse(error.exception.recoverable_edit)
                record=m.action_record(self.job,action);self.assertEqual(record['status'],'failed')
                observed=record['rounds'][0]
                self.assertEqual(observed['response_id'],'test-id');self.assertEqual(observed['returned_model'],model)
                self.assertEqual(observed['finish_reason'],'length');self.assertTrue(observed['stream_done']);self.assertFalse(observed['complete'])
                self.assertEqual(observed['usage'],usage);self.assertNotIn('reasoning_content',observed)
                attempt=self.job/'provider'/action/'runtime/attempts'/record['attempt_id']
                self.assertEqual(json.loads((attempt/'round_01_stream_status.json').read_text()),observed)
                self.assertNotIn('private text',json.dumps(observed))
                for name in ('round_01_response.json','parsed_result.json','validated_result.json','raw_content.txt'):
                    self.assertFalse((attempt/name).exists(),name)
                original=(attempt/'execution.json').read_bytes()
                with self.assertRaises(m.ProviderActionError):
                    m.run_action(self.root,self.job,action,'task',valid,transport=truncated,offline=True,host_tools=tools if action.endswith('finalize') else None)
                self.assertEqual(len(calls),1);self.assertEqual((attempt/'execution.json').read_bytes(),original)

    def test_missing_done_and_wrong_model_metadata_do_not_infer_completion(self):
        cases=[('no_done',lambda:list(stream())[:-1],'incomplete_stream','deepseek-v4-pro','stop'),
               ('wrong_model',lambda:stream(model='deepseek-flash'),'model_mismatch','deepseek-flash',None)]
        for label,events,code,returned,finish in cases:
            with self.subTest(label=label):
                with self.assertRaises(m.ProviderActionError) as error:
                    m.run_action(self.root,self.job,'p0_draft',label,valid,transport=lambda *a:events(),offline=True)
                self.assertEqual(error.exception.code,code)
                observed=m.action_record(self.job,'p0_draft')['rounds'][0]
                self.assertEqual(observed['returned_model'],returned);self.assertEqual(observed['finish_reason'],finish)
                self.assertFalse(observed['stream_done']);self.assertFalse(observed['complete'])

    def test_thinking_only_not_valid_business_result(self):
        transport=lambda *args: stream(content='')
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        self.assertEqual(error.exception.code,'invalid_result_json')

    def test_production_rejects_injected_results_and_missing_key(self):
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_draft','task',valid,transport=lambda *a:stream())
        self.assertEqual(error.exception.code,'production_transport_override')
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_draft','task',valid)
        self.assertEqual(error.exception.code,'missing_api_key')

    def test_glm_tool_conversation_preserves_reasoning_and_requires_stop(self):
        tools=FakeTools();payloads=[]
        def transport(profile,key,payload):
            payloads.append(json.loads(json.dumps(payload)))
            if len(payloads)==1: return tool_stream('read_material',{'artifact_id':'one'})
            if len(payloads)==2: return tool_stream('submit_result',{'result':{'ok':True}})
            return stream(model='glm-5.3')
        result=m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertTrue(result['ok']);self.assertEqual(len(payloads),3)
        self.assertEqual(payloads[1]['messages'][2]['reasoning_content'],'preserved tool thought')
        self.assertEqual(payloads[1]['messages'][3]['role'],'tool')
        self.assertEqual(payloads[2]['tool_choice'],'none')
        self.assertEqual(m.action_record(self.job,'p0_blueprint')['tool_calls'],2)

    def test_host_cannot_finish_before_required_read(self):
        with self.assertRaises(m.ProviderActionError):
            m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=lambda *a:stream(model='glm-5.3'),offline=True,host_tools=FakeTools())

    def test_source_read_contract_applies_to_new_results_and_cache(self):
        class SourceTools(FakeTools):
            blocked = False
            checks = 0
            def validate_result_sources(self, value):
                self.checks += 1
                if self.blocked:
                    raise ValueError('selected source was not read')
        tools = SourceTools()
        calls = []
        def transport(*args):
            calls.append(1)
            if len(calls) == 1:
                return tool_stream('read_material', {'artifact_id': 'one'})
            return stream(model='glm-5.3')
        m.run_action(self.root, self.job, 'p0_blueprint', 'task', valid,
                     transport=transport, offline=True, host_tools=tools)
        self.assertEqual(tools.checks, 1)
        tools.blocked = True
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root, self.job, 'p0_blueprint', 'task', valid,
                         transport=transport, offline=True, host_tools=tools)
        self.assertEqual(error.exception.code, 'cached_result_invalid')
        self.assertEqual(tools.checks, 2)
        self.assertEqual(len(calls), 2)

    def test_success_cache_revalidates_without_paid_call(self):
        calls=[]
        def transport(*args): calls.append(1);return stream()
        a=m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        b=m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        self.assertEqual(a,b);self.assertEqual(len(calls),1)
        def reject(value): raise ValueError('changed contract')
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_draft','task',reject,transport=transport,offline=True)
        self.assertEqual(error.exception.code,'cached_result_invalid');self.assertEqual(len(calls),1)

    def test_failed_call_requires_explicit_retry_and_keeps_history(self):
        calls=[]
        def transport(*args): calls.append(1);return stream(content='bad' if len(calls)==1 else '{"ok":true}')
        for _ in range(2):
            with self.assertRaises(m.ProviderActionError):
                m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        self.assertEqual(len(calls),1)
        result=m.run_action(self.root,self.job,'p0_draft','task',valid,retry=True,transport=transport,offline=True)
        self.assertTrue(result['ok']);self.assertEqual(len(calls),2)
        records=list((self.job/'provider/p0_draft/runtime/attempts').glob('*/execution.json'))
        self.assertEqual(len(records),2)
        self.assertEqual({json.loads(x.read_text())['status'] for x in records},{'failed','succeeded'})

    def test_complete_but_invalid_e8_is_recoverable_not_network_failure(self):
        for action in ('p0_edit','article_edit'):
            with self.assertRaises(m.ProviderActionError) as error:
                m.run_action(self.root,self.job,action,'task',valid,transport=lambda *a:stream(content='{"article_markdown":"candidate body"}'),offline=True)
            self.assertTrue(error.exception.recoverable_edit)
            self.assertIn('candidate body',error.exception.readable_candidate)
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_edit','different prompt',valid,transport=lambda *a:list(stream())[:-1],offline=True)
        self.assertFalse(error.exception.recoverable_edit)

    def test_complete_writer_revalidates_without_call_or_mutating_failed_attempt(self):
        candidate = {"article_markdown": "完整正文", "requires_reconfirmation": False,
                     "reconfirmation_reason": None}
        def original_validator(value):
            if not isinstance(value.get("reconfirmation_reason"), str):
                raise ValueError("reconfirmation_reason must be text")
            return value
        def corrected_validator(value):
            value = dict(value)
            if value.get("requires_reconfirmation") is False and value.get("reconfirmation_reason") is None:
                value["reconfirmation_reason"] = ""
            return original_validator(value)
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root, self.job, "article_edit", "same complete manuscript", original_validator,
                         transport=lambda *args: stream(content=json.dumps(candidate)), offline=True)
        self.assertEqual(error.exception.code, "invalid_result_contract")
        previous = m.action_record(self.job, "article_edit")
        original = self.job / "provider/article_edit/runtime/attempts" / previous["attempt_id"]
        original_files = {p.name: p.read_bytes() for p in original.iterdir() if p.is_file()}
        calls = []
        def no_call(*args):
            calls.append(1)
            raise AssertionError("complete writer response must not generate again")
        with self.assertRaises(m.ProviderActionError):
            m.run_action(self.root, self.job, "article_edit", "same complete manuscript", corrected_validator,
                         transport=no_call, offline=True)
        result = m.run_action(self.root, self.job, "article_edit", "same complete manuscript", corrected_validator,
                              retry=True, transport=no_call, offline=True)
        self.assertEqual(result, {**candidate, "reconfirmation_reason": ""})
        recovered = m.action_record(self.job, "article_edit")
        self.assertEqual(recovered["recovered_from_attempt"], previous["attempt_id"])
        self.assertEqual(recovered["model_calls"], 0)
        self.assertEqual(recovered["rounds"], [])
        self.assertEqual(recovered["recovery_reason"], "complete_writer_result_verified_against_original_request_and_stream")
        self.assertEqual(m.run_action(self.root, self.job, "article_edit", "same complete manuscript", corrected_validator,
                                     transport=no_call, offline=True), result)
        self.assertEqual(m.action_record(self.job, "article_edit"), recovered)
        self.assertEqual(calls, [])
        self.assertEqual({p.name: p.read_bytes() for p in original.iterdir() if p.is_file()}, original_files)

    def test_writer_incomplete_stream_requires_a_new_call_on_explicit_retry(self):
        with self.assertRaises(m.ProviderActionError):
            m.run_action(self.root, self.job, "article_edit", "same complete manuscript", valid,
                         transport=lambda *args: list(stream())[:-1], offline=True)
        previous = m.action_record(self.job, "article_edit")
        original = self.job / "provider/article_edit/runtime/attempts" / previous["attempt_id"]
        original_files = {p.name: p.read_bytes() for p in original.iterdir() if p.is_file()}
        calls = []
        def complete(*args):
            calls.append(1)
            return stream()
        self.assertEqual(m.run_action(self.root, self.job, "article_edit", "same complete manuscript", valid,
                                      retry=True, transport=complete, offline=True), {"ok": True})
        self.assertEqual(calls, [1])
        self.assertNotIn("recovered_from_attempt", m.action_record(self.job, "article_edit"))
        self.assertEqual({p.name: p.read_bytes() for p in original.iterdir() if p.is_file()}, original_files)

    def test_parsed_result_survives_interrupted_state_write(self):
        calls=[]
        def transport(*args):calls.append(1);return stream()
        m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        record=m.action_record(self.job,'p0_draft');record['status']='running'
        path=self.job/'provider/p0_draft/runtime/attempts'/record['attempt_id']/'execution.json'
        path.write_text(json.dumps(record))
        result=m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        self.assertTrue(result['ok']);self.assertEqual(len(calls),1)

    def test_incomplete_host_result_only_reruns_on_explicit_retry(self):
        calls=[]; tools=FakeTools();tools.read=True
        def transport(*args):
            calls.append(1)
            return stream(content=json.dumps({'outcome':'incomplete' if len(calls)==1 else 'accepted'}),model='glm-5.3')
        validator=lambda value:value
        first=m.run_action(self.root,self.job,'p0_finalize','task',validator,transport=transport,offline=True,host_tools=tools)
        same=m.run_action(self.root,self.job,'p0_finalize','task',validator,transport=transport,offline=True,host_tools=tools)
        last=m.run_action(self.root,self.job,'p0_finalize','task',validator,retry=True,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(first,same);self.assertEqual(last['outcome'],'accepted');self.assertEqual(len(calls),2)

    def test_prompt_changes_invalidate_cache(self):
        calls=[]
        def transport(*a):calls.append(1);return stream()
        for prompt in ('one','two'):
            m.run_action(self.root,self.job,'p0_draft',prompt,valid,transport=transport,offline=True)
        self.assertEqual(len(calls),2)

    def test_round_limit_stops_instead_of_fake_result(self):
        with patch.object(m,'MAX_ROUNDS',2):
            with self.assertRaises(m.ProviderActionError) as error:
                m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=lambda *a:tool_stream('read_material',{'artifact_id':'one'}),offline=True,host_tools=FakeTools())
        self.assertEqual(error.exception.code,'round_limit')

    def test_raw_completed_response_recovers_before_parsed_state_commit(self):
        calls=[]
        def transport(*args):calls.append(1);return stream()
        m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        record=m.action_record(self.job,'p0_draft');record['status']='running'
        saved=self.job/'provider/p0_draft/runtime/attempts'/record['attempt_id']
        (saved/'execution.json').write_text(json.dumps(record))
        (saved/'parsed_result.json').unlink()
        result=m.run_action(self.root,self.job,'p0_draft','task',valid,transport=transport,offline=True)
        self.assertTrue(result['ok']);self.assertEqual(len(calls),1)

    def test_contract_valid_tampered_result_is_not_cache_success(self):
        m.run_action(self.root,self.job,'p0_draft','task',valid,transport=lambda *a:stream(),offline=True)
        record=m.action_record(self.job,'p0_draft')
        saved=self.job/'provider/p0_draft/runtime/attempts'/record['attempt_id']
        (saved/'parsed_result.json').write_text('{"ok":true,"tampered":true}')
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_draft','task',valid,transport=lambda *a:stream(),offline=True)
        self.assertEqual(error.exception.code,'cached_result_invalid')

    def test_explicit_retry_reuses_completed_tool_read(self):
        first=FakeTools();calls=[]
        def failing(profile,key,payload):
            calls.append(1)
            if len(calls)==1:return tool_stream('read_material',{'artifact_id':'one'})
            return list(stream(model='glm-5.3'))[:-1]
        with self.assertRaises(m.ProviderActionError):
            m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=failing,offline=True,host_tools=first)
        resumed=FakeTools();payloads=[]
        def success(profile,key,payload):
            payloads.append(json.loads(json.dumps(payload)))
            return stream(model='glm-5.3')
        result=m.run_action(self.root,self.job,'p0_blueprint','task',valid,retry=True,transport=success,offline=True,host_tools=resumed)
        self.assertTrue(result['ok']);self.assertTrue(resumed.read)
        self.assertEqual(len(payloads),1)
        self.assertEqual(payloads[0]['messages'][-1]['role'],'tool')
        self.assertIn('resumed_tools_from_attempt',m.action_record(self.job,'p0_blueprint'))

    def test_final_stop_cannot_change_submitted_result(self):
        tools=FakeTools();tools.read=True;calls=[]
        def transport(*args):
            calls.append(1)
            if len(calls)==1:return tool_stream('submit_result',{'result':{'ok':True}})
            return stream(content='{"ok":true,"changed":true}',model='glm-5.3')
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(error.exception.code,'submitted_result_mismatch')

    def test_added_source_invalidates_host_but_unrelated_log_does_not(self):
        tools=FakeTools();tools.read=True;calls=[]
        def transport(*a): calls.append(1);return stream(model='glm-5.3')
        m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        (self.job/'logs').mkdir();(self.job/'logs/debug.txt').write_text('unrelated log')
        m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(len(calls),1)
        (self.job/'materials').mkdir();(self.job/'materials/new.txt').write_text('new source input')
        m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(len(calls),2)

    def test_approval_timestamp_does_not_invalidate_semantic_decision(self):
        state={'decisions':{'comparison_scope':{'comparison_targets':['c001'],'revision':3,'confirmed_at':'old'}}}
        (self.job/'job_state.json').write_text(json.dumps(state))
        before=m.context_fingerprint(self.job,'positioning_value_synthesis')
        state['decisions']['comparison_scope'].update(revision=4,confirmed_at='new')
        (self.job/'job_state.json').write_text(json.dumps(state))
        self.assertEqual(before,m.context_fingerprint(self.job,'positioning_value_synthesis'))
        state['decisions']['comparison_scope']['comparison_targets']=['c002']
        (self.job/'job_state.json').write_text(json.dumps(state))
        self.assertNotEqual(before,m.context_fingerprint(self.job,'positioning_value_synthesis'))

    def test_invalid_finalize_submission_stops_without_second_correction(self):
        tools=FakeTools();tools.read=True;calls=[]
        def transport(*a):calls.append(1);return tool_stream('submit_result',{'result':{'ok':False}})
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_finalize','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(error.exception.code,'invalid_result_contract')
        self.assertEqual(len(calls),1)

    def test_finalize_does_not_reopen_raw_material_selection(self):
        tools=FakeTools();tools.read=True;calls=[]
        def transport(*a):calls.append(1);return stream(model='glm-5.3')
        m.run_action(self.root,self.job,'p0_finalize','confirmed material prompt',valid,transport=transport,offline=True,host_tools=tools)
        (self.job/'materials').mkdir();(self.job/'materials/unselected.txt').write_text('unselected raw material')
        m.run_action(self.root,self.job,'p0_finalize','confirmed material prompt',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(len(calls),1)

    def test_explicit_research_epoch_changes_only_requested_action(self):
        before_research=m.context_fingerprint(self.job,'positioning_market_research')
        before_synthesis=m.context_fingerprint(self.job,'positioning_value_synthesis')
        before_finalize=m.context_fingerprint(self.job,'p0_finalize')
        (self.job/'job_state.json').write_text(json.dumps({'flags':{'model_action_epochs':{'positioning_market_research':'explicit-user-rerun'}}}))
        self.assertNotEqual(before_research,m.context_fingerprint(self.job,'positioning_market_research'))
        self.assertEqual(before_synthesis,m.context_fingerprint(self.job,'positioning_value_synthesis'))
        self.assertEqual(before_finalize,m.context_fingerprint(self.job,'p0_finalize'))

    def test_glm_single_complete_fence_envelope_only(self):
        for text in ('{"ok":true}', '```json\n{"ok":true}\n```', '  ```JSON\n{"ok":true}\n```  '):
            self.assertEqual(m.parse_business_json(text), {'ok':True})
        for text in ('Here is JSON: {"ok":true}', '```json\n{"ok":true}', '```json\n{"ok":true}\n``` tail', '```json\n{"ok":true}\n```\n```json\n{}\n```'):
            with self.assertRaises(ValueError):m.parse_business_json(text)
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_draft','task',valid,transport=lambda *a:stream(content='```json\n{"ok":true}\n```'),offline=True)
        self.assertEqual(error.exception.code,'invalid_result_json')

    def test_glm_tiny_stop_ack_uses_original_submission_and_cache(self):
        tools=FakeTools();tools.read=True;calls=[]
        def transport(*args):
            calls.append(1)
            if len(calls)==1:return tool_stream('submit_result',{'result':{'ok':True}})
            return stream(content='{"submitted":true}',model='glm-5.3')
        first=m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        again=m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(first,{'ok':True});self.assertEqual(first,again);self.assertEqual(len(calls),2)

    def test_pending_submission_tamper_is_rejected_against_raw_tool(self):
        tools=FakeTools();tools.read=True;calls=[]
        def transport(*args):
            calls.append(1)
            if len(calls)==1:return tool_stream('submit_result',{'result':{'ok':True}})
            return stream(content='{"submitted":true}',model='glm-5.3')
        m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        record=m.action_record(self.job,'p0_blueprint')
        saved=self.job/'provider/p0_blueprint/runtime/attempts'/record['attempt_id']
        (saved/'pending_submission.json').write_text('{"ok":true,"tampered":true}')
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(error.exception.code,'cached_result_invalid');self.assertEqual(len(calls),2)

    def test_explicit_fenced_recovery_adds_zero_call_record_keeps_failure_immutable(self):
        tools=FakeTools();tools.read=True;calls=[]
        def transport(*args):
            calls.append(1)
            if len(calls)==1:return tool_stream('submit_result',{'result':{'ok':True}})
            return stream(content='```json\n{"ok":true}\n```',model='glm-5.3')
        with patch.object(m,'parse_business_json',m.strict_json):
            with self.assertRaises(m.ProviderActionError):
                m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        original=m.action_record(self.job,'p0_blueprint')
        source=self.job/'provider/p0_blueprint/runtime/attempts'/original['attempt_id']
        originals={str(p.relative_to(source)):p.read_bytes() for p in source.rglob('*') if p.is_file()}
        with self.assertRaises(m.ProviderActionError):
            m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        result=m.run_action(self.root,self.job,'p0_blueprint','task',valid,retry=True,transport=transport,offline=True,host_tools=tools)
        recovered=m.action_record(self.job,'p0_blueprint')
        self.assertEqual(result,{'ok':True});self.assertEqual(len(calls),2)
        self.assertEqual(recovered['model_calls'],0)
        self.assertEqual(recovered['recovered_from_attempt'],original['attempt_id'])
        for name, raw in originals.items():self.assertEqual((source/name).read_bytes(),raw)
        self.assertEqual(json.loads((source/'execution.json').read_text())['status'],'failed')
        again=m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=transport,offline=True,host_tools=tools)
        self.assertEqual(result,again);self.assertEqual(len(calls),2)

    def test_ack_without_original_submission_cannot_complete(self):
        tools=FakeTools();tools.read=True
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=lambda *a:stream(content='{"submitted":true}',model='glm-5.3'),offline=True,host_tools=tools)
        self.assertEqual(error.exception.code,'unbound_submission_ack')

    def test_interrupted_ack_reuses_original_submission_and_remains_cacheable(self):
        tools=FakeTools();tools.read=True;calls=[]
        def initial(*args):
            calls.append(1)
            if len(calls)==1:return tool_stream('submit_result',{'result':{'ok':True}})
            return list(stream(content='{"submitted":true}',model='glm-5.3'))[:-1]
        with self.assertRaises(m.ProviderActionError):
            m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=initial,offline=True,host_tools=tools)
        original=m.action_record(self.job,'p0_blueprint')
        retry_calls=[]
        def ack(*args):retry_calls.append(1);return stream(content='{"submitted":true}',model='glm-5.3')
        result=m.run_action(self.root,self.job,'p0_blueprint','task',valid,retry=True,transport=ack,offline=True,host_tools=tools)
        self.assertEqual(result,{'ok':True});self.assertEqual(len(retry_calls),0)
        resumed=m.action_record(self.job,'p0_blueprint')
        self.assertEqual(resumed['recovered_from_attempt'],original['attempt_id'])
        self.assertEqual(resumed['model_calls'],0)
        cached=m.run_action(self.root,self.job,'p0_blueprint','task',valid,transport=ack,offline=True,host_tools=tools)
        self.assertEqual(cached,result);self.assertEqual(len(retry_calls),0)

    def test_blueprint_submit_schema_exposes_materials_and_structural_contract(self):
        for action, kind in (('p0_blueprint','p0'),('article_blueprint','article')):
            tool=m.build_payload(action,'task')['tools'][-1]
            result=tool['function']['parameters']['properties']['result']
            self.assertEqual(set(result['required']),{'kind','article_brief','example_use','opening','sections','ending','writing_material_markdown','writing_material_sources'})
            self.assertEqual(result['properties']['kind']['enum'],[kind])
            self.assertEqual(result['properties']['writing_material_markdown']['type'],'string')
            sources=result['properties']['writing_material_sources']
            self.assertEqual(sources['type'],'array');self.assertEqual(sources['minItems'],1)
            options=sources['items']['anyOf']
            self.assertEqual({x['type'] for x in options},{'object','string'})
            source_object=next(x for x in options if x['type']=='object')
            self.assertEqual(set(source_object['required']),{'source_ref','use'})
            section=result['properties']['sections']['items']
            self.assertEqual(set(section['required']),{'heading','task'})
            self.assertTrue(result['additionalProperties']);self.assertTrue(section['additionalProperties'])

    def test_finalize_submit_schema_exposes_four_outcomes_and_full_result(self):
        for action in ('p0_finalize','article_finalize'):
            result=m.build_payload(action,'task')['tools'][-1]['function']['parameters']['properties']['result']
            self.assertEqual(set(result['required']),{'outcome','article_markdown','editorial_notes','reason'})
            self.assertEqual(set(result['properties']['outcome']['enum']),{'accepted','revised','requires_blueprint_reconfirmation','incomplete'})
            self.assertEqual(result['properties']['article_markdown']['type'],'string')
            self.assertEqual(result['properties']['editorial_notes']['type'],'array')
            self.assertEqual(result['properties']['reason']['type'],'string')
            self.assertTrue(result['additionalProperties'])
        # Building a specialized schema must not mutate the generic contract.
        generic=m.build_payload('positioning_market_research','task')['tools'][-1]
        self.assertNotIn('required',generic['function']['parameters']['properties']['result'])
        self.assertNotIn('tools',m.build_payload('p0_draft','task'))

    def test_finalize_submission_batch_fails_without_another_automatic_correction(self):
        for action in ('p0_finalize','article_finalize'):
            tools=FakeTools();tools.read=True;calls=[]
            def transport(*args):
                calls.append(1)
                if len(calls)==1:
                    batch=[{'index':i,'id':'call-'+str(i),'function':{'name':'submit_result','arguments':json.dumps({'result':{'ok':True,'revision':i}})}} for i in range(2)]
                    return iter([{'model':'glm-5.3','id':'offline','choices':[{'index':0,'delta':{'tool_calls':batch},'finish_reason':'tool_calls'}]},'[DONE]'])
                return stream(model='glm-5.3')
            for _ in range(2):
                with self.assertRaises(m.ProviderActionError) as error:
                    m.run_action(self.root,self.job,action,'task',valid,transport=transport,offline=True,host_tools=tools)
                self.assertEqual(error.exception.code,'invalid_finalize_submission_batch')
            self.assertEqual(len(calls),1)
            failed=m.action_record(self.job,action)
            self.assertEqual(failed['status'],'failed');self.assertEqual(len(failed['rounds']),1)
            result=m.run_action(self.root,self.job,action,'task',valid,retry=True,transport=transport,offline=True,host_tools=tools)
            self.assertTrue(result['ok']);self.assertEqual(len(calls),2)
            records=list((self.job/'provider'/action/'runtime/attempts').glob('*/execution.json'))
            self.assertEqual({json.loads(p.read_text())['status'] for p in records},{'failed','succeeded'})

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ValueError):m.strict_json('{"ok":true,"ok":false}')

    def test_secret_in_prompt_not_written_or_sent(self):
        (self.root/'config').mkdir()
        secret='unit-test-private-key'
        (self.root/'config/deepseek.json').write_text(json.dumps({'api_key':secret}))
        with self.assertRaises(m.ProviderActionError) as error:
            m.run_action(self.root,self.job,'p0_draft','task '+secret,valid,transport=lambda *a:stream(),offline=True)
        self.assertEqual(error.exception.code,'credential_in_prompt')
        self.assertFalse((self.job/'provider').exists())


if __name__=='__main__':unittest.main()
