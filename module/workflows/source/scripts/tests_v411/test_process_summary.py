"""Offline secondary API and cache tests. No live billing or customer evidence."""
import importlib.util
import json
import os
from pathlib import Path
from tempfile import mkdtemp
import unittest
from unittest.mock import patch,Mock
import sys
SCRIPTS=Path(__file__).resolve().parents[3]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import process_summary as summary

class ProcessSummaryTests(unittest.TestCase):
    def fixture(self):
        root=Path(mkdtemp(prefix='frontmind-summary-test-'));job=root/'job';cache=root/'cache'
        attempt=job/'provider/article_blueprint/runtime/attempts/one';attempt.mkdir(parents=True)
        record={'action':'article_blueprint','attempt_id':'one','session_id':'session','execution_mode':'production','started_at':'2026-10-04T01:00:00Z','status':'running','requested_configuration':{'wire_api':'zhipu_managed_agents'}}
        (attempt/'execution.json').write_text(json.dumps(record))
        events=[{'id':'thinking','type':'agent.thinking','processed_at':'2026-10-04T01:00:01Z','content':'内部判断需要先核对温控资料，再比较长发场景。'}, {'id':'call','type':'agent.custom_tool_use','name':'web_read','input':{'url':'https://example.com/'},'processed_at':'2026-10-04T01:00:02Z'}]
        events.append({'id':'idle','type':'session.status_idle','stop_reason':{'type':'requires_action'},'processed_at':'2026-10-04T01:00:02.500Z'})
        (attempt/'events.json').write_text(json.dumps(events))
        return job,cache,attempt,events

    def test_deduplication_source_binding_and_tool_revision(self):
        job,cache,attempt,events=self.fixture();seen=[]
        def client(source):
            seen.append(source)
            return '已请求读取官网资料，准备核对现有材料。' if source['kind']=='thinking' else '官网读取失败，温控参数的适用范围未能核验。'
        first=summary.update_summaries(job,cache,0,client)
        summary.update_summaries(job,cache,0,client)
        self.assertEqual(len(seen),1);self.assertTrue(all(row['summaryState']=='ready' for row in first['rows'].values()))
        events.append({'id':'result','type':'user.custom_tool_result','custom_tool_use_id':'call','is_error':True,'content':[{'text':'请求失败'}],'processed_at':'2026-10-04T01:00:03Z'})
        (attempt/'events.json').write_text(json.dumps(events))
        second=summary.update_summaries(job,cache,0,client)
        self.assertEqual(len(seen),2);self.assertTrue(seen[-1]['payload']['failed'])
        tool=next(r for r in second['rows'].values() if r['kind']=='tool');self.assertEqual(tool['revision'],summary.SUMMARY_REVISION)
        spec=importlib.util.spec_from_file_location('summary_export',SCRIPTS/'export-managed-timeline.py');export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
        with patch.dict(os.environ,{'FRONTMIND_PROCESS_SUMMARY_CACHE':str(cache)}):
            public=export.conversation_projection(export.export_job(job,task_id='test'))
            text=json.dumps(public,ensure_ascii=False)
            self.assertIn('已请求读取官网资料',text);self.assertIn('summaryOrigin',text);self.assertNotIn('web_read',text);self.assertNotIn('内部判断',text);self.assertEqual(public[0]['tools'][0]['status'],'failed')
            events[0]['content']='修改后的内部记录'
            (attempt/'events.json').write_text(json.dumps(events))
            public=export.conversation_projection(export.export_job(job,task_id='test'));self.assertEqual(len(public[0]['thinking']),1)
            events[1]['input']['url']='https://changed.example.com/'
            (attempt/'events.json').write_text(json.dumps(events))
            public=export.conversation_projection(export.export_job(job,task_id='test'));self.assertEqual(public[0]['thinking'],[])

    def test_failure_is_cached_without_retries_and_private_reasoning_never_leaves_source(self):
        job,cache,attempt,events=self.fixture();client=Mock(side_effect=TimeoutError)
        summary.update_summaries(job,cache,0,client);summary.update_summaries(job,cache,0,client)
        self.assertEqual(client.call_count,1)
        self.assertNotIn('内部判断',(summary.cache_path(cache,job)).read_text())
        job,cache,attempt,events=self.fixture()
        client=Mock(return_value='已请求读取官网资料，准备核对现有材料。')
        result=summary.update_summaries(job,cache,0,client)
        thought=next(r for r in result['rows'].values() if r['kind']=='thinking')
        self.assertEqual(thought['summaryState'],'ready')
        self.assertNotIn(events[0]['content'],json.dumps(client.call_args.args[0],ensure_ascii=False))
        self.assertNotIn('apiReturnedReasoning',client.call_args.args[0]['payload'])

    def test_no_content_no_invented_thinking_and_old_evidence_not_billed(self):
        job,cache,attempt,events=self.fixture();events[0].pop('content');(attempt/'events.json').write_text(json.dumps(events))
        sources=summary.summary_sources(job,0)
        self.assertEqual([s['kind'] for s in sources],['thinking'])
        self.assertNotIn('apiReturnedReasoning',sources[0]['payload'])
        self.assertIn('completedModelStep',sources[0]['payload'])
        self.assertEqual(summary.summary_sources(job,summary.millis('2026-10-04T02:00:00Z')),[])

    def test_secrets_paths_and_tool_protocol_are_rejected(self):
        for text in ['思考内容包含 sk-testingsecret。','调用 read_material 获取内容。','读取 /Users/test/private.json 完成。','参数 {"url":"test"} 已返回。','联系 test@example.com 确认。','请调用 secret(参数) 完成。','拨打 13812345678 确认。']:
            self.assertIsNone(summary.safe_summary(text),text)
        value=summary.redact_input({'api_key':'not-public','content':'/Users/test/data Bearer hidden sk-testingsecret 13812345678','token':'other'})
        self.assertNotIn('not-public',json.dumps(value));self.assertNotIn('hidden',json.dumps(value));self.assertNotIn('/Users',json.dumps(value))

    def test_secondary_api_gets_complete_content_and_official_context(self):
        with patch.dict(os.environ,{'FRONTMIND_CONTENT_ZHIPU_API_KEY':'private-test-key'},clear=True):client=summary.SummaryClient()
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=None)
        response.read.side_effect=[json.dumps({'usage':{'prompt_tokens':20000}}).encode(),json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'summary':'官网内容与温控资料尚需比对，暂不形成性能结论。'},ensure_ascii=False)}}]}).encode()]
        body='实际返回的判断原文，尚未取得测评。'*2000+'末尾完整证据'
        with patch.object(summary,'urlopen',return_value=response) as api:
            text=client({'kind':'thinking','payload':{'completedModelStep':[{'type':'message','content':body}], 'reasoning_content':'PRIVATE_REASONING', 'apiReturnedReasoning':'PRIVATE_REASONING', 'confirmedMaterials':['完整材料']*100}})
        counted=json.loads(api.call_args_list[0].args[0].data);payload=json.loads(api.call_args_list[1].args[0].data)
        self.assertEqual(counted['messages'],payload['messages']);self.assertIn(body,payload['messages'][1]['content']);self.assertEqual(payload['messages'][0]['content'],summary.SYSTEM_PROMPT);self.assertIsNotNone(text)
        self.assertNotIn('PRIVATE_REASONING',json.dumps(payload))
        self.assertFalse(payload['stream']);self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertEqual(payload['model'],'glm-5.2');self.assertEqual(payload['max_tokens'],4096);self.assertEqual(summary.CONTEXT_TOKENS,1048576)
        self.assertEqual(len(summary.redact_input(['材料']*100)),100)

    def test_official_window_overflow_and_incomplete_response_do_not_generate_a_summary(self):
        with patch.dict(os.environ,{'FRONTMIND_CONTENT_ZHIPU_API_KEY':'private-test-key'},clear=True):client=summary.SummaryClient()
        source={'kind':'thinking','payload':{'completedModelStep':[{'type':'message','content':'已经核对的真实内容'}]}}
        with patch.object(client,'request',return_value={'usage':{'prompt_tokens':summary.CONTEXT_TOKENS-summary.OUTPUT_TOKENS+1}}) as api:
            with self.assertRaisesRegex(ValueError,'summary_context_exceeded'):client(source)
            self.assertEqual(api.call_count,1)
        with patch.object(client,'request',side_effect=[{'usage':{'prompt_tokens':summary.CONTEXT_TOKENS-summary.OUTPUT_TOKENS}},{'choices':[{'finish_reason':'length'}]}]) as api:
            with self.assertRaisesRegex(ValueError,'summary_response_incomplete'):client(source)
            self.assertEqual(api.call_count,2)
        with patch.object(client,'request') as api:
            with self.assertRaisesRegex(ValueError,'summary_step_incomplete'):client({'kind':'tool','payload':{}})
            api.assert_not_called()

    def test_stream_waits_for_completion_and_keeps_the_entire_step(self):
        path=Path(mkdtemp())/'round_01_stream.jsonl'
        text='关于选购场景的内容。'*2000+'末尾完整证据'
        line=json.dumps({'choices':[{'delta':{'content':text,'reasoning_content':'PRIVATE_REASONING'}}]})+'\n'
        path.write_text(line+'{incomplete');self.assertEqual(summary.stream_content(path),[])
        path.write_text(line+json.dumps('[DONE]')+'\n');self.assertEqual(summary.stream_content(path),[text])
        path.write_text(json.dumps({'choices':[{'delta':{'reasoning_content':'PRIVATE_ONLY'}}]})+'\n'+json.dumps('[DONE]')+'\n')
        self.assertEqual(summary.stream_content(path),[])

    def test_managed_step_closure_and_observable_evidence_without_hidden_reasoning(self):
        job,cache,attempt,events=self.fixture();events[0].pop('content');events.pop()
        (attempt/'events.json').write_text(json.dumps(events));client=Mock(return_value='已识别需要核验温控资料的任务要求，尚不能形成性能结论。')
        self.assertEqual(summary.update_summaries(job,cache,0,client)['rows'],{});client.assert_not_called()
        events.append({'id':'idle','type':'session.status_idle','stop_reason':{'type':'requires_action'},'processed_at':'2026-10-04T01:00:02.500Z'})
        (attempt/'events.json').write_text(json.dumps(events));first=summary.update_summaries(job,cache,0,client)
        self.assertEqual(client.call_count,1);self.assertNotIn('apiReturnedReasoning',client.call_args.args[0]['payload'])
        events.extend([{'id':'result','type':'user.custom_tool_result','custom_tool_use_id':'call','content':[{'text':'示例页面读取成功'}],'processed_at':'2026-10-04T01:00:03Z'}, {'id':'answer','type':'agent.message','content':[{'text':'该网页用于文档示例'}],'processed_at':'2026-10-04T01:00:04Z'}, {'id':'finished','type':'session.status_idle','stop_reason':{'type':'end_turn'},'processed_at':'2026-10-04T01:00:05Z'}])
        (attempt/'events.json').write_text(json.dumps(list(reversed(events))))
        second=summary.update_summaries(job,cache,0,client);self.assertEqual(client.call_count,3)
        first_id=next(iter(first['rows']));self.assertEqual(second['rows'][first_id],first['rows'][first_id])
        summary.update_summaries(job,cache,0,client);self.assertEqual(client.call_count,3)

    def test_equal_timestamp_and_duplicate_events_do_not_change_closed_step_identity(self):
        job,cache,attempt,events=self.fixture()
        for e in events:e['processed_at']='2026-10-04T01:00:02Z'
        events[-1]['id']='0-closed'
        (attempt/'events.json').write_text(json.dumps(events));before=summary.summary_sources(job,0)
        (attempt/'events.json').write_text(json.dumps(list(reversed(events))+[events[1]]));after=summary.summary_sources(job,0)
        self.assertEqual(before,after);self.assertEqual(len(after),1)

    def test_completed_stream_and_response_share_identity_without_duplicate_billing(self):
        job,cache,attempt,events=self.fixture();record=json.loads((attempt/'execution.json').read_text());record.pop('session_id');(attempt/'execution.json').write_text(json.dumps(record))
        body='已核对材料中的温控范围，但缺少实际测评结果。'
        (attempt/'round_01_stream.jsonl').write_text(json.dumps({'choices':[{'delta':{'content':body,'reasoning_content':'PRIVATE_STREAM'}}]})+'\n'+json.dumps('[DONE]')+'\n')
        client=Mock(return_value='现有温控资料缺少实际测评，不能作性能排名。')
        first=summary.update_summaries(job,cache,0,client)
        (attempt/'round_01_response.json').write_text(json.dumps({'content':body,'reasoning_content':'PRIVATE_RESPONSE','tool_calls':[]}))
        second=summary.update_summaries(job,cache,0,client)
        self.assertEqual(first,second);self.assertEqual(client.call_count,1)
        self.assertNotIn('PRIVATE',json.dumps(client.call_args.args[0]))

    def test_private_only_native_and_managed_steps_have_no_summary_source(self):
        job,cache,attempt,events=self.fixture()
        (attempt/'events.json').write_text(json.dumps([events[0],events[-1]]))
        self.assertEqual(summary.summary_sources(job,0),[])
        record=json.loads((attempt/'execution.json').read_text());record.pop('session_id')
        (attempt/'execution.json').write_text(json.dumps(record))
        (attempt/'round_01_response.json').write_text(json.dumps({'reasoning_content':'PRIVATE_ONLY','content':'','tool_calls':[]}))
        self.assertEqual(summary.summary_sources(job,0),[])

    def test_legacy_reasoning_summary_is_not_projected_for_observable_output(self):
        job,cache,attempt,events=self.fixture()
        record=json.loads((attempt/'execution.json').read_text());record.pop('session_id')
        (attempt/'execution.json').write_text(json.dumps(record))
        (attempt/'round_01_response.json').write_text(json.dumps({'reasoning_content':'PRIVATE_OLD','content':'本篇正文已返回。','tool_calls':[]}))
        source=summary.summary_sources(job,0)[0]
        old={k:v for k,v in source.items() if k!='payload'}
        old.update(revision=5,summaryState='ready',text='旧摘要来自内部规划。',
                   sourceHash=summary.identity(json.dumps({'apiReturnedReasoning':'PRIVATE_OLD'},sort_keys=True,ensure_ascii=False)))
        summary.atomic(summary.cache_path(cache,job),{'version':summary.PROMPT_VERSION,'rows':{old['id']:old}})
        spec=importlib.util.spec_from_file_location('legacy_summary_export',SCRIPTS/'export-managed-timeline.py');export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
        with patch.dict(os.environ,{'FRONTMIND_PROCESS_SUMMARY_CACHE':str(cache)}):
            public=export.conversation_projection(export.export_job(job,task_id='test'))
        self.assertEqual(public[0]['thinking'],[])
        self.assertNotIn('旧摘要',json.dumps(public,ensure_ascii=False))

