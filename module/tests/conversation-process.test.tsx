// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {afterEach,expect,it} from "vitest";
import Process from "../client/ConversationExecutionProcess";
import {mergeConversationProcesses,readConversationProcesses,type ConversationProcess} from "../contracts/conversation-process";
import {bindConversationProcesses} from "../server/conversation-process";
import {publicContentConversation} from "../server/conversations";
import type {ContentMessage} from "../client/host";

const fixture=(status:ConversationProcess["status"]="running"):ConversationProcess=>({id:"turn-1",userMessageId:"user-1",startedAt:100,status,thinking:[{id:"thought-1",timestamp:100,text:"正在处理：问题文章方案。",status:"recorded"},{id:"thought-2",timestamp:115,text:"正在结合登记材料处理：问题文章方案。",status:"recorded"}],tools:[{id:"tool-1",timestamp:110,text:"已完成读取登记材料。",status:"completed"}]});
afterEach(()=>{localStorage.clear();document.body.innerHTML="";});
async function mount(process=fixture()){
 (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
 const container=document.createElement("div");document.body.append(container);const root=createRoot(container);
 const render=async(p:ConversationProcess)=>act(async()=>root.render(<Process process={p}/>));await render(process);
 return {container,render,close:()=>act(async()=>root.unmount()),button:()=>container.querySelector(".cp-process-toggle")};
}
it("keeps summaries visible through running, confirmation, completion and refresh",async()=>{
 localStorage.setItem("frontmind-process-open:turn-1","false");
 const view=await mount();const node=view.container.querySelector("section");
 try{
  expect(view.button()).toBeNull();expect(view.container.querySelectorAll('li:not([hidden])')).toHaveLength(3);
  expect(view.container.querySelector(".cp-process-spinner")).not.toBeNull();
  for(const status of ["awaiting_input","completed"] as const){
   await view.render(fixture(status));
   expect(view.container.querySelector(".cp-process-spinner")).toBeNull();
   expect(view.button()).toBeNull();expect(view.container.querySelectorAll('li:not([hidden])')).toHaveLength(3);
   expect(view.container.querySelector("section")).toBe(node);
  }
 }finally{await view.close();}
 const refreshed=await mount(fixture("completed"));
 try{expect(refreshed.container.querySelectorAll('li:not([hidden])')).toHaveLength(3);}finally{await refreshed.close();}
});
it("renders public summary Markdown directly without a thinking disclosure",async()=>{
 const view=await mount({...fixture("completed"),thinking:[{id:"markdown-summary",text:"已核对**温控资料**，还需补充实际测评。",status:"recorded",summaryOrigin:"model",summaryRevision:7}]});
 try{
  expect(view.container.querySelector("strong")?.textContent).toBe("温控资料");
  expect(view.container.textContent).not.toContain("**");
  expect(view.container.querySelector("details")).toBeNull();expect(view.button()).toBeNull();
 }finally{await view.close();}
});
it("keeps original-task recovery visible after completion",async()=>{
 const view=await mount({...fixture("completed"),recovery:"已沿用原会话恢复。"});
 try{expect(view.container.querySelector(".cp-process-recovery")?.textContent).toContain("原会话");}finally{await view.close();}
});
it.each(["failed","cancelled","unknown"] as const)("does not call %s complete or show a spinner",async(status)=>{
 const view=await mount({...fixture(status),thinking:[],tools:[],reason:status==="cancelled"?"本次执行已取消。":"执行结果尚未确认。"});
 try{expect(view.button()).toBeNull();expect(view.container.querySelector(".cp-process-spinner")).toBeNull();expect(view.container.textContent).toContain("执行记录尚未返回");expect(view.container.textContent).not.toContain("已完成");}finally{await view.close();}
});
it("drops arbitrary summary payloads, unsafe identities and private extras on the server boundary",()=>{
 const input={...fixture(),reason:"SECRET /private/path",nextStep:"read_material(args)",input:"SECRET",thinking:[{...fixture().thinking[0],text:"SECRET internal reasoning"}],tools:[{...fixture().tools[0],args:{key:"SECRET"},result:"SECRET",stack:"SECRET"}]};
 const safe=JSON.stringify(readConversationProcesses([input]));expect(safe).not.toMatch(/SECRET|read_material|args|result|stack|private/);expect(readConversationProcesses([{...fixture(),id:"/private/path"}])).toEqual([]);
});
it("deduplicates replay, preserves terminal states and sorts by stable identity",()=>{
 const prior={...fixture("completed"),tools:[{...fixture().tools[0],status:"completed" as const,text:"已完成读取登记材料。"}]};
 const merged=mergeConversationProcesses([prior],[fixture(),fixture()]);expect(merged).toHaveLength(1);expect(merged[0].status).toBe("completed");expect(merged[0].tools).toHaveLength(1);expect(merged[0].tools[0].status).toBe("completed");
});
it("keeps UI rounds separate from imported history and anchors processes to users",()=>{
 const history={...fixture("failed"),id:"attempt-old",startedAt:10};const first={id:"turn-a",userMessageId:"user-a",startedAt:100,baseline:["attempt-old"]};const second={id:"turn-b",userMessageId:"user-b",startedAt:300,baseline:["attempt-old","attempt-a"]};
 const messages:ContentMessage[]=[{id:"user-a",role:"user",content:"first",timestamp:100},{id:"user-b",role:"user",content:"second",timestamp:300}];
 const processes=bindConversationProcesses([history,{...fixture("completed"),id:"attempt-a",startedAt:150},{...fixture(),id:"attempt-b",startedAt:350}],messages,[first,second],"running");
 expect(processes.find(p=>p.id==="turn-a")?.status).toBe("unknown");expect(processes.find(p=>p.id==="turn-b")?.userMessageId).toBe("user-b");expect(processes.find(p=>p.id==="attempt-old")?.userMessageId).toBe("history-attempt-old");expect(messages.at(-1)?.id).toBe("history-attempt-old");
});
it("creates a stable pre-session process and keeps old failure frozen during same-session recovery",()=>{
 const old={...fixture("failed"),id:"attempt-old",userMessageId:"history-attempt-old"};const turn={id:"turn-retry",userMessageId:"retry",startedAt:300,baseline:[old.id],summaryBaseline:["thought-1","thought-2","tool-1"],recoverAttemptId:old.id};
 const pending=bindConversationProcesses([],[],[turn],"running",[old]);expect(pending.find(p=>p.id===turn.id)?.thinking).toEqual([]);
 const resumed={...old,status:"completed",thinking:[...old.thinking,{id:"new-judgement",timestamp:400,text:"已提交阶段结果；交付状态另行核验。",status:"recorded"}],recovery:"已沿用原会话恢复。"};
 const output=bindConversationProcesses([resumed],[],[turn],"completed",[old]);expect(output.find(p=>p.id===old.id)?.status).toBe("failed");expect(output.find(p=>p.id===turn.id)?.thinking.map(r=>r.id)).toEqual(["new-judgement"]);expect(output.find(p=>p.id===turn.id)?.recovery).toContain("原会话");
});

it("enforces the same summary boundary in the installed module router",()=>{
 const snapshot=publicContentConversation({id:"content-1",purpose:"content_production",messages:[],execution:{timeline:[{reasoning:"SECRET",functionName:"read_material",arguments:{key:"SECRET"}}]},processes:[{...fixture(),privatePath:"SECRET"}]});
 expect(snapshot.execution).toBeUndefined();expect(JSON.stringify(snapshot)).not.toMatch(/SECRET|functionName|read_material|arguments/);
});

it("accepts bounded model summaries at the server boundary and rejects raw protocol or private text",()=>{
 const base=fixture();
 const summary={...base.tools[0],text:"已读取官网，温控参数仍需与实际使用场景比对。",summaryOrigin:"model",summaryRevision:7};
 const safe=readConversationProcesses([{...base,tools:[summary],thinking:[]}]);
 expect(safe[0]?.tools[0]?.text).toContain("温控参数");
 for(const text of ["调用 read_material 获取内容。","读取 /Users/test/private.json 完成。","返回 {参数:内容} 后继续。","实际凭据 sk-secretvalue 已返回。"]){
  expect(readConversationProcesses([{...base,tools:[{...summary,text}]}])[0]?.tools).toEqual([]);
 }
 expect(readConversationProcesses([{...base,tools:[{...summary,summaryOrigin:undefined}]}])[0]?.tools).toEqual([]);
});

it("keeps a real document receipt when its Chinese model summary contains the public term OCR",()=>{
 const base=fixture("completed");
 const receipt={...base.tools[0],text:"已提取指定文档，共1791字符并包含一张图片，OCR无待识别页，提取完成。",summaryOrigin:"model",summaryRevision:7,status:"completed"};
 const first=readConversationProcesses([{...base,thinking:[],tools:[receipt]}]);
 expect(first[0]?.tools).toHaveLength(1);expect(first[0]?.tools[0]?.status).toBe("completed");
 expect(readConversationProcesses(first)).toEqual(first);
});

it("late model summaries update the same completed row without status or caption regression",()=>{
 const prior={...fixture("completed"),tools:[{...fixture().tools[0],status:"completed" as const,text:"已完成读取登记材料。"}]};
 const model={...prior,tools:[{...prior.tools[0],text:"已核对产品材料，噪音数据只适用于指定测试条件。",summaryOrigin:"model" as const,summaryRevision:7}]};
 const merged=mergeConversationProcesses([prior],[model]);
 expect(merged[0].tools[0].id).toBe(prior.tools[0].id);expect(merged[0].tools[0].text).toContain("噪音数据");
 const stale={...fixture(),tools:[{...fixture().tools[0],text:"正在读取产品材料。",summaryOrigin:"model" as const,summaryRevision:6}]};
 const again=mergeConversationProcesses(merged,[stale]);expect(again[0].status).toBe("completed");expect(again[0].tools[0].status).toBe("completed");expect(again[0].tools[0].text).toContain("噪音数据");
});

it("late summaries remain in the archived user turn after the next turn starts",()=>{
 const old={...fixture("completed"),id:"turn-old",userMessageId:"user-old"};
 const native={...old,id:"attempt-old",startedAt:110,tools:[{...old.tools[0],status:"completed" as const,text:"已核对温控材料，测试范围尚不能代表全部使用场景。",summaryOrigin:"model" as const,summaryRevision:7}]};
 const messages=[{id:"user-old",role:"user" as const,timestamp:100,content:"旧任务"},{id:"user-new",role:"user" as const,timestamp:300,content:"新任务"}];
 const turns=[{id:"turn-old",userMessageId:"user-old",startedAt:100,baseline:[]},{id:"turn-new",userMessageId:"user-new",startedAt:300,baseline:["attempt-old"]}];
 const result=bindConversationProcesses([native],messages,turns,"running",[old]);
 expect(result.find(p=>p.id==="turn-old")!.tools[0].text).toContain("温控材料");expect(result.find(p=>p.id==="turn-new")!.tools).toEqual([]);
});

it("shows only a fixed activity hint before the step ends, then keeps its completed summary identity",async()=>{
 const pending={...fixture(),thinking:[],tools:[{id:"pending-tool",timestamp:110,text:"正在调用工具。",status:"running" as const}]};
 const view=await mount({...pending,tools:[]});
 try{
  expect(view.container.textContent).toBe("正在思考");expect(view.button()).toBeNull();
  await view.render(pending);expect(view.container.querySelector(".cp-process-status")?.textContent).toBe("正在调用工具");expect(view.container.querySelectorAll("li:not([hidden])")).toHaveLength(0);const pendingNode=view.container.querySelector("li");
  const complete={...pending,tools:[{...pending.tools[0],text:"已读取示例网页，内容仅用于文档示例说明。",status:"completed" as const,summaryOrigin:"model" as const,summaryRevision:7}]};
  await view.render(complete);const node=view.container.querySelector("li");expect(node).toBe(pendingNode);expect(view.container.textContent).toContain("正在思考");
  await view.render(mergeConversationProcesses([complete],[pending])[0]);expect(view.container.querySelector("li")).toBe(node);expect(view.container.textContent).not.toContain("正在调用工具");
 }finally{await view.close();}
});

it.each([false,true])("keeps the PPTX receipt and pending image notice across the public boundary, model=%s",async(model)=>{
 const row={...fixture().tools[0],text:model?"已取得文档全部原生文字。":"已完成提取文档内容。",pendingImageText:true,...(model?{summaryOrigin:"model",summaryRevision:6}:{})};
 const process=readConversationProcesses([{...fixture("completed"),thinking:[],tools:[row]}])[0];
 expect(process.tools).toHaveLength(1);expect(process.tools[0].pendingImageText).toBe(true);
 const view=await mount(process);
 try{expect(view.container.textContent).toContain("本次提取尚未识别图片文字。");expect(view.container.querySelectorAll("li")).toHaveLength(1);}finally{await view.close();}
});


it("rejects persisted reasoning-source summaries while retaining task history and receipt facts",()=>{
 const base=fixture("completed");
 for(const summaryRevision of [1,2,3,4,5]){
  const legacy={id:"legacy",text:"模型规划了资料整理与文章扩写步骤。",status:"recorded",summaryOrigin:"model",summaryRevision};
  const input={...base,thinking:[legacy],tools:[...base.tools,{...legacy,id:"legacy-tool",status:"completed"}]};
  const publicSnapshot=publicContentConversation({id:"saved",taskId:"original",purpose:"content_production",messages:[],processes:[input]});
  const rows=readConversationProcesses(publicSnapshot.processes);
  expect(publicSnapshot.taskId).toBe("original");expect(rows[0].id).toBe(base.id);expect(rows[0].status).toBe("completed");
  expect(rows[0].thinking).toEqual([]);expect(rows[0].tools).toEqual(base.tools);
  expect(readConversationProcesses([{...base,thinking:[{...legacy,summaryRevision:6}]}])[0].thinking).toHaveLength(1);
 }
});
