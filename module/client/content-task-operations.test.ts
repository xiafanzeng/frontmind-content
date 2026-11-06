import {describe,it,expect} from "vitest";
import {buildTaskOperationSubmission,contentPatternChoice,mapContentTaskOperations} from "./content-task-operations";
import {parseContentConfirmationInput} from "./content-confirmation-input";
import type {ContentProductionDto} from "../contracts/content-production";

const progress=(patch:Partial<ContentProductionDto>={}):ContentProductionDto=>({
 mode:"production",workflowStatus:"positioning_ready",executionStatus:"awaiting_input",failureCode:null,currentStage:null,jobKind:"reference_pack",runnerRevision:3,pauseTitle:null,choices:[],productionStep:null,factGate:null,confirmation:null,progressPosition:null,completedConfirmations:[],availableActions:["confirm_core_positioning"],knowledgeBase:null,source:"runner_job_state",...patch
} as ContentProductionDto);
const card=(cards:ReturnType<typeof mapContentTaskOperations>,id:string)=>{const value=cards.find(item=>item.id===id);expect(value,id).toBeDefined();return value!;};

describe("mapContentTaskOperations",()=>{
 it.each([
  null,
  progress({runnerRevision:0,availableActions:[]}),
  progress({availableActions:["provide_reference_pack_inputs"]}),
 ])("submits startup upload as materials for card context %#",currentProgress=>{
  const start=card(mapContentTaskOperations(currentProgress,{startupConfig:true}),"start-production");
  const startupReview=progress({runnerRevision:0,availableActions:["provide_reference_pack_inputs"]});
  const plain=buildTaskOperationSubmission(start,{fileCount:1},0);
  expect(parseContentConfirmationInput(startupReview,plain.prompt,1).action).toEqual({kind:"provide_reference_pack_inputs",revision:0});
  const noted=buildTaskOperationSubmission(start,{fileCount:1,text:"官网：example.cn；重点介绍门店服务"},0);
  expect(noted.prompt).toBe("资料：官网：example.cn；重点介绍门店服务");
  expect(parseContentConfirmationInput(startupReview,noted.prompt,1).action).toEqual({kind:"provide_reference_pack_inputs",revision:0});
  expect(buildTaskOperationSubmission(start,{fileCount:0},0).error).toBe("请上传文件或填写资料说明。");
  expect(buildTaskOperationSubmission(start,{fileCount:0,text:"官网 example.cn"},0).prompt).toBe("资料：官网 example.cn");
 });
 it("maps available actions to revision-bound cards",()=>{const cards=mapContentTaskOperations(progress());expect(cards[0].action).toEqual({kind:"confirm_core_positioning",revision:3});});
 it("prioritizes running state over selectable actions",()=>{const cards=mapContentTaskOperations(progress({executionStatus:"running",workflowStatus:"running_core_positioning_synthesis"}));expect(cards[0].status).toBe("running");});
 it("builds a revise card with server-provided edit suggestions and attachments",()=>{
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_p0_blueprint_confirmation",availableActions:["confirm_p0_blueprint","revise_current_step"],choices:["确认写作方案","修改写作方案","补充材料","返回上一步","更换文风"]}));
  const revise=card(cards,"revise-current-step");
  expect(revise).toMatchObject({kind:"input",form:{type:"text",attach:true,suggestions:["修改写作方案","补充材料","返回上一步","更换文风"]}});
  expect(buildTaskOperationSubmission(revise,{text:"第三部分压缩到 600 字"},3)).toEqual({action:{kind:"revise_current_step",revision:3,instructions:"第三部分压缩到 600 字"},prompt:"修改：第三部分压缩到 600 字"});
  expect(buildTaskOperationSubmission(revise,{text:"  "},3).error).toBe("请填写修改要求。");
 });
 it("offers both existing and new reference pack routes",()=>{const cards=mapContentTaskOperations(progress({confirmation:"awaiting_reference_pack_route",availableActions:["choose_reference_pack_route"]}));expect(cards.map(item=>item.action)).toEqual([{kind:"choose_reference_pack_route",revision:3,route:"use"},{kind:"choose_reference_pack_route",revision:3,route:"create"}]);expect(buildTaskOperationSubmission(cards[0],{fileCount:0},3).error).toBeUndefined();});
 it("keeps stageIndex and kind on retry and running cards",()=>{const retry=mapContentTaskOperations(progress({availableActions:["resume_current_execution"]}),{failed:true})[0];const running=mapContentTaskOperations(progress({executionStatus:"running"}))[0];expect(retry).toMatchObject({stageIndex:1,kind:"action"});expect(running).toMatchObject({stageIndex:1,kind:"view"});});
 it("maps only numbered server choices to questions and keeps a free-text question entry",()=>{
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_question_selection",availableActions:["choose_question","provide_question_research_inputs","revise_current_step"],choices:["1. 问题甲","2. 问题乙","导入监控问答表"]}));
  expect(cards.filter(item=>item.id.startsWith("question-")&&item.kind==="choice").map(item=>item.action)).toEqual([{kind:"choose_question",revision:3,selection:"问题甲"},{kind:"choose_question",revision:3,selection:"问题乙"}]);
  expect(buildTaskOperationSubmission(card(cards,"question-custom"),{text:"药店中医健康检测设备推荐"},3).action).toEqual({kind:"choose_question",revision:3,selection:"药店中医健康检测设备推荐"});
  expect(card(cards,"provide_question_research_inputs").kind).toBe("upload");
 });
 it("lets the user edit competitors instead of only confirming",()=>{
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_competitor_selection",availableActions:["update_competitor_selection","confirm_competitors","revise_current_step"],choices:["确认比较对象","修改选择或补充名称","重新研究"]}));
  expect(cards[0].action).toEqual({kind:"confirm_competitors",revision:3});
  expect(buildTaskOperationSubmission(card(cards,"update-competitor-selection"),{text:"保留甲、乙；删除丙"},3)).toEqual({action:{kind:"update_competitor_selection",revision:3,selection:"保留甲、乙；删除丙"},prompt:"比较对象：保留甲、乙；删除丙"});
 });
 it("maps translated pattern choices back to their protocol ids",()=>{
  const choices=["采用推荐 多对象推荐与选择指南","选择 单一对象推荐","选择 多对象推荐与选择指南","选择 场景解决方案","选择 事件报道","选择 指定对象对比","选择 口碑与可信度评估"];
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_pattern_confirmation",jobKind:"article",availableActions:["confirm_pattern","revise_current_step"],choices}));
  expect(cards.filter(item=>item.id.startsWith("pattern-")).map(item=>[item.title,item.action])).toEqual([
   ["采用推荐：多对象推荐与选择指南",{kind:"confirm_pattern",revision:3}],
   ["单一对象推荐",{kind:"confirm_pattern",revision:3,selectedPattern:"P01"}],
   ["场景解决方案",{kind:"confirm_pattern",revision:3,selectedPattern:"P03"}],
   ["事件报道",{kind:"confirm_pattern",revision:3,selectedPattern:"P04"}],
   ["指定对象对比",{kind:"confirm_pattern",revision:3,selectedPattern:"P05"}],
   ["口碑与可信度评估",{kind:"confirm_pattern",revision:3,selectedPattern:"P06"}],
  ]);
  expect(contentPatternChoice("文章类型：P03")).toEqual({selectedPattern:"P03",recommended:false,label:"场景解决方案"});
 });
 it("keeps user-written response requirements instead of forcing no extra requirements",()=>{
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_response_brief",jobKind:"article",availableActions:["submit_response_brief","revise_current_step"]}));
  const brief=card(cards,"response-brief");
  expect(cards.some(item=>item.action?.kind==="submit_response_brief")).toBe(false);
  expect(buildTaskOperationSubmission(brief,{requirementsMode:"custom",requirements:"突出门店服务流程",recognition:"insufficient"},3)).toEqual({action:{kind:"submit_response_brief",revision:3,requirements:"突出门店服务流程",aiBrandRecognition:"insufficient"},prompt:"额外要求：突出门店服务流程；品牌认知：不充分"});
  expect(buildTaskOperationSubmission(brief,{requirementsMode:"none",recognition:"sufficient"},3)).toEqual({action:{kind:"submit_response_brief",revision:3,noExtraRequirements:true,aiBrandRecognition:"sufficient"},prompt:"无额外要求；品牌认知：充分"});
  expect(buildTaskOperationSubmission(brief,{requirementsMode:"custom",requirements:" ",recognition:"sufficient"},3).error).toContain("请填写额外应答要求");
  expect(buildTaskOperationSubmission(brief,{requirementsMode:"none"},3).error).toContain("品牌认知");
 });
 it("collects style and article-pool references in one form",()=>{
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_example_confirmation",jobKind:"article",availableActions:["choose_examples","revise_current_step"],choices:["方案 A","方案 B","文章池：填写 1—2 个编号或不采用"]}));
  const examples=card(cards,"examples");
  expect(examples.form).toEqual({type:"examples",pool:true});
  expect(buildTaskOperationSubmission(examples,{route:"A",pool:"1、5"},3)).toEqual({action:{kind:"choose_examples",revision:3,route:"A"},prompt:"文风：A；文章池：1、5"});
  expect(buildTaskOperationSubmission(examples,{route:"B",noPool:true},3).prompt).toBe("文风：B；文章池：不采用");
  expect(buildTaskOperationSubmission(examples,{route:"A",pool:"1、2、3"},3).error).toContain("1—2");
  expect(buildTaskOperationSubmission(examples,{route:"A"},3).error).toContain("文章池");
  const parsed=parseContentConfirmationInput(progress({availableActions:["choose_examples"],choices:["文章池"]}),"文风：A；文章池：1、5");
  expect(parsed.action).toEqual({kind:"choose_examples",revision:3,route:"A"});
 });
 it("requires a source file before importing an existing brand article",()=>{
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_p0_route",jobKind:"p0",availableActions:["choose_p0_route","revise_current_step"]}));
  const importing=card(cards,"p0-route-import");
  expect(importing.kind).toBe("upload");
  expect(buildTaskOperationSubmission(importing,{fileCount:0},3).error).toBe("请先选择文件。");
  expect(buildTaskOperationSubmission(importing,{fileCount:1},3)).toEqual({action:{kind:"choose_p0_route",revision:3,route:"import"},prompt:"导入 P0"});
 });
 it("keeps only numbered positioning directions as choices and moves control items to text entries",()=>{
  const cards=mapContentTaskOperations(progress({confirmation:"awaiting_core_positioning_direction",availableActions:["choose_core_positioning_direction","revise_current_step"],choices:["采用方向 1","采用方向 2","主方向加一个辅助方向","提交我的方向","补充材料后重新生成","探索其他方向","重新调研"]}));
  expect(cards.filter(item=>item.kind==="choice").map(item=>item.action)).toEqual([{kind:"choose_core_positioning_direction",revision:3,direction:"采用方向 1"},{kind:"choose_core_positioning_direction",revision:3,direction:"采用方向 2"}]);
  expect(buildTaskOperationSubmission(card(cards,"direction-custom"),{text:"方向 1 为主，方向 2 辅助"},3).action).toEqual({kind:"choose_core_positioning_direction",revision:3,direction:"方向 1 为主，方向 2 辅助"});
  expect(card(cards,"revise-current-step").form).toMatchObject({suggestions:["补充材料后重新生成","探索其他方向","重新调研"]});
 });
 it("shows recovery and fact repair only when the server offers them",()=>{
  expect(mapContentTaskOperations(progress({executionFailure:{action:"x",code:"y",attemptId:null},availableActions:[]}),{failed:true})).toEqual([]);
  expect(mapContentTaskOperations(progress({executionFailure:{action:"x",code:"y",attemptId:null},availableActions:["resume_current_execution"]}),{failed:true})[0].action).toEqual({kind:"resume_current_execution",revision:3});
  // 事实返工时原生阶段名仍为 running_article_production，外层状态为 error。
  const repair=mapContentTaskOperations(progress({workflowStatus:"running_article_production",executionStatus:"error",jobKind:"article",availableActions:["repair_article_facts"],factGate:{issueCount:2,categories:[],publishReady:false}}),{failed:true});
  expect(repair.map(item=>item.id)).toEqual(["repair-article-facts"]);
  expect(repair[0].action).toEqual({kind:"repair_article_facts",revision:3,rejectedClaimIds:[]});
  expect(mapContentTaskOperations(progress({workflowStatus:"running_article_production",executionStatus:"running",availableActions:[]}))[0].id).toBe("running");
 });
 it("offers delivered-manuscript edits and a restart path for startup-stopped tasks",()=>{
  const delivered=mapContentTaskOperations(progress({workflowStatus:"p0_ready",jobKind:"p0",availableActions:[]}),{delivered:true});
  expect(buildTaskOperationSubmission(card(delivered,"revise-delivery"),{text:"合并重复段落"},3)).toEqual({prompt:"合并重复段落"});
  const stopped=mapContentTaskOperations(progress({source:"awaiting_runner",workflowStatus:null,runnerRevision:null,executionStatus:"cancelled",availableActions:[]}),{failed:true,startupStopped:true});
  expect(stopped.map(item=>item.id)).toEqual(["restart-chat"]);
 });
});
