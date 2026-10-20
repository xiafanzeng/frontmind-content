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
            return '长发场景需要结合温控资料判断，暂不作产品排名。' if source['kind']=='thinking' else '官网读取失败，温控参数的适用范围未能核验。'
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
            self.assertIn('长发场景',text);self.assertIn('summaryOrigin',text);self.assertNotIn('web_read',text);self.assertNotIn('内部判断',text);self.assertEqual(public[0]['tools'][0]['status'],'failed')
            events[0]['content']='修改后的内部记录'
            (attempt/'events.json').write_text(json.dumps(events))
            public=export.conversation_projection(export.export_job(job,task_id='test'));self.assertEqual(public[0]['thinking'],[])

    def test_failure_is_cached_without_retries_and_original_reasoning_not_copied(self):
        job,cache,attempt,events=self.fixture();client=Mock(side_effect=TimeoutError)
        summary.update_summaries(job,cache,0,client);summary.update_summaries(job,cache,0,client)
        self.assertEqual(client.call_count,1)
        self.assertNotIn('内部判断',(summary.cache_path(cache,job)).read_text())
        job,cache,attempt,events=self.fixture()
        result=summary.update_summaries(job,cache,0,lambda source:events[0]['content'])
        thought=next(r for r in result['rows'].values() if r['kind']=='thinking')
        self.assertEqual(thought['summaryState'],'unavailable')

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
            text=client({'kind':'thinking','payload':{'apiReturnedReasoning':body,'confirmedMaterials':['完整材料']*100}})
        counted=json.loads(api.call_args_list[0].args[0].data);payload=json.loads(api.call_args_list[1].args[0].data)
        self.assertEqual(counted['messages'],payload['messages']);self.assertIn(body,payload['messages'][1]['content']);self.assertEqual(payload['messages'][0]['content'],summary.SYSTEM_PROMPT);self.assertIsNotNone(text)
        self.assertFalse(payload['stream']);self.assertEqual(payload['thinking'],{'type':'disabled'})
        self.assertEqual(payload['model'],'glm-5.2');self.assertEqual(payload['max_tokens'],4096);self.assertEqual(summary.CONTEXT_TOKENS,1048576)
        self.assertEqual(len(summary.redact_input(['材料']*100)),100)

    def test_official_window_overflow_and_incomplete_response_do_not_generate_a_summary(self):
        with patch.dict(os.environ,{'FRONTMIND_CONTENT_ZHIPU_API_KEY':'private-test-key'},clear=True):client=summary.SummaryClient()
        source={'kind':'thinking','payload':{'apiReturnedReasoning':'已经核对的真实内容'}}
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
        line=json.dumps({'choices':[{'delta':{'reasoning_content':text}}]})+'\n'
        path.write_text(line+'{incomplete');self.assertEqual(summary.stream_reasoning(path),[])
        path.write_text(line+json.dumps('[DONE]')+'\n');self.assertEqual(summary.stream_reasoning(path),[text])

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
        (attempt/'round_01_stream.jsonl').write_text(json.dumps({'choices':[{'delta':{'reasoning_content':body}}]})+'\n'+json.dumps('[DONE]')+'\n')
        client=Mock(return_value='现有温控资料缺少实际测评，不能作性能排名。')
        first=summary.update_summaries(job,cache,0,client)
        (attempt/'round_01_response.json').write_text(json.dumps({'reasoning_content':body,'tool_calls':[]}))
        second=summary.update_summaries(job,cache,0,client)
        self.assertEqual(first,second);self.assertEqual(client.call_count,1)

class SummaryLaunchTests(unittest.TestCase):
    def test_model_summary_requires_explicit_opt_in(self):
        spec=importlib.util.spec_from_file_location('summary_default_launcher',SCRIPTS/'run_managed.py');launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        root=Path(mkdtemp(prefix='frontmind-summary-default-'))
        environment={'FRONTMIND_CONTENT_ZHIPU_API_KEY':'synthetic-zhipu-key','FRONTMIND_CONTENT_DEEPSEEK_API_KEY':'synthetic-deepseek-key','FRONTMIND_PROCESS_SUMMARY_CACHE':str(root/'cache')}
        with patch.dict(os.environ,environment,clear=True),patch.object(launcher.subprocess,'Popen') as worker,patch.object(launcher.subprocess,'call',return_value=0),patch.object(launcher.os,'execve'):
            self.assertEqual(launcher.main(['--config-dir',str(root),'--','continue','--job-dir',str(root/'job')]),0)
            worker.assert_not_called()

    def test_worker_start_failure_does_not_block_business_executor(self):
        spec=importlib.util.spec_from_file_location('summary_launcher',SCRIPTS/'run_managed.py');launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        root=Path(mkdtemp(prefix='frontmind-summary-launch-'))
        environment={'FRONTMIND_CONTENT_ZHIPU_API_KEY':'synthetic-zhipu-key','FRONTMIND_CONTENT_DEEPSEEK_API_KEY':'synthetic-deepseek-key','FRONTMIND_PROCESS_SUMMARY_CACHE':str(root/'cache'),'FRONTMIND_ENABLE_MODEL_SUMMARIES':'1'}
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
        environment={'FRONTMIND_CONTENT_ZHIPU_API_KEY':'synthetic-zhipu-key','FRONTMIND_CONTENT_DEEPSEEK_API_KEY':'synthetic-deepseek-key','FRONTMIND_PROCESS_SUMMARY_CACHE':'/private/tmp/unused-summary-test-cache'}
        with patch.dict(os.environ,environment,clear=True),patch.object(launcher.subprocess,'Popen') as worker,patch.object(launcher.subprocess,'call',return_value=0),patch.object(launcher.os,'execve'):
            launcher.main(['--config-dir','/private/tmp','--','preflight']);worker.assert_not_called()

class WriterSummaryOrderTests(unittest.TestCase):
    def test_reasoning_precedes_its_tools_and_next_round_without_invented_times(self):
        root=Path(mkdtemp(prefix='frontmind-writer-summary-order-'));attempt=root/'provider/article_draft/runtime/attempts/one';attempt.mkdir(parents=True)
        record={'action':'article_draft','attempt_id':'one','execution_mode':'production','started_at':'2026-10-04T01:00:00Z','requested_configuration':{'provider':'deepseek'},'status':'succeeded','finished_at':'2026-10-04T01:01:00Z'}
        (attempt/'execution.json').write_text(json.dumps(record))
        response={'reasoning_content':'初稿内容需围绕长发场景展开，接着检查正文篇幅。','tool_calls':[{'id':'count','function':{'name':'count_article','arguments':'{}'}}]}
        (attempt/'round_01_response.json').write_text(json.dumps(response))
        (attempt/'round_02_response.json').write_text(json.dumps({'reasoning_content':'篇幅已经检查，现在准备下一段编辑安排。','tool_calls':[]}))
        (attempt/'tool_count.json').write_text(json.dumps({'tool_call_id':'count','result':{'body_characters':100}}))
        sources=summary.summary_sources(root,0)
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