class SdkProcessSummaryTests(unittest.TestCase):
    def fixture(self):
        root=Path(mkdtemp(prefix='frontmind-sdk-summary-test-'));job=root/'job';cache=root/'cache'
        attempt=job/'provider/positioning_market_research/runtime/attempts/one';attempt.mkdir(parents=True)
        record={'action':'positioning_market_research','attempt_id':'one','session_id':'sdk-session','execution_mode':'production','started_at':'2026-10-04T01:00:00Z','status':'failed','failed_at':'2026-10-04T01:00:05Z','error':{'code':'source_acquisition_failed','message':'PRIVATE_ERROR'},'requested_configuration':{'wire_api':'openai_agents_sdk','provider':'xty'}}
        (attempt/'execution.json').write_text(json.dumps(record))
        (attempt/'request_plan.json').write_text(json.dumps({'input':[{'role':'user','content':'核对样例企业材料'}]}))
        (attempt/'model_0001_request.json').write_text(json.dumps({'started_at':'2026-10-04T01:00:01Z'}))
        response={'completed_at':'2026-10-04T01:00:02Z','output':[{'type':'function_call','call_id':'read-one','name':'read_material','arguments':'{"material_id":"PRIVATE_MATERIAL"}'}]}
        (attempt/'model_0001_response.json').write_text(json.dumps(response))
        receipt={'call_id':'read-one','name':'read_material','status':'completed','started_at':'2026-10-04T01:00:03Z','completed_at':'2026-10-04T01:00:04Z','output':{'ok':False,'error':'material_reference_missing','message':'PRIVATE_ERROR'},'host_state':{'PRIVATE':'never summarize full host state'}}
        (attempt/'tool_one.json').write_text(json.dumps(receipt))
        spec=importlib.util.spec_from_file_location('sdk_summary_export',SCRIPTS/'export-managed-timeline.py');export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
        return job,cache,attempt,export

    def test_material_read_scope_distinguishes_full_body_prefix_and_empty_eof(self):
        job,cache,attempt,export=self.fixture()
        receipt_path=attempt/'tool_one.json'
        receipt=json.loads(receipt_path.read_text())
        observed=[]
        for text,offset,full in [('完整正文',0,True),('完',0,False),('',4,False)]:
            receipt['output']={'text':text,'offset':offset,'total_chars':4,'complete_read':True}
            receipt_path.write_text(json.dumps(receipt))
            source=next(row for row in summary.summary_sources(job,0) if row['kind']=='tool')
            scope=source['payload']['readingScope']
            self.assertEqual(scope,{'returnedChars':len(text),'offset':offset,'totalChars':4,
                                    'currentReadCoversWholeMaterial':full,'cumulativeReadComplete':True})
            observed.append(source['payload'])
        self.assertNotEqual(observed[0],observed[1])
        self.assertNotEqual(observed[1],observed[2])
        self.assertIn('complete_read 表示此前与本次读取合计覆盖全文',summary.SYSTEM_PROMPT)
        self.assertIn('返回零字符时写本次没有新增正文',summary.SYSTEM_PROMPT)

    def test_sdk_outputs_and_completed_receipts_generate_public_chinese_summaries(self):
        job,cache,attempt,export=self.fixture();seen=[]
        path=attempt/'model_0001_response.json';response=json.loads(path.read_text())
        response['output'].extend([{'type':'reasoning','summary':[{'type':'summary_text','text':'PRIVATE_REASONING'}],'encrypted_content':'PRIVATE_ENCRYPTED'}, {'type':'message','content':[{'type':'output_text','text':'已确定需要读取材料','annotations':[{'PRIVATE':'annotation'}]},{'type':'reasoning_text','text':'PRIVATE_HIDDEN'}]}])
        path.write_text(json.dumps(response))
        def client(source):
            seen.append(source)
            return '已确定需要核对**产品材料**，尚未形成比较结论。' if source['kind']=='thinking' else '产品材料未能读取，需要先核对登记目录。'
        summary.update_summaries(job,cache,0,client)
        summary.update_summaries(job,cache,0,client)
        self.assertEqual(len(seen),2)
        self.assertNotIn('apiReturnedReasoning',seen[0]['payload'])
        self.assertNotIn('host_state',json.dumps(seen))
        observed=json.dumps(seen[0]['payload']['completedModelStep'])
        self.assertNotIn('PRIVATE_REASONING',observed);self.assertNotIn('PRIVATE_ENCRYPTED',observed)
        self.assertNotIn('PRIVATE_HIDDEN',observed);self.assertNotIn('annotations',observed)
        with patch.dict(os.environ,{'FRONTMIND_PROCESS_SUMMARY_CACHE':str(cache)}):
            execution=export.export_job(job,task_id='sdk-task')
            processes=export.conversation_projection(execution)
        self.assertEqual(execution['sources'],['openai_agents_sdk'])
        self.assertEqual(processes[0]['status'],'failed')
        self.assertEqual(processes[0]['tools'][0]['status'],'failed')
        self.assertEqual(processes[0]['tools'][0]['reason'],'材料标识未登记。')
        self.assertIn('**产品材料**',processes[0]['thinking'][0]['text'])
        self.assertEqual(processes[0]['tools'][0]['summaryOrigin'],'model')
        self.assertNotIn('PRIVATE',json.dumps(processes))
        self.assertEqual(summary.summary_sources(job,summary.millis('2026-10-04T02:00:00Z')),[])

    def test_sdk_reasoning_only_step_has_no_public_summary_source(self):
        job,cache,attempt,export=self.fixture()
        path=attempt/'model_0001_response.json';response=json.loads(path.read_text())
        response['output']=[{'type':'reasoning','summary':[{'type':'summary_text','text':'PRIVATE_REASONING'}],'encrypted_content':'PRIVATE_ENCRYPTED'}]
        path.write_text(json.dumps(response))
        self.assertEqual(summary.summary_sources(job,0),[])

    def test_sdk_started_tool_is_unknown_after_failure_and_never_summarized_as_finished(self):
        job,cache,attempt,export=self.fixture()
        (attempt/'tool_one.json').write_text(json.dumps({'call_id':'read-one','name':'read_material','status':'started','started_at':'2026-10-04T01:00:03Z'}))
        self.assertEqual([source['kind'] for source in summary.summary_sources(job,0)],['thinking'])
        process=export.conversation_projection(export.export_job(job,task_id='sdk-task'))[0]
        self.assertEqual(process['tools'][0]['status'],'unknown')
        self.assertNotIn('已完成',process['tools'][0]['text'])

    def test_sdk_tool_request_summary_cannot_claim_that_tool_execution_finished(self):
        job,cache,attempt,export=self.fixture()
        source=next(row for row in summary.summary_sources(job,0) if row['kind']=='thinking')
        self.assertTrue(source['payload']['toolRequestsOnly'])
        self.assertFalse(source['payload']['hasReceipt'])
        # Even a separately recorded receipt does not turn this model request into a result.
        for text in ['已完成官网页面的抓取。','已抓取官网内容并核对材料。','已获取产品资料，形成比较范围。']:
            value=summary.update_summaries(job,cache/text,0,lambda _:text)
            self.assertEqual(value['rows'][source['id']]['summaryState'],'unavailable')
        value=summary.update_summaries(job,cache/'request',0,lambda _:'已请求读取官网产品页面，准备核对品牌与功能信息。')
        self.assertEqual(value['rows'][source['id']]['summaryState'],'ready')

    def test_sdk_same_session_recovery_retains_tool_identity(self):
        job,cache,attempt,export=self.fixture()
        before=export.conversation_projection(export.export_job(job,task_id='sdk-task'))[0]
        record=json.loads((attempt/'execution.json').read_text())
        (attempt/'resume_001_previous_execution.json').write_text(json.dumps(record))
        record.update(status='succeeded',completed_at='2026-10-04T01:01:00Z')
        (attempt/'execution.json').write_text(json.dumps(record))
        after=export.conversation_projection(export.export_job(job,task_id='sdk-task'))[0]
        self.assertEqual(after['id'],before['id']);self.assertEqual(after['tools'][0]['id'],before['tools'][0]['id'])
        self.assertEqual(after['tools'][0]['status'],'failed')
        self.assertEqual(after['recovery'],'已沿用原会话恢复。')


