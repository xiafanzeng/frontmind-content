import type {ContentProductionInput,ContentProductionAction,ContentProductionKnowledgeSource} from "../contracts/content-production";
import type {FrozenContentTaskContext} from "../contracts/task-context";
import {freezeContentWorkflow,originalContentWorkflowArchive} from "./workflow-catalog";
export class ContentTaskError extends Error {readonly retryable=false;readonly dispatchSettled=true;constructor(public readonly code:string,public readonly statusCode:number){super(code);}}
export function validateContentTaskCreation(value:{purpose?:string;contentProduction?:ContentProductionInput;localAssetIds:readonly string[]}) {
 if(Boolean(value.contentProduction)!==(value.purpose==="content_production"))throw new ContentTaskError("CONTENT_PRODUCTION_INPUT_REQUIRED",400);
 if(!value.contentProduction)return;
 const sourceIds=[...value.contentProduction.monitoringAnswerAssetIds,...(value.contentProduction.sourceWorkbookAssetId?[value.contentProduction.sourceWorkbookAssetId]:[])];
 if(sourceIds.some(id=>!value.localAssetIds.includes(id)))throw new ContentTaskError("CONTENT_PRODUCTION_INPUT_ASSET_CONFLICT",400);
}
/** Called within the host's existing create/credit-reservation transaction. */
export async function freezeContentTaskContext(input:{
 userId:number;enterpriseProjectId:string|null;input:ContentProductionInput;localAssetIds:readonly string[];
 loadKnowledge():Promise<{knowledgeBase:ContentProductionKnowledgeSource;knowledgeText:string}|null>;
 loadOwnedFiles(ids:readonly string[]):Promise<Array<{localAssetId:string;filename:string}>>;
 workflow?:()=>ReturnType<typeof freezeContentWorkflow>;
}):Promise<FrozenContentTaskContext> {
 validateContentTaskCreation({purpose:"content_production",contentProduction:input.input,localAssetIds:input.localAssetIds});
 const knowledge=input.input.knowledgeSource==="published"?await input.loadKnowledge():null;
 if(input.input.knowledgeSource==="published"&&!knowledge)throw new ContentTaskError("ENTERPRISE_QA_KNOWLEDGE_REQUIRED",428);
 const files=input.localAssetIds.length?await input.loadOwnedFiles(input.localAssetIds):[];
 if(files.length!==new Set(input.localAssetIds).size)throw new ContentTaskError("LOCAL_ASSET_NOT_FOUND",404);
 return {revision:1,accountUserId:input.userId,enterpriseProjectId:input.enterpriseProjectId,purpose:"content_production",knowledgeBase:knowledge?.knowledgeBase??null,knowledgeText:knowledge?.knowledgeText??null,contentProduction:input.input,contentWorkflow:(input.workflow??freezeContentWorkflow)(),inputFiles:files};
}
export function assertContentConfirmation(input:{action?:ContentProductionAction;availableActions?:ContentProductionAction["kind"][];runnerRevision?:number|null}) {
 if(input.action&&(!input.availableActions?.includes(input.action.kind)||input.action.revision!==input.runnerRevision))throw new ContentTaskError("CONTENT_PRODUCTION_CONFIRMATION_CONFLICT",409);
}
