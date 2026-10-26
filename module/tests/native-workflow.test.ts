import * as workflowCatalog from "../server/workflow-catalog";
import { describe, expect, it, vi } from "vitest";
import { contentProductionActionSchema, contentProductionInputSchema } from "../contracts/content-production";
import { parseContentRunnerState, reduceContentProductionProgress, contentProductionPublicDto, contentProductionTaskStatus } from "../server/state";
import { contentProductionSystemContext, contentProductionClientOptions, contentWorkflowRuntimeFor } from "../server/runtime";
import { assertContentConfirmation } from "../server/task-handlers";
import type { FrozenContentTaskContext } from "../contracts/task-context";
import release from "../workflows/release.json";

const context: FrozenContentTaskContext = {
  revision: 1, accountUserId: 1, purpose: "content_production", knowledgeBase: null, knowledgeText: null,
  contentProduction: contentProductionInputSchema.parse({ mode: "single_article", enterpriseName: "合成企业", knowledgeSource: "files" }),
  contentWorkflow: { version: "4.13.2-v16.2", rootDirectory: "FrontMind_Content_Workflow_v4.13.2", filename: "workflow.zip", sha256: "a".repeat(64) },
};

it("原 Job 跨阶段接续保持进度与历史确认，不把资料包交付当成六步全部结束", () => {
  const first = parseContentRunnerState(Buffer.from(JSON.stringify({...state("positioning_ready","reference_pack"),job_kind:"reference_pack",
    metadata:{session_phase_contract:"frontmind-session-phases/1",completed_phase_confirmations:[]},
    decisions:{core_positioning_confirmation:{confirmed:true}}})))!;
  const before = reduceContentProductionProgress(null,{providerRank:1,eventId:"pack",artifactId:"pack-state",sha256:"a".repeat(64),state:first},"new_reference_pack");
  expect(before.progressPosition).toBe(7);
  const second = parseContentRunnerState(Buffer.from(JSON.stringify({...state("awaiting_p0_route","p0_route"),job_kind:"p0",revision:9,
    updated_at:"2026-09-29T10:01:00+00:00",current_pause:{...state("awaiting_p0_route").current_pause,revision:9},
    metadata:{session_phase_contract:"frontmind-session-phases/1",completed_phase_confirmations:["awaiting_core_positioning_confirmation"]}})))!;
  const after = reduceContentProductionProgress(before,{providerRank:2,eventId:"p0",artifactId:"p0-state",sha256:"b".repeat(64),state:second},"new_reference_pack");
  expect(after.lastObservation.state.job_id).toBe(first.job_id);
  expect(after.lastObservation.state.job_kind).toBe("p0");
  expect(after.progressPosition).toBe(8);
  expect(after.completedConfirmations).toContain("awaiting_core_positioning_confirmation");
});

it.each([["p0","p0_ready","reference_pack"],["article","completed","E10"]] as const)("资料包原任务接续到 %s 后按实际阶段判断完成",(kind,status,stage)=>{
 const parsed=parseContentRunnerState(Buffer.from(JSON.stringify({...state(status,stage),job_kind:kind,
  metadata:{session_phase_contract:"frontmind-session-phases/1",completed_phase_confirmations:["awaiting_core_positioning_confirmation"]}})))!;
 const phaseContext={...context,contentProduction:{...context.contentProduction!,mode:"new_reference_pack" as const}};
 const progress=reduceContentProductionProgress(null,{state:parsed,providerRank:1,eventId:"phase",artifactId:"state",sha256:"a".repeat(64)},"new_reference_pack");
 const dto=contentProductionPublicDto(phaseContext,{contentProductionProgress:progress},{operationStatus:"completed"})!;
 expect(dto).toMatchObject({executionStatus:"completed",jobKind:kind,workflowStatus:status});
 expect(contentProductionTaskStatus(dto,"completed")).toBe("completed");
 expect(progress.progressPosition).toBe(kind==="p0"?12:20);
 const failed=contentProductionPublicDto(phaseContext,{contentProductionProgress:progress},{operationStatus:"error"})!;
 expect(failed).toMatchObject({executionStatus:"error",workflowStatus:status,availableActions:["resume_current_execution"]});
});

it("阶段接续指令只对新的应用修订启用，历史冻结任务不改变",()=>{
  const current={...context,contentWorkflow:{...context.contentWorkflow!,version:"4.13.2-v16.8-app1"}};
  expect(contentWorkflowRuntimeFor(current)).toBe("native_content_v1");
  expect(contentProductionSystemContext(current)).toContain("--next-task p0");
  expect(contentProductionSystemContext({...current,contentWorkflow:{...current.contentWorkflow,version:"4.13.2-v16.8"}})).not.toContain("--next-task p0");
});

