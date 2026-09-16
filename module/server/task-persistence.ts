import {and,eq,type SQL} from "drizzle-orm";
import {persistObservations,type ContentRunnerObservation} from "./persistence";
import type {FrozenContentTaskContext} from "../contracts/task-context";
/** Generic execution tables are Core infrastructure. The content module owns
 * the row-lock, purpose check, reduction, and runtime update for its job. */
export interface ContentPersistencePorts {
 tables:{agentTasks:any;agentOperations:any};
 ownerPredicate(table:any,userId:number):SQL|undefined;
 readContext(task:{providerRuntime?:Record<string,unknown>|null},userId:number):FrozenContentTaskContext|null;
}
export function createContentPersistence(ports:ContentPersistencePorts) {
 const {agentTasks,agentOperations}=ports.tables;
 return async function persistContentProductionObservations(input:{executor:any;taskId:string;operationId:string;userId:number;observations:ContentRunnerObservation[]}) {
  return persistObservations(input,{withLockedTask:(scope,run)=>input.executor.transaction(async(tx:any)=>{
   const [row]=await tx.select({task:agentTasks}).from(agentTasks).innerJoin(agentOperations,eq(agentOperations.id,agentTasks.operationId)).where(and(eq(agentTasks.id,scope.taskId),eq(agentOperations.id,scope.operationId),eq(agentOperations.scope,"managed_user"),ports.ownerPredicate(agentOperations,scope.userId))).limit(1).for("update");
   if(!row)throw new Error("CONTENT_PRODUCTION_TASK_NOT_FOUND");
   const context=ports.readContext(row.task,scope.userId);
   if(context?.purpose!=="content_production")throw new Error("CONTENT_PRODUCTION_PURPOSE_MISMATCH");
   await run({context,providerRuntime:row.task.providerRuntime,saveRuntime:async providerRuntime=>{await tx.update(agentTasks).set({providerRuntime}).where(eq(agentTasks.id,scope.taskId));}});
  })});
 };
}
