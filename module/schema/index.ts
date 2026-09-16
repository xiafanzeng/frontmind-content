import { int, index, json, mysqlEnum, mysqlTable, text, timestamp, uniqueIndex, varchar, type AnyMySqlColumn } from "drizzle-orm/mysql-core";
import type { FrozenContentTaskContext } from "../contracts/task-context.js";
import type { ContentProductionProgress, ContentRunnerObservation } from "../server/state.js";
export interface ContentSchemaCore { users: { id: AnyMySqlColumn }; }
export const contentTaskStatuses = ["queued", "running", "awaiting_input", "completed", "failed", "cancelled"] as const;
export function createContentSchema(core: ContentSchemaCore) {
  const contentTasks = mysqlTable("content_tasks", {
    id: varchar("id", { length: 36 }).primaryKey(),
    ownerUserId: int("owner_user_id").notNull().references(() => core.users.id, { onDelete: "cascade" }),
    enterpriseProjectId: varchar("enterprise_project_id", { length: 36 }),
    operationId: varchar("operation_id", { length: 128 }).notNull(),
    clientRequestId: varchar("client_request_id", { length: 128 }).notNull(),
    status: mysqlEnum("status", contentTaskStatuses).notNull().default("queued"),
    context: json("context").$type<FrozenContentTaskContext>().notNull(),
    providerRuntime: json("provider_runtime").$type<Record<string, unknown>>(),
    progress: json("progress").$type<ContentProductionProgress>(),
    workflowVersion: varchar("workflow_version", { length: 64 }).notNull(),
    workflowFilename: varchar("workflow_filename", { length: 255 }).notNull(),
    workflowSha256: varchar("workflow_sha256", { length: 64 }).notNull(),
    workflowRootDirectory: varchar("workflow_root_directory", { length: 255 }).notNull(),
    revision: int("revision", { unsigned: true }).notNull().default(1),
    createdAt: timestamp("created_at").defaultNow().notNull(),
    updatedAt: timestamp("updated_at").defaultNow().onUpdateNow().notNull(),
  }, table => [
    uniqueIndex("content_tasks_owner_client_request_uq").on(table.ownerUserId, table.clientRequestId),
    uniqueIndex("content_tasks_operation_uq").on(table.operationId),
    index("content_tasks_owner_status_updated_idx").on(table.ownerUserId, table.status, table.updatedAt),
  ]);
  const contentTaskObservations = mysqlTable("content_task_observations", {
    id: varchar("id", { length: 36 }).primaryKey(),
    taskId: varchar("task_id", { length: 36 }).notNull().references(() => contentTasks.id, { onDelete: "cascade" }),
    providerRank: int("provider_rank", { unsigned: true }).notNull(),
    sequence: int("sequence", { unsigned: true }).notNull(),
    observation: json("observation").$type<ContentRunnerObservation>().notNull(),
    payloadHash: varchar("payload_hash", { length: 64 }).notNull(),
    observedAt: timestamp("observed_at").notNull(),
  }, table => [
    uniqueIndex("content_task_observations_task_sequence_uq").on(table.taskId, table.sequence),
    index("content_task_observations_task_rank_idx").on(table.taskId, table.providerRank),
  ]);
  return { contentTasks, contentTaskObservations };
}
export type ContentSchema = ReturnType<typeof createContentSchema>;