it("v16.8.6 冻结阶段接续能力，同时保留上游编辑规则和失败停止指令",()=>{
  const current:FrozenContentTaskContext={...context,contentWorkflow:{...context.contentWorkflow!,
    version:release.version,runtime:"native_content_v1",capabilities:["structured_article","editorial_v16_8","session_phases"]}};
  const system=contentProductionSystemContext(current);
  expect(contentProductionPublicDto(current)?.sessionPhases).toBe(true);
  expect(release.version).toBe("4.13.2-v16.8.6");
  expect(contentWorkflowRuntimeFor(current)).toBe("native_content_v1");
  expect(system).toContain("--next-task p0");
  expect(system).toContain("--pool-selection");
  expect(system).toContain("Do not invoke --retry-current-action");
  expect(system).not.toContain("the next P0/article is a separate task");
  const previous={...current,contentWorkflow:{...current.contentWorkflow!,version:"4.13.2-v16.8.2",
    capabilities:["structured_article","editorial_v16_8"] as ("structured_article"|"editorial_v16_8")[]}};
  expect(contentProductionPublicDto(previous)?.sessionPhases).toBe(false);
  expect(contentProductionSystemContext(previous)).not.toContain("--next-task p0");
  expect(contentProductionSystemContext(previous)).toContain("the next P0/article is a separate task");
});

it("阶段元数据与上游安全错误投影同时保留，不把错误资料包进度标成全部完成",()=>{
  const observed=parseContentRunnerState(Buffer.from(JSON.stringify({
    ...state("running_positioning_market_research","positioning_research"),job_kind:"reference_pack",
    pending_action:{action:"positioning_market_research",error:{code:"tool_call_source_mismatch",attempt_id:"phase-attempt",message:"private provider detail"}},
    metadata:{session_phase_contract:"frontmind-session-phases/1",completed_phase_confirmations:["awaiting_reference_pack_route"]},
  })))!;
  const progress=reduceContentProductionProgress(null,{providerRank:1,eventId:"phase-failure",artifactId:"phase-state",sha256:"c".repeat(64),state:observed},"new_reference_pack");
  expect(progress.completedConfirmations).toContain("awaiting_reference_pack_route");
  expect(progress.progressPosition).toBeLessThan(20);
  expect(contentProductionPublicDto(context,{contentProductionProgress:progress})?.executionFailure).toEqual({
    action:"positioning_market_research",code:"tool_call_source_mismatch",attemptId:"phase-attempt",
  });
  expect(JSON.stringify(observed)).not.toContain("private provider detail");
});
function state(status = "awaiting_question_selection", stage = "question_selection") {
  return {
    schema_version: "4.11", artifact_type: "frontmind_content_job_state", workflow_version: "4.11",
    job_id: "one-job", job_kind: "article", updated_at: "2026-09-29T10:00:00+00:00", stage, status, revision: 7,
    current_pause: status.startsWith("awaiting_") ? {
      pause_type: status, title: "选择问题", available_choices: ["1. 合成问题"], revision: 7,
      requires_user_input: true, user_pause: true, must_stop: true,
    } : null,
    pending_action: null, flags: {}, decisions: {}, p0_route: null,
  };
}

