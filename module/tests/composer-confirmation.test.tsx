// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {expect,it,vi} from "vitest";
import {ModuleWorkspace,type ContentBusinessClient} from "../client/runtime";
import type {ContentConversation} from "../client/host";
import type {ContentProductionDto} from "../contracts/content-production";

it("真实统一输入框：本地预览不写入，返回修改保留文字，确认成功才发送并清空",async()=>{
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
  const workspace="composer-confirmation-test";
  localStorage.setItem(`frontmind-content-active:${workspace}`,"conversation");
  let row:ContentConversation={id:"conversation",taskId:"task",title:"离线输入验收",purpose:"content_production",status:"awaiting_input",createdAt:1,updatedAt:1,messages:[{id:"ask",role:"assistant",content:"请选择新建或导入品牌文章。",timestamp:1}]};
  const progress:ContentProductionDto={mode:"p0",enterpriseName:"离线测试",workflowVersion:"4.13.2-v16.8-app1",workflowStatus:"awaiting_p0_route",currentStage:"p0_route",jobKind:"p0",runnerRevision:4,pauseTitle:"选择品牌文章制作方式",choices:["新建品牌文章","导入已有品牌文章"],productionStep:null,confirmation:"awaiting_p0_route",progressPosition:8,completedConfirmations:[],availableActions:["choose_p0_route"],knowledgeBase:null,source:"runner_job_state"};
  const task=async()=>({id:"task",purpose:"content_production" as const,status:"awaiting_input",contentProduction:progress});
  const forbidden=vi.fn(async():Promise<never>=>{throw new Error("禁止本地预览产生额外请求");});
  const save=vi.fn(async(value:ContentConversation)=>{row=structuredClone(value);return structuredClone(row);});
  const dispatch=vi.fn(async()=>task());
  const client:ContentBusinessClient={list:async()=>structuredClone([row]),task,save,dispatch,upload:forbidden,stop:forbidden,remove:forbidden};
  const el=document.createElement("div");document.body.append(el);const root=createRoot(el);
  const button=(text:string)=>[...el.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent===text)!;
  try{
    await act(async()=>root.render(<ModuleWorkspace context={{module:"content",workspace:{id:workspace,ownerUserId:0},marketEdition:"cn",capabilities:["content"]}} client={client}/>));
    const input=el.querySelector<HTMLTextAreaElement>("textarea")!;
    expect(input).not.toBeNull();expect(el.querySelectorAll("textarea")).toHaveLength(1);
    await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value")!.set!.call(input,"新建品牌文章");input.dispatchEvent(new Event("input",{bubbles:true}));});
    await act(async()=>el.querySelector<HTMLButtonElement>('[aria-label="发送消息"]')!.click());
    expect(el.querySelector(".cp-composer-confirmation-text")?.textContent).toBe("新建品牌文章");
    expect(dispatch).not.toHaveBeenCalled();expect(save).not.toHaveBeenCalled();expect(forbidden).not.toHaveBeenCalled();
    await act(async()=>button("返回修改").click());
    expect(input.value).toBe("新建品牌文章");
    await act(async()=>el.querySelector<HTMLButtonElement>('[aria-label="发送消息"]')!.click());
    await act(async()=>button("确认提交").click());
    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({prompt:"新建品牌文章",contentProductionAction:{kind:"choose_p0_route",revision:4,route:"create"}}),"task");
    expect(input.value).toBe("");expect(forbidden).not.toHaveBeenCalled();
  }finally{await act(async()=>root.unmount());el.remove();localStorage.removeItem(`frontmind-content-active:${workspace}`);}
});
