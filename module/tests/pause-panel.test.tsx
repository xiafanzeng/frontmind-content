// @vitest-environment jsdom
import React, {act} from "react";
import {createRoot} from "react-dom/client";
import {afterEach, expect, it, vi} from "vitest";
import ContentTaskActionDeck from "../client/ContentTaskActionDeck";
import {ModuleWorkspace, type ContentBusinessClient} from "../client/runtime";
import {buildTaskOperationSubmission, mapContentTaskOperations, type TaskOperationCard} from "../client/content-task-operations";
import type {ContentConversation} from "../client/host";
import type {ContentProductionDto} from "../contracts/content-production";

(globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
const revise:TaskOperationCard={id:"revise-current-step",stageIndex:2,kind:"input",title:"返回修改",description:"补充调整",status:"awaiting-confirm",prompt:"修改：",form:{type:"text",label:"修改要求",placeholder:"修改"}};
const draft=(key:string)=>localStorage.getItem(`frontmind-content-pause-draft:${key}`);
const type=async(el:HTMLElement,value:string)=>{const area=el.querySelector("textarea")!;await act(async()=>{Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value")!.set!.call(area,value);area.dispatchEvent(new Event("input",{bubbles:true}));});};
const click=async(el:HTMLElement,text:string)=>{await act(async()=>[...el.querySelectorAll("button")].find(item=>item.textContent?.includes(text))!.click());};
afterEach(()=>{localStorage.clear();document.body.replaceChildren();});

function mountDeck(){
 const el=document.createElement("div");document.body.append(el);const root=createRoot(el);
 const render=(draftScope:string,draftKey:string,onSelect:(card:TaskOperationCard,submission:{prompt:string})=>Promise<boolean>)=>act(async()=>root.render(<ContentTaskActionDeck cards={[revise]} busy={false} revision={3} draftScope={draftScope} draftKey={draftKey} onSelect={onSelect}/>));
 return {el,render,unmount:()=>act(async()=>root.unmount())};
}

it("刷新后恢复文字，推进确认版本后清理本页离开的旧草稿",async()=>{
 const first=mountDeck();await first.render("a","a|t|3|x",async()=>false);
 await click(first.el,"返回修改");await type(first.el,"压缩第三部分");
 expect(draft("a|t|3|x")).toContain("压缩第三部分");await first.unmount();
 const second=mountDeck();await second.render("a","a|t|3|x",async()=>false);
 expect(second.el.querySelector("textarea")!.value).toBe("压缩第三部分");
 await second.render("a","a|t|4|y",async()=>false);
 expect(draft("a|t|3|x")).toBeNull();await second.unmount();
});

it("旧聊天提交成功时不清除已切换聊天的同名草稿",async()=>{
 localStorage.setItem("frontmind-content-pause-draft:b|t|1|x",JSON.stringify({open:"revise-current-step",values:{"revise-current-step":{text:"B 聊天的修改"}}}));
 let release!:(value:boolean)=>void;const pending=new Promise<boolean>(resolve=>{release=resolve;});
 const view=mountDeck();await view.render("a","a|t|3|x",()=>pending);
 await click(view.el,"返回修改");await type(view.el,"A 聊天的修改");await click(view.el,"核对并提交");
 await view.render("b","b|t|1|x",()=>pending);
 expect(view.el.querySelector("textarea")!.value).toBe("B 聊天的修改");
 await act(async()=>{release(true);await pending;});
 expect(view.el.querySelector("textarea")!.value).toBe("B 聊天的修改");
 expect(draft("b|t|1|x")).toContain("B 聊天的修改");expect(draft("a|t|3|x")).toBeNull();await view.unmount();
});

it("提交未被接受时保留表单与文字，交付稿修改的按钮说明直接提交",async()=>{
 const view=mountDeck();const select=vi.fn(async()=>false);await view.render("a","a|t|3|x",select);
 await click(view.el,"返回修改");await type(view.el,"补充门店流程");await click(view.el,"核对并提交");
 expect(select).toHaveBeenCalledOnce();expect(view.el.querySelector("textarea")!.value).toBe("补充门店流程");await view.unmount();
 const progress={workflowStatus:"p0_ready",executionStatus:"completed",jobKind:"p0",runnerRevision:3,availableActions:[],choices:[],confirmation:null} as unknown as ContentProductionDto;
 expect(mapContentTaskOperations(progress,{delivered:true})[0].form).toMatchObject({submitLabel:"提交修改"});
});

it("超过接口长度限制的文字不生成动作，已提供资料包时可不重新上传",()=>{
 const text=mapContentTaskOperations({confirmation:"awaiting_reference_pack_route",workflowStatus:"awaiting_reference_pack_route",executionStatus:"awaiting_input",runnerRevision:1,availableActions:["choose_reference_pack_route"],choices:[]} as unknown as ContentProductionDto);
 expect(buildTaskOperationSubmission(text[0],{fileCount:0},1)).toEqual({action:{kind:"choose_reference_pack_route",revision:1,route:"use"},prompt:"使用已有资料包"});
 const tooLong=buildTaskOperationSubmission(revise,{text:"字".repeat(20001)},3);
 expect(tooLong.action).toBeUndefined();expect(tooLong.error).toContain("20000");
});

it("服务端明确拒绝过期修订时结算待发请求，不重放旧动作",async()=>{
 const workspace="pause-conflict";localStorage.setItem(`frontmind-content-active:${workspace}`,"chat");
 const progress={mode:"single_article",enterpriseName:"合成主体",workflowVersion:"v",sessionPhases:true,workflowStatus:"awaiting_blueprint_confirmation",executionStatus:"awaiting_input",currentStage:"blueprint",jobKind:"article",runnerRevision:7,pauseTitle:"确认",choices:[],productionStep:null,confirmation:"awaiting_blueprint_confirmation",progressPosition:18,completedConfirmations:[],availableActions:["confirm_blueprint","revise_current_step"],knowledgeBase:null,source:"runner_job_state"} as ContentProductionDto;
 const row:ContentConversation={id:"chat",title:"合成聊天",purpose:"content_production",status:"awaiting_input",taskId:"task",messages:[],createdAt:1,updatedAt:1};
 const saved:ContentConversation[]=[];
 const dispatch=vi.fn(async()=>{throw Object.assign(new Error("冲突"),{code:"CONTENT_PRODUCTION_CONFIRMATION_CONFLICT",dispatchSettled:true});});
 const client:ContentBusinessClient={list:async()=>structuredClone([row]),task:async id=>({id,status:"awaiting_input",purpose:"content_production",contentProduction:progress}),save:async value=>{saved.push(structuredClone(value));return value;},dispatch,upload:vi.fn(),stop:vi.fn(),remove:vi.fn(),readSubjectWorkspace:async()=>({schemaVersion:1,revision:0,folders:[{id:"s",name:"合成主体",versions:[]}],bindings:{chat:{folderId:"s",kind:"article",packVersionId:null,generation:0}}}),saveSubjectWorkspace:async value=>value};
 const el=document.createElement("div");document.body.append(el);const root=createRoot(el);
 await act(async()=>root.render(<ModuleWorkspace context={{module:"content",workspace:{id:workspace,ownerUserId:0},marketEdition:"cn",capabilities:["content"]}} client={client}/>));
 await act(async()=>{await new Promise(resolve=>setTimeout(resolve,20));});
 await click(el,"确认写作方案，开始写作");await click(el,"确认提交");
 await act(async()=>{await new Promise(resolve=>setTimeout(resolve,20));});
 expect(dispatch).toHaveBeenCalledOnce();
 expect(saved[0].messages.at(-1)?.generalChatDispatch).toBeDefined();
 expect(saved.at(-1)!.messages.at(-1)?.generalChatDispatch).toBeUndefined();
 expect(el.textContent).toContain("当前制作阶段已更新");
 await act(async()=>root.unmount());
});
