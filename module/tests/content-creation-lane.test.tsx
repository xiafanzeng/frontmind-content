// @vitest-environment jsdom
import React,{act} from "react";
import {createRoot} from "react-dom/client";
import {expect,it,vi} from "vitest";
import {ContentCreationLane,CONTENT_CREATION_STAGES,contentCreationLaneModel,contentCreationStageIndex,contentCreationTranscriptAnchors} from "../client/ContentCreationLane";
import type {ContentProductionDto} from "../contracts/content-production";
import type {ContentMessage} from "../client/host";

const progress=(status:string,extra:Partial<ContentProductionDto>={}):ContentProductionDto=>({
  mode:"single_article",enterpriseName:"本地样例",workflowVersion:"4.13.2-v16.8-app1",workflowStatus:status,currentStage:null,
  jobKind:"article",runnerRevision:1,pauseTitle:null,choices:[],productionStep:null,confirmation:null,
  progressPosition:20,completedConfirmations:[],availableActions:[],knowledgeBase:null,source:"runner_job_state",...extra,
});
const marked=(id:string,position:number):ContentMessage=>({id,role:"assistant",content:"这段正文不会用于推断进度",timestamp:1,contentWorkflowPosition:position});
const reviewed=(id:string,status:string):ContentMessage=>({id,role:"assistant",content:"原生确认稿",timestamp:1,outputFiles:[{fileName:`review_${status}_r1.md`,fileUrl:"/local/review",mimeType:"text/markdown"}]});

it.each([
  [1,null,0],[4,null,0],[5,null,1],[7,null,1],[8,null,2],[12,null,2],
  [13,"awaiting_question_research_inputs",3],[13,"awaiting_question_selection",4],
  [13,null,null],[14,null,4],[16,null,4],[17,null,5],[20,null,5],[0,null,null],[21,null,null],
] as const)("原生位置 %s、状态 %s 映射到六阶段 %s",(position,status,expected)=>{
  expect(contentCreationStageIndex(position,status)).toBe(expected);
});

it("六阶段标题和说明与新版 HTML 保持一致",()=>{
  expect(CONTENT_CREATION_STAGES).toEqual([
    {title:"企业资料与范围",description:"主体资料与比较范围"},
    {title:"确认定位与资料包",description:"确认定位，形成可用资料包"},
    {title:"P0 品牌长文",description:"蓝图确认与品牌长文"},
    {title:"问题与监控数据",description:"推荐问题、问答与引用数据"},
    {title:"选题、类型与参考",description:"本题要求、文章类型与参考"},
    {title:"蓝图、写作与交付",description:"定位、蓝图、写作与导出"},
  ]);
});

it("精确区分位置相同的数据导入与选题，并把紧邻用户输入作为回看起点",()=>{
  const anchors=contentCreationTranscriptAnchors([
    {id:"data-user",role:"user",content:"附件",timestamp:1},reviewed("data","awaiting_question_research_inputs"),
    {id:"question-user",role:"user",content:"序号 1",timestamp:2},reviewed("question","awaiting_question_selection"),
  ]);
  expect([...anchors]).toEqual([[3,"data-user"],[4,"question-user"]]);
});

it("结构化原生状态优先于兼容位置，不凭正文或含糊的位置 13 伪造节点",()=>{
  const anchors=contentCreationTranscriptAnchors([
    {id:"unknown",role:"assistant",content:"问题与监控数据、品牌长文、蓝图已完成",timestamp:1},
    marked("ambiguous",13),
    {...marked("native",13),contentWorkflowStatus:"awaiting_question_selection"},
    {...marked("later",13),contentWorkflowStatus:"awaiting_question_selection"},
  ]);
  expect([...anchors]).toEqual([[4,"native"]]);
});

it("文章直接完成时不把未做的 P0 与监控导入标成完成",()=>{
  const model=contentCreationLaneModel({progress:progress("completed"),messages:[],kind:"article",boundPack:true});
  expect(model.current).toBe(5);
  expect(model.steps.map(step=>step.state)).toEqual(["done","done","pending","pending","done","done"]);
  expect(model.steps[2].target).toBeNull();
  expect(model.steps[3].target).toBeNull();
});

it("已绑定且确认含 P0 的资料包可证明品牌长文已交付，但不会生成不存在的回看锚点",()=>{
  const model=contentCreationLaneModel({progress:progress("awaiting_question_selection"),messages:[],kind:"article",boundPack:true,packIncludesP0:true,hasPackSource:true});
  expect(model.steps[2].state).toBe("done");
  expect(model.steps[2].target).toBeNull();
  expect(model.steps[3].state).toBe("pending");
  expect(model.steps[0].target).toBe("pack");
  const unbound=contentCreationLaneModel({progress:null,messages:[],kind:"article",boundPack:false,packIncludesP0:true});
  expect(unbound.steps[2].state).toBe("pending");
});

it("资料包交付只完成前两个阶段，P0 交付不会完成问题文章阶段",()=>{
  const pack=contentCreationLaneModel({progress:progress("positioning_ready",{jobKind:"reference_pack"}),messages:[],kind:"pack"});
  expect(pack.steps.map(step=>step.state)).toEqual(["done","done","pending","pending","pending","pending"]);
  const p0=contentCreationLaneModel({progress:progress("p0_ready",{jobKind:"p0"}),messages:[],kind:"article",boundPack:true});
  expect(p0.steps.map(step=>step.state)).toEqual(["done","done","done","pending","pending","pending"]);
});

