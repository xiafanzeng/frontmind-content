import type { ContentBusinessClient } from "./runtime";

export type IntakeVerificationRequest = <T>(path: string, init?: RequestInit) => Promise<T>;
const root = "/api/modules/content";

export function intakeVerificationRequested(search: string): boolean {
  return new URLSearchParams(search).get("verify") === "intake";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  init.signal?.addEventListener("abort", abort, { once: true });
  if (init.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 20_000);
  try {
    const response = await fetch(path, { credentials: "same-origin", ...init, signal: controller.signal });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error?.message ?? value.message ?? "真实收件接口暂不可用，请刷新核对记录，勿重复提交。");
    return value as T;
  } finally {
    clearTimeout(timer);
    init.signal?.removeEventListener("abort", abort);
  }
}

/** 必须先确认正式收件能力；失败时不返回客户端，更不能回退生成。 */
export async function createIntakeVerificationClient(
  base: ContentBusinessClient,
  options: { request?: IntakeVerificationRequest; signal?: AbortSignal } = {},
): Promise<ContentBusinessClient> {
  const send = options.request ?? request;
  const capability = await send<{ module?: unknown; features?: unknown }>(`${root}/capabilities`, { signal: options.signal });
  if (capability?.module !== "content" || !Array.isArray(capability.features) || !capability.features.includes("intake")) {
    throw new Error("当前版本未提供正式收件接口，验收已停止；不会转为生成任务。");
  }
  const body = (value: unknown): RequestInit => ({ method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(value) });
  const blocked = async (): Promise<never> => { throw new Error("收件验收模式禁止生成、任务查询和停止操作。"); };
  return {
    ...base,
    readSubjectWorkspace: () => send(`${root}/subject-workspace`),
    saveSubjectWorkspace: value => send(`${root}/subject-workspace`, body(value)),
    list: () => send(`${root}/conversations`),
    save: value => send(`${root}/conversations/${encodeURIComponent(value.id)}`, body(value)),
    remove: async id => { await send(`${root}/conversations/${encodeURIComponent(id)}`, { method: "DELETE" }); },
    async submitIntake(input) {
      const receipt = await send<Awaited<ReturnType<NonNullable<ContentBusinessClient["submitIntake"]>>>>(`${root}/intake`, { ...body(input), method: "POST" });
      if (receipt?.id !== input.clientRequestId || receipt.conversationId !== input.conversationId || receipt.status !== "received"
        || receipt.executionStarted !== false || !Number.isFinite(receipt.acceptedAt) || receipt.conversation?.id !== input.conversationId
        || receipt.conversation.purpose !== "content_production" || receipt.conversation.taskId || receipt.conversation.executionKind || receipt.conversation.execution) {
        throw new Error("真实收件回执不一致，请刷新核对记录，勿重新提交或生成。");
      }
      return receipt;
    },
    dispatch: blocked,
    task: blocked,
    stop: blocked,
  };
}
