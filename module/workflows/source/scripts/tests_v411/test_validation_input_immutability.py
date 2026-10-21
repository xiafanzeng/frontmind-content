"""离线回归：业务规范化不得改写模型参数、工具签名或来源证据。"""
import copy,json,tempfile,unittest
from pathlib import Path
from shared import agents_runtime as ar,model_runtime as rt
from scripts.tests_v411.agents_sdk_fake import bundle
from scripts.tests_v411.test_model_runtime import FakeTools


def normalize(value):
    for index,item in enumerate(value['competitor_candidates'],1):
        item['id']=f'c{index:03d}'
        item['source_urls']=[url for url in item['source_urls'] if url is not None]
    return value


class ValidationInputImmutabilityTests(unittest.TestCase):
    def payload(self):
        return {'competitor_candidates':[{'name':'离线候选A','source_urls':[None,'https://example.test/a']}]}

    def test_in_place_validator_produces_normalized_copy(self):
        original=self.payload();before=copy.deepcopy(original)
        checked=rt._checked(normalize,original)
        self.assertEqual(original,before)
        self.assertIsNot(checked,original)
        self.assertEqual(checked['competitor_candidates'][0]['id'],'c001')
        self.assertEqual(checked['competitor_candidates'][0]['source_urls'],['https://example.test/a'])

    def test_none_returning_validator_still_returns_its_normalized_copy(self):
        original=self.payload();before=copy.deepcopy(original)
        def validate(value):normalize(value)
        checked=rt._checked(validate,original)
        self.assertEqual(original,before)
        self.assertEqual(checked['competitor_candidates'][0]['id'],'c001')

    def test_failed_validation_cannot_corrupt_original_arguments(self):
        original=self.payload();before=copy.deepcopy(original)
        def validate(value):
            normalize(value)
            raise ValueError('离线校验失败')
        with self.assertRaisesRegex(ValueError,'离线校验失败'):rt._checked(validate,original)
        self.assertEqual(original,before)

    def test_source_checker_cannot_mutate_original_payload(self):
        original=self.payload();before=copy.deepcopy(original)
        class Tools:
            def validate_result_sources(self,value):value['competitor_candidates'][0]['verified']=True
        checked=rt._checked(lambda value:value,original,Tools())
        self.assertEqual(original,before)
        self.assertTrue(checked['competitor_candidates'][0]['verified'])

    def test_sdk_submission_keeps_raw_evidence_and_recovers_without_paid_calls(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);pkg=root/'pkg';job=root/'job';pkg.mkdir();job.mkdir()
            payload=self.payload();sdk,engine=bundle(result=payload)
            def execute(retry=False):
                return rt.run_action(pkg,job,'p0_blueprint','离线证据回归',normalize,retry=retry,
                    host_tools=FakeTools(),transport=sdk,offline=True)
            result=execute();self.assertEqual(result,normalize(copy.deepcopy(payload)))
            record=rt.action_record(job,'p0_blueprint')
            attempt=job/'provider/p0_blueprint/runtime/attempts'/record['attempt_id']
            submission=rt._read_json(attempt/'submission.json')
            receipt=rt._read_json(attempt/submission['tool_file'])
            self.assertEqual(receipt['arguments'],{'result':payload})
            self.assertEqual(receipt['signature'],ar.digest({'name':'submit_result','arguments':receipt['arguments'],'call_id':receipt['call_id']}))
            self.assertEqual(ar._source_call(attempt,receipt['call_id'],'submit_result',receipt['arguments']),receipt['source'])
            self.assertEqual(rt._read_json(attempt/'parsed_result.json'),payload)
            self.assertEqual(rt._read_json(attempt/'validated_result.json'),result)
            before_calls=engine.calls;self.assertEqual(execute(),result);self.assertEqual(engine.calls,before_calls)
            self.assertEqual(ar.restore_result(attempt,record,FakeTools(),normalize),result)
            tampered=copy.deepcopy(receipt['arguments']);tampered['result']['competitor_candidates'][0]['name']='已篡改'
            with self.assertRaises(rt.ProviderActionError) as error:
                ar._source_call(attempt,receipt['call_id'],'submit_result',tampered)
            self.assertEqual(error.exception.code,'tool_call_source_mismatch')



class OfficialSdkMutationTests(unittest.TestCase):
    payload=ValidationInputImmutabilityTests.payload
    @unittest.skipUnless(__import__('importlib.util',fromlist=['find_spec']).find_spec('agents'),'未安装官方SDK')
    def test_real_sdk_with_fake_model_preserves_submission_arguments(self):
        import agents,openai
        from agents.items import ModelResponse
        from agents.usage import Usage
        from openai.types.responses import ResponseFunctionToolCall,ResponseOutputMessage,ResponseOutputText
        from unittest.mock import patch
        calls=[];payload=self.payload()
        async def model_response(instance,*args,**kwargs):
            items=kwargs.get('input',args[1] if len(args)>1 else [])
            outputs=[x for x in items if isinstance(x,dict) and x.get('type')=='function_call_output']
            calls.append(True)
            if outputs and json.loads(outputs[-1]['output']).get('submitted') is True:
                text=ResponseOutputText(text='已提交。',annotations=[],type='output_text')
                return ModelResponse(output=[ResponseOutputMessage(id='offline_done',role='assistant',status='completed',content=[text],type='message')],usage=Usage(),response_id=None)
            name='submit_result' if outputs else 'read_material'
            arguments={'result':payload} if outputs else {'artifact_id':'one'}
            return ModelResponse(output=[ResponseFunctionToolCall(type='function_call',name=name,arguments=json.dumps(arguments),call_id='offline_'+name,id='fc_'+name)],usage=Usage(),response_id=None)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);pkg=root/'pkg';job=root/'job';pkg.mkdir();job.mkdir()
            with patch.object(agents.OpenAIChatCompletionsModel,'get_response',model_response):
                result=ar.run_agents_action(pkg,job,'p0_blueprint','离线官方SDK证据回归',normalize,host_tools=FakeTools(),offline=True,sdk_override=(agents,openai))
            record=rt.action_record(job,'p0_blueprint')
            attempt=job/'provider/p0_blueprint/runtime/attempts'/record['attempt_id']
            sub=rt._read_json(attempt/'submission.json');receipt=rt._read_json(attempt/sub['tool_file'])
            self.assertEqual(result,normalize(copy.deepcopy(payload)))
            self.assertEqual(receipt['arguments'],{'result':payload})
            self.assertEqual(ar._source_call(attempt,receipt['call_id'],'submit_result',receipt['arguments']),receipt['source'])
            self.assertEqual(ar.restore_result(attempt,record,FakeTools(),normalize),result)
            self.assertEqual(len(calls),3)


if __name__=='__main__':unittest.main()
