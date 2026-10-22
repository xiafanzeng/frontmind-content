// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {afterEach,expect,it,vi} from "vitest";
import ExecutionFeedback from "../client/ExecutionFeedback";
import type {ContentConversation} from "../client/host";
import {useContentWorkspaceHost} from "../client/host";
vi.mock("../client/ContentProductionWorkspace",()=>({default:()=>{const host=useContentWorkspaceHost();const state=host.useConversation();const Home=host.Home;return state.activeConversation?<Home purpose="content_production"/>:null;}}));
vi.mock("@frontmind/module-ui/components/BusinessChatInput",()=>({default:()=>null}));
import {ModuleWorkspace,liveContentClient} from "../client/runtime";
afterEach(()=>{vi.restoreAllMocks();vi.useRealTimers();localStorage.clear();document.body.innerHTML="";});
const base:ContentConversation={id:"conversation",taskId:"task",title:"离线反馈测试",status:"running",createdAt:1000,updatedAt:1000,messages:[{id:"user",role:"user",content:"离线输入",timestamp:1000}]};
async function mount(props:any={}){
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
 const el=document.createElement("div");document.body.append(el);const root=createRoot(el);
 const render=async(next:any)=>act(async()=>root.render(<ExecutionFeedback conversation={base} {...next}/>));
 await render(props);return {el,render,unmount:()=>act(async()=>root.unmount())};
}
it("keeps waiting feedback and an advancing timer when the model has no summary",async()=>{
 vi.useFakeTimers();vi.setSystemTime(1000);const view=await mount();try{
  expect(view.el.textContent).toContain("等待下一条服务端记录");
  await act(async()=>vi.advanceTimersByTimeAsync(31000));
  expect(view.el.textContent).toContain("31 秒");expect(view.el.textContent).toContain("暂未收到新记录");
 }finally{await view.unmount();}
});
it("keeps feedback after a completed tool while the task is still running",async()=>{
 const conversation:any={...base,execution:{schemaVersion:1,taskId:"task",coverage:"complete",timeline:[{id:"tool",turnId:"turn",userMessageId:"user",userSequence:0,timestamp:2000,rank:0,kind:"tool",label:"工具结果",status:"completed"}]}};
 const view=await mount({conversation});try{expect(view.el.querySelector('[role="status"]')?.textContent).toContain("任务正在执行");}finally{await view.unmount();}
});
it("shows fallback and failure facts after refresh without exposing upstream payloads",async()=>{
 const conversation:any={...base,status:"error",execution:{timeline:[{id:"fallback",turnId:"turn",timestamp:2000,kind:"status",status:"retrying",serviceNotice:{code:"model_fallback",reason:"timeout",message:"Bearer secret"}},{id:"error",turnId:"turn",timestamp:3000,kind:"status",status:"error",serviceNotice:{code:"model_failure",reason:"upstream"}}]}};
 const view=await mount({conversation});try{
  expect(view.el.textContent).toContain("已切换备用模型（GLM-5.3）");expect(view.el.textContent).toContain("响应超时");expect(view.el.textContent).toContain("上游服务返回错误");expect(view.el.textContent).not.toContain("secret");
  await view.render({conversation:structuredClone(conversation)});expect(view.el.textContent).toContain("本轮执行失败");
 }finally{await view.unmount();}
});
it("distinguishes an observation failure from confirmed generation progress and recovers",async()=>{
 const view=await mount({observation:{taskId:"task",checkedAt:2000,error:true}});try{
  expect(view.el.textContent).toContain("无法确认服务器进度");
  await view.render({observation:{taskId:"task",checkedAt:3000}});expect(view.el.textContent).not.toContain("无法确认");
  await view.render({stopping:true});expect(view.el.textContent).toContain("等待服务器确认");
  await view.render({conversation:{...base,status:"cancelled"}});expect(view.el.textContent).toContain("本轮已停止");expect(view.el.querySelector('[role="timer"]')).toBeNull();
 }finally{await view.unmount();}
});
it("does not carry a previous turn's fallback into a fresh turn",async()=>{
 const conversation:any={...base,execution:{timeline:[{id:"old",turnId:"old",timestamp:1,kind:"status",status:"retrying",serviceNotice:{code:"model_fallback",reason:"unknown"}},{id:"new",turnId:"new",timestamp:2,kind:"status",status:"running"}]}};
 const view=await mount({conversation});try{expect(view.el.textContent).not.toContain("已切换备用");expect(view.el.textContent).toContain("任务正在执行");}finally{await view.unmount();}
});
it("surfaces polling and stop failures in the real runtime without resubmitting generation",async()=>{
 (globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();
 localStorage.setItem("frontmind-content-active:feedback-runtime","conversation");
 let broken=true;
 const forbidden=vi.fn(async():Promise<never>=>{throw new Error("Generation is forbidden");});
 const client={list:async()=>[structuredClone(base)],save:forbidden,upload:forbidden,dispatch:forbidden,remove:forbidden,task:async()=>{if(broken)throw new Error("offline");return {id:"task",status:"running"};},stop:async()=>{throw new Error("offline");}};
 const el=document.createElement("div");document.body.append(el);const root=createRoot(el);
 try{
  await act(async()=>root.render(<ModuleWorkspace context={{module:"content",workspace:{id:"feedback-runtime",ownerUserId:0},marketEdition:"cn",capabilities:[]}} client={client}/>));
  expect(el.textContent).toContain("无法确认服务器进度");
  broken=false;await act(async()=>vi.advanceTimersByTimeAsync(3000));expect(el.textContent).toContain("等待下一条服务端记录");
  await act(async()=>el.querySelector<HTMLButtonElement>(".cp-live-stop")!.click());expect(el.textContent).toContain("停止请求未确认");
  expect(el.textContent).not.toContain("本轮已停止");expect(forbidden).not.toHaveBeenCalled();
 }finally{await act(async()=>root.unmount());}
});
it("allows a slow material upload beyond the normal request deadline and still bounds the wait",async()=>{
 vi.useFakeTimers();let signal:AbortSignal|undefined;
 vi.spyOn(globalThis,"fetch").mockImplementation(async(_url,init)=>new Promise((_resolve,reject)=>{signal=init?.signal??undefined;signal?.addEventListener("abort",()=>reject(new DOMException("Aborted","AbortError")));}));
 const pending=liveContentClient.upload(new File(["offline material"],"material.txt"));
 const rejected=expect(pending).rejects.toThrow("请求超时");
 await vi.advanceTimersByTimeAsync(25000);expect(signal?.aborted).toBe(false);
 await vi.advanceTimersByTimeAsync(575000);expect(signal?.aborted).toBe(true);await rejected;
});

it("reads confirmed terminal status from an old idle conversation without reviving execution",async()=>{
 for(const [status,label] of [["cancelled","本轮已停止"],["error","本轮执行失败"],["ended","本轮已结束"]]){
  const conversation:any={...base,status:"idle",execution:{timeline:[{id:"terminal",turnId:"turn",timestamp:3000,kind:"status",status}]}};
  const view=await mount({conversation});try{expect(view.el.textContent).toContain(label);expect(view.el.querySelector('[role="timer"]')).toBeNull();}finally{await view.unmount();}
 }
});
