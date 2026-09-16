import {describe,it,expect,vi} from "vitest";
import {assertContentConfirmation,freezeContentTaskContext,validateContentTaskCreation} from "../server/task-handlers";
import {assertContentSnapshot} from "../server/conversations";
import {observeContentArtifact} from "../worker/observations";
const source={mode:"single_article" as const,enterpriseName:"合成测试品牌",knowledgeSource:"files" as const,question:"如何选择服务？",monitoringAnswerAssetIds:["asset_answer"]};
const workflow={version:"4.11.0",filename:"workflow.zip",sha256:"a".repeat(64),rootDirectory:"workflow"};
describe("content business handlers",()=>{
 it("rejects missing purpose and asset references before dispatch",()=>{
  expect(()=>validateContentTaskCreation({purpose:"content_production",localAssetIds:[]})).toThrow("CONTENT_PRODUCTION_INPUT_REQUIRED");
  expect(()=>validateContentTaskCreation({purpose:"content_production",contentProduction:source,localAssetIds:[]})).toThrow("CONTENT_PRODUCTION_INPUT_ASSET_CONFLICT");
 });
 it("freezes manual input, original workflow and owned file map without reading knowledge",async()=>{
  const loadKnowledge=vi.fn();const context=await freezeContentTaskContext({userId:7,enterpriseProjectId:"workspace",input:source,localAssetIds:["asset_answer"],loadKnowledge,loadOwnedFiles:async()=>[{localAssetId:"asset_answer",filename:"original-answer.txt"}],workflow:()=>workflow});
  expect(loadKnowledge).not.toHaveBeenCalled();expect(context.contentWorkflow).toEqual(workflow);expect(context.inputFiles?.[0]?.filename).toBe("original-answer.txt");expect(context.knowledgeBase).toBeNull();
 });
 it("rejects files outside the fixed request workspace",async()=>{
  await expect(freezeContentTaskContext({userId:7,enterpriseProjectId:"workspace",input:source,localAssetIds:["asset_answer"],loadKnowledge:async()=>null,loadOwnedFiles:async()=>[],workflow:()=>workflow})).rejects.toThrow("LOCAL_ASSET_NOT_FOUND");
 });
 it("requires the exact saved runner revision and allowed business confirmation",()=>{
  expect(()=>assertContentConfirmation({action:{kind:"confirm_competitors",revision:3},runnerRevision:4,availableActions:["confirm_competitors"]})).toThrow("CONTENT_PRODUCTION_CONFIRMATION_CONFLICT");
  expect(()=>assertContentConfirmation({action:{kind:"confirm_competitors",revision:4},runnerRevision:4,availableActions:["confirm_competitors"]})).not.toThrow();
 });
 it("does not turn existing general/QA history into a content conversation",()=>{
  const incoming={id:"existing",purpose:"content_production",messages:[]};expect(()=>assertContentSnapshot(incoming,{...incoming,purpose:"enterprise_qa"})).toThrow("CONTENT_CONVERSATION_PURPOSE_MISMATCH");
  expect(()=>assertContentSnapshot({...incoming,taskId:"new"},{...incoming,taskId:"original"})).toThrow("CONTENT_CONVERSATION_TASK_MISMATCH");
 });
 it("keeps recovery snapshots private and never reads oversized state",async()=>{
  const readBytes=vi.fn();expect(await observeContentArtifact({artifact:{id:"snapshot",filename:`frontmind_workflow_job_snapshot_${"1".repeat(13)}_${"a".repeat(16)}_${"b".repeat(16)}.zip`,sizeBytes:100,contentSha256:"a".repeat(64)},providerRank:1,eventId:"event",readBytes})).toEqual({hidden:true});
  expect(await observeContentArtifact({artifact:{id:"state",filename:"frontmind_workflow_job_state.json",sizeBytes:256*1024+1,contentSha256:"b".repeat(64)},providerRank:1,eventId:"event",readBytes})).toEqual({hidden:true});expect(readBytes).not.toHaveBeenCalled();
 });
});
