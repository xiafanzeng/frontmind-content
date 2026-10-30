// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useContentWorkspaceHost, type ContentConversation } from "../client/host";
import type { ContentIntakeReceipt } from "../contracts/content-intake-receipt";
import ExecutionFeedback from "../client/ExecutionFeedback";

vi.mock("../client/ContentSubjectWorkspace", () => ({ default: () => {
  const host = useContentWorkspaceHost();
  const state = host.useConversation();
  const { sendMessage } = host.useSendMessage();
  const Home = host.Home;
  return state.activeConversation ? <>
    <button data-testid="direct-send" onClick={() => void sendMessage("合成收件材料").catch(() => {})}>直接提交</button>
    <button data-testid="refresh" onClick={() => void state.refreshConversations?.()}>刷新列表</button>
    <Home purpose="content_production" />
  </> : null;
} }));
vi.mock("@frontmind/module-ui/components/BusinessChatInput", () => ({ default: () => null }));
import { ModuleWorkspace, type ContentBusinessClient } from "../client/runtime";

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); document.body.innerHTML = ""; });

const receipt: ContentIntakeReceipt = {
  schemaVersion: 1, id: "request-1", conversationId: "conversation-1", messageId: "user-1",
  acceptedAt: 1000, status: "received", executionStarted: false,
};
function pendingConversation(): ContentConversation {
  return {
    id: "conversation-1", title: "合成收件会话", purpose: "content_production", status: "idle", createdAt: 1, updatedAt: 1000,
    messages: [{ id: "user-1", role: "user", content: "合成收件材料", timestamp: 1000,
      generalChatDispatch: { schemaVersion: 1, kind: "pending_user", clientRequestId: "request-1", providerPrompt: "合成收件材料", localAssetIds: [], localTaskId: null, modelProfile: "frontmind-base", purpose: "content_production" } }],
  };
}
function clientFor(conversation: ContentConversation) {
  let rows = [structuredClone(conversation)];
  const unexpected = vi.fn(async (): Promise<never> => { throw new Error("Unexpected write or execution"); });
  const client: ContentBusinessClient = {
    list: vi.fn(async () => structuredClone(rows)),
    save: vi.fn(async value => { rows = [structuredClone(value)]; return value; }),
    dispatch: vi.fn(async () => ({ id: "mock-task", purpose: "content_production" as const, status: "completed" })),
    task: vi.fn(async () => ({ id: "mock-task", status: "completed" })),
    readSubjectWorkspace: unexpected, saveSubjectWorkspace: unexpected, remove: unexpected, upload: unexpected, stop: unexpected,
  };
  return { client, unexpected };
}
async function mount(client: ContentBusinessClient, workspaceId: string) {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.setItem(`frontmind-content-active:${workspaceId}`, "conversation-1");
  const container = document.createElement("div"); document.body.append(container);
  let root = createRoot(container);
  const render = () => <ModuleWorkspace client={client} context={{ module: "content", workspace: { id: workspaceId, ownerUserId: 1 }, marketEdition: "cn", capabilities: [] }} />;
  await act(async () => root.render(render()));
  return {
    container,
    async remount() { await act(async () => root.unmount()); root = createRoot(container); await act(async () => root.render(render())); },
    async unmount() { await act(async () => root.unmount()); container.remove(); },
  };
}

it("已绑定任务的旧首轮回执不再显示重试或误建第二个任务", async () => {
  const {client}=clientFor({...pendingConversation(),taskId:"mock-task",status:"awaiting_input"});
  const view=await mount(client,"existing-task-pending-receipt");
  try{
    expect(view.container.querySelector(".cp-live-retry")).toBeNull();
    await act(async()=>view.container.querySelector<HTMLButtonElement>('[data-testid="direct-send"]')!.click());
    expect(client.dispatch).toHaveBeenCalledTimes(1);
    expect(client.dispatch).toHaveBeenCalledWith(expect.objectContaining({conversationId:"conversation-1",prompt:"合成收件材料"}),"mock-task");
    expect(vi.mocked(client.dispatch).mock.calls[0][0]).not.toHaveProperty("contentProduction");
  }finally{await view.unmount();}
});

it("普通客户端在刷新和重挂载后保留已收件状态，且发送入口不会派发任务", async () => {
  const { client, unexpected } = clientFor({ ...pendingConversation(), contentIntakeReceipt: receipt });
  expect(client.submitIntake).toBeUndefined();
  const view = await mount(client, "receipt-readback");
  const assertReceived = () => {
    expect(view.container.textContent).toContain("服务器已收件，生成尚未启动");
    expect(view.container.textContent).not.toContain("本次提交尚未确认");
    expect(view.container.textContent).not.toContain("重试本次提交");
    expect(view.container.querySelector(".cp-live-retry")).toBeNull();
  };
  try {
    assertReceived();
    await act(async () => view.container.querySelector<HTMLButtonElement>('[data-testid="direct-send"]')!.click());
    expect(client.dispatch).not.toHaveBeenCalled(); expect(client.save).not.toHaveBeenCalled();
    await act(async () => view.container.querySelector<HTMLButtonElement>('[data-testid="refresh"]')!.click());
    expect(client.list).toHaveBeenCalledTimes(2); assertReceived();
    await view.remount(); assertReceived();
    expect(client.list).toHaveBeenCalledTimes(3);
    expect(client.dispatch).not.toHaveBeenCalled(); expect(client.task).not.toHaveBeenCalled(); expect(unexpected).not.toHaveBeenCalled();
  } finally { await view.unmount(); }
});

it.each(["missing", "mismatched"] as const)("%s 收件回执不吞掉普通待确认提交的重试", async marker => {
  const conversation = pendingConversation();
  if (marker === "mismatched") conversation.contentIntakeReceipt = { ...receipt, conversationId: "other-conversation" };
  const { client, unexpected } = clientFor(conversation);
  const view = await mount(client, `pending-retry-${marker}`);
  try {
    const retry = view.container.querySelector<HTMLButtonElement>(".cp-live-retry");
    expect(retry?.textContent).toBe("重试本次提交");
    expect(view.container.textContent).toContain("本次提交尚未确认");
    await act(async () => retry!.click());
    expect(client.dispatch).toHaveBeenCalledTimes(1);
    expect(client.dispatch).toHaveBeenCalledWith({ conversationId: "conversation-1", clientRequestId: "request-1", prompt: "合成收件材料", localAssetIds: [], modelProfile: "frontmind-base", purpose: "content_production", contentProduction: undefined }, undefined);
    expect(client.save).toHaveBeenCalledTimes(1); expect(unexpected).not.toHaveBeenCalled();
    expect(view.container.textContent).not.toContain("重试本次提交");
  } finally { await view.unmount(); }
});

it("已收件执行反馈不会把保留的 pending_user 消息显示为未确认", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  try {
    await act(async () => root.render(<ExecutionFeedback conversation={{ ...pendingConversation(), contentIntakeReceipt: receipt }} />));
    expect(container.textContent).not.toContain("尚未确认");
    expect(container.textContent).not.toContain("执行失败");
    expect(container.querySelector('[role="timer"]')).toBeNull();
  } finally { await act(async () => root.unmount()); container.remove(); }
});
