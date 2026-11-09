import {expect,it,vi} from "vitest";
import {createHash} from "node:crypto";
import * as catalog from "../server/workflow-catalog";
import {contentProductionActionSchema,contentProductionInputSchema} from "../contracts/content-production";
import type {FrozenContentTaskContext} from "../contracts/task-context";
import {contentProductionSystemContext,contentProductionClientOptions,contentWorkflowRuntimeFor} from "../server/runtime";
import {contentProductionPublicDto,parseContentRunnerState,reduceContentProductionProgress} from "../server/state";
import {assertContentConfirmation,freezeContentTaskContext} from "../server/task-handlers";
import {twoStageTurnContext} from "../server/two-stage-runtime";
import release from "../workflows/release.json";

const context:FrozenContentTaskContext={revision:1,accountUserId:1,purpose:"content_production",knowledgeBase:null,knowledgeText:null,
  contentProduction:contentProductionInputSchema.parse({mode:"single_article",workflowVersion:"16.25.1",enterpriseName:"合成品牌",knowledgeSource:"files"}),
  contentWorkflow:{version:"16.25.1",runtime:"native_content_v2",capabilities:["two_stage_v16251"],filename:"frozen.zip",rootDirectory:"Workflow",sha256:"a".repeat(64)}};
function state(status="awaiting_writing_selection"){
  return {schema_version:"16.25.1",workflow_version:"16.25.1",artifact_type:"frontmind_content_job_state",job_id:"same-original-job",job_kind:"article",
    updated_at:"2026-11-08T01:00:00Z",stage:"writing_selection",status,revision:4,flags:{},decisions:{},p0_route:null,pending_action:null,
    current_pause:{pause_type:status,title:"选择问题类型与模式",available_choices:["P01｜单品牌推荐","P02｜多品牌推荐","P06｜评价回应"],revision:4,requires_user_input:true,user_pause:true,must_stop:true},
    metadata:{completed_phase_confirmations:["awaiting_question_selection","awaiting_question_answers","awaiting_question_sources"],private_key:"never public"}};
}

it("keeps pre-fix frozen system and turn bytes unchanged for pending command replays",()=>{
  // SHA-256 of the exact outputs on the 4ec4be73 production baseline.
  const digest=(text:string)=>createHash("sha256").update(text).digest("hex");
  const before=JSON.stringify(context);
  expect(digest(contentProductionSystemContext(context))).toBe("7ada6410b39a6694fdbf0133882373a7b8d6a8a0321cd3a40d38dbbb46c37e40");
  expect(digest(twoStageTurnContext())).toBe("1e7afc14903b20492dfe950384080319576e067fce8bb3a7b10b06ee4d65f584");
  const action={kind:"confirm_advantages" as const,revision:4,advantageIds:["adv2","adv1"],none:false,note:"原用户顺序"};
  expect(digest(twoStageTurnContext(action))).toBe("ed1a2dba91336db85e6c584ac7b6848a33f86d7fea044e5604194bed7032e7e2");
  expect(twoStageTurnContext(action,1)).toBe(twoStageTurnContext(action));
  expect(JSON.stringify(context)).toBe(before);
});

it("freezes explicit first-start instructions only for a newly created v2 knowledge task",async()=>{
  const files=[{localAssetId:"asset_original_kb",filename:"正式知识库.zip"}];
  const input=contentProductionInputSchema.parse({mode:"new_reference_pack",workflowVersion:"16.25.1",enterpriseName:"合成品牌",knowledgeSource:"files"});
  const workflowBefore=JSON.stringify(context.contentWorkflow);
  const fresh=await freezeContentTaskContext({userId:1,enterpriseProjectId:"project",input,localAssetIds:[files[0].localAssetId],loadKnowledge:async()=>null,loadOwnedFiles:async()=>files,workflow:()=>context.contentWorkflow!});
  expect(fresh).toMatchObject({contentStartupContractVersion:1,contentProduction:input,inputFiles:files,contentWorkflow:context.contentWorkflow});
  expect(JSON.stringify(context.contentWorkflow)).toBe(workflowBefore);
  const read=vi.spyOn(catalog,"originalContentWorkflowArchive").mockReturnValue(Buffer.from("offline archive fixture"));
  try{
    const original=JSON.stringify(fresh),options=contentProductionClientOptions(fresh);
    expect(options.systemContext).toContain("FIRST START:");
    expect(options.systemContext).toContain("new_reference_pack -> start --task reference-pack");
    expect(options.turnContext).toContain("run preflight and then the exact start command");
    expect(options.turnContext).toContain("If the original Job already exists, do not start again");
    expect(options.turnContext).toContain("stop with the real transport error instead of creating another Job");
    const action={kind:"confirm_advantages" as const,revision:4,advantageIds:["adv2","adv1"],none:false,note:"原用户顺序"};
    const continuation=contentProductionClientOptions(fresh,action);
    expect(continuation.turnContext).toBe(twoStageTurnContext(action));
    expect(continuation.turnContext).toContain(JSON.stringify(action));
    expect(continuation.turnContext).not.toContain("authorizes the original task's startup");
    expect(JSON.stringify(fresh)).toBe(original);
  }finally{read.mockRestore();}
  const legacy=await freezeContentTaskContext({userId:1,enterpriseProjectId:"project",input:{...input,workflowVersion:undefined},localAssetIds:[files[0].localAssetId],loadKnowledge:async()=>null,loadOwnedFiles:async()=>files,workflow:()=>({...context.contentWorkflow!,version:"4.13.2-v16.8.7",runtime:"native_content_v1"})});
  expect(legacy.contentStartupContractVersion).toBeUndefined();
  const imported=await freezeContentTaskContext({userId:1,enterpriseProjectId:"project",input:{...input,mode:"import_reference_pack"},localAssetIds:[files[0].localAssetId],loadKnowledge:async()=>null,loadOwnedFiles:async()=>files,workflow:()=>context.contentWorkflow!});
  expect(imported.contentStartupContractVersion).toBeUndefined();
});

