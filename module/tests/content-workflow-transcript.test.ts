import {expect,it} from "vitest";
import {contentWorkflowTranscriptAnchors} from "../client/content-workflow-transcript";

const output = (fileName:string) => ({fileName,fileUrl:"/api/frontmind/v2/artifacts/local/content",mimeType:"text/markdown"});
const reply = (id:string,...filenames:string[]) => ({id,role:"assistant" as const,content:"不参与阶段识别",timestamp:1,outputFiles:filenames.map(output)});

it("原生阶段标记优先于文件和兼容标记，首次阶段锚点包含紧邻的用户输入",()=>{
  const anchors=contentWorkflowTranscriptAnchors([
    {id:"input",role:"user",content:"确认",timestamp:1},
    {...reply("first","review_awaiting_p0_blueprint_confirmation_r5.md"),contentWorkflowPosition:9,contentPhase:5},
    {...reply("later"),contentWorkflowPosition:9},
  ]);
  expect([...anchors]).toEqual([[9,"input"]]);
});

it.each([
  ["reviews/awaiting_core_positioning_confirmation.r2.md",6],
  ["review_awaiting_p0_route_r4.md",8],
  ["workflow_review_awaiting_p0_example_confirmation_r5.md",9],
  ["review_awaiting_p0_blueprint_confirmation_r6.html",10],
  ["awaiting_response_brief_r9.md",14],
  ["review_awaiting_pattern_confirmation_r10.md",15],
  ["review_awaiting_example_confirmation_r11.md",16],
  ["review_awaiting_question_positioning_confirmation_r12.md",17],
  ["review_awaiting_blueprint_confirmation_r13.md",18],
] as const)("以原生状态识别确认稿 %s",(filename,position)=>{
  expect([...contentWorkflowTranscriptAnchors([reply("a",filename)])]).toEqual([[position,"a"]]);
});

it.each([
  ["仁南医生蛋仔机器人_企业资料与比较范围预览.html",1],
  ["仁南医生蛋仔机器人_核心定位确认稿.html",5],
  ["仁南医生蛋仔机器人_核心定位与竞品比较.html",7],
  ["仁南医生蛋仔机器人_Reference_Pack.zip",7],
  ["仁南医生蛋仔机器人_P0写作蓝图确认稿.html",10],
  ["仁南医生蛋仔机器人_P0正文.docx",12],
  ["P0_5加5标题.html",12],
  ["仁南医生蛋仔机器人_Reference_Pack_P0_v10.zip",12],
  ["仁南医生蛋仔机器人_问题1应答要求确认稿.html",13],
  ["仁南医生蛋仔机器人_问题1文章类型确认稿.html",15],
  ["仁南医生蛋仔机器人_问题1参考文章与文风确认稿.html",16],
  ["仁南医生蛋仔机器人_问题1定位确认稿.html",17],
  ["仁南医生蛋仔机器人_问题1写作蓝图确认稿.html",18],
  ["仁南医生蛋仔机器人_问题1正文.md",20],
  ["仁南医生蛋仔机器人_问题1候选标题.html",20],
] as const)("按飞书原生产物名称识别 %s",(filename,position)=>{
  expect([...contentWorkflowTranscriptAnchors([reply("a",filename)])]).toEqual([[position,"a"]]);
});

it("同轮多个产物只锚定本轮最晚的精确阶段，不凭正文猜测未知阶段",()=>{
  const anchors=contentWorkflowTranscriptAnchors([
    reply("p0-delivery","品牌_Reference_Pack.zip","品牌_P0正文.html","品牌_Reference_Pack_P0_v10.zip"),
    {id:"unknown",role:"assistant",content:"P0、问题正文、核心定位确认稿",timestamp:2,outputFiles:[output("客户自定义文件.pdf")]},
    reply("bad-status","review_not_a_native_status_r1.md"),
  ]);
  expect([...anchors]).toEqual([[12,"p0-delivery"]]);
});

it("兼容粗阶段只作后备；无效元数据仍可使用精准文件名",()=>{
  const anchors=contentWorkflowTranscriptAnchors([
    {...reply("legacy"),contentPhase:2},
    {...reply("exact","品牌_P0写作蓝图确认稿.html"),contentPhase:2},
    {...reply("invalid","品牌_问题1正文.html"),contentWorkflowPosition:21},
    {...reply("zero"),contentWorkflowPosition:0},
    {...reply("invalid-only"),contentWorkflowPosition:NaN,contentPhase:9},
  ]);
  expect([...anchors]).toEqual([[8,"legacy"],[10,"exact"],[20,"invalid"],[0,"zero"]]);
});
