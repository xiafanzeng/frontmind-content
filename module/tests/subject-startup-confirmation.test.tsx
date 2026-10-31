// @vitest-environment jsdom
import React, {act} from "react";
import {createRoot} from "react-dom/client";
import {expect, it, vi} from "vitest";
import Workspace from "../client/ContentSubjectWorkspace";
import {ContentWorkspaceHostProvider, type ContentConversation, type ContentHomeProps, type ContentWorkspaceHost} from "../client/host";
import type {ContentBusinessClient} from "../client/runtime";
import type {ContentProductionDto} from "../contracts/content-production";
import type {ContentSubjectWorkspace} from "../contracts/content-subject-workspace";
import {useComposerConfirmation} from "../client/useComposerConfirmation";


const nativeProgress: ContentProductionDto = {
  mode:"single_article",enterpriseName:"合成主体",workflowVersion:"4.13.2-v16.8-app1",sessionPhases:true,workflowStatus:"awaiting_blueprint_confirmation",
  currentStage:"awaiting_blueprint_confirmation",jobKind:"article",runnerRevision:12,pauseTitle:"确认写作方案",choices:[],productionStep:null,
  confirmation:"awaiting_blueprint_confirmation",progressPosition:18,completedConfirmations:[],availableActions:["confirm_blueprint"],knowledgeBase:null,source:"runner_job_state",
};

async function mount(options: {kind?:"pack"|"article";taskId?:string;intake?:boolean;progress?:ContentProductionDto;status?:string;messages?:ContentConversation["messages"];contentIntakeReceipt?:ContentConversation["contentIntakeReceipt"];latest?:boolean;generation?:number;unbound?:boolean;emptyWorkspace?:boolean;missingPack?:boolean;otherConversation?:boolean;emptyFolder?:boolean;deleteError?:Error} = {}) {
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT = true;
  let conversation:ContentConversation={id:"chat",title:"合成聊天",purpose:"content_production",status:options.status??(options.taskId?"awaiting_input":"idle"),taskId:options.taskId,messages:options.messages??[],contentIntakeReceipt:options.contentIntakeReceipt,createdAt:1,updatedAt:1};
  const kind=options.kind??"pack";
  const subjects:ContentSubjectWorkspace={schemaVersion:1,revision:0,folders:[{id:"subject",name:"合成主体",versions:kind==="article"||options.latest?[{id:"pack-v1",folderId:"subject",version:1,sourceConversationId:"source",file:{fileUrl:"/local-pack.zip",fileName:"资料包.zip",mimeType:"application/zip"},createdAt:"2026-10-23T00:00:00.000Z",includesP0:true}]:[]}],bindings:{chat:{folderId:"subject",kind,packVersionId:kind==="article"?"pack-v1":null,generation:options.generation??0},source:{folderId:"subject",kind:"pack",packVersionId:null,generation:0},other:{folderId:"subject",kind:"pack",packVersionId:null,generation:0}}};
  if(options.unbound)delete subjects.bindings.chat;
  if(options.emptyWorkspace){subjects.folders=[];subjects.bindings={};}
  if(options.emptyFolder){subjects.bindings={};subjects.folders[0].versions=[];}
  if(options.missingPack){subjects.folders[0].versions=[];subjects.bindings.chat.packVersionId=null;}
  const send=vi.fn(async()=>true);
  const task=vi.fn(async(id:string)=>({id,status:options.status??"awaiting_input",purpose:"content_production" as const,contentProduction:options.progress??nativeProgress}));
  const refresh=vi.fn(async()=>{});
  const deleteConversation=vi.fn(async()=>{if(options.deleteError)throw options.deleteError;});
  const setActive=vi.fn();
  const otherConversation:ContentConversation={id:"other",title:"同文件夹下一聊天",purpose:"content_production",status:"idle",messages:[],createdAt:2,updatedAt:2};
  const conversations=options.otherConversation?[conversation,otherConversation]:[conversation];
  const client:ContentBusinessClient={list:vi.fn(async()=>[conversation]),save:vi.fn(async(value)=>value),remove:vi.fn(async()=>{}),upload:vi.fn(async()=>({fileId:"unused",filename:"unused"})),dispatch:vi.fn(async()=>{throw new Error("测试不能启动任务");}),task,stop:vi.fn(async()=>{}),readSubjectWorkspace:vi.fn(async()=>structuredClone(subjects)),saveSubjectWorkspace:vi.fn(async value=>value),...(options.intake?{submitIntake:vi.fn(async()=>{throw new Error("提交由宿主运行时负责");})}:{})};
  let home!:ContentHomeProps;
  const host:ContentWorkspaceHost={connections:{publishedKnowledge:false},ConversationPurposeProvider:({children})=><>{children}</>,useConversation:()=>({state:{conversations},activeConversation:conversation,hydrated:true,createConversation:()=>"",setActive,deleteConversation,refreshConversations:refresh}),useSendMessage:()=>({sendMessage:send}),retrieveTask:task,captureWorkspaceRestOperation:(signal=new AbortController().signal)=>({signal,assertActive:()=>signal.throwIfAborted(),fetch}),useWorkspaceDraftGuard(){},requestWorkspaceNavigation:operation=>operation(),Home:props=>{home=props;return <div>{props.conversationFooter}</div>;},FilePreview:()=>null,WorkbenchTaskToolbar:()=>null,BusinessWorkspaceInspector:()=>null,AgentWorkbenchShell:({main,auxiliary})=><>{main}{auxiliary}</>};
  const container=document.createElement("div");document.body.append(container);const root=createRoot(container);
  const render=async()=>{await act(async()=>root.render(<ContentWorkspaceHostProvider value={host}><Workspace client={client}/></ContentWorkspaceHostProvider>));};
  await render();
  return {container,client,send,task,refresh,deleteConversation,setActive,home:()=>home,update:async(changes:Partial<ContentConversation>)=>{conversation={...conversation,...changes};await render();},cleanup:async()=>{await act(async()=>root.unmount());container.remove();}};
}

