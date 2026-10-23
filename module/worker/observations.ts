import {isContentWorkflowInternalFilename,isContentWorkflowStateFilename} from "../server/runtime";
import {parseContentRunnerState,type ContentRunnerObservation} from "../server/state";
import {createHash} from "node:crypto";
export interface ContentArtifact {id:string;filename:string;sizeBytes:number;contentSha256:string}
/** Internal runner state/snapshots never become public deliverables. */
export async function observeContentArtifact(input:{artifact:ContentArtifact;providerRank:number;eventId:string;readBytes(id:string,maxBytes:number):Promise<Buffer|null>}):Promise<{hidden:boolean;observation?:ContentRunnerObservation}> {
 const {artifact}=input;
 if(!isContentWorkflowInternalFilename(artifact.filename))return {hidden:false};
 if(!isContentWorkflowStateFilename(artifact.filename)||artifact.sizeBytes>256*1024)return {hidden:true};
 const bytes=await input.readBytes(artifact.id,256*1024);
 const state=bytes?parseContentRunnerState(bytes):null;
 return {hidden:true,...(state?{observation:{state,providerRank:input.providerRank,eventId:input.eventId,artifactId:artifact.id,sha256:artifact.contentSha256}}:{})};
}
export function registerWorker(host:{registerObserver(purpose:"content_production",observer:typeof observeContentArtifact):void}){host.registerObserver("content_production",observeContentArtifact);}

/** Re-read the same immutable state artifact when an older projection dropped error fields.
 * This does not resume the job, change its version or rewrite historical execution evidence. */
export async function restoreContentObservationFields(
 runtime:Record<string,unknown>|null|undefined,
 readBytes:(id:string,maxBytes:number)=>Promise<Buffer|null>,
):Promise<Record<string,unknown>|null|undefined> {
 const progress=runtime?.contentProductionProgress as {revision?:number;lastObservation?:ContentRunnerObservation}|undefined;
 const old=progress?.lastObservation;
 if(progress?.revision!==2||!old?.state?.pending_action||old.state.pending_action.error!==undefined)return runtime;
 try {
  const bytes=await readBytes(old.artifactId,256*1024);
  if(!bytes||createHash("sha256").update(bytes).digest("hex")!==old.sha256)return runtime;
  const state=parseContentRunnerState(bytes);
  if(!state||state.job_id!==old.state.job_id||state.revision!==old.state.revision||state.updated_at!==old.state.updated_at)return runtime;
  return {...runtime,contentProductionProgress:{...progress,lastObservation:{...old,state}}};
 }catch{return runtime;}
}