it("new release uses the two-stage adapter while frozen v16.8.7 still uses its SDK route",()=>{
  expect(release).toMatchObject({version:"16.25.1",runtime:"native_content_v2"});
  expect(contentWorkflowRuntimeFor(context)).toBe("native_content_v2");
  const text=contentProductionSystemContext(context);
  expect(text).toContain("frontmind_v16251.py");expect(text).toContain("kimi-k3.1-pro/high");expect(text).toContain("gemini-4-argon/high");
  const legacy={...context,contentWorkflow:{...context.contentWorkflow!,version:"4.13.2-v16.8.7",runtime:"native_content_v1" as const,capabilities:["editorial_v16_8" as const]}};
  expect(contentWorkflowRuntimeFor(legacy)).toBe("native_content_v1");
  expect(contentProductionSystemContext(legacy)).toContain("its own OpenAI Agents SDK");
  expect(catalog.hasContentWorkflowCapability({...legacy.contentWorkflow,capabilities:undefined},"two_stage_v16251")).toBe(false);
});

it("strict new choices exclude P05 without invalidating legacy confirmations",()=>{
  const choose={kind:"choose_writing",revision:4,category:"行业排名",pattern:"P02",subjects:["c003","c001"],requiredMedia:["抖音"],note:"用户选行业排名、P02及具体主体"};
  expect(contentProductionActionSchema.parse(choose)).toEqual(choose);
  expect(contentProductionActionSchema.safeParse({...choose,pattern:"P05"}).success).toBe(false);
  expect(contentProductionActionSchema.safeParse({...choose,hiddenApproval:true}).success).toBe(false);
  expect(contentProductionActionSchema.safeParse({kind:"confirm_pattern",revision:4,selectedPattern:"P05"}).success).toBe(true);
});

it("new UI projection retains real revision and source confirmations, strips private metadata",()=>{
  const raw=state(),parsed=parseContentRunnerState(Buffer.from(JSON.stringify(raw)))!;
  expect(parsed).not.toBeNull();expect(JSON.stringify(parsed)).not.toContain("never public");
  const observation={providerRank:2,eventId:"real-state",artifactId:"state",sha256:"b".repeat(64),state:parsed};
  const progress=reduceContentProductionProgress(null,observation,"single_article");
  const dto=contentProductionPublicDto(context,{contentProductionProgress:progress},{operationStatus:"completed"})!;
  expect(dto).toMatchObject({confirmation:"awaiting_writing_selection",runnerRevision:4,executionStatus:"awaiting_input",availableActions:["choose_writing"]});
  expect(dto.completedConfirmations).toContain("awaiting_question_sources");
  expect(()=>assertContentConfirmation({action:{kind:"choose_writing",revision:3,category:"行业排名",pattern:"P01",subjects:[],requiredMedia:[],note:"用户选P01"},availableActions:dto.availableActions,runnerRevision:4})).toThrow();
  raw.current_pause.revision=3;expect(parseContentRunnerState(Buffer.from(JSON.stringify(raw)))).toBeNull();
});

it("v2 resume instructions never fall through to legacy retry flags",()=>{
  const read=vi.spyOn(catalog,"originalContentWorkflowArchive").mockReturnValue(Buffer.from("offline archive fixture"));
  const result=contentProductionClientOptions(context,{kind:"resume_current_execution",revision:4});
  // Attachment loading is separately exercised by the workflow catalog suite;
  // the system contract itself must explain exact JSON actions and same-request polls.
  expect(contentProductionSystemContext(context)).toContain("WITHOUT an action file");
  expect(contentProductionSystemContext(context)).toContain("EXACT JSON unchanged");
  expect(result.contentWorkflowRuntime).toBe("native_content_v2");
  expect(result.turnContext).toContain('"revision":4');
  expect(result.turnContext).not.toContain("--retry-current-action");
  read.mockRestore();
});

it.each([['reference_pack','positioning_ready',7],['p0','p0_ready',12],['article','completed',20]] as const)("new %s delivery completes only its own phase",(job_kind,status,position)=>{
  const parsed=parseContentRunnerState(Buffer.from(JSON.stringify({...state(status),job_kind,stage:job_kind==='article'?'E10':'reference_pack',current_pause:null})))!;
  const progress=reduceContentProductionProgress(null,{providerRank:1,eventId:'delivery',artifactId:'state',sha256:'c'.repeat(64),state:parsed},'single_article');
  const dto=contentProductionPublicDto(context,{contentProductionProgress:progress},{operationStatus:'completed'})!;
  expect(dto.executionStatus).toBe('completed');
  expect(dto.progressPosition).toBe(position);
  expect(dto.availableActions).toEqual(job_kind==='reference_pack'?['revise_advantages']:[]);
});
