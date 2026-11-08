"""Offline protocol tests; fixture records are temporary and not provider evidence."""
from pathlib import Path
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'source/v16_25_1/stage2'
sys.path.insert(0,str(ROOT/'scripts'))
import kimi_hosted as kh
import provider_http as ph


class FakeClient:
    sent=0;created=0;uploaded=0;attached=0;ready=False;fail_send=False;names=[]
    def __init__(self,config):self.http=self
    def upload(self,path):
        type(self).uploaded+=1
        return {'id':'file_offline','filename':'offline_bundle.zip'}
    def create_session(self,title,resources,system=kh.SYSTEM):
        type(self).created+=1
        return {'id':'sesn_offline'},{'agent_overrides':{'model':{'id':kh.MODEL,'reasoning_effort':kh.EFFORT}}}
    def events(self,sid):return [{'id':'sevt_fixture','type':'agent.thinking','data':{'text':'PRIVATE_FIXTURE'}}]
    def artifacts(self,sid):
        return [{'id':'arti_offline','name':name,'version':'1'} for name in type(self).names] if type(self).ready else []
    def download(self,artifact):return b'{"result":"offline_fixture"}'
    def json(self,method,path,data=None,headers=None):
        if method=='POST' and path.endswith('/events'):
            type(self).sent+=1
            if type(self).fail_send:raise ph.ProviderError('offline response lost',None,True)
            import re
            text=data['events'][0]['data']['content'][0]['text']
            type(self).names.append(re.search(r'frontmind_result_[a-f0-9]+\.json',text)[0])
            return {'event_id':'sevt_ack'}
        if method=='POST' and path.endswith('/resources'):
            type(self).attached+=1;return {}
        return {'status':'idle' if type(self).ready else 'running','usage':{'input_tokens':1,'output_tokens':1}}