it("当前节点按实际确认暂停位置显示，不受最高历史进度影响",()=>{
  const model=contentCreationLaneModel({progress:progress("awaiting_p0_blueprint_confirmation",{progressPosition:20}),messages:[marked("prior-article",20)],kind:"article",boundPack:true});
  expect(model.current).toBe(2);
  expect(model.steps[2].state).toBe("current");
  expect(model.steps[5].state).toBe("pending");
  expect(model.steps[2].target).toEqual({stageIndex:2,latest:true});
});

it("独立文章可回到已存在的资料包源聊天，本聊天已有资料历史时优先定位该消息",()=>{
  const empty=contentCreationLaneModel({progress:progress("awaiting_p0_route"),messages:[],kind:"article",boundPack:true,hasPackSource:true});
  expect(empty.steps[0].target).toBe("pack");
  expect(empty.steps[1].target).toBe("pack");
  const history=contentCreationLaneModel({progress:progress("awaiting_p0_route"),messages:[marked("pack-intake",1),marked("pack-done",7)],kind:"article",boundPack:true,hasPackSource:true});
  expect(history.steps[0].target).toEqual({stageIndex:0,messageId:"pack-intake"});
  expect(history.steps[1].target).toEqual({stageIndex:1,messageId:"pack-done"});
});

it("无已确认资料包的文章等待资料包，不显示后续工作已完成",()=>{
  const model=contentCreationLaneModel({progress:progress("completed"),messages:[],kind:"article",boundPack:false,hasPackSource:true});
  expect(model.current).toBe(0);
  expect(model.steps.map(step=>step.state)).toEqual(["current","pending","pending","pending","pending","pending"]);
  expect(model.steps[0].detail).toBe("等待本文件夹的资料包");
  expect(model.steps[0].target).toBe("pack");
});

it("数据导入和选题当前阶段遵守原生流程暂停，已确认例文后仍需单独确认定位与蓝图",()=>{
  const data=contentCreationLaneModel({progress:progress("awaiting_question_research_inputs"),messages:[],kind:"article",boundPack:true});
  const question=contentCreationLaneModel({progress:progress("awaiting_question_selection"),messages:[],kind:"article",boundPack:true});
  const examples=contentCreationLaneModel({progress:progress("awaiting_example_confirmation"),messages:[],kind:"article",boundPack:true});
  const positioning=contentCreationLaneModel({progress:progress("awaiting_question_positioning_confirmation"),messages:[],kind:"article",boundPack:true});
  expect([data.current,question.current,examples.current,positioning.current]).toEqual([3,4,4,5]);
  expect(examples.steps[5].state).toBe("pending");
  expect(positioning.steps[5].detail).toBe("确认本题差异化定位");
});

it("问题文章 P02 的本题比较对象归选题阶段，资料包整体比较范围仍归企业资料阶段",()=>{
  const article=contentCreationLaneModel({progress:progress("awaiting_competitor_selection",{jobKind:"article"}),messages:[],kind:"article",boundPack:true});
  const pack=contentCreationLaneModel({progress:progress("awaiting_competitor_selection",{jobKind:"reference_pack"}),messages:[],kind:"pack"});
  expect(article.current).toBe(4);
  expect(pack.current).toBe(0);
  expect([...contentCreationTranscriptAnchors([
    {...reviewed("pack-comparison","awaiting_competitor_selection"),contentWorkflowKind:"reference_pack"},
    {...reviewed("p02-comparison","awaiting_competitor_selection"),contentWorkflowKind:"article"},
  ])]).toEqual([[0,"pack-comparison"],[4,"p02-comparison"]]);
});

it("节点直接点击和键盘回看只发导航，当前节点返回最新，未来节点不可操作且没有泳道按钮",async()=>{
  (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;
  const navigation=vi.fn(),openPack=vi.fn();
  const container=document.createElement("div");document.body.append(container);const root=createRoot(container);
  const snapshot=progress("awaiting_p0_blueprint_confirmation");
  try{
    await act(async()=>root.render(<ContentCreationLane progress={snapshot} messages={[marked("p0-route",8)]} conversationId="article-chat" kind="article" boundPack onNavigate={navigation} onOpenPack={openPack}/>));
    const items=[...container.querySelectorAll<HTMLLIElement>(".cp-creation-steps>li")];
    expect(items).toHaveLength(6);
    expect(container.querySelectorAll("button")).toHaveLength(0);
    await act(async()=>items[0].click());
    expect(openPack).toHaveBeenCalledTimes(1);
    expect(openPack).toHaveBeenLastCalledWith(0);
    await act(async()=>items[1].dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true})));
    expect(openPack).toHaveBeenCalledTimes(2);
    expect(openPack).toHaveBeenLastCalledWith(1);
    await act(async()=>items[2].click());
    expect(navigation).toHaveBeenLastCalledWith({stageIndex:2,latest:true});
    await act(async()=>items[2].dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true})));
    expect(navigation).toHaveBeenCalledTimes(2);
    await act(async()=>items[5].click());
    expect(navigation).toHaveBeenCalledTimes(2);
    expect(items[5].getAttribute("aria-disabled")).toBe("true");
    expect(snapshot.workflowStatus).toBe("awaiting_p0_blueprint_confirmation");
    expect(container.querySelector('[aria-current="step"]')).toBe(items[2]);
    await act(async()=>root.render(<ContentCreationLane progress={progress("awaiting_blueprint_confirmation")} messages={[marked("p0-route",8)]} conversationId="article-chat" kind="article" boundPack onNavigate={navigation}/>));
    await act(async()=>container.querySelector<HTMLLIElement>('[data-stage-index="2"]')!.click());
    expect(navigation).toHaveBeenLastCalledWith({stageIndex:2,messageId:"p0-route"});
  }finally{await act(async()=>root.unmount());container.remove();}
});
