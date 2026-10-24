import type {FrozenContentTaskContext} from "../contracts/task-context";
import type {ContentProductionProgress} from "../server/state";
import { index, int, json, mysqlTable, timestamp, varchar } from "drizzle-orm/mysql-core";
import type { ContentSubjectWorkspace } from "../contracts/content-subject-workspace";

/** 正式主体资料库；宿主负责账号/企业项目定位、事务及版本化迁移。 */
export const contentSubjectWorkspaces = mysqlTable("content_subject_workspaces", {
  workspaceKey: varchar("workspace_key", { length: 64 }).notNull().primaryKey(),
  ownerUserId: int("owner_user_id").notNull(),
  projectId: varchar("project_id", { length: 36 }),
  revision: int("revision", { unsigned: true }).notNull().default(0),
  payload: json("payload").$type<ContentSubjectWorkspace>().notNull(),
  updatedAt: timestamp("updated_at").notNull().defaultNow().onUpdateNow(),
}, table => [index("content_subject_owner_project_idx").on(table.ownerUserId, table.projectId)]);

export type ContentSubjectWorkspaceRow = typeof contentSubjectWorkspaces.$inferSelect;

/** 已确认收件的服务器幂等账本，独立于浏览器可同步的聊天消息。 */
export const contentIntakeReceipts = mysqlTable("content_intake_receipts", {
  receiptKey: varchar("receipt_key", { length: 64 }).notNull().primaryKey(),
  ownerUserId: int("owner_user_id").notNull(),
  projectId: varchar("project_id", { length: 36 }),
  clientRequestId: varchar("client_request_id", { length: 128 }).notNull(),
  conversationId: varchar("conversation_id", { length: 128 }).notNull(),
  fingerprint: varchar("fingerprint", { length: 64 }).notNull(),
  payload: json("payload").$type<Record<string, unknown>>().notNull(),
  acceptedAt: timestamp("accepted_at").notNull().defaultNow(),
}, table => [
  index("content_intake_owner_project_idx").on(table.ownerUserId, table.projectId),
  index("content_intake_conversation_idx").on(table.conversationId),
]);

export type ContentIntakeReceiptRow = typeof contentIntakeReceipts.$inferSelect;

/** Execution remains in the existing Core ledger. These are module-owned JSON
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
