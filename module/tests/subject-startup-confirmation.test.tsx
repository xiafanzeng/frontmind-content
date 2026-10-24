// @vitest-environment jsdom
import React, {act} from "react";
import {createRoot} from "react-dom/client";
import {expect, it, vi} from "vitest";
import Workspace from "../client/ContentSubjectWorkspace";
import {ContentWorkspaceHostProvider, type ContentConversation, type ContentHomeProps, type ContentWorkspaceHost} from "../client/host";
import type {ContentBusinessClient} from "../client/runtime";
import type {ContentProductionDto} from "../contracts/content-production";
import type {ContentSubjectWorkspace} from "../contracts/content-subject-workspace";

vi.mock("@frontmind/module-ui/dashboard/ModuleShell", () => ({useModuleSidebarTarget: () => null}));

const nativeProgress: ContentProductionDto = {
  mode:"single_article",enterpriseName:"合成主体",workflowVersion:"4.13.2-v16.8-app1",workflowStatus:"awaiting_blueprint_confirmation",
  currentStage:"awaiting_blueprint_confirmation",jobKind:"article",runnerRevision:12,pauseTitle:"确认写作方案",choices:[],productionStep:null,
  confirmation:"awaiting_blueprint_confirmation",progressPosition:18,completedConfirmations:[],availableActions:["confirm_blueprint"],knowledgeBase:null,source:"runner_job_state",
};

async function mount(options: {kind?:"pack"|"article";taskId?:string;intake?:boolean} = {}) {
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT = true;
  let conversation:ContentConversation={id:"chat",title:"合成聊天",purpose:"content_production",status:options.taskId?"awaiting_input":"idle",taskId:options.taskId,messages:[],createdAt:1,updatedAt:1};
  const kind=options.kind??"pack";
  const subjects:ContentSubjectWorkspace={schemaVersion:1,revision:0,folders:[{id:"subject",name:"合成主体",versions:kind==="article"?[{id:"pack-v1",folderId:"subject",version:1,sourceConversationId:"source",file:{fileUrl:"/local-pack.zip",fileName:"资料包.zip",mimeType:"application/zip"},createdAt:"2026-10-23T00:00:00.000Z",includesP0:true}]:[]}],bindings:{chat:{folderId:"subject",kind,packVersionId:kind==="article"?"pack-v1":null,generation:0},source:{folderId:"subject",kind:"pack",packVersionId:null,generation:0},other:{folderId:"subject",kind:"pack",packVersionId:null,generation:0}}};
  const send=vi.fn(async()=>true);
  const task=vi.fn(async(id:string)=>({id,status:"awaiting_input",purpose:"content_production" as const,contentProduction:nativeProgress}));
  const refresh=vi.fn(async()=>{});
  const client:ContentBusinessClient={list:vi.fn(async()=>[conversation]),save:vi.fn(async(value)=>value),remove:vi.fn(async()=>{}),upload:vi.fn(async()=>({fileId:"unused",filename:"unused"})),dispatch:vi.fn(async()=>{throw new Error("测试不能启动任务");}),task,stop:vi.fn(async()=>{}),readSubjectWorkspace:vi.fn(async()=>structuredClone(subjects)),saveSubjectWorkspace:vi.fn(async value=>value),...(options.intake?{submitIntake:vi.fn(async()=>{throw new Error("提交由宿主运行时负责");})}:{})};
  let home!:ContentHomeProps;
  const host:ContentWorkspaceHost={connections:{publishedKnowledge:false},ConversationPurposeProvider:({children})=><>{children}</>,useConversation:()=>({state:{conversations:[conversation]},activeConversation:conversation,hydrated:true,createConversation:()=>"",setActive(){},deleteConversation(){},refreshConversations:refresh}),useSendMessage:()=>({sendMessage:send}),retrieveTask:task,captureWorkspaceRestOperation:(signal=new AbortController().signal)=>({signal,assertActive:()=>signal.throwIfAborted(),fetch}),useWorkspaceDraftGuard(){},requestWorkspaceNavigation:operation=>operation(),Home:props=>{home=props;return <div>{props.conversationFooter}</div>;},FilePreview:()=>null,WorkbenchTaskToolbar:()=>null,BusinessWorkspaceInspector:()=>null,AgentWorkbenchShell:({main,auxiliary})=><>{main}{auxiliary}</>};
  const container=document.createElement("div");document.body.append(container);const root=createRoot(container);
  const render=async()=>{await act(async()=>root.render(<ContentWorkspaceHostProvider value={host}><Workspace client={client}/></ContentWorkspaceHostProvider>));};
  await render();
  return {container,client,send,task,refresh,home:()=>home,update:async(changes:Partial<ContentConversation>)=>{conversation={...conversation,...changes};await render();},cleanup:async()=>{await act(async()=>root.unmount());container.remove();}};
}

