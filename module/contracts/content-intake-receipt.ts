import { z } from "zod";

/** 服务端从既有收件账本投影；不以浏览器模式或消息文案认定收件成功。 */
export const contentIntakeReceiptSchema = z.object({
  schemaVersion: z.literal(1),
  id: z.string().min(1).max(128),
  conversationId: z.string().min(1).max(128),
  messageId: z.string().min(1).max(128),
  acceptedAt: z.number().finite().nonnegative(),
  status: z.literal("received"),
  executionStarted: z.literal(false),
}).strict();

export type ContentIntakeReceipt = z.infer<typeof contentIntakeReceiptSchema>;

type ReceiptConversation = {
  id: string; purpose?: string; taskId?: string; previousResponseId?: string;
  executionKind?: string; execution?: unknown; contentIntakeReceipt?: unknown;
  messages: readonly {id: string; role: string; generalChatDispatch?: unknown}[];
};

export function receivedContentIntake(conversation?: ReceiptConversation | null): ContentIntakeReceipt | null {
  if (!conversation || conversation.purpose !== "content_production" || conversation.taskId
    || conversation.previousResponseId || conversation.executionKind || conversation.execution) return null;
  const receipt = contentIntakeReceiptSchema.safeParse(conversation.contentIntakeReceipt);
  if (!receipt.success || receipt.data.conversationId !== conversation.id) return null;
  const message = conversation.messages.find(item => item.id === receipt.data.messageId && item.role === "user");
  const dispatch = message?.generalChatDispatch as {kind?: unknown; clientRequestId?: unknown} | undefined;
  return dispatch?.kind === "pending_user" && dispatch.clientRequestId === receipt.data.id ? receipt.data : null;
}
