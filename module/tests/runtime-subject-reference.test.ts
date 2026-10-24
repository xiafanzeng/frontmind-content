import {describe,expect,it} from "vitest";
import {contentProductionSystemContext} from "../server/runtime";
import type {FrozenContentTaskContext} from "../contracts/task-context";

const assetId="asset_authorized_pack_001";
const contentSha256="0123456789abcdef".repeat(4);
const context:FrozenContentTaskContext={
 revision:1,accountUserId:7,enterpriseProjectId:"synthetic-project",purpose:"content_production",
 knowledgeBase:null,knowledgeText:null,
 contentProduction:{mode:"single_article",enterpriseName:"合成主体",knowledgeSource:"files",monitoringAnswerAssetIds:[]},
 contentWorkflow:{version:"4.20.0",filename:"workflow.zip",rootDirectory:"workflow",sha256:"a".repeat(64),runtime:"native_content_v1",capabilities:["structured_article","editorial_v16_8"]},
 inputFiles:[{localAssetId:assetId,filename:"主体资料包-v2.zip"}],
};

describe("运行时引用服务器冻结资料包",()=>{
 it("把已授权assetId、完整SHA及原生reference-pack启动要求传入系统上下文",()=>{
  const subjectContext={revision:1 as const,conversationId:"chat",folderId:"subject",generation:2,packVersionId:"pack-v2",sourceTaskId:"source-task",artifactId:`artifact_${"b".repeat(64)}`,localAssetId:assetId,contentSha256};
  const text=contentProductionSystemContext({...context,subjectContext});
  const paragraph=text.split("\n\n").find(item=>item.startsWith("The server-authorized Reference Pack"));
  expect(paragraph).toBeDefined();
  expect(paragraph).toContain(assetId);expect(paragraph).toContain(contentSha256);
  expect(paragraph).toContain("mounted original ZIP");expect(paragraph).toContain("verify its full SHA256");
  expect(paragraph).toContain("--reference-pack");expect(paragraph).toContain("Missing bytes or a digest mismatch must stop");
  expect(text).toContain(`Input file identity mapping: ${JSON.stringify(context.inputFiles)}`);
 });
 it("既有无主体任务保留旧系统上下文，不添加新的主体资料包指令",()=>{
  const text=contentProductionSystemContext(context);
  expect(text).not.toContain("The server-authorized Reference Pack");
  expect(text).not.toContain("frozen localAssetId");
  expect(text).not.toContain(contentSha256);
 });
 it("新主体尚无资料包时不要求加载不存在的ZIP",()=>{
  const text=contentProductionSystemContext({...context,inputFiles:[],subjectContext:{revision:1,conversationId:"new-chat",folderId:"subject",generation:0,packVersionId:null}});
  expect(text).not.toContain("The server-authorized Reference Pack");
  expect(text).not.toContain("frozen localAssetId");
 });
});