function button(container:HTMLElement,text:string){return [...container.querySelectorAll("button")].find(item=>item.textContent===text)!;}

it("首轮企业材料先核对，确认后才提交配置；不伪造原生状态或提前上传",async()=>{
  const view=await mount({intake:true});
  try{
    const file=new File(["合成材料"],"企业简介.txt",{type:"text/plain"});let result!:Promise<boolean|void>;
    await act(async()=>{result=view.home().onComposerSubmit!("本公司提供便携式设备。",[file]);});
    expect(view.send).not.toHaveBeenCalled();expect(view.client.upload).not.toHaveBeenCalled();expect(view.client.dispatch).not.toHaveBeenCalled();
    expect(view.container.querySelector('[aria-label="输入确认卡片"]')?.textContent).toContain("核对本次输入");
    expect(view.container.textContent).toContain("仅核对输入，生成尚未启动");
    expect(view.container.textContent).not.toContain("服务器已收件");
    await act(async()=>button(view.container,"确认提交").click());
    expect(await result).toBe(true);
    expect(view.send).toHaveBeenCalledWith("本公司提供便携式设备。",[file],{contentProduction:{mode:"new_reference_pack",enterpriseName:"合成主体",knowledgeSource:"files",monitoringAnswerAssetIds:[]},contentWorkflowGeneration:0});
    expect(view.task).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it("首轮返回修改保留原提交承诺，不调用宿主发送",async()=>{
  const view=await mount();
  try{let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("企业产品介绍",[]);});await act(async()=>button(view.container,"返回修改").click());expect(await result).toBe(false);expect(view.send).not.toHaveBeenCalled();expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();}
  finally{await view.cleanup();}
});

it("首轮文章完整题目也先建卡，确认时保留原单篇配置",async()=>{
  const view=await mount({kind:"article"});
  try{let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("如何选择便携式健康终端？",[]);});expect(view.send).not.toHaveBeenCalled();expect(button(view.container,"确认提交")).toBeDefined();await act(async()=>button(view.container,"确认提交").click());expect(await result).toBe(true);expect(view.send.mock.calls[0][2]).toEqual({contentProduction:{mode:"single_article",enterpriseName:"合成主体",knowledgeSource:"files",monitoringAnswerAssetIds:[]},contentWorkflowGeneration:0});}
  finally{await view.cleanup();}
});

it("首轮提交失败保留卡片及原输入，重试成功后才结束承诺",async()=>{
  const view=await mount();
  try{view.send.mockRejectedValueOnce(new Error("收件未确认"));let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("企业介绍与产品服务材料",[]);});await act(async()=>button(view.container,"确认提交").click());expect(view.container.textContent).toContain("收件未确认");expect(button(view.container,"确认提交").disabled).toBe(false);expect(view.container.querySelector('[aria-label="输入确认卡片"]')?.textContent).toContain("企业介绍与产品服务材料");await act(async()=>button(view.container,"确认提交").click());expect(await result).toBe(true);expect(view.send).toHaveBeenCalledTimes(2);}
  finally{await view.cleanup();}
});

it("首轮切换聊天取消旧确认卡，不将旧材料提交到新聊天",async()=>{
  const view=await mount();
  try{let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("旧聊天材料",[]);});await view.update({id:"other",title:"另一聊天"});expect(await result).toBe(false);expect(view.send).not.toHaveBeenCalled();expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();}
  finally{await view.cleanup();}
});

it("已有真实停点继续使用原动作与修订号，不走首轮输入投影",async()=>{
  const view=await mount({kind:"article",taskId:"native-task"});
  try{let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("确认写作方案",[]);});expect(view.send).not.toHaveBeenCalled();await act(async()=>button(view.container,"确认提交").click());expect(await result).toBe(true);expect(view.send.mock.calls[0][2]).toMatchObject({contentProductionAction:{kind:"confirm_blueprint",revision:12},contentWorkflowPosition:18,contentWorkflowStatus:"awaiting_blueprint_confirmation",contentWorkflowGeneration:0,contentWorkflowKind:"article"});expect(view.send.mock.calls[0][2]).not.toHaveProperty("contentProduction");}
  finally{await view.cleanup();}
});

it("只在宿主回填已接受用户消息后显示收件提示，仍不宣称资料包已创建",async()=>{
  const view=await mount({intake:true});
  try{expect(view.container.textContent).not.toContain("服务器已收件");await view.update({messages:[{id:"accepted-input",role:"user",content:"实际收件后回填的输入",timestamp:2}]});expect(view.container.textContent).toContain("服务器已收件，生成尚未启动");expect(view.task).not.toHaveBeenCalled();}
  finally{await view.cleanup();}
});