class SummaryLaunchTests(unittest.TestCase):
    def test_real_dispatch_starts_summary_worker_by_default(self):
        spec=importlib.util.spec_from_file_location('summary_default_launcher',SCRIPTS/'run_managed.py');launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        root=Path(mkdtemp(prefix='frontmind-summary-default-'))
        environment={'FRONTMIND_CONTENT_XTY_API_KEY':'synthetic-xty-key','FRONTMIND_CONTENT_ZHIPU_API_KEY':'synthetic-zhipu-key','FRONTMIND_CONTENT_DEEPSEEK_API_KEY':'synthetic-deepseek-key','FRONTMIND_PROCESS_SUMMARY_CACHE':str(root/'cache')}
        with patch.dict(os.environ,environment,clear=True),patch.object(launcher.subprocess,'Popen') as worker,patch.object(launcher.subprocess,'call',return_value=0),patch.object(launcher.os,'execve'):
            self.assertEqual(launcher.main(['--config-dir',str(root),'--','continue','--job-dir',str(root/'job')]),0)
            worker.assert_called_once()

    def test_worker_start_failure_does_not_block_business_executor(self):
        spec=importlib.util.spec_from_file_location('summary_launcher',SCRIPTS/'run_managed.py');launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        root=Path(mkdtemp(prefix='frontmind-summary-launch-'))
        environment={'FRONTMIND_CONTENT_XTY_API_KEY':'synthetic-xty-key','FRONTMIND_CONTENT_ZHIPU_API_KEY':'synthetic-zhipu-key','FRONTMIND_CONTENT_DEEPSEEK_API_KEY':'synthetic-deepseek-key','FRONTMIND_PROCESS_SUMMARY_CACHE':str(root/'cache'),'FRONTMIND_ENABLE_MODEL_SUMMARIES':'1'}
        with patch.dict(os.environ,environment,clear=True),patch.object(launcher.subprocess,'Popen',side_effect=OSError) as worker,patch.object(launcher.subprocess,'call',return_value=0) as call,patch.object(launcher.os,'execve') as execute:
            self.assertEqual(launcher.main(['--config-dir',str(root),'--','continue','--job-dir',str(root/'job')]),0)
            worker.assert_called_once()
            if os.name == 'nt':
                call.assert_called_once();execute.assert_not_called()
            else:
                execute.assert_called_once();call.assert_not_called()
            self.assertIn('--since',worker.call_args.args[0]);self.assertIn('--parent-pid',worker.call_args.args[0])
            self.assertNotIn('synthetic',json.dumps(worker.call_args.args[0]))

    def test_preflight_never_starts_summary_calls(self):
        spec=importlib.util.spec_from_file_location('summary_preflight_launcher',SCRIPTS/'run_managed.py');launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        environment={'FRONTMIND_CONTENT_XTY_API_KEY':'synthetic-xty-key','FRONTMIND_CONTENT_ZHIPU_API_KEY':'synthetic-zhipu-key','FRONTMIND_CONTENT_DEEPSEEK_API_KEY':'synthetic-deepseek-key','FRONTMIND_PROCESS_SUMMARY_CACHE':'/private/tmp/unused-summary-test-cache'}
        with patch.dict(os.environ,environment,clear=True),patch.object(launcher.subprocess,'Popen') as worker,patch.object(launcher.subprocess,'call',return_value=0),patch.object(launcher.os,'execve'):
            launcher.main(['--config-dir','/private/tmp','--','preflight']);worker.assert_not_called()

    def test_readonly_status_and_help_do_not_start_summary_calls(self):
        spec=importlib.util.spec_from_file_location('summary_readonly_launcher',SCRIPTS/'run_managed.py');launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        environment={'FRONTMIND_CONTENT_XTY_API_KEY':'synthetic-xty-key','FRONTMIND_CONTENT_ZHIPU_API_KEY':'synthetic-zhipu-key','FRONTMIND_CONTENT_DEEPSEEK_API_KEY':'synthetic-deepseek-key','FRONTMIND_PROCESS_SUMMARY_CACHE':'/private/tmp/unused-summary-test-cache'}
        for command in [['status','--job-dir','/private/tmp/unused-summary-job'], ['start','--help','--job-dir','/private/tmp/unused-summary-job']]:
            with patch.dict(os.environ,environment,clear=True),patch.object(launcher.subprocess,'Popen') as worker,patch.object(launcher.subprocess,'call',return_value=0),patch.object(launcher.os,'execve'):
                launcher.main(['--config-dir','/private/tmp','--',*command]);worker.assert_not_called()

