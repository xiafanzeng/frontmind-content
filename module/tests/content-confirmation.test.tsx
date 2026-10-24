// @vitest-environment jsdom
import React,{act} from 'react';
import {createRoot} from 'react-dom/client';
import {expect,it,vi} from 'vitest';
import Confirmation from '../client/ContentProductionConfirmation';
import {ContentWorkspaceHostProvider,type ContentWorkspaceHost} from '../client/host';
import type {ContentProductionDto} from '../contracts/content-production';

it('分别提交文风与文章池选择；缺选择或提交失败时保留草稿',async()=>{
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
  const host={useWorkspaceDraftGuard:vi.fn()} as unknown as ContentWorkspaceHost;
  const progress={workflowVersion:'4.13.2-v16.8',confirmation:'awaiting_example_route',availableActions:['choose_examples'],runnerRevision:9,
    choices:['文风 A/B','文章池请选择1—2篇或不采用']} as unknown as ContentProductionDto;
  const action=vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true),notice=vi.fn();
  const el=document.createElement('div');document.body.append(el);const root=createRoot(el);
  try{
    await act(async()=>root.render(<ContentWorkspaceHostProvider value={host}><Confirmation progress={progress} busy={false} onAction={action} onNotice={notice}/></ContentWorkspaceHostProvider>));
    const button=[...el.querySelectorAll('button')].find(b=>b.textContent==='使用工作流写作规范')!;
    await act(async()=>button.click());expect(action).not.toHaveBeenCalled();expect(notice).toHaveBeenCalled();
    const input=el.querySelector<HTMLInputElement>('input[aria-label="文章池构思参考"]')!;
    await act(async()=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(input,'1、5');input.dispatchEvent(new Event('input',{bubbles:true}));});
    const submit=[...el.querySelectorAll('button')].find(b=>b.textContent==='确认文风与构思参考')!;
    await act(async()=>submit.click());
    expect(action).toHaveBeenLastCalledWith(expect.stringContaining('文章池构思参考选择：1、5'),[],{kind:'choose_examples',revision:9,route:'B'});
    expect(action.mock.calls[0]![0]).toContain('AI 答案不作为文风样本');expect(input.value).toBe('1、5');
    await act(async()=>submit.click());expect(input.value).toBe('');
  }finally{await act(async()=>root.unmount());el.remove();}
});
