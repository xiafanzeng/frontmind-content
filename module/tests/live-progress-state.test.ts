import {expect,it} from "vitest";
import {contentProductionPublicDto,parseContentRunnerState} from "../server/state";
import {contentLiveProgressLabel} from "../client/content-live-progress";
import type {FrozenContentTaskContext} from "../contracts/task-context";
import {CONTENT_PRODUCTION_RUNNER_STATUSES,type ContentProductionDto} from "../contracts/content-production";

const context={purpose:"content_production",contentProduction:{mode:"p0",enterpriseName:"任意主体"}} as FrozenContentTaskContext;
const base={schema_version:"4.11",artifact_type:"frontmind_content_job_state",workflow_version:"4.11",job_id:"same-job",job_kind:"p0",updated_at:"2026-10-25T00:00:00+00:00",stage:"p0_blueprint",status:"awaiting_p0_blueprint_confirmation",revision:5,current_pause:{pause_type:"awaiting_p0_blueprint_confirmation",title:"确认蓝图",available_choices:[],revision:5,requires_user_input:true,user_pause:true,must_stop:true},pending_action:null,flags:{},decisions:{},p0_route:"create"};
const stored={revision:2,lastObservation:{state:parseContentRunnerState(Buffer.from(JSON.stringify(base)))!,providerRank:1,eventId:"old",artifactId:"unchanged-artifact",sha256:"unchanged-sha"},progressPosition:10,completedConfirmations:[]};
const live={...base,updated_at:"2026-10-25T00:00:01+00:00",status:"running_p0_production",stage:"p0_production",current_pause:null,pending_action:{action:"p0_style"},flags:{p0_production_step:"style"},decisions:{p0_blueprint_confirmation:{revision:5,confirmed:true}}};
it("same-task live state replaces an old confirmation before turn completion without rewriting stored evidence",()=>{
 const runtime={contentProductionProgress:stored,xtyCodex:{contentWorkflowRuntime:"native_content_v1",contentWorkflowLiveState:live}};
 const result=contentProductionPublicDto(context,runtime)!;
 expect(result).toMatchObject({confirmation:null,pauseTitle:null,workflowStatus:"running_p0_production",productionStep:"style",runnerRevision:5,completedConfirmations:["awaiting_p0_route","awaiting_p0_blueprint_confirmation"]});
 expect(contentLiveProgressLabel(result)).toBe("正在处理品牌长文文风");
 expect(stored.lastObservation.artifactId).toBe("unchanged-artifact");expect(stored.lastObservation.state.status).toBe("awaiting_p0_blueprint_confirmation");
});
it.each([{...live,job_id:"other-job"},{...live,revision:4},{...live,updated_at:"2026-10-24T00:00:00+00:00"},{...live,flags:{p0_production_step:"invented-step"}}])("rejects unrelated, stale or invalid live state",value=>{
 expect(contentProductionPublicDto(context,{contentProductionProgress:stored,xtyCodex:{contentWorkflowRuntime:"native_content_v1",contentWorkflowLiveState:value}})?.confirmation).toBe("awaiting_p0_blueprint_confirmation");
});
it("only a trusted native runtime may provide live state; absent detail does not invent a step",()=>{
 expect(contentProductionPublicDto(context,{contentProductionProgress:stored,xtyCodex:{contentWorkflowLiveState:live}})?.confirmation).toBe("awaiting_p0_blueprint_confirmation");
 expect(contentLiveProgressLabel(null)).toBeNull();
});
it("每一种原生执行状态都有中文说明，不遗漏方案生成或资料包回写阶段",()=>{
 for(const status of CONTENT_PRODUCTION_RUNNER_STATUSES.filter(status=>status.startsWith("running_"))){
  const label=contentLiveProgressLabel({jobKind:status.includes("p0")?"p0":"article",workflowStatus:status,productionStep:null} as ContentProductionDto);
  expect(label,status).toMatch(/^正在/u);
 }
});