class HostedTransport(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.base=Path(self.temp.name)
        self.prepared=self.base/'prepared';self.prepared.mkdir()
        (self.prepared/'system.md').write_text('离线测试合同，非真实业务。')
        (self.prepared/'user.md').write_text('输出测试JSON。')
        self.config=self.base/'kimi.json'
        self.config.write_text(json.dumps({'api_key':'offline-fixture-no-real-key','agent_id':'agent_offline',
            'agent_version':'1','environment_id':'env_offline','model':kh.MODEL,'reasoning_effort':'high'}))
        FakeClient.sent=FakeClient.created=FakeClient.uploaded=FakeClient.attached=0
        FakeClient.ready=False;FakeClient.fail_send=False;FakeClient.names=[]

    def run_fixture(self,action='analysis'):
        with patch.object(kh,'Client',FakeClient):
            return kh.run_prepared(self.config,self.base/'workspace',self.prepared,action,wait_seconds=0)

    def test_resume_reads_same_dispatched_request_without_reposting(self):
        first=self.run_fixture();self.assertEqual(first['status'],'waiting')
        FakeClient.ready=True;second=self.run_fixture()
        self.assertEqual(second['status'],'succeeded');self.assertEqual(FakeClient.sent,1)
        self.assertEqual(FakeClient.created,1);self.assertEqual(FakeClient.uploaded,1)
        self.assertEqual(json.loads(Path(second['result_file']).read_text()),{'result':'offline_fixture'})
        self.assertNotIn('PRIVATE_FIXTURE',(Path(second['run_dir'])/'public_events.json').read_text())
        self.run_fixture();self.assertEqual(FakeClient.sent,1)

    def test_later_action_reuses_session_and_adds_new_resource(self):
        FakeClient.ready=True;self.run_fixture('first');self.run_fixture('second')
        self.assertEqual(FakeClient.created,1);self.assertEqual(FakeClient.sent,2)
        self.assertEqual(FakeClient.uploaded,2);self.assertEqual(FakeClient.attached,1)

    def test_style_review_uses_isolated_session_and_reuses_it_for_followup(self):
        FakeClient.ready=True
        self.run_fixture('analysis')
        first=self.run_fixture('p0_check')
        self.run_fixture('step8_review')
        self.assertEqual(FakeClient.created,2)
        self.assertEqual(FakeClient.attached,1)
        workspace=self.base/'workspace'
        self.assertTrue((workspace/'hosted_session.json').is_file())
        self.assertTrue((workspace/'hosted_style_session.json').is_file())
        self.assertEqual(first['session_kind'],'style')
        request=json.loads((Path(first['run_dir'])/'session_request.json').read_text())
        self.assertEqual((Path(first['run_dir'])/'system.md').read_text(),kh.STYLE_SYSTEM)

    def test_style_session_rejects_external_fact_resources(self):
        resource=self.base/'knowledge.zip';resource.write_bytes(b'offline')
        with patch.object(kh,'Client',FakeClient),self.assertRaisesRegex(ValueError,'不接收知识库'):
            kh.run_prepared(self.config,self.base/'workspace',self.prepared,'step8_review',resource_paths=[resource],wait_seconds=0)
        self.assertEqual(FakeClient.uploaded,0)

    def test_unknown_mutation_outcome_is_not_automatically_retried(self):
        FakeClient.fail_send=True
        with self.assertRaisesRegex(ValueError,'未自动重发'):self.run_fixture()
        with self.assertRaisesRegex(ValueError,'结果未知'):self.run_fixture()
        self.assertEqual(FakeClient.sent,1)

    def test_high_model_override_is_explicit_in_session_request(self):
        config=json.loads(self.config.read_text());client=kh.Client(config)
        with patch.object(client.http,'json',return_value={'id':'sesn_unit'}) as call:
            _,payload=client.create_session('offline',[])
        self.assertEqual(payload['agent_overrides']['model'],{'id':'kimi-k3.1-pro','reasoning_effort':'high'})
        self.assertEqual(call.call_args.args[:2],('POST','/v1/sessions'))

    def test_private_thinking_does_not_become_public_trace(self):
        self.assertIsNone(kh.public_event({'type':'agent.thinking','data':{'text':'private'}}))
        self.assertIsNone(kh.public_event({'type':'agent.delta'}))
        public=kh.public_event({'type':'agent.tool_use','data':{'tool_use':{'name':'read_file','description':'核对页面','arguments':{'secret':'private'}}}})
        self.assertEqual(public['description'],'核对页面');self.assertNotIn('arguments',public)

    def test_xty_sse_keeps_original_content_and_model_identity(self):
        values=[{'model':'gemini-4-argon','choices':[{'delta':{'content':'原始'},'finish_reason':None}]},
                {'model':'gemini-4-argon','choices':[{'delta':{'content':'全文'},'finish_reason':'stop'}],'usage':{'output_tokens':2}}]
        raw=('\n\n'.join('data: '+json.dumps(v,ensure_ascii=False) for v in values)+'\n\ndata: [DONE]\n\n').encode()
        class Response(io.BytesIO):headers={'Content-Type':'text/event-stream','x-request-id':'offline-id'}
        payload={'model':'gemini-4-argon','messages':[],'stream':True,'reasoning_effort':'high'}
        with patch.object(ph.Http,'open',return_value=Response(raw)) as opened:
            result=ph.chat_completion({'api_key':'offline-key','base_url':'https://offline.invalid/v1'},payload)
        self.assertEqual(result['content'],'原始全文');self.assertEqual(result['models'],['gemini-4-argon'])
        self.assertEqual(result['finish_reason'],'stop');self.assertEqual(result['request_id'],'offline-id')
        self.assertIs(opened.call_args.args[2],payload)

    def test_wrong_effort_or_missing_shared_definitions_is_rejected(self):
        config=json.loads(self.config.read_text());config['reasoning_effort']='max'
        with self.assertRaisesRegex(ValueError,'high'):kh.Client(config)
        config['reasoning_effort']='high';config.pop('environment_id')
        with self.assertRaisesRegex(ValueError,'共享'):kh.Client(config)


if __name__=='__main__':unittest.main()
