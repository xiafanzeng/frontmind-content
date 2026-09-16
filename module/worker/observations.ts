import {isContentWorkflowInternalFilename,isContentWorkflowStateFilename} from "../server/runtime";
import {parseContentRunnerState,type ContentRunnerObservation} from "../server/state";
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
