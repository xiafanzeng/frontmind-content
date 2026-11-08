// @vitest-environment jsdom
import React,{act,useState} from "react";
import {createRoot} from "react-dom/client";
import {afterEach,expect,it,vi} from "vitest";
import {TwoStageConfirmation,TwoStageStart} from "../client/TwoStageConfirmation";
import {ContentWorkspaceHostProvider,type ContentWorkspaceHost} from "../client/host";
import type {ContentProductionDto,ContentProductionMode} from "../contracts/content-production";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
const roots:Array<ReturnType<typeof createRoot>>=[];
const host={useWorkspaceDraftGuard:()=>{}} as unknown as ContentWorkspaceHost;
async function mount(element:React.ReactNode){
  const div=document.createElement("div");document.body.appendChild(div);const root=createRoot(div);roots.push(root);
  await act(async()=>root.render(<ContentWorkspaceHostProvider value={host}>{element}</ContentWorkspaceHostProvider>));return div;
}
afterEach(async()=>{for(const root of roots.splice(0))await act(async()=>root.unmount());document.body.replaceChildren();});
async function change(element:Element,value:string){
  await act(async()=>{const prototype=element instanceof HTMLSelectElement?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(prototype,"value")!.set!.call(element,value);element.dispatchEvent(new Event(element instanceof HTMLSelectElement?"change":"input",{bubbles:true}));});
}
const progress=(confirmation:ContentProductionDto["confirmation"]):ContentProductionDto=>({mode:"single_article",enterpriseName:"合成品牌",workflowVersion:"16.25.1",workflowStatus:confirmation,currentStage:"writing_selection",jobKind:"article",runnerRevision:4,pauseTitle:"新版确认",choices:[],productionStep:null,confirmation,progressPosition:15,completedConfirmations:[],availableActions:[],knowledgeBase:null,source:"runner_job_state"});
const button=(div:HTMLElement,text:string)=>[...div.querySelectorAll("button")].find(element=>element.textContent===text)!;

it("article mode is explicit, excludes P05 and preserves the selected P02 subset order",async()=>{
  const submit=vi.fn().mockResolvedValue(true);
  const div=await mount(<TwoStageConfirmation progress={progress("awaiting_writing_selection")} busy={false} onAction={submit} onNotice={()=>{}}/>);
  expect(div.textContent).not.toContain("P05");
  const confirm=button(div,"确认类型、模式与主体");expect(confirm.disabled).toBe(true);
  await change(div.querySelector('[aria-label="问题类型"]')!,"行业排名");
  await change(div.querySelector('[aria-label="文章模式"]')!,"P02");expect(confirm.disabled).toBe(true);
  await change(div.querySelector('[aria-label="本篇其他主体"]')!,"c003、c001");
  await act(async()=>confirm.click());
  expect(submit).toHaveBeenCalledOnce();
  expect(submit.mock.calls[0][0]).toMatchObject({kind:"choose_writing",revision:4,pattern:"P02",category:"行业排名",subjects:["c003","c001"]});
});

it("ordered advantages are submitted only on explicit confirmation",async()=>{
  const submit=vi.fn().mockResolvedValue(true),dto={...progress("awaiting_advantages_confirmation"),choices:["adv1｜特点甲","adv2｜特点乙","adv3｜特点丙"]};
  const div=await mount(<TwoStageConfirmation progress={dto} busy={false} onAction={submit} onNotice={()=>{}}/>);
  expect(submit).not.toHaveBeenCalled();
  await change(div.querySelector('[aria-label="优势顺序"]')!,"adv3、adv1");
  await act(async()=>button(div,"确认优势与顺序").click());
  expect(submit.mock.calls[0][0]).toMatchObject({kind:"confirm_advantages",revision:4,advantageIds:["adv3","adv1"]});
});

it("no answers is a separate concrete choice, without treating missing input as consent",async()=>{
  const submit=vi.fn().mockResolvedValue(true);
  const div=await mount(<TwoStageConfirmation progress={progress("awaiting_question_answers")} busy={false} onAction={submit} onNotice={()=>{}}/>);
  expect(button(div,"关联完整回答").disabled).toBe(true);expect(submit).not.toHaveBeenCalled();
  await act(async()=>button(div,"本次暂无回答").click());
  expect(submit.mock.calls[0][0]).toMatchObject({kind:"set_question_answers",revision:4,noAnswers:true});
  expect(submit.mock.calls[0][2]).toEqual([]);
});

it("first-stage import is visible and validates a single real ZIP before staging input",async()=>{
  const start=vi.fn().mockResolvedValue(true),notice=vi.fn();
  function Start(){const [mode,setMode]=useState<Extract<ContentProductionMode,"new_reference_pack"|"import_reference_pack"|"p0"|"single_article">>("new_reference_pack");return <TwoStageStart kind="pack" mode={mode} onMode={setMode} onStart={start} onNotice={notice} busy={false}/>;}
  const div=await mount(<Start/>);
  expect(div.textContent).toContain("导入已有资料包");
  await act(async()=>[...div.querySelectorAll<HTMLInputElement>('input[type="radio"]')][1].click());
  await act(async()=>button(div,"核对本次输入").click());expect(start).not.toHaveBeenCalled();expect(notice).toHaveBeenCalled();
  const file=new File(["real fixture bytes"],"三项资料包.zip",{type:"application/zip"});
  const input=div.querySelector<HTMLInputElement>('[aria-label="三项资料包 ZIP"]')!;
  await act(async()=>{Object.defineProperty(input,"files",{value:[file],configurable:true});input.dispatchEvent(new Event("change",{bubbles:true}));});
  await act(async()=>button(div,"核对本次输入").click());
  expect(start).toHaveBeenCalledWith(expect.stringContaining("导入已有三项资料包"),[file]);
});
