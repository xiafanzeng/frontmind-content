from scripts.tests_v411.historical_profiles import historical_profile
"""Native Responses execution, original-event recovery, and fixed v4.11.6 routing."""
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'shared'))
from shared import model_runtime as m
from scripts.tests_v411.test_model_runtime import FakeTools, valid, stream


def native(*, name=None, arguments=None, content='{"ok":true}', model='gpt-6-astra', status='completed'):
    output=[{'id':'rs-test','type':'reasoning','summary':[], 'encrypted_content':'opaque-test-reasoning'}]
    yield {'type':'response.created','response':{'id':'resp-test','model':model,'status':'in_progress','output':[]}}
    if name:
        text=json.dumps(arguments,ensure_ascii=False)
        item={'id':'fc-test','type':'function_call','call_id':'call-test','name':name,'arguments':text,'status':'completed'}
        yield {'type':'response.output_item.added','output_index':1,'item':{**item,'arguments':'','status':'in_progress'}}
        n=len(text)//2
        for fragment in (text[:n],text[n:]):
            yield {'type':'response.function_call_arguments.delta','output_index':1,'delta':fragment}
    else:
        item={'id':'msg-test','type':'message','role':'assistant','status':'completed',
              'content':[{'type':'output_text','text':content,'annotations':[]}]}
        yield {'type':'response.output_item.added','output_index':1,'item':{**item,'content':[],'status':'in_progress'}}
        yield {'type':'response.output_text.delta','output_index':1,'content_index':0,'delta':content}
    output.append(item)
    yield {'type':'response.output_item.done','output_index':1,'item':item}
    yield {'type':'response.completed' if status=='completed' else 'response.incomplete',
           'response':{'id':'resp-test','model':model,'status':status,'output':output,
             'usage':{'input_tokens':100,'output_tokens':20,'output_tokens_details':{'reasoning_tokens':10},'total_tokens':120}}}