function button(container:HTMLElement,text:string){return [...container.querySelectorAll("button")].find(item=>item.textContent===text)!;}
function deckCard(container:HTMLElement,text:string){return [...container.querySelectorAll<HTMLButtonElement>(".cp-task-card-trigger")].find(item=>item.textContent?.includes(text))!;}

it("主体文件夹内嵌在工作区第二列，搜索只过滤当前目录且不依赖全局侧栏 portal",async()=>{
 const view=await mount();
 try{
  const nav=view.container.querySelector<HTMLElement>('nav[aria-label="主体文件夹与聊天"]');
  expect(nav).not.toBeNull();
  expect(nav?.parentElement?.classList.contains("cp-subject-workspace")).toBe(true);
  expect(nav?.querySelector('input[aria-label="搜索主体与聊天"]')).not.toBeNull();
  expect(view.container.querySelector(".cp-subject-nav--sidebar")).toBeNull();
  expect(view.container.querySelector(".is-sidebar-integrated")).toBeNull();
  const input=nav!.querySelector("input") as HTMLInputElement;
  const setValue=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value")?.set;
  await act(async()=>{setValue?.call(input,"合成聊天");input.dispatchEvent(new Event("input",{bubbles:true}));});
  expect(nav!.textContent).toContain("合成主体");
  expect(nav!.textContent).toContain("合成聊天");
  await act(async()=>{setValue?.call(input,"没有匹配项");input.dispatchEvent(new Event("input",{bubbles:true}));});
  expect(nav!.textContent).toContain("没有匹配的主体或聊天");
  expect(nav!.querySelector(".cp-subject-chat")).toBeNull();
 }finally{await view.cleanup();}
});
it("执行期间隐藏上轮确认卡和快捷确认按钮，不重复提交",async()=>{
 const view=await mount({taskId:"same-task",status:"running"});
 try{expect(view.container.textContent).not.toContain("当前需要确认");expect(button(view.container,"确认蓝图，开始写作")).toBeUndefined();expect(view.send).not.toHaveBeenCalled();}
 finally{await view.cleanup();}
});
it("服务器已接受后立即结束确认卡，不等待慢速列表刷新而显示正在提交",async()=>{
 const view=await mount({taskId:"same-task"});
 let release!:()=>void;vi.mocked(view.refresh).mockImplementationOnce(()=>new Promise<void>(resolve=>{release=resolve;}));
 try{
  let sent!:Promise<boolean|void>;await act(async()=>{sent=view.home().onComposerSubmit!("确认写作方案",[]);});
  await act(async()=>button(view.container,"确认提交").click());
  expect(await sent).toBe(true);expect(view.send).toHaveBeenCalledTimes(1);expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();
 }finally{await act(async()=>release?.());await view.cleanup();}
});
it("装配中断后仅在明确继续时复用原任务，不创建新流程或重跑研究",async()=>{
  const view=await mount({taskId:"original-task",status:"completed",progress:{...nativeProgress,jobKind:"reference_pack",workflowStatus:"running_reference_pack_assembly",confirmation:null,availableActions:[]}});
  try{
    expect(view.send).not.toHaveBeenCalled();expect(view.container.textContent).toContain("继续未完成步骤");
    await act(async()=>{await view.home().onComposerSubmit!("继续原任务中未完成的资料包装配",[]);});
    expect(view.send).toHaveBeenCalledTimes(1);
    expect(view.send.mock.calls[0][2]).not.toHaveProperty("contentProduction");
    expect(view.client.dispatch).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it.each([['p0','p0_ready'],['article','completed']] as const)("%s 正文交付后仍可沿原任务提交修改与附件",async(jobKind,workflowStatus)=>{
 const view=await mount({taskId:"original-task",status:"completed",generation:4,progress:{...nativeProgress,jobKind,workflowStatus,confirmation:null,availableActions:[]}});
 try{
  const file=new File(["本次正文修改依据"],"补充事实.txt",{type:"text/plain"});
  await act(async()=>{expect(await view.home().onComposerSubmit!("修改正文，合并重复段落并更新交付文件",[file])).toBe(true);});
  expect(view.send).toHaveBeenCalledTimes(1);
  expect(view.send).toHaveBeenCalledWith("修改正文，合并重复段落并更新交付文件",[file],expect.objectContaining({contentWorkflowStatus:workflowStatus,contentWorkflowGeneration:4,contentWorkflowKind:jobKind}));
  expect(view.send.mock.calls[0][2]).not.toHaveProperty("contentProduction");
  expect(view.send.mock.calls[0][2]).not.toHaveProperty("contentProductionAction");
  expect(view.client.dispatch).not.toHaveBeenCalled();
  expect(view.container.textContent).not.toContain("当前没有待确认的写作步骤");
 }finally{await view.cleanup();}
});

it("交付后修改未被服务器接受时保留输入，不将提交记为成功",async()=>{
 const view=await mount({taskId:"original-task",status:"completed",progress:{...nativeProgress,jobKind:"p0",workflowStatus:"p0_ready",confirmation:null,availableActions:[]}});
 try{
  view.refresh.mockClear();
  view.send.mockResolvedValueOnce(false);
  await act(async()=>{expect(await view.home().onComposerSubmit!("修改正文",[])).toBe(false);});
  expect(view.send).toHaveBeenCalledOnce();expect(view.refresh).not.toHaveBeenCalled();
 }finally{await view.cleanup();}
});

it("阶段尚未读取时不把修改文字当作已交付稿件续写",async()=>{
 const view=await mount({taskId:"original-task",status:"completed",progress:{...nativeProgress,workflowStatus:null,confirmation:null,availableActions:[]}});
 try{
  await act(async()=>{expect(await view.home().onComposerSubmit!("修改正文",[])).toBe(false);});
  expect(view.send).not.toHaveBeenCalled();expect(view.container.textContent).toContain("当前没有待确认的写作步骤");
 }finally{await view.cleanup();}
});

it("归档入口已移除，历史聊天行提供真实删除入口",async()=>{
  const view=await mount();
  try{
    expect(view.container.querySelector('[aria-label="归档聊天：合成聊天"]')).toBeNull();
    expect(view.container.querySelector('[aria-label="删除聊天：合成聊天"]')).not.toBeNull();
    expect(view.container.textContent).not.toContain("已归档（");
  }finally{await view.cleanup();}
});

it("历史项目无需归属和新资料包即可打开，原消息、附件、任务均不改写",async()=>{
  const history:ContentConversation["messages"]=[{id:"legacy-user",role:"user",content:"原客户资料",timestamp:1,attachments:[{id:"original-asset",fileId:"original-asset",type:"file",name:"原附件.pdf"}]},{id:"legacy-answer",role:"assistant",content:"原回答",timestamp:2,contentWorkflowPosition:3,contentWorkflowGeneration:4,outputFiles:[{fileUrl:"/original-output.md",fileName:"原交付.md",mimeType:"text/markdown"}]}];
  const original=structuredClone(history);
  const view=await mount({unbound:true,emptyWorkspace:true,taskId:"original-task",messages:history});
  try{
    expect(view.home()).toBeDefined();expect(view.container.textContent).toContain("历史项目");expect(view.container.textContent).toContain("原任务与附件");
    expect(view.container.textContent).not.toContain("请先明确所属主体");expect(view.container.textContent).not.toContain("当前文件夹尚无已确认资料包");
    expect(view.home().knowledgeEditingBlocked).toBe(false);expect(view.container.textContent).toContain("交付文件（1）");
    expect(view.task).toHaveBeenCalledWith("original-task",expect.anything());
    expect(view.client.saveSubjectWorkspace).not.toHaveBeenCalled();expect(view.client.save).not.toHaveBeenCalled();expect(view.client.upload).not.toHaveBeenCalled();expect(view.client.dispatch).not.toHaveBeenCalled();expect(view.send).not.toHaveBeenCalled();
    expect(history).toEqual(original);
    const first=[...view.container.querySelectorAll('[data-stage-index]')].find(item=>item.getAttribute("data-stage-index")==="0")!;
    await act(async()=>{first.dispatchEvent(new MouseEvent("click",{bubbles:true}));});
    expect(view.home().transcriptNavigation?.messageId).toBe("legacy-user");
  }finally{await view.cleanup();}
});

it("历史任务确认沿用原动作和代际，不创建新流程或补主体绑定",async()=>{
  const view=await mount({unbound:true,emptyWorkspace:true,taskId:"original-task",messages:[{id:"original-message",role:"assistant",content:"历史方案",timestamp:1,contentWorkflowGeneration:3}]});
  try{
    let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("确认写作方案",[]);});
    expect(view.send).not.toHaveBeenCalled();await act(async()=>button(view.container,"确认提交").click());expect(await result).toBe(true);
    expect(view.send.mock.calls[0][2]).toMatchObject({contentProductionAction:{kind:"confirm_blueprint",revision:12},contentWorkflowGeneration:3});
    expect(view.send.mock.calls[0][2]).not.toHaveProperty("contentProduction");expect(view.client.saveSubjectWorkspace).not.toHaveBeenCalled();
    expect(view.task.mock.calls.every(([id])=>id==="original-task")).toBe(true);
  }finally{await view.cleanup();}
});

it("已有任务的旧文章不因新版没有资料包登记而被阻断",async()=>{
  const view=await mount({kind:"article",missingPack:true,taskId:"original-task"});
  try{expect(view.home()).toBeDefined();expect(view.container.textContent).not.toContain("请先完成资料包，再继续这篇文章");expect(view.home().knowledgeEditingBlocked).toBe(false);expect(view.container.querySelector('[aria-current="step"]')?.getAttribute("data-stage-index")).toBe("5");expect(view.client.saveSubjectWorkspace).not.toHaveBeenCalled();}
  finally{await view.cleanup();}
});

it("没有任务的历史记录也直接显示，打开时不补建任务",async()=>{
  const view=await mount({unbound:true,emptyWorkspace:true,messages:[{id:"old",role:"assistant",content:"旧聊天",timestamp:1}]});
  try{expect(view.home()).toBeDefined();expect(view.home().knowledgeEditingBlocked).toBe(true);expect(view.container.textContent).toContain("历史记录可直接查看");expect(view.task).not.toHaveBeenCalled();expect(view.send).not.toHaveBeenCalled();expect(view.client.dispatch).not.toHaveBeenCalled();expect(view.client.save).not.toHaveBeenCalled();}
  finally{await view.cleanup();}
});

it("旧聊天归入主体后保留原内容，不因尚未登记版本而重新被遮挡",async()=>{
  const view=await mount({kind:"article",missingPack:true,messages:[{id:"existing",role:"assistant",content:"原有文章",timestamp:1,outputFiles:[{fileUrl:"/existing.md",fileName:"原文章.md",mimeType:"text/markdown"}]}]});
  try{expect(view.home()).toBeDefined();expect(view.container.textContent).toContain("交付文件（1）");expect(view.container.textContent).not.toContain("请先完成资料包，再继续这篇文章");expect(view.home().knowledgeEditingBlocked).toBe(true);expect(view.client.save).not.toHaveBeenCalled();expect(view.client.saveSubjectWorkspace).not.toHaveBeenCalled();}
  finally{await view.cleanup();}
});

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
    expect(view.send).toHaveBeenCalledWith("本公司提供便携式设备。",[file],{contentProduction:{mode:"new_reference_pack",enterpriseName:"合成主体",knowledgeSource:"files",monitoringAnswerAssetIds:[],subjectContext:{folderId:"subject",generation:0,packVersionId:null}},contentWorkflowGeneration:0});
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
  try{let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("如何选择便携式健康终端？",[]);});expect(view.send).not.toHaveBeenCalled();expect(button(view.container,"确认提交")).toBeDefined();await act(async()=>button(view.container,"确认提交").click());expect(await result).toBe(true);expect(view.send.mock.calls[0][2]).toEqual({contentProduction:{mode:"single_article",enterpriseName:"合成主体",knowledgeSource:"files",monitoringAnswerAssetIds:[],subjectContext:{folderId:"subject",generation:0,packVersionId:"pack-v1"}},contentWorkflowGeneration:0});}
  finally{await view.cleanup();}
});

