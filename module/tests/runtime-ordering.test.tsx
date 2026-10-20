// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import { ModuleWorkspace, type ContentBusinessClient } from "../client/runtime";
import { useContentWorkspaceHost, type ContentConversation, type ContentConversationApi, type TaskResponse } from "../client/host";

type TestRuntime = ContentConversationApi & {
  refresh(): Promise<void>;
  sendMessage(prompt: string): Promise<boolean>;
};
let runtime: TestRuntime;
vi.mock("../client/ContentProductionWorkspace", () => ({
  default: function RuntimeProbe() {
    runtime = useContentWorkspaceHost().useConversation() as TestRuntime;
    return <output>{JSON.stringify(runtime.state.conversations)}</output>;
  },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
const initial: ContentConversation = {
  id: "conversation-1", title: "合成排序测试", taskId: "task-1", status: "awaiting_input",
  messages: [{ id: "plan", role: "assistant", content: "等待方案确认", timestamp: 1 }],
  createdAt: 1, updatedAt: 1,
};

async function mount() {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  const list = vi.fn<ContentBusinessClient["list"]>().mockResolvedValue([structuredClone(initial)]);
  const dispatch = deferred<TaskResponse>();
  const client: ContentBusinessClient = {
    list, save: vi.fn(async value => structuredClone(value)), remove: vi.fn(async () => {}),
    upload: vi.fn(), dispatch: vi.fn(() => dispatch.promise),
    // Hold the automatic task probe. Each test controls list reads explicitly.
    task: vi.fn(() => new Promise<TaskResponse>(() => {})), stop: vi.fn(async () => {}),
  };
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(<ModuleWorkspace client={client} context={{ module: "content", workspace: { id: "ordering-test", ownerUserId: 1 }, marketEdition: "test", capabilities: [] }} />));
  await act(async () => runtime.setActive(initial.id));
  return { client, list, dispatch, cleanup: async () => {
    await act(async () => root.unmount()); container.remove(); localStorage.clear();
  } };
}

it("keeps the newer list response when an older read finishes later, even with equal timestamps", async () => {
  const view = await mount();
  const older = deferred<ContentConversation[]>(), newer = deferred<ContentConversation[]>();
  view.list.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
  let first!: Promise<void>, second!: Promise<void>;
  try {
    await act(async () => { first = runtime.refresh(); second = runtime.refresh(); });
    const latest = { ...initial, messages: [...initial.messages, { id: "tool-result", role: "assistant" as const, content: "来源核验完成", timestamp: 2 }] };
    await act(async () => { newer.resolve([latest]); await second; });
    await act(async () => { older.resolve([initial]); await first; });
    expect(runtime.activeConversation?.messages.at(-1)?.id).toBe("tool-result");
    expect(runtime.activeConversation?.updatedAt).toBe(initial.updatedAt);
  } finally { await view.cleanup(); }
});

it("does not let a pre-submit read remove the pending message during dispatch", async () => {
  const view = await mount();
  const older = deferred<ContentConversation[]>(); view.list.mockReturnValueOnce(older.promise);
  let refresh!: Promise<void>, send!: Promise<boolean>;
  try {
    await act(async () => { refresh = runtime.refresh(); send = runtime.sendMessage("确认方案"); });
    await act(async () => { older.resolve([initial]); await refresh; });
    expect(runtime.activeConversation?.messages.at(-1)?.content).toBe("确认方案");
    expect(runtime.activeConversation?.messages.at(-1)?.generalChatDispatch).toBeDefined();
    await act(async () => { view.dispatch.resolve({ id: "task-1", purpose: "content_production", status: "running" }); await send; });
    expect(runtime.activeConversation?.status).toBe("running");
    expect(runtime.activeConversation?.messages.at(-1)?.generalChatDispatch).toBeUndefined();
  } finally { await view.cleanup(); }
});

it.each(["pending", "accepted"])("ignores reads started during dispatch that arrive while %s, then resumes fresh reads", async state => {
  const view = await mount();
  const older = deferred<ContentConversation[]>(); view.list.mockReturnValueOnce(older.promise);
  let refresh!: Promise<void>, send!: Promise<boolean>;
  try {
    await act(async () => { send = runtime.sendMessage("确认方案"); });
    await act(async () => { refresh = runtime.refresh(); });
    if (state === "pending") {
      await act(async () => { older.resolve([initial]); await refresh; });
      expect(runtime.activeConversation?.messages.at(-1)?.content).toBe("确认方案");
      expect(runtime.activeConversation?.messages.at(-1)?.generalChatDispatch).toBeDefined();
    }
    await act(async () => { view.dispatch.resolve({ id: "task-1", purpose: "content_production", status: "running" }); await send; });
    if (state === "accepted") await act(async () => { older.resolve([initial]); await refresh; });
    expect(runtime.activeConversation?.status).toBe("running");
    expect(runtime.activeConversation?.messages.at(-1)?.content).toBe("确认方案");
    expect(runtime.activeConversation?.messages.at(-1)?.generalChatDispatch).toBeUndefined();
    const completed = { ...runtime.activeConversation!, status: "completed" };
    view.list.mockResolvedValueOnce([completed]);
    await act(async () => runtime.refresh());
    expect(runtime.activeConversation?.status).toBe("completed");
  } finally { await view.cleanup(); }
});

it("does not restore a removed conversation from an earlier list read", async () => {
  const view = await mount();
  const older = deferred<ContentConversation[]>(); view.list.mockReturnValueOnce(older.promise);
  let refresh!: Promise<void>;
  try {
    await act(async () => { refresh = runtime.refresh(); runtime.deleteConversation(initial.id); });
    expect(runtime.state.conversations).toHaveLength(0);
    await act(async () => { older.resolve([initial]); await refresh; });
    expect(runtime.state.conversations).toHaveLength(0);
  } finally { await view.cleanup(); }
});
