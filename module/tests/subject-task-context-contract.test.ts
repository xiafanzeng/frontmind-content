import {describe,expect,it} from "vitest";
import {contentProductionInputSchema} from "../contracts/content-production";

const base={mode:"single_article",enterpriseName:"合成主体",knowledgeSource:"files"};
const subjectContext={folderId:"subject",generation:0,packVersionId:"pack-v1"};

describe("主体任务输入契约",()=>{
 it("兼容既有无主体输入，仅携带版本期望值",()=>{
  expect(contentProductionInputSchema.parse(base)).not.toHaveProperty("subjectContext");
  expect(contentProductionInputSchema.parse({...base,subjectContext}).subjectContext).toEqual(subjectContext);
  expect(contentProductionInputSchema.parse({...base,subjectContext:{...subjectContext,packVersionId:null}}).subjectContext?.packVersionId).toBeNull();
 });
 it.each([
  {folderId:"subject",generation:0},
  {generation:0,packVersionId:null},
  {...subjectContext,generation:-1},
  {...subjectContext,generation:1.5},
  {...subjectContext,folderId:" "},
  {...subjectContext,fileUrl:"https://untrusted.invalid/package.zip"},
  {...subjectContext,localAssetId:"browser-chosen-asset"},
  {...subjectContext,sourceTaskId:"browser-chosen-task"},
 ])("拒绝缺字段或浏览器指定产物身份 %j",value=>{
  expect(contentProductionInputSchema.safeParse({...base,subjectContext:value}).success).toBe(false);
 });
});
