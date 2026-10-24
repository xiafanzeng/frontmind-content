import {expect,it} from "vitest";
import {chineseContentSummary,projectContentExecutionLanguage} from "../contracts/content-execution-language";
import {CONTENT_PRODUCTION_LANGUAGE_CONTEXT,contentProductionFilePhase} from "../contracts/content-production-public";
import type {GeneralExecutionDto} from "@frontmind/module-contracts/execution";

it("将已知英文执行摘要改为中文，不改写原始记录与执行状态",()=>{
  const original = {schemaVersion:1,timeline:[{id:"step1",kind:"status",status:"thinking",turnId:"turn1",timestamp:1,publicSummary:"Reading the uploaded materials."}]} as unknown as GeneralExecutionDto;
  const copy = structuredClone(original);
  const output = projectContentExecutionLanguage(original)!;
  expect(output.timeline[0]).toMatchObject({id:"step1",status:"thinking",publicSummary:"正在读取本轮提供的资料。"});
  expect(original).toEqual(copy);
  expect(CONTENT_PRODUCTION_LANGUAGE_CONTEXT).toContain("公开过程摘要");
  expect(CONTENT_PRODUCTION_LANGUAGE_CONTEXT).toContain("简体中文");
});
it("不为未知英文编造完成事实，也不翻译中文摘要中的产品名",()=>{
  expect(chineseContentSummary("I might have completed a product comparison, but this was not verified.")).toBe("本条过程记录暂无中文摘要。");
  expect(chineseContentSummary("正在核对 ThinkPad 与品牌材料的适用范围。")).toBe("正在核对 ThinkPad 与品牌材料的适用范围。");
});
it("没有中文摘要时不生成重复空白思考卡，保留后端状态与事件标识",()=>{
  const original={schemaVersion:1,timeline:[{id:"pending",kind:"status",status:"thinking",turnId:"turn",timestamp:1,publicSummary:"本条过程记录暂无中文摘要。"}]} as unknown as GeneralExecutionDto;
  expect(projectContentExecutionLanguage(original)?.timeline[0]).toEqual({id:"pending",kind:"status",status:"thinking",turnId:"turn",timestamp:1});
  expect(original.timeline[0]).toHaveProperty("publicSummary");
});
it("只对原生文件名归组，不猜测普通上传材料的阶段",()=>{
  expect(contentProductionFilePhase("review_awaiting_p0_blueprint_confirmation_r5.md")).toBe(2);
  expect(contentProductionFilePhase("review_awaiting_example_confirmation_r8.md")).toBe(4);
  expect(contentProductionFilePhase("客户自定义文件.pdf")).toBeNull();
});