describe("native v16.2 and v16.3 host integration", () => {
  it.each(["4.13.2-v16.3", "4.13.2-v16.4"])("connects frozen %s to native providers and preserves legacy execution", (version) => {
    expect(contentWorkflowRuntimeFor(context)).toBe("native_content_v1");
    const next = {...context,contentWorkflow:{...context.contentWorkflow!,version}};
    expect(contentWorkflowRuntimeFor(next)).toBe("native_content_v1");
    expect(contentProductionSystemContext(next)).toContain("5 formal plus 5 scenario");
    expect(contentProductionSystemContext(next)).not.toContain("exactly ten same-topic");
    expect(contentProductionSystemContext(context)).toContain("Never hand-write provider results");
    expect(contentProductionSystemContext(context)).toContain("timeout_seconds=7200");
    expect(contentProductionSystemContext(context)).toContain("title policy frozen");
    expect(contentProductionSystemContext(context)).not.toContain("No external provider SDK");
    const legacy = { ...context, contentWorkflow: undefined };
    expect(contentWorkflowRuntimeFor(legacy)).toBeUndefined();
    expect(contentProductionSystemContext(legacy)).toContain("No external provider SDK");
    expect(contentProductionSystemContext(legacy)).not.toContain("This frozen release uses its own OpenAI Agents SDK");
  });

  it("keeps v16.4 article scope and native preflight instructions together", () => {
    const input = contentProductionInputSchema.parse({
      mode: "single_article", enterpriseName: "合成企业", knowledgeSource: "files",
      genre: "industry_roundup", subjectScope: ["合成企业", "品牌甲", "品牌乙"],
      comparisonDimensions: ["温控", "售后"], articleFocus: "选购比较",
    });
    const current = {...context, contentProduction: input,
      contentWorkflow: {...context.contentWorkflow!, version: "4.13.2-v16.4"}};
    const instructions = contentProductionSystemContext(current);
    expect(contentWorkflowRuntimeFor(current)).toBe("native_content_v1");
    expect(instructions).toContain("FRONTMIND_CONTENT_PROVIDER_PROXY");
    expect(instructions).toContain("preflight before model work");
    expect(instructions).toContain("--genre industry_roundup");
    expect(instructions).toContain(JSON.stringify({genre: input.genre,
      subjectScope: input.subjectScope, comparisonDimensions: input.comparisonDimensions}));
    expect(instructions).not.toContain("No external provider SDK");
  });

  it("projects question selection with its real revision and rejects stale or cross-stage submission", () => {
    const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(state())))!;
    expect(parsed).not.toBeNull();
    const progress = reduceContentProductionProgress(null, { providerRank: 1, eventId: "event", artifactId: "state", sha256: "a".repeat(64), state: parsed }, "single_article");
    const dto = contentProductionPublicDto(context, { contentProductionProgress: progress });
    expect(dto).toMatchObject({ workflowVersion: "4.13.2-v16.2", confirmation: "awaiting_question_selection", runnerRevision: 7, progressPosition: 13 });
    expect(dto.availableActions).toContain("choose_question");
    const action = contentProductionActionSchema.parse({ kind: "choose_question", selection: "1", revision: 7 });
    expect(() => assertContentConfirmation({ action, availableActions: dto.availableActions, runnerRevision: 7 })).not.toThrow();
    expect(() => assertContentConfirmation({ action, availableActions: dto.availableActions, runnerRevision: 8 })).toThrow();
    expect(() => assertContentConfirmation({ action, availableActions: ["confirm_blueprint"], runnerRevision: 7 })).toThrow();
    expect(contentProductionActionSchema.safeParse({ ...action, selection: " " }).success).toBe(false);
    const wrong = state(); wrong.current_pause!.revision = 6;
    expect(parseContentRunnerState(Buffer.from(JSON.stringify(wrong)))).toBeNull();
  });

  it("projects v16.3 fact-gate failure as an explicit repair action", () => {
    const raw = {...state("running_article_production","article_production"),
      flags:{article_production_step:"deliver"},pending_action:{action:"article_fact_repair"}};
    const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(raw)))!;
    expect(parsed).not.toBeNull();
    const progress = reduceContentProductionProgress(null,{providerRank:1,eventId:"gate",artifactId:"state",sha256:"a".repeat(64),state:parsed},"single_article");
    const dto = contentProductionPublicDto({...context,contentWorkflow:{...context.contentWorkflow!,version:"4.13.2-v16.3"}},
      {contentProductionProgress:progress});
    expect(dto?.availableActions).toEqual(["repair_article_facts"]);
    expect(dto?.factGate?.publishReady).toBe(false);
  });

  it.each(["style", "finalize", "repair", "polish", "title_review"])("accepts native substage %s without claiming completion", (step) => {
    const raw = { ...state("running_article_production", "article_production"), flags: step === "style" ? { p0_production_step: step } : { article_production_step: step } };
    const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(raw)))!;
    expect(parsed).not.toBeNull();
    const progress = reduceContentProductionProgress(null, { providerRank: 1, eventId: "event", artifactId: "state", sha256: "a".repeat(64), state: parsed }, "single_article");
    expect(progress.progressPosition).toBeLessThan(20);
    expect(parseContentRunnerState(Buffer.from(JSON.stringify({ ...raw, status: "completed" })))).toBeNull();
  });

  it("preserves a 100-question catalog and its two additional input actions", () => {
    const raw = state();
    raw.current_pause!.available_choices = [
      ...Array.from({ length: 100 }, (_, index) => `${index + 1}. 合成问题${index + 1}`),
      "导入监控问答表", "更换Reference Pack",
    ];
    const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(raw)));
    expect(parsed?.current_pause?.available_choices).toEqual(raw.current_pause!.available_choices);
  });
});