it("首轮提交失败保留卡片及原输入，重试成功后才结束承诺",async()=>{
  const view=await mount();
  try{view.send.mockRejectedValueOnce(new Error("收件未确认"));let result!:Promise<boolean|void>;await act(async()=>{result=view.home().onComposerSubmit!("企业介绍与产品服务材料",[]);});await act(async()=>button(view.container,"确认提交").click());expect(view.container.textContent).toContain("收件未确认");expect(button(view.container,"确认提交").disabled).toBe(false);expect(view.container.querySelector('[aria-label="输入确认卡片"]')?.textContent).toContain("企业介绍与产品服务材料");await act(async()=>button(view.container,"确认提交").click());expect(await result).toBe(true);expect(view.send).toHaveBeenCalledTimes(2);expect(view.container.textContent).not.toContain("收件未确认");}
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

it("刷新后的已收件聊天保留持久提示，不再提示补资料或生成第二张确认卡",async()=>{
  const view=await mount({intake:true,messages:[{id:"received-input",role:"user",content:"已存储的真实材料",timestamp:2,generalChatDispatch:{kind:"pending_user"}}]});
  try{
    expect(view.container.textContent).toContain("服务器已收件，生成尚未启动");
    expect(view.container.textContent).not.toContain("可直接输入主体简介");
    expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();
    expect(view.home().knowledgeEditingBlocked).toBe(false);
    let accepted:boolean|void;await act(async()=>{accepted=await view.home().onComposerSubmit!("重复输入",[]);});
    expect(accepted!).toBe(false);expect(view.container.textContent).toContain("请勿重复提交当前聊天");
    expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();
    expect(view.send).not.toHaveBeenCalled();expect(view.client.upload).not.toHaveBeenCalled();expect(view.client.dispatch).not.toHaveBeenCalled();expect(view.task).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it("正常生成模式中已有用户消息仍可继续本轮输入，不被仅收件状态拦截",async()=>{
  const view=await mount({messages:[{id:"normal-user",role:"user",content:"普通首轮原文",timestamp:1}]});
  try{
    await act(async()=>{void view.home().onComposerSubmit!("继续补充产品材料",[]);});
    expect(button(view.container,"确认提交")).toBeDefined();expect(view.container.textContent).not.toContain("服务器已收件");expect(view.send).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it("普通客户端首次和更新读回有效收件回执后不再确认或重复提交",async()=>{
  const receipt:NonNullable<ContentConversation["contentIntakeReceipt"]>={schemaVersion:1,id:"received-request",conversationId:"chat",messageId:"received-user",acceptedAt:2,status:"received",executionStarted:false};
  const messages:ContentConversation["messages"]=[{id:"received-user",role:"user",content:"合成已收件材料",timestamp:2,generalChatDispatch:{kind:"pending_user",clientRequestId:"received-request"}}];
  const view=await mount({messages,contentIntakeReceipt:receipt});
  const assertReceived=()=>{
    expect(view.container.textContent).toContain("服务器已收件，生成尚未启动");
    expect(view.container.textContent).not.toContain("可直接输入主体简介");
    expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();
  };
  try{
    expect(view.client.submitIntake).toBeUndefined();assertReceived();
    await view.update({messages:structuredClone(messages),contentIntakeReceipt:structuredClone(receipt),updatedAt:3});assertReceived();
    const file=new File(["重复材料"],"duplicate.txt",{type:"text/plain"});let accepted:boolean|void;
    await act(async()=>{accepted=await view.home().onComposerSubmit!("重复提交已收件材料",[file]);});
    expect(accepted!).toBe(false);assertReceived();
    expect(view.container.textContent).toContain("请勿重复提交当前聊天");
    expect(view.send).not.toHaveBeenCalled();expect(view.client.upload).not.toHaveBeenCalled();expect(view.client.dispatch).not.toHaveBeenCalled();expect(view.task).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it.each(["running","completed"])("主体工作区：外层 %s 不掩盖实际失败，也不采用遗留确认动作",async(status)=>{
  const progress={...nativeProgress,executionFailure:{action:"positioning_market_research",code:"tool_call_source_mismatch",attemptId:"synthetic-attempt"}};
  const view=await mount({kind:"article",taskId:"failed-task",progress,status});
  try{
    expect(view.container.querySelector('[role="alert"]')?.textContent).toContain("市场研究执行失败");
    expect(view.container.querySelector('[role="alert"]')?.textContent).toContain("tool_call_source_mismatch");
    expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();
    expect(view.container.querySelector(".cp-task-deck")).not.toBeNull();
    let accepted:boolean|void;
    await act(async()=>{accepted=await view.home().onComposerSubmit!("确认写作方案",[]);});
    expect(accepted!).toBe(false);
    expect(view.send).not.toHaveBeenCalled();
    expect(view.container.textContent).toContain("本轮执行已停止");
  }finally{await view.cleanup();}
});

it("主体工作区：P0 已有产出但本轮失败时，不提供问题文章接续",async()=>{
  const progress:ContentProductionDto={...nativeProgress,jobKind:"p0",workflowVersion:"4.13.2-v16.8.3",workflowStatus:"p0_ready",currentStage:"p0_ready",confirmation:null,availableActions:[],executionFailure:{action:"write_p0",code:"synthetic_failure",attemptId:"synthetic-attempt"}};
  const view=await mount({kind:"article",taskId:"failed-task",progress,status:"completed"});
  try{
    expect(view.container.querySelector('[role="alert"]')?.textContent).toContain("本轮执行失败");
    expect([...view.container.querySelectorAll("button")].some(item=>item.textContent==="继续问题与监控数据")).toBe(false);
    expect(view.send).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it("主体工作区：已确认提交后列表读取失败，不回退为可重试的提交卡片",async()=>{
  const view=await mount();
  try{
    view.refresh.mockRejectedValueOnce(new Error("列表读取暂时失败"));
    let result!:Promise<boolean|void>;
    await act(async()=>{result=view.home().onComposerSubmit!("企业介绍与产品服务材料",[]);});
    await act(async()=>button(view.container,"确认提交").click());
    expect(await result).toBe(true);
    expect(view.send).toHaveBeenCalledTimes(1);
    expect(view.container.querySelector('[aria-label="输入确认卡片"]')).toBeNull();
    expect(view.container.textContent).toContain("已提交，状态读取失败");
    expect(view.container.textContent).toContain("勿重复提交");
  }finally{await view.cleanup();}
});

it("确认提交中阶段失效且请求失败，清除旧确认卡，不把重试带到下一阶段",async()=>{
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
  let reject!:(reason:Error)=>void;
  const commit=vi.fn(()=>new Promise<never>((_resolve,fail)=>{reject=fail;}));
  let confirmation!:ReturnType<typeof useComposerConfirmation>;
  function Harness({phase}:{phase:string|null}){
    confirmation=useComposerConfirmation(phase,nativeProgress,commit,()=>{});
    return confirmation.pending?<div data-testid="pending-confirmation"/>:null;
  }
  const container=document.createElement("div");document.body.append(container);const root=createRoot(container);
  try{
    await act(async()=>root.render(<Harness phase="old-phase"/>));
    let staged!:Promise<boolean>;
    await act(async()=>{staged=confirmation.stage("确认写作方案",[]);});
    let submitting!:Promise<void>;
    await act(async()=>{submitting=confirmation.confirm();});
    await act(async()=>root.render(<Harness phase={null}/>));
    await act(async()=>{reject(new Error("旧阶段请求失败"));await submitting;});
    expect(container.querySelector('[data-testid="pending-confirmation"]')).toBeNull();
    expect(await staged).toBe(false);
    await act(async()=>{await confirmation.confirm();});
    expect(commit).toHaveBeenCalledTimes(1);
  }finally{await act(async()=>root.unmount());container.remove();}
});


it("资料包更新首轮携带最新已确认版本和当前代际，不从浏览器传文件地址",async()=>{
  const view=await mount({latest:true,generation:2});
  try{
    let result!:Promise<boolean|void>;
    await act(async()=>{result=view.home().onComposerSubmit!("更新企业产品材料",[]);});
    await act(async()=>button(view.container,"确认提交").click());
    expect(await result).toBe(true);
    expect(view.send.mock.calls[0][2]).toEqual({contentProduction:{mode:"refresh_reference_pack",enterpriseName:"合成主体",knowledgeSource:"files",monitoringAnswerAssetIds:[],subjectContext:{folderId:"subject",generation:2,packVersionId:"pack-v1"}},contentWorkflowGeneration:2});
    expect(view.client.dispatch).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});


it("同一聊天重启后清除旧失败任务，不阻塞新首轮确认且保留历史交付",async()=>{
  const history:ContentConversation["messages"]=[{id:"old-answer",role:"assistant",content:"历史交付",timestamp:1,outputFiles:[{fileUrl:"/historical-output.md",fileName:"历史文章.md",mimeType:"text/markdown"}]}];
  const view=await mount({kind:"article",taskId:"old-failed-task",status:"error",messages:history});
  try{
    let rejected:boolean|void;
    await act(async()=>{rejected=await view.home().onComposerSubmit!("旧任务未重启时不能继续",[]);});
    expect(rejected!).toBe(false);expect(view.send).not.toHaveBeenCalled();
    const oldReads=view.task.mock.calls.length;
    await view.update({taskId:undefined,previousResponseId:undefined,status:"idle"});
    let result!:Promise<boolean|void>;
    await act(async()=>{result=view.home().onComposerSubmit!("切换后重新确认本篇题目",[]);});
    expect(view.container.querySelector('[aria-label="输入确认卡片"]')?.textContent).toContain("核对本次输入");
    expect(view.container.textContent).toContain("交付文件（1）");
    await act(async()=>button(view.container,"确认提交").click());
    expect(await result).toBe(true);
    expect(view.send.mock.calls[0][2]).toMatchObject({contentProduction:{mode:"single_article",subjectContext:{folderId:"subject",generation:0,packVersionId:"pack-v1"}}});
    expect(view.send.mock.calls[0][2]).not.toHaveProperty("contentProductionAction");
    expect(view.task.mock.calls).toHaveLength(oldReads);
  }finally{await view.cleanup();}
});


it.each(["error","stopped","cancelled"])("启动前 %s 后明确重试原任务，沿用附件且不重建冻结上下文",async(status)=>{
 const original={id:"original-user",role:"user" as const,content:"读取原材料完成 1.1–1.3",timestamp:1,attachments:[{id:"original-asset",fileId:"original-asset",type:"file" as const,name:"原材料.docx"}]};
 const view=await mount({taskId:"original-task",status,messages:[original],progress:{...nativeProgress,source:"awaiting_runner",workflowStatus:null,currentStage:null,jobKind:null,runnerRevision:null,confirmation:null,availableActions:[]}});
 try{const retry=deckCard(view.container,"重试启动原任务");expect(retry).toBeDefined();await act(async()=>{retry.click();retry.click();});expect(view.send).toHaveBeenCalledTimes(1);expect(view.send).toHaveBeenCalledWith(original.content,[],{});expect(view.client.upload).not.toHaveBeenCalled();expect(view.task).toHaveBeenCalledWith("original-task");}
 finally{await view.cleanup();}
});

it("已创建 Workflow 后通过共有工作区恢复原执行，发送当前修订号",async()=>{
 const view=await mount({taskId:"original-task",status:"stopped",progress:{...nativeProgress,confirmation:null,availableActions:["resume_current_execution"]}});
 try{expect(deckCard(view.container,"重试启动原任务")).toBeUndefined();await act(async()=>deckCard(view.container,"恢复当前执行").click());expect(view.send).toHaveBeenCalledWith("恢复当前执行",[],{contentProductionAction:{kind:"resume_current_execution",revision:12}});}
 finally{await view.cleanup();}
});


it("共有工作区停止原任务，服务端确认后刷新记录",async()=>{
 const view=await mount({taskId:"original-task",status:"running"});
 try{vi.mocked(view.client.task).mockResolvedValue({id:"original-task",status:"stopped",contentProduction:{...nativeProgress,confirmation:null,availableActions:["resume_current_execution"]}});await act(async()=>{const stop=button(view.container,"停止当前执行");stop.click();stop.click();});expect(view.client.stop).toHaveBeenCalledTimes(1);expect(view.client.stop).toHaveBeenCalledWith("original-task");expect(view.refresh).toHaveBeenCalled();expect(view.send).not.toHaveBeenCalled();}
 finally{await view.cleanup();}
});

it("按任务冻结能力接续 v16.8.4 资料包并保留原聊天",async()=>{
  const view=await mount({taskId:"original-task",status:"completed",progress:{...nativeProgress,workflowVersion:"4.13.2-v16.8.4",sessionPhases:true,jobKind:"reference_pack",workflowStatus:"positioning_ready",confirmation:null,availableActions:[]}});
  try{
    expect(view.container.textContent).toContain("在本聊天继续品牌长文");
    await act(async()=>deckCard(view.container,"继续制作品牌长文").click());
    expect(view.send).toHaveBeenCalledTimes(1);
    expect(view.send).toHaveBeenCalledWith("继续 P0");
    expect(view.client.save).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});
it("冻结能力未启用时不因发行版本较新开放阶段接续",async()=>{
  const view=await mount({taskId:"historical-task",status:"completed",progress:{...nativeProgress,workflowVersion:"4.13.2-v16.8.4",sessionPhases:false,jobKind:"reference_pack",workflowStatus:"positioning_ready",confirmation:null,availableActions:[]}});
  try{expect(deckCard(view.container,"继续制作品牌长文")).toBeUndefined();}
  finally{await view.cleanup();}
});

it("确认页已生成但外层执行失败时，先显式恢复原任务再提交业务选择",async()=>{
 const view=await mount({taskId:"original-task",status:"error",progress:{...nativeProgress,confirmation:"awaiting_p0_route",availableActions:["resume_current_execution"]}});
 try{expect(button(view.container,"先制作品牌长文")).toBeUndefined();await act(async()=>deckCard(view.container,"恢复当前执行").click());expect(view.send).toHaveBeenCalledWith("恢复当前执行",[],{contentProductionAction:{kind:"resume_current_execution",revision:12}});}
 finally{await view.cleanup();}
});

it("按真实内容哈希合并重复交付，保留同名修订稿",async()=>{
 const file={fileName:"定位.md",mimeType:"text/markdown",sha256:"a".repeat(64)};
 const messages:ContentConversation["messages"]=[{id:"one",role:"assistant",content:"第一次交付",timestamp:1,outputFiles:[{...file,fileUrl:"/artifact-one"}]},{id:"two",role:"assistant",content:"重复导出与修订",timestamp:2,outputFiles:[{...file,fileUrl:"/artifact-two"},{...file,fileUrl:"/artifact-three",sha256:"b".repeat(64)}]}];
 const view=await mount({messages});
 try{expect(view.container.textContent).toContain("交付文件（2）");}finally{await view.cleanup();}
});


it("绑定聊天点击删除会显示包含聊天名的二次确认",async()=>{
 const view=await mount();
 try{
  await act(async()=>{(view.container.querySelector('[aria-label="删除聊天：合成聊天"]') as HTMLButtonElement).click();});
  expect(view.container.querySelector('[role="dialog"]')?.textContent).toContain("确认删除聊天");
  expect(view.container.querySelector('[role="dialog"]')?.textContent).toContain("合成聊天");
  expect(view.deleteConversation).not.toHaveBeenCalled();
 }finally{await view.cleanup();}
});

it("绑定聊天确认删除成功后刷新会话和主体资料库并显示成功提示",async()=>{
 const view=await mount({otherConversation:true});
 try{
  await act(async()=>{(view.container.querySelector('[aria-label="删除聊天：合成聊天"]') as HTMLButtonElement).click();});
  await act(async()=>{button(view.container,"确认删除").click();});
  expect(view.deleteConversation).toHaveBeenCalledWith("chat");
  expect(view.refresh).toHaveBeenCalled();
  expect(view.client.readSubjectWorkspace).toHaveBeenCalledTimes(2);
  expect(view.setActive).toHaveBeenCalledWith("other");
  expect(view.container.textContent).toContain("聊天已删除");
 }finally{await view.cleanup();}
});

it("删除遇到服务端 409 时透出原始原因且不显示成功提示，聊天仍可重试",async()=>{
 const view=await mount({deleteError:new Error("该聊天是已确认资料包版本的来源，不能删除。")});
 try{
  await act(async()=>{(view.container.querySelector('[aria-label="删除聊天：合成聊天"]') as HTMLButtonElement).click();});
  await act(async()=>{button(view.container,"确认删除").click();});
  expect(view.container.textContent).toContain("该聊天是已确认资料包版本的来源，不能删除。");
  expect(view.container.textContent).not.toContain("聊天已删除");
  expect(view.container.querySelector('[aria-label="删除聊天：合成聊天"]')).not.toBeNull();
  expect(view.deleteConversation).toHaveBeenCalledTimes(1);
 }finally{await view.cleanup();}
});

it("未绑定历史聊天仍显示二次确认并走删除调用",async()=>{
 const view=await mount({unbound:true,emptyWorkspace:true});
 try{
  await act(async()=>{(view.container.querySelector('[aria-label="删除聊天：合成聊天"]') as HTMLButtonElement).click();});
  expect(view.container.querySelector('[role="dialog"]')?.textContent).toContain("合成聊天");
  await act(async()=>{button(view.container,"确认删除").click();});
  expect(view.deleteConversation).toHaveBeenCalledWith("chat");
  expect(view.container.textContent).toContain("聊天已删除");
 }finally{await view.cleanup();}
});

it("删除当前选中聊天后回退到同文件夹下一聊天",async()=>{
 const view=await mount({otherConversation:true});
 try{
  await act(async()=>{(view.container.querySelector('[aria-label="删除聊天：合成聊天"]') as HTMLButtonElement).click();});
  await act(async()=>{button(view.container,"确认删除").click();});
  expect(view.setActive).toHaveBeenCalledWith("other");
 }finally{await view.cleanup();}
});


it("空文件夹仍需二次确认后才删除，保留原有资料库删除路径",async()=>{
 const view=await mount({emptyFolder:true});
 try{
  await act(async()=>{(view.container.querySelector('[aria-label="删除文件夹：合成主体"]') as HTMLButtonElement).click();});
  expect(view.container.querySelector('[role="dialog"]')?.textContent).toContain("确认删除文件夹");
  await act(async()=>{button(view.container,"确认删除").click();});
  expect(view.client.saveSubjectWorkspace).toHaveBeenCalled();
  expect(view.container.textContent).toContain("文件夹已删除");
 }finally{await view.cleanup();}
});
