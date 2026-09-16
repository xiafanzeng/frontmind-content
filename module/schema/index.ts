import type {FrozenContentTaskContext} from "../contracts/task-context";
import type {ContentProductionProgress} from "../server/state";
/** Content is persisted in the existing Core execution ledger. Extraction does
 * not create replacement jobs or new tables. These are the module-owned JSON
 * fields in agent_tasks.providerRuntime; Core owns generic task/turn identity. */
export interface ContentTaskRuntime {
 generalPurpose:FrozenContentTaskContext & {purpose:"content_production"};
 contentProductionProgress?:ContentProductionProgress;
 [key:string]:unknown;
}
export const CONTENT_STORAGE={
 tasks:"agent_tasks",operations:"agent_operations",events:"agent_events",
 conversations:"conversations",messages:"messages",turns:"conversation_turns",
 frozenContextField:"generalPurpose",progressField:"contentProductionProgress",
} as const;
