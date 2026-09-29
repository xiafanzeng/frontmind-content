"""Actual official SDK, fake MODEL only. Skips when dependency is absent.
This is separate from the public-surface fake suite and from paid XTY probes.
"""
import importlib.util,json
import pytest
from unittest.mock import patch
from shared import agents_runtime as ar,model_runtime as rt
from scripts.tests_v411.test_model_runtime import FakeTools,valid
pytestmark=pytest.mark.skipif(importlib.util.find_spec('agents') is None,reason='official openai-agents not installed in this environment')

@pytest.mark.parametrize('fail_once',[False,True])
def test_real_runner_sqlite_and_serialized_resume(tmp_path,fail_once):
    import agents
    import openai
    from agents.items import ModelResponse
    from agents.usage import Usage
    from openai.types.responses import ResponseFunctionToolCall
    calls=[];failed=False
    async def model_response(self,*args,**kwargs):
        nonlocal failed
        items=kwargs.get('input',args[1] if len(args)>1 else [])
        read=any(isinstance(x,dict) and x.get('type')=='function_call_output' for x in items)
        calls.append(read)
        if fail_once and read and not failed:failed=True;raise OSError('synthetic one-time model failure')
        # Local fix 4.13.3 removed the hard stop at submit_result: a validated
        # submission is answered with an "already submitted" tool receipt and the
        # run only ends when the model produces a plain closing message.
        outputs=[x for x in items if isinstance(x,dict) and x.get('type')=='function_call_output']
        if outputs:
            try: last=json.loads(outputs[-1]['output'])
            except (TypeError,ValueError): last={}
            if isinstance(last,dict) and last.get('submitted') is True:
                from openai.types.responses import ResponseOutputMessage,ResponseOutputText
                text=ResponseOutputText(text='已提交,收尾。',annotations=[],type='output_text')
                return ModelResponse(output=[ResponseOutputMessage(id='msg_close_1',role='assistant',status='completed',content=[text],type='message')],usage=Usage(),response_id=None)
        name='submit_result' if read else 'read_material'
        arguments={'result':{'ok':True}} if read else {'artifact_id':'one'}
        return ModelResponse(output=[ResponseFunctionToolCall(type='function_call',name=name,arguments=json.dumps(arguments),call_id='real_sdk_'+name,id='fc_'+name)],usage=Usage(),response_id=None)
    pkg=tmp_path/'pkg';job=tmp_path/'job';pkg.mkdir();job.mkdir()
    with patch.object(agents.OpenAIChatCompletionsModel,'get_response',model_response):
        if fail_once:
            with pytest.raises(rt.ProviderActionError):ar.run_agents_action(pkg,job,'p0_blueprint','task',valid,host_tools=FakeTools(),offline=True,sdk_override=(agents,openai))
        result=ar.run_agents_action(pkg,job,'p0_blueprint','task',valid,retry=fail_once,host_tools=FakeTools(),offline=True,sdk_override=(agents,openai))
    assert result=={'ok':True}
    # 4.13.3 local fix: one extra plain closing turn after a validated submit,
    # per attempt; the failing attempt contributes its calls as well.
    assert len(calls)==(4 if fail_once else 3)


@pytest.mark.parametrize('scenario',['contract_error','started_read'])
def test_real_runner_hotfix_error_feedback_and_readonly_resume(tmp_path,scenario):
    """Official Runner/RunState/SQLite; only model responses are fabricated."""
    import agents
    import openai
    from agents.items import ModelResponse
    from agents.usage import Usage
    from openai.types.responses import ResponseFunctionToolCall
    from shared.host_tools import ToolError
    class TestTools(FakeTools):
        def __init__(self,fail=True):super().__init__();self.fail=fail;self.executions=0
        def execute(self,name,args):
            self.executions+=1
            if self.fail:
                self.fail=False
                if scenario=='contract_error':raise ToolError('Use the exact registered source.')
                raise OSError('synthetic interruption after local read start')
            return super().execute(name,args)
    async def model_response(self,*args,**kwargs):
        items=kwargs.get('input',args[1] if len(args)>1 else [])
        outputs=[x for x in items if isinstance(x,dict) and x.get('type')=='function_call_output']
        last={}
        if outputs:
            try: last=json.loads(outputs[-1]['output'])
            except (TypeError,ValueError): last={}
        # Same closing-message contract as the other real-SDK test: after a
        # validated submission the model must end with plain text, not resubmit.
        if isinstance(last,dict) and last.get('submitted') is True:
            from openai.types.responses import ResponseOutputMessage,ResponseOutputText
            text=ResponseOutputText(text='已提交,收尾。',annotations=[],type='output_text')
            return ModelResponse(output=[ResponseOutputMessage(id='msg_close_2',role='assistant',status='completed',content=[text],type='message')],usage=Usage(),response_id=None)
        error=isinstance(last,dict) and last.get('ok') is False
        name='read_material' if not outputs or error else 'submit_result'
        arguments={'artifact_id':'one'} if name=='read_material' else {'result':{'ok':True}}
        cid='official_'+name+('_corrected' if error else '_1')
        return ModelResponse(output=[ResponseFunctionToolCall(type='function_call',name=name,
            arguments=json.dumps(arguments),call_id=cid,id='fc_'+cid)],usage=Usage(),response_id=None)
    pkg=tmp_path/'pkg';job=tmp_path/'job';pkg.mkdir();job.mkdir();tools=TestTools()
    with patch.object(agents.OpenAIChatCompletionsModel,'get_response',model_response):
        if scenario=='started_read':
            with pytest.raises(rt.ProviderActionError):
                ar.run_agents_action(pkg,job,'p0_blueprint','task',valid,host_tools=tools,offline=True,sdk_override=(agents,openai))
            old=rt.action_record(job,'p0_blueprint')
            tools=TestTools(fail=False)
        result=ar.run_agents_action(pkg,job,'p0_blueprint','task',valid,retry=scenario=='started_read',
            host_tools=tools,offline=True,sdk_override=(agents,openai))
    assert result=={'ok':True}
    record=rt.action_record(job,'p0_blueprint')
    attempt=job/'provider/p0_blueprint/runtime/attempts'/record['attempt_id']
    receipts=[rt._read_json(p) for p in attempt.glob('tool_*.json')]
    assert record['status']=='succeeded'
    if scenario=='contract_error':
        assert any(r['status']=='completed' and r['output'].get('ok') is False for r in receipts)
        assert tools.executions==2
    else:
        assert record['session_id']==old['session_id']
        assert tools.executions==1
        assert any(r.get('readonly_replay_count')==1 and r['status']=='completed' for r in receipts)
