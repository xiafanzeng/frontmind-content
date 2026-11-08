import { z } from "zod";

export const enterpriseQaKnowledgeReferenceSchema = z.object({
  snapshotId: z.string().min(1).max(128),
  version: z.number().int().nonnegative(),
  sourceFileName: z.string().min(1).max(512),
  documentCount: z.number().int().nonnegative(),
  companyName: z.string().min(1).max(255).optional(),
});
export type EnterpriseQaKnowledgeReference = z.infer<typeof enterpriseQaKnowledgeReferenceSchema>;

/** A server rule reply is a persisted chat message, never a provider task. */
export const enterpriseQaLocalReplyMetadataSchema = z.object({
  schemaVersion: z.literal(1), kind: z.literal("local_reply"),
  source: z.literal("rule"), reason: z.literal("greeting"),
  evaluation: z.literal("not_required"), serverOwned: z.literal(true),
  turnId: z.string().uuid(), userMessageId: z.string().min(1).max(128),
  answerMessageId: z.string().min(1).max(128),
  /** Optional for backward compatibility; required on newly persisted greetings. */
  knowledgeBase: enterpriseQaKnowledgeReferenceSchema.optional(),
});
export type EnterpriseQaLocalReplyMetadata = z.infer<typeof enterpriseQaLocalReplyMetadataSchema>;
export type EnterpriseQaLocalReply = {
  object: "frontmind.local_reply";
  conversationId: string; turnId: string; userMessageId: string; answerMessageId: string;
  content: string; status: "completed"; completedAt: number;
  reason: "greeting"; evaluation: "not_required";
  enterpriseQaLocalReply: EnterpriseQaLocalReplyMetadata;
};
export type EnterpriseQaFollowupItem = {
  id: string; text: string;
  status: "queued" | "dispatching" | "failed" | "completed" | "cancelled";
  paused: boolean; error?: string; canCancel: boolean; canRetry: boolean;
};
export type EnterpriseQaFollowupSnapshot = { items: EnterpriseQaFollowupItem[]; paused: boolean };
/** A browser send lost admission to an earlier FIFO item and is now durably queued. */
export type EnterpriseQaQueuedFollowupReceipt = {
  object: "frontmind.queued_followup"; conversationId: string; userMessageId: string;
  item: EnterpriseQaFollowupItem;
};
/** The worker owns this pending user message; browsers only observe it. */
export const enterpriseQaFollowupMetadataSchema = z.object({
  schemaVersion: z.literal(1), queueId: z.string().uuid(), serverOwned: z.literal(true),
});
export type EnterpriseQaFollowupMetadata = z.infer<typeof enterpriseQaFollowupMetadataSchema>;

/** Exact greeting vocabulary only: a business question prefixed with hello is not a greeting. */
export function isPureEnterpriseQaGreeting(text: string) {
  const normalized = text.normalize("NFKC").trim().toLowerCase().replace(/[\s，。！？、,.!?~～]+/gu, "");
  return new Set(["你好", "您好", "嗨", "hello", "hi", "hey", "早上好", "上午好", "中午好", "下午好", "晚上好", "早安", "晚安"]).has(normalized);
}