it("connects v16.8 to the native chain and keeps independent choices",()=>{
 const next={...context,contentWorkflow:{...context.contentWorkflow!,version:"4.13.2-v16.8"}};
 expect(contentWorkflowRuntimeFor(next)).toBe("native_content_v1");
 const text=contentProductionSystemContext(next);
 for(const fragment of ["--source-workbook","--source-period","--pool-selection","usage_hint","questions-recommend","never duplicate the Job"])expect(text).toContain(fragment);
 expect(text).toContain("do not insert routine competitor confirmation");
 expect(text).toContain("not the AI answers as style samples");
});

it("keeps an inner failure distinct from a successfully completed Agent reply",()=>{
 const parsed=parseContentRunnerState(Buffer.from(JSON.stringify({...state("running_positioning_market_research","positioning_research"),
  pending_action:{action:"positioning_market_research",requires_provider_action:true,error:{code:"tool_call_source_mismatch",message:"PRIVATE_PROVIDER_ERROR",attempt_id:"private-attempt"}}})))!;
 const progress=reduceContentProductionProgress(null,{state:parsed,providerRank:1,eventId:"failure",artifactId:"state",sha256:"a".repeat(64)},"single_article");
 const dto=contentProductionPublicDto(context,{contentProductionProgress:progress},{operationStatus:"completed"})!;
 expect(dto).toMatchObject({executionStatus:"error",failureCode:"tool_call_source_mismatch",runnerRevision:7,availableActions:["resume_current_execution"]});
 expect(contentProductionTaskStatus(dto,"completed")).toBe("error");
 expect(JSON.stringify(parsed)).not.toContain("PRIVATE_PROVIDER_ERROR");
 expect(contentProductionActionSchema.parse({kind:"resume_current_execution",revision:7})).toEqual({kind:"resume_current_execution",revision:7});
 expect(()=>assertContentConfirmation({action:{kind:"resume_current_execution",revision:6},runnerRevision:7,availableActions:dto.availableActions})).toThrow();
});

it("uses actual pause and completion states instead of the outer turn outcome",()=>{
 const project=(raw:ReturnType<typeof state>,operationStatus:string)=>{
  const parsed=parseContentRunnerState(Buffer.from(JSON.stringify(raw)))!;
  const progress=reduceContentProductionProgress(null,{state:parsed,providerRank:1,eventId:"state",artifactId:"state",sha256:"b".repeat(64)},"single_article");
  return contentProductionPublicDto(context,{contentProductionProgress:progress},{operationStatus})!;
 };
 expect(contentProductionTaskStatus(project(state(),"completed"),"completed")).toBe("awaiting_input");
 for(const outcome of ["error","failed","cancelled"]) {
  const paused=project(state(),outcome);
  expect(paused).toMatchObject({confirmation:"awaiting_question_selection",runnerRevision:7,availableActions:["resume_current_execution"]});
  expect(contentProductionTaskStatus(paused,outcome)).toBe(outcome === "cancelled" ? "cancelled" : "error");
 }
 expect(project(state(),"running")).toMatchObject({executionStatus:"running",confirmation:null,availableActions:[]});
 expect(contentProductionTaskStatus(project(state("completed","E10"),"completed"),"completed")).toBe("completed");
 const interrupted={...state("running_positioning_market_research","positioning_research"),pending_action:{action:"positioning_market_research",requires_provider_action:true}};
 expect(project(interrupted as ReturnType<typeof state>,"cancelled")).toMatchObject({executionStatus:"cancelled",availableActions:["resume_current_execution"]});
});


it("原生任务停止后直接续用持久化 Job，保留检查点与用户修订号",()=>{
 const native={...context,contentWorkflow:{...context.contentWorkflow!,runtime:"native_content_v1" as const}};
 const archive=vi.spyOn(workflowCatalog,"originalContentWorkflowArchive").mockReturnValue(Buffer.from("synthetic release"));
 let options:ReturnType<typeof contentProductionClientOptions>;try{options=contentProductionClientOptions(native,{kind:"resume_current_execution",revision:0});}finally{archive.mockRestore();}
 expect(options.systemContext).toContain("reuse the complete original Job already present");expect(options.systemContext).toContain("Do not overwrite a present Job with an older snapshot");expect(options.turnContext).toContain("original Job restored by the host");expect(options.turnContext).toContain("report a concrete transport error if it is absent");expect(options.turnContext).toContain("--revision 0 --retry-current-action");expect(options.turnContext).toContain("status --job-dir DIR --json");expect(options.turnContext).toContain("without invoking a business action or model");
 const legacy={...context,contentWorkflow:{...context.contentWorkflow!,version:"4.11.0"}};expect(contentProductionSystemContext(legacy)).toContain("Before each continuation, restore the complete current Job from its private snapshot");
});
