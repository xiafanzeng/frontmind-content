"""Explicit OFFLINE fake of the SDK public surface, not a substitute SDK.

Tests use a real local sqlite file but fabricated model outputs. This does not
prove official SDK or XTY integration; test_agents_real_sdk_v4130 is separate.
"""
import copy,json,sqlite3
from types import SimpleNamespace as NS


def bundle(*, fault=None, result=None):
    engine=NS(calls=0,client_kwargs=[],closed=0,session_closed=0,fault=fault,failed=False,result=result or {'ok':True},runs=0,submits=0,submit_feedback_tolerance=3,bad_args_done=False)
    class Session:
        def __init__(self,session_id,path):
            self.session_id=session_id;self.db=sqlite3.connect(path)
            self.db.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER PRIMARY KEY, session TEXT, item TEXT)');self.db.commit()
        async def get_items(self,limit=None):
            rows=[json.loads(r[0]) for r in self.db.execute('SELECT item FROM items WHERE session=? ORDER BY id',(self.session_id,))]
            return rows if limit is None else rows[-limit:]
        async def add_items(self,items):
            self.db.executemany('INSERT INTO items(session,item) VALUES (?,?)',[(self.session_id,json.dumps(x)) for x in items]);self.db.commit()
        async def clear_session(self):self.db.execute('DELETE FROM items WHERE session=?',(self.session_id,));self.db.commit()
        def close(self):self.db.close();engine.session_closed+=1
    class State:
        def __init__(self,items,pending,approved=None,rejected=None):self.items,self.pending,self.approved,self.rejected=copy.deepcopy(items),copy.deepcopy(pending),list(approved or []),list(rejected or [])
        def approve(self,item,always_approve=False):self.approved.append(item.raw_item['call_id'])
        def reject(self,item,always_reject=False,rejection_message=None):self.rejected.append((item.raw_item['call_id'],rejection_message))
        def to_json(self):return {'items':self.items,'pending':self.pending,'approved':self.approved,'rejected':self.rejected}
        @classmethod
        async def from_json(cls,agent,value):return cls(value['items'],value['pending'],value.get('approved'),value.get('rejected'))
        def get_interruptions(self):return [NS(name=c['name'],arguments=c['arguments'],raw_item=c) for c in self.pending if c['call_id'] not in self.approved]
    class Result:
        def __init__(self,state=None,output=None):
            self.state=state;self.final_output=output;self.interruptions=state.get_interruptions() if state else []
        def to_state(self):return self.state
    class Client:
        def __init__(self,**kwargs):engine.client_kwargs.append(kwargs)
        async def close(self):engine.closed+=1
    class Model:
        def __init__(self,model,openai_client):self.model=model
        async def get_response(self,**kwargs):
            engine.calls+=1;items=kwargs['input']
            read=any(x.get('type')=='function_call_output' for x in items)
            if engine.fault=='network_always':
                raise OSError('offline simulated lost response')
            if ((engine.fault=='network_first' and not read) or (engine.fault=='network_after_read' and read)) and not engine.failed:
                engine.failed=True;raise OSError('offline simulated lost response')
            if engine.fault=='no_submit':return NS(output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'done'}]}],response_id='fixture')
            # Local fix 2026-09-21: the agent no longer stops at submit_result, so
            # emulate a model that ends its run after a successful submit receipt
            # and that corrects itself once after a validation feedback receipt.
            receipts=[]
            for x in items:
                if x.get('type')=='function_call_output' and isinstance(x.get('output'),str):
                    try:receipts.append(json.loads(x['output']))
                    except ValueError:pass
            if any(isinstance(r,dict) and r.get('submitted') for r in receipts):
                return NS(output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'{"submitted":true}'}]}],response_id='fixture_final')
            feedbacks=[r for r in receipts if isinstance(r,dict) and r.get('error')]
            if len(feedbacks)>engine.submit_feedback_tolerance:
                return NS(output=[{'type':'message','role':'assistant','content':[{'type':'output_text','text':'giving up'}]}],response_id='fixture_giveup')
            # After an argument-parse rejection the required read never ran; a
            # well-behaved model reissues the read before submitting again.
            if engine.fault=='bad_args_once' and feedbacks and not any(isinstance(r,dict) and not r.get('error') for r in receipts):
                return NS(output=[{'type':'function_call','call_id':'read_2','name':'read_material','arguments':'{"artifact_id":"one"}'}],response_id='fixture_retry_read')
            if engine.fault=='bad_args_once' and not feedbacks and not engine.bad_args_done:
                engine.bad_args_done=True
                return NS(output=[{'type':'function_call','call_id':'read_bad_1','name':'read_material','arguments':'{"artifact_id":"one","artifact_id":"two"}'}],response_id='fixture_badargs')
            result=engine.result
            if engine.fault=='invalid_final' and not feedbacks:
                # First submission deliberately violates the content contract
                # (simulates the real blueprint that dropped required fields).
                result={'ok':False,'reason':'deliberately invalid first submission'}
            name='submit_result' if read or engine.fault=='unread' else 'read_material'
            if feedbacks:name='submit_result'
            if engine.fault=='forbidden':name='execute_shell'
            args={'result':result} if name=='submit_result' else {'artifact_id':'one'}
            # Real models mint a fresh tool-call ID per invocation; reuse here
            # would trip the journal's call-ID reuse guard spuriously.
            if name=='submit_result':engine.submits+=1
            call={'type':'function_call','call_id':(name+'_'+str(engine.submits)) if name=='submit_result' else name+'_1','id':'fixture_'+name,'name':name,'arguments':json.dumps(args)}
            out=[call]
            if engine.fault=='mixed' and name=='submit_result':out.append({'type':'function_call','call_id':'read_2','name':'read_material','arguments':'{"artifact_id":"one"}'})
            return NS(output=out,response_id='fixture_response_'+str(engine.calls))
    class Runner:
        @staticmethod
        async def run(agent,current,*,session,max_turns,run_config):
            engine.runs+=1
            assert run_config.tracing_disabled is True
            if isinstance(current,State):
                items=copy.deepcopy(current.items)
                for call in current.pending:
                    rejection=next((m for cid,m in current.rejected if cid==call['call_id']),None)
                    if rejection is not None:
                        item={'type':'function_call_output','call_id':call['call_id'],'output':json.dumps({'error':rejection},ensure_ascii=False)}
                        items.append(item);await session.add_items([item]);continue
                    assert call['call_id'] in current.approved
                    t=next(t for t in agent.tools if t.name==call['name'])
                    output=await t.on_invoke_tool(NS(tool_call_id=call['call_id']),call['arguments'])
                    item={'type':'function_call_output','call_id':call['call_id'],'output':output}
                    items.append(item);await session.add_items([item])
                    # The durable submit receipt is written inside on_invoke_tool;
                    # this fault emulates a crash after commit but before return.
                    if call['name']=='submit_result' and engine.fault=='after_submit' and not engine.failed:
                        engine.failed=True;raise OSError('offline crash after tool commit')
                    stop_names=agent.tool_use_behavior.get('stop_at_tool_names') if isinstance(agent.tool_use_behavior,dict) else []
                    if call['name'] in (stop_names or []):
                        return Result(output=output)
            else:
                items=await session.get_items()+copy.deepcopy(current);await session.add_items(current)
            response=await agent.model.get_response(system_instructions=agent.instructions,input=items,model_settings=agent.model_settings,tools=agent.tools)
            await session.add_items(response.output)
            pending=[x for x in response.output if x['type']=='function_call']
            if pending:return Result(State(items+response.output,pending))
            return Result(output='plain text without submission')
    ag=NS(Agent=lambda **kw:NS(**{'tool_use_behavior':'run_llm',**kw}),FunctionTool=lambda **kw:NS(**kw),ModelSettings=lambda **kw:NS(**kw),RunConfig=lambda **kw:NS(**kw),SQLiteSession=Session,RunState=State,Runner=Runner,OpenAIChatCompletionsModel=Model)
    oa=NS(AsyncOpenAI=Client,DefaultAsyncHttpxClient=lambda **kw:NS(**kw))
    return (ag,oa),engine