class ResponsesRuntimeTests(unittest.TestCase):
    def setUp(self):
        archived=patch.object(m, "profile_for", side_effect=historical_profile)
        archived.start(); self.addCleanup(archived.stop)
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)/'package';self.root.mkdir()
        self.job=Path(temp.name)/'job';self.job.mkdir()
    def execute(self, transport, *, action='p0_blueprint', prompt='complete input', retry=False, tools=None, validator=valid):
        return m.run_action(self.root,self.job,action,prompt,validator,retry=retry,
                            host_tools=tools or FakeTools(),transport=transport,offline=True)
    def test_all_routes_fixed_native_astra_high_and_pro_max(self):
        with patch.dict(os.environ,{'FRONTMIND_DEEPSEEK_MODEL':'deepseek-flash','FRONTMIND_ZHIPU_REASONING_EFFORT':'max','FRONTMIND_HOST_MODEL':'other'}):
            self.assertEqual(len(m.HOST_ACTIONS - {"article_polish", "article_editorial_preparation"}),11);self.assertEqual(len(m.DEEPSEEK_ACTIONS - {"p0_repair", "article_repair"}),7)
            for action in m.HOST_ACTIONS:
                payload=m.build_payload(action,'full input')
                self.assertEqual(payload['model'],'gpt-6-astra');self.assertEqual(payload['reasoning'],{'effort':'high'})
                self.assertEqual(payload['max_output_tokens'],65536);self.assertFalse(payload['store'])
                self.assertEqual(payload['include'],['reasoning.encrypted_content'])
                self.assertNotIn('messages',payload);self.assertNotIn('thinking',payload)
                self.assertEqual(m.profile_for(action)['provider'],'xty')
                self.assertFalse({'temperature','speed','standard','reasoning_effort'}&set(payload))
            for action in m.DEEPSEEK_ACTIONS:
                p=m.build_payload(action,'full input')
                self.assertEqual(p['model'],'deepseek-v4-pro');self.assertEqual(p['reasoning_effort'],'max')
                self.assertEqual(p['thinking'],{'type':'enabled'});self.assertNotIn('temperature',p)
        self.assertTrue({'zhipu','deepseek'} <= set(m.configuration_status(self.root)))
    def test_native_parser_matches_fragmented_arguments_and_separates_reasoning(self):
        result=m.collect_model_stream(native(name='read_material',arguments={'artifact_id':'one'}),m.profile_for('p0_blueprint'))
        self.assertEqual(result['wire_api'],'responses');self.assertEqual(result['response_status'],'completed')
        self.assertEqual(result['content'],'');self.assertEqual(result['reasoning_content'],'')
        self.assertEqual(result['response_output'][0]['encrypted_content'],'opaque-test-reasoning')
        self.assertEqual(json.loads(result['tool_calls'][0]['function']['arguments']),{'artifact_id':'one'})
    def test_native_completion_requires_final_event_exact_model_and_complete_state(self):
        for events,code in ((list(native())[:-1],'incomplete_stream'),(native(model='gpt-5.4'),'model_mismatch'),
                            (native(status='incomplete'),'incomplete_response')):
            with self.subTest(code=code),self.assertRaises(m.ProviderActionError) as exc:
                m.collect_model_stream(events,m.profile_for('p0_blueprint'))
            self.assertEqual(exc.exception.code,code)
    def test_native_delta_cannot_differ_from_final_body_or_arguments(self):
        for events in (list(native()),list(native(name='read_material',arguments={'artifact_id':'one'}))):
            for event in events:
                if event['type'].endswith('.delta'):event['delta']='forged'
            with self.assertRaises(m.ProviderActionError) as exc:
                m.collect_model_stream(events,m.profile_for('p0_blueprint'))
            self.assertEqual(exc.exception.code,'stream_result_mismatch')
    def test_reasoning_reencryption_keeps_final_opaque_token_only(self):
        events=list(native())
        final=events[-1]['response']['output'][0]
        done={**final,'encrypted_content':'earlier-opaque-token'}
        events.insert(-1,{'type':'response.output_item.done','output_index':0,'item':done})
        result=m.collect_model_stream(events,m.profile_for('p0_finalize'))
        self.assertEqual(result['response_output'][0],final)
        for key,value in [('summary',[{'type':'summary_text','text':'changed'}]),('id','different'),('encrypted_content',None)]:
            changed=copy.deepcopy(events);changed[-2]['item'][key]=value
            with self.subTest(key=key),self.assertRaises(m.ProviderActionError):
                m.collect_model_stream(changed,m.profile_for('p0_finalize'))

    def omitted_message_id_events(self, *, with_item_done=False, two_parts=False):
        # Synthetic reconstruction of the gateway's final-envelope omission;
        # no real article or reasoning content is embedded in the test.
        parts=['{"ok":', 'true}'] if two_parts else ['{"ok":true}']
        msg={'id':'msg-test','type':'message','role':'assistant','status':'completed',
             'content':[{'type':'output_text','text':text,'annotations':[]} for text in parts]}
        events=[{'type':'response.created','response':{'id':'resp-test','model':'gpt-6-astra','status':'in_progress','output':[]}},
                {'type':'response.output_item.added','output_index':0,'item':{**msg,'content':[],'status':'in_progress'}}]
        for index,text in enumerate(parts):
            cut=max(1,len(text)//2)
            for chunk in (text[:cut],text[cut:]):
                events.append({'type':'response.output_text.delta','output_index':0,'content_index':index,'item_id':'msg-test','delta':chunk})
            events.append({'type':'response.output_text.done','output_index':0,'content_index':index,'item_id':'msg-test','text':text})
        if with_item_done:
            events.append({'type':'response.output_item.done','output_index':0,'item':copy.deepcopy(msg)})
        final={key:value for key,value in msg.items() if key!='id'}
        events.append({'type':'response.completed','response':{'id':'resp-test','model':'gpt-6-astra','status':'completed','output':[final]}})
        return events

    def test_gateway_omitted_message_id_requires_exact_stream_and_preserves_raw_final(self):
        for with_done,two_parts in ((False,False),(True,False),(False,True),(True,True)):
            with self.subTest(with_done=with_done,two_parts=two_parts):
                events=self.omitted_message_id_events(with_item_done=with_done,two_parts=two_parts)
                before=copy.deepcopy(events)
                result=m.collect_model_stream(events,m.profile_for('p0_finalize'))
                self.assertEqual(result['content'],'{"ok":true}')
                self.assertEqual(result['finish_reason'],'stop')
                self.assertEqual(result['response_output'],before[-1]['response']['output'])
                self.assertNotIn('id',result['response_output'][0])
                self.assertEqual(events,before)
                self.assertEqual(result['protocol_observations'][0]['kind'],'completed_message_id_omitted')
                self.assertEqual(result['protocol_observations'][0]['matched_added_item_id'],'msg-test')

    def test_gateway_omission_rejects_conflicting_identity_shape_or_unproved_text(self):
        cases=['different_final_id','empty_final_id','null_final_id','missing_added','missing_added_id',
               'added_type','added_role','final_type','final_role','final_status','delta_item_id','delta_position',
               'delta_content_index','delta_text','missing_delta','missing_text_done','done_item_id','done_position',
               'done_text','extra_done_part','missing_completed','incomplete','wrong_response_id','wrong_model',
               'missing_final_response_id','missing_final_model','duplicate_added_id','item_done_changed','item_done_id']
        for case in cases:
            events=self.omitted_message_id_events(with_item_done=case.startswith('item_done'))
            final=events[-1]['response']['output'][0]
            delta=next(e for e in events if e['type']=='response.output_text.delta')
            done=next(e for e in events if e['type']=='response.output_text.done')
            if case=='different_final_id':final['id']='different'
            elif case=='empty_final_id':final['id']=''
            elif case=='null_final_id':final['id']=None
            elif case=='missing_added':events=[e for e in events if e['type']!='response.output_item.added']
            elif case=='missing_added_id':events[1]['item'].pop('id')
            elif case=='added_type':events[1]['item']['type']='function_call'
            elif case=='added_role':events[1]['item']['role']='user'
            elif case=='final_type':final['type']='function_call'
            elif case=='final_role':final['role']='user'
            elif case=='final_status':final['status']='in_progress'
            elif case=='delta_item_id':delta['item_id']='different'
            elif case=='delta_position':delta['output_index']=1
            elif case=='delta_content_index':delta['content_index']=1
            elif case=='delta_text':delta['delta']='different'
            elif case=='missing_delta':events=[e for e in events if e['type']!='response.output_text.delta']
            elif case=='missing_text_done':events=[e for e in events if e['type']!='response.output_text.done']
            elif case=='done_item_id':done['item_id']='different'
            elif case=='done_position':done['output_index']=1
            elif case=='done_text':done['text']='different'
            elif case=='extra_done_part':events.insert(-1,{**done,'content_index':1})
            elif case=='missing_completed':events.pop()
            elif case=='incomplete':events[-1]['response']['status']='incomplete'
            elif case=='wrong_response_id':events[-1]['response']['id']='different'
            elif case=='wrong_model':events[-1]['response']['model']='different'
            elif case=='missing_final_response_id':events[-1]['response'].pop('id')
            elif case=='missing_final_model':events[-1]['response'].pop('model')
            elif case=='duplicate_added_id':events.insert(2,{'type':'response.output_item.added','output_index':1,'item':copy.deepcopy(events[1]['item'])})
            elif case=='item_done_changed':events[-2]['item']['content'][0]['text']='different'
            elif case=='item_done_id':events[-2]['item']['id']='different'
            with self.subTest(case=case),self.assertRaises(m.ProviderActionError):
                m.collect_model_stream(events,m.profile_for('p0_finalize'))

    def test_gateway_message_exception_does_not_relax_tool_or_reasoning_ids(self):
        events=list(native(name='read_material',arguments={'artifact_id':'one'}))
        events[-1]['response']['output'][1].pop('id')
        with self.assertRaises(m.ProviderActionError):m.collect_model_stream(events,m.profile_for('p0_blueprint'))
        events=list(native());reasoning=copy.deepcopy(events[-1]['response']['output'][0])
        events.insert(1,{'type':'response.output_item.added','output_index':0,'item':reasoning})
        events[-1]['response']['output'][0].pop('id')
        with self.assertRaises(m.ProviderActionError):m.collect_model_stream(events,m.profile_for('p0_blueprint'))

    def test_parser_failed_complete_raw_stream_recovers_without_overwriting_evidence(self):
        from host_tools import HostTools
        tools=HostTools(self.root,self.job,'p0_finalize')
        tools.register_text('Entire example','Example','example',True)
        real=m.collect_model_stream
        def old_parser(events,profile,on_event=None):
            real(events,profile,on_event)
            raise m.ProviderActionError('stream_result_mismatch','old opaque-token comparison')
        with patch.object(m,'collect_model_stream',side_effect=old_parser):
            with self.assertRaises(m.ProviderActionError):
                self.execute(lambda *a:native(name='submit_result',arguments={'result':{'ok':True,'article_markdown':'body'}}),
                    action='p0_finalize',prompt='Entire example',tools=tools)
        record=m.action_record(self.job,'p0_finalize')
        attempt=self.job/'provider/p0_finalize/runtime/attempts'/record['attempt_id']
        self.assertFalse((attempt/'round_01_response.json').exists())
        before={p.name:p.read_bytes() for p in attempt.iterdir() if p.is_file()}
        result=self.execute(lambda *a:self.fail('complete raw recovery called model'),
            action='p0_finalize',prompt='Entire example',tools=tools,retry=True)
        self.assertEqual(result,{'ok':True,'article_markdown':'body'})
        self.assertEqual(m.action_record(self.job,'p0_finalize')['model_calls'],0)
        self.assertEqual(before,{p.name:p.read_bytes() for p in attempt.iterdir() if p.is_file()})
        self.assertEqual(self.execute(lambda *a:self.fail('recovered cache called model'),
            action='p0_finalize',prompt='Entire example',tools=tools),result)

    def test_full_tool_loop_keeps_native_items_and_finishes_on_real_submission(self):
        payloads=[]
        def transport(profile,key,payload):
            payloads.append(copy.deepcopy(payload))
            return native(name='read_material',arguments={'artifact_id':'one'}) if len(payloads)==1 else native(name='submit_result',arguments={'result':{'ok':True}})
        self.assertEqual(self.execute(transport),{'ok':True});self.assertEqual(len(payloads),2)
        final=payloads[1]
        self.assertEqual(final['input'][0],{'role':'user','content':'complete input'})
        self.assertEqual(final['input'][1]['type'],'reasoning')
        self.assertEqual(final['input'][2]['type'],'function_call')
        self.assertEqual(final['input'][3]['type'],'function_call_output')
        self.assertEqual(json.loads(final['input'][3]['output'])['text'],'start middle end')
        self.assertTrue(all(t['type']=='function' and 'function' not in t for t in final['tools']))
        record=m.action_record(self.job,'p0_blueprint');self.assertEqual(len(record['rounds']),2)
        attempt=self.job/'provider/p0_blueprint/runtime/attempts'/record['attempt_id']
        self.assertTrue((attempt/'round_02_context.json').exists())
        raw=[json.loads(v) for v in (attempt/'round_02_stream.jsonl').read_text().splitlines()]
        self.assertEqual(raw[-1]['type'],'response.completed');self.assertNotIn('choices',raw[-1])
        self.assertEqual(self.execute(lambda *a:self.fail('cached native result made network request')),{'ok':True})
    def _inline_failed(self):
        from host_tools import HostTools
        tools=HostTools(self.root,self.job,'p0_finalize')
        tools.register_text('Entire example','Example','example',True)
        calls=[]
        def transport(*a):
            calls.append(1);return native(name='submit_result',arguments={'result':{'ok':True,'article_markdown':'body'}})
        with patch.object(tools,'record_inline_inputs',return_value={}):
            with self.assertRaises(m.ProviderActionError) as exc:
                self.execute(transport,action='p0_finalize',prompt='Entire example',tools=tools)
        self.assertEqual(exc.exception.code,'invalid_result_contract');self.assertEqual(len(calls),1)
        record=m.action_record(self.job,'p0_finalize')
        return tools,self.job/'provider/p0_finalize/runtime/attempts'/record['attempt_id']
    def test_submit_wrapper_feedback_moves_fields_only_when_model_resubmits(self):
        payloads=[];tools=FakeTools()
        facts={'writing_material_markdown':'自然事实素材',
               'writing_material_sources':[{'source_ref':'one','use':'本篇事实'}]}
        wrong={'result':{'ok':True},**facts}
        complete={'ok':True,**facts}
        def transport(*args):
            payloads.append(copy.deepcopy(args[2]))
            if len(payloads)==1:
                return native(name='read_material',arguments={'artifact_id':'one'})
            if len(payloads)==2:
                return native(name='submit_result',arguments=wrong)
            feedback=json.loads(payloads[-1]['input'][-1]['output'])
            self.assertFalse(feedback['ok'])
            self.assertIn('当前外层非法字段',feedback['message'])
            self.assertIn('writing_material_markdown',feedback['message'])
            self.assertIn('writing_material_sources',feedback['message'])
            self.assertIn('所有业务字段都必须放进 result 对象内',feedback['message'])
            self.assertIn('无需重复读取',feedback['message'])
            return native(name='submit_result',arguments={'result':complete})
        with patch.object(tools,'execute',wraps=tools.execute) as reads:
            self.assertEqual(self.execute(transport,tools=tools),complete)
            self.assertEqual(reads.call_count,1)
        self.assertEqual(len(payloads),3)
        record=m.action_record(self.job,'p0_blueprint')
        attempt=self.job/'provider/p0_blueprint/runtime/attempts'/record['attempt_id']
        rejected=json.loads((attempt/'tool_002.json').read_text())
        self.assertEqual(rejected['arguments'],wrong)
        self.assertFalse(rejected['result']['ok'])
        self.assertEqual(self.execute(lambda *a:self.fail('corrected cached result called model')),complete)

    def test_cached_submit_envelope_uses_same_shape_check_as_live_submission(self):
        tools=FakeTools();calls=[]
        def transport(*args):
            calls.append(1)
            return native(name='read_material',arguments={'artifact_id':'one'}) if len(calls)==1 else native(
                name='submit_result',arguments={'result':{'ok':True},'writing_material_markdown':'outside result'})
        # Reproduce an older runtime that ignored extra outer arguments.
        with patch.object(m,'_submission_result',side_effect=lambda arguments:arguments['result']):
            self.assertEqual(self.execute(transport,tools=tools),{'ok':True})
        with self.assertRaises(m.ProviderActionError) as exc:
            self.execute(lambda *a:self.fail('invalid cached envelope called model'))
        self.assertEqual(exc.exception.code,'cached_result_invalid')

    def test_native_complete_submit_recovers_without_new_call_or_changed_failure(self):
        tools,attempt=self._inline_failed();before={p.name:p.read_bytes() for p in attempt.iterdir() if p.is_file()}
        result=self.execute(lambda *a:self.fail('recovery made network call'),action='p0_finalize',
                            prompt='Entire example',retry=True,tools=tools)
        self.assertEqual(result,{'ok':True,'article_markdown':'body'})
        record=m.action_record(self.job,'p0_finalize');self.assertEqual(record['model_calls'],0)
        self.assertEqual(record['recovered_from_attempt'],attempt.name)
        self.assertEqual(before,{p.name:p.read_bytes() for p in attempt.iterdir() if p.is_file()})
        self.assertEqual(self.execute(lambda *a:self.fail('recovered cache made network call'),
                         action='p0_finalize',prompt='Entire example',tools=tools),result)
    def test_native_recovery_rejects_changed_native_request_and_internal_context(self):
        for target in ('request','context','raw'):
            with self.subTest(target=target):
                import shutil
                shutil.rmtree(self.job);self.job.mkdir()
                tools,attempt=self._inline_failed()
                if target=='request':
                    path=attempt/'round_01_request.json';v=json.loads(path.read_text());v['reasoning']['effort']='low';path.write_text(json.dumps(v))
                elif target=='context':
                    path=attempt/'round_01_context.json';v=json.loads(path.read_text());v[1]['content']='different';path.write_text(json.dumps(v))
                else:
                    path=attempt/'round_01_stream.jsonl';rows=path.read_text().splitlines();path.write_text('\n'.join(rows[:-1]))
                with self.assertRaises(m.ProviderActionError) as exc:
                    self.execute(lambda *a:self.fail('invalid submission triggered rewrite'),action='p0_finalize',
                                 prompt='Entire example',retry=True,tools=tools)
                self.assertEqual(exc.exception.code,'saved_submission_not_recoverable')
    def test_native_tool_read_interruption_resumes_without_reading_twice(self):
        payloads=[]
        def interrupted(*args):
            payloads.append(args[2])
            if len(payloads)==1:return native(name='read_material',arguments={'artifact_id':'one'})
            raise OSError('simulated offline network interruption')
        with self.assertRaises(m.ProviderActionError):self.execute(interrupted)
        saved=m.action_record(self.job,'p0_blueprint')
        resumed=[]
        def complete(*args):
            resumed.append(copy.deepcopy(args[2]));return native(name='submit_result',arguments={'result':{'ok':True}})
        self.assertEqual(self.execute(complete,retry=True),{'ok':True});self.assertEqual(len(resumed),1)
        self.assertEqual(resumed[0]['input'][-1]['type'],'function_call_output')
        self.assertEqual(m.action_record(self.job,'p0_blueprint')['resumed_tools_from_attempt'],saved['attempt_id'])
        self.assertEqual(self.execute(lambda *a:self.fail('recovered tool loop cache called model')),{'ok':True})
    def test_native_cannot_submit_before_actual_full_read(self):
        tools=FakeTools()
        with self.assertRaises(m.ProviderActionError) as exc:
            self.execute(lambda *a:native(name='submit_result',arguments={'result':{'ok':True}}),action='p0_finalize',tools=tools)
        self.assertEqual(exc.exception.code,'invalid_result_contract')
    def test_native_configuration_key_and_secret_are_separate_from_prompt_and_errors(self):
        (self.root/'config').mkdir();(self.root/'config/xty.json').write_text(json.dumps({'api_key':'fake-private-xty-key'}))
        with self.assertRaises(m.ProviderActionError) as exc:
            m.run_action(self.root,self.job,'p0_blueprint','fake-private-xty-key',valid,host_tools=FakeTools())
        self.assertEqual(exc.exception.code,'credential_in_prompt');self.assertFalse((self.job/'provider').exists())
    def test_native_model_or_prompt_changes_invalidate_fingerprint(self):
        first=m.request_fingerprint('p0_blueprint','same input')
        profile=m.profile_for('p0_blueprint')
        with patch.object(m,'profile_for',return_value={**profile,'reasoning':{'effort':'low'}}):
            self.assertNotEqual(first,m.request_fingerprint('p0_blueprint','same input'))
        self.assertNotEqual(first,m.request_fingerprint('p0_blueprint','changed input'))
    def test_native_saved_result_binds_original_result_not_only_valid_json(self):
        calls=[]
        def transport(*args):
            calls.append(1)
            return native(name='read_material',arguments={'artifact_id':'one'}) if len(calls)==1 else native(name='submit_result',arguments={'result':{'ok':True}})
        self.execute(transport)
        rec=m.action_record(self.job,'p0_blueprint');attempt=self.job/'provider/p0_blueprint/runtime/attempts'/rec['attempt_id']
        (attempt/'validated_result.json').write_text('{"ok":true,"new":"forged"}')
        # A normal successful attempt validates parsed_result + original stream;
        # tampering parsed_result is rejected even if the business shape is legal.
        (attempt/'parsed_result.json').write_text('{"ok":true,"new":"forged"}')
        with self.assertRaises(m.ProviderActionError) as exc:self.execute(lambda *a:self.fail('tampering triggered automatic API call'))
        self.assertEqual(exc.exception.code,'cached_result_invalid')
    def test_both_routes_author_and_editors_recheck_inherited_fact_conditions(self):
        task='本篇素材、完整例文和实际稿件保持完整传递。'
        for prefix in ('p0','article'):
            for stage in ('draft','edit','finalize'):
                with self.subTest(action=prefix+'_'+stage):
                    payload=m.build_payload(prefix+'_'+stage,task)
                    system=payload['instructions'] if stage=='finalize' else payload['messages'][0]['content']
                    self.assertIn('对照本篇素材检查适用范围、时间起算点和触发条件',system)
                    self.assertIn('初稿或前一编辑已经写出的限定也必须有依据',system)
                    self.assertIn('不能因前一模型写过就认可',system)
                    actual_input=payload['input'][0]['content'] if stage=='finalize' else payload['messages'][1]['content']
                    self.assertEqual(actual_input,task)
                    if stage in ('edit','finalize'):
                        self.assertIn('编辑说明只记录已经落实的修改，以实际正文为准',system)
        for action in ('p0_blueprint','article_blueprint'):
            self.assertNotIn(m.WRITING_FACTS_CORE,m.build_payload(action,task)['instructions'])

    def test_deepseek_max_uses_existing_strict_json_execution(self):
        payloads=[]
        def transport(*args):payloads.append(args[2]);return stream()
        self.assertEqual(self.execute(transport,action='p0_draft'),{'ok':True})
        self.assertEqual(payloads[0]['reasoning_effort'],'max')
        self.assertEqual(payloads[0]['response_format'],{'type':'json_object'})