class WriterSummaryOrderTests(unittest.TestCase):
    def test_observable_output_precedes_its_tools_and_next_round_without_invented_times(self):
        root=Path(mkdtemp(prefix='frontmind-writer-summary-order-'));attempt=root/'provider/article_draft/runtime/attempts/one';attempt.mkdir(parents=True)
        record={'action':'article_draft','attempt_id':'one','execution_mode':'production','started_at':'2026-10-04T01:00:00Z','requested_configuration':{'provider':'deepseek'},'status':'succeeded','finished_at':'2026-10-04T01:01:00Z'}
        (attempt/'execution.json').write_text(json.dumps(record))
        response={'content':'请检查正文篇幅。','reasoning_content':'PRIVATE_REASONING','tool_calls':[{'id':'count','function':{'name':'count_article','arguments':'{}'}}]}
        (attempt/'round_01_response.json').write_text(json.dumps(response))
        (attempt/'round_02_response.json').write_text(json.dumps({'content':'正文已完成。','reasoning_content':'PRIVATE_REASONING','tool_calls':[]}))
        (attempt/'tool_count.json').write_text(json.dumps({'tool_call_id':'count','result':{'body_characters':100}}))
        sources=summary.summary_sources(root,0)
        self.assertNotIn('PRIVATE_REASONING',json.dumps(sources))
        first=next(s for s in sources if s['kind']=='thinking' and s['sequence']==1000)
        tool=next(s for s in sources if s['kind']=='tool')
        second=next(s for s in sources if s['kind']=='thinking' and s['sequence']==2000)
        self.assertLess(first['sequence'],tool['sequence']);self.assertLess(tool['sequence'],second['sequence']);self.assertNotIn('timestamp',tool)
        spec=importlib.util.spec_from_file_location('writer_order_export',SCRIPTS/'export-managed-timeline.py');export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
        self.assertEqual(export.writer_tool_summaries(attempt/'execution.json',first['attemptId'])[0]['sequence'],tool['sequence'])

class ReceiptTruthTests(unittest.TestCase):
    def test_summary_cannot_claim_success_for_a_failed_receipt_or_ongoing_work_for_a_finished_receipt(self):
        fixture=ProcessSummaryTests()
        for failed,text in [(True,'已成功读取官网，取得温控测试条件。'),(False,'正在读取官网，准备核对温控测试条件。')]:
            job,cache,attempt,events=fixture.fixture()
            events.append({'id':'result','type':'user.custom_tool_result','custom_tool_use_id':'call','is_error':failed,'content':[{'text':'连接失败' if failed else '已取得网页'}],'processed_at':'2026-10-04T01:00:03Z'})
            (attempt/'events.json').write_text(json.dumps(events))
            value=summary.update_summaries(job,cache,0,lambda source:text)
            tool=next(r for r in value['rows'].values() if r['kind']=='tool')
            self.assertEqual(tool['summaryState'],'unavailable');self.assertNotIn('text',tool)
