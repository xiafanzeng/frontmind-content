// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {expect,it,vi} from "vitest";
import {ModuleWorkspace,type ContentBusinessClient} from "../client/runtime";
import type {ContentConversation} from "../client/host";
import type {ContentProductionDto} from "../contracts/content-production";

it("卡片工作台：统一输入框已隐藏，卡片选择经确认承诺提交且不产生额外请求",async()=>{
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
  const workspace="composer-confirmation-test";
  localStorage.setItem(`frontmind-content-active:${workspace}`,"conversation");
  let row:ContentConversation={id:"conversation",taskId:"task",title:"离线输入验收",purpose:"content_production",status:"awaiting_input",createdAt:1,updatedAt:1,messages:[{id:"ask",role:"assistant",content:"请选择新建或导入品牌文章。",timestamp:1}]};
  const progress:ContentProductionDto={mode:"p0",enterpriseName:"离线测试",workflowVersion:"4.13.2-v16.8-app1",workflowStatus:"awaiting_p0_route",currentStage:"p0_route",jobKind:"p0",runnerRevision:4,pauseTitle:"选择品牌文章制作方式",choices:["新建品牌文章","导入已有品牌文章"],productionStep:null,confirmation:"awaiting_p0_route",progressPosition:8,completedConfirmations:[],availableActions:["choose_p0_route"],knowledgeBase:null,source:"runner_job_state"};
  const task=async()=>({id:"task",purpose:"content_production" as const,status:"awaiting_input",contentProduction:progress});
  const forbidden=vi.fn(async():Promise<never>=>{throw new Error("禁止本地预览产生额外请求");});
  const save=vi.fn(async(value:ContentConversation)=>{row=structuredClone(value);return structuredClone(row);});
  const dispatch=vi.fn(async()=>task());
  // 使用正式主体入口：当前文章明确引用此前已确认的 v1 资料包，测试只读取夹具。
  const subjects={schemaVersion:1 as const,revision:1,folders:[{id:"subject",name:"离线测试",expanded:true,versions:[{
    id:"pack-v1",folderId:"subject",version:1,sourceConversationId:"pack-source",includesP0:false,
    createdAt:"2026-10-24T00:00:00Z",file:{fileUrl:"/synthetic/reference-pack.zip",fileName:"合成资料包.zip",mimeType:"application/zip"},
  }]}],bindings:{
    "pack-source":{folderId:"subject",kind:"pack" as const,packVersionId:null,generation:0},
    conversation:{folderId:"subject",kind:"article" as const,packVersionId:"pack-v1",generation:0},
  }};
  const source:ContentConversation={id:"pack-source",title:"合成资料包来源",purpose:"content_production",status:"completed",messages:[],createdAt:0,updatedAt:0};
  const client:ContentBusinessClient={list:async()=>structuredClone([row,source]),task,save,dispatch,upload:forbidden,stop:forbidden,remove:forbidden,
    readSubjectWorkspace:vi.fn(async()=>structuredClone(subjects)),saveSubjectWorkspace:forbidden};
  const el=document.createElement("div");document.body.append(el);const root=createRoot(el);
  const button=(text:string)=>[...el.querySelectorAll<HTMLButtonElement>("button")].find(item=>item.textContent===text)!;
  try{
    await act(async()=>root.render(<ModuleWorkspace context={{module:"content",workspace:{id:workspace,ownerUserId:0},marketEdition:"cn",capabilities:["content"]}} client={client}/>));
    expect(el.querySelector("textarea")).toBeNull();
    expect(el.querySelector(".agent-composer-controls")).toBeNull();
    const deckCard=(text:string)=>[...el.querySelectorAll<HTMLButtonElement>(".cp-task-card-trigger")].find(item=>item.textContent?.includes(text))!;
    await act(async()=>deckCard("新建品牌长文").click());
    expect(el.querySelector('[aria-label="输入确认卡片"]')).not.toBeNull();
    expect(dispatch).not.toHaveBeenCalled();expect(save).not.toHaveBeenCalled();expect(forbidden).not.toHaveBeenCalled();
    await act(async()=>button("返回修改").click());
    expect(el.querySelector('[aria-label="输入确认卡片"]')).toBeNull();
    await act(async()=>deckCard("新建品牌长文").click());
    await act(async()=>button("确认提交").click());
    expect(dispatch).toHaveBeenCalledTimes(1);
    expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({contentProductionAction:{kind:"choose_p0_route",revision:4,route:"create"}}),"task");
    expect(forbidden).not.toHaveBeenCalled();
  }finally{await act(async()=>root.unmount());el.remove();localStorage.removeItem(`frontmind-content-active:${workspace}`);}
});
