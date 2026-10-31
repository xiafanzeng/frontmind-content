// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useContentWorkspaceHost } from "../client/host";
import type { ContentConversation } from "../client/host";

vi.mock("../client/ContentSubjectWorkspace", () => ({ default: () => {
  const state = useContentWorkspaceHost().useConversation();
  return <div data-active={state.activeConversation?.id ?? ""}>{String(state.hydrated)}<button type="button" onClick={()=>{void (state.deleteConversation as unknown as (id:string)=>Promise<void>)("saved-task").catch(()=>{});}}>删除测试聊天</button></div>;
} }));
import { ModuleWorkspace, type ContentBusinessClient } from "../client/runtime";

afterEach(() => { localStorage.clear(); document.body.innerHTML = ""; });
it("keeps the remembered task while loading and restores it after remount", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const key = "frontmind-content-active:synthetic-workspace";
  localStorage.setItem(key, "saved-task");
  const rows: ContentConversation[] = [{ id: "saved-task", title: "合成测试任务", purpose: "content_production", status: "completed", createdAt: 1, updatedAt: 1, messages: [] }];
  let finish!: (rows: ContentConversation[]) => void;
  const pending = new Promise<ContentConversation[]>(resolve => { finish = resolve; });
  const reject = vi.fn(async (): Promise<never> => { throw new Error("Unexpected write"); });
  const client = { list: vi.fn(() => pending), readSubjectWorkspace: reject, saveSubjectWorkspace: reject, save: reject, remove: reject, upload: reject, dispatch: reject, task: reject, stop: reject };
  const container = document.createElement("div"); document.body.append(container);
  const props = { context: { module: "content", workspace: { id: "synthetic-workspace", ownerUserId: 1 }, marketEdition: "cn", capabilities: [] }, client };
  let root = createRoot(container);
  await act(async () => { root.render(<ModuleWorkspace {...props} />); });
  expect(localStorage.getItem(key)).toBe("saved-task");
  await act(async () => { finish(rows); });
  expect(container.querySelector("[data-active]")?.getAttribute("data-active")).toBe("saved-task");
  await act(async () => root.unmount());
  root = createRoot(container);
  await act(async () => { root.render(<ModuleWorkspace {...props} />); });
  expect(container.querySelector("[data-active]")?.getAttribute("data-active")).toBe("saved-task");
  expect(reject).not.toHaveBeenCalled();
  await act(async () => root.unmount());
});

function readOnlyClient(list: ContentBusinessClient["list"]) {
  // 恢复过程只能读列表；任何写入、上传或任务派发都会使断言失败。
  const unexpectedWrite = vi.fn(async (): Promise<never> => { throw new Error("Unexpected write"); });
  const client: ContentBusinessClient = { list, readSubjectWorkspace: unexpectedWrite, saveSubjectWorkspace: unexpectedWrite, save: unexpectedWrite, remove: unexpectedWrite, upload: unexpectedWrite, dispatch: unexpectedWrite, task: unexpectedWrite, stop: unexpectedWrite };
  return { client, unexpectedWrite };
}

it("retries a failed initial read once while pending and restores the remembered task without writes", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const key = "frontmind-content-active:retry-workspace";
  localStorage.setItem(key, "saved-task");
  let finish!: (rows: ContentConversation[]) => void;
  const pending = new Promise<ContentConversation[]>(resolve => { finish = resolve; });
  const list = vi.fn<ContentBusinessClient["list"]>().mockRejectedValueOnce(new Error("网络暂时不可用")).mockReturnValueOnce(pending);
  const { client, unexpectedWrite } = readOnlyClient(list);
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ModuleWorkspace context={{ module: "content", workspace: { id: "retry-workspace", ownerUserId: 1 }, marketEdition: "cn", capabilities: [] }} client={client} />));
    expect(container.textContent).toContain("任务列表加载失败：网络暂时不可用");
    expect(localStorage.getItem(key)).toBe("saved-task");
    const retry = container.querySelector<HTMLButtonElement>("button")!;
    expect(retry.textContent).toBe("重试加载任务");
    await act(async () => { retry.click(); retry.click(); });
    expect(list).toHaveBeenCalledTimes(2);
    expect(retry.disabled).toBe(true);
    expect(retry.textContent).toBe("正在重试…");
    expect(localStorage.getItem(key)).toBe("saved-task");
    await act(async () => finish([{ id: "saved-task", title: "合成测试任务", purpose: "content_production", status: "completed", createdAt: 1, updatedAt: 1, messages: [] }]));
    expect(container.querySelector("[data-active]")?.getAttribute("data-active")).toBe("saved-task");
    expect(container.querySelector("[data-active]")?.textContent).toBe("true");
    expect(container.querySelector("[role=alert]")).toBeNull();
    expect(localStorage.getItem(key)).toBe("saved-task");
    expect(unexpectedWrite).not.toHaveBeenCalled();
  } finally { await act(async () => root.unmount()); container.remove(); }
});

it("allows another retry after a failed retry and initializes an empty task list", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const list = vi.fn<ContentBusinessClient["list"]>()
    .mockRejectedValueOnce(new Error(""))
    .mockRejectedValueOnce("非标准读取错误")
    .mockResolvedValueOnce([]);
  const { client, unexpectedWrite } = readOnlyClient(list);
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ModuleWorkspace context={{ module: "content", workspace: { id: "empty-retry-workspace", ownerUserId: 1 }, marketEdition: "cn", capabilities: [] }} client={client} />));
    expect(container.textContent).toContain("读取任务失败，请重试。");
    await act(async () => container.querySelector<HTMLButtonElement>("button")!.click());
    expect(container.textContent).toContain("读取任务失败，请重试。");
    expect(container.querySelector<HTMLButtonElement>("button")!.disabled).toBe(false);
    await act(async () => container.querySelector<HTMLButtonElement>("button")!.click());
    expect(container.querySelector("[data-active]")?.textContent).toBe("true");
    expect(container.querySelector("[data-active]")?.getAttribute("data-active")).toBe("");
    expect(container.querySelector("[role=alert]")).toBeNull();
    expect(list).toHaveBeenCalledTimes(3);
    expect(unexpectedWrite).not.toHaveBeenCalled();
  } finally { await act(async () => root.unmount()); container.remove(); }
});

it("ignores an old retry response after the workspace is unmounted", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const key = "frontmind-content-active:unmounted-retry-workspace";
  localStorage.setItem(key, "remembered-task");
  let finish!: (rows: ContentConversation[]) => void;
  const pending = new Promise<ContentConversation[]>(resolve => { finish = resolve; });
  const list = vi.fn<ContentBusinessClient["list"]>().mockRejectedValueOnce(new Error("读取失败")).mockReturnValueOnce(pending);
  const { client, unexpectedWrite } = readOnlyClient(list);
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(<ModuleWorkspace context={{ module: "content", workspace: { id: "unmounted-retry-workspace", ownerUserId: 1 }, marketEdition: "cn", capabilities: [] }} client={client} />));
  await act(async () => container.querySelector<HTMLButtonElement>("button")!.click());
  await act(async () => root.unmount());
  await act(async () => finish([]));
  expect(localStorage.getItem(key)).toBe("remembered-task");
  expect(container.textContent).toBe("");
  expect(unexpectedWrite).not.toHaveBeenCalled();
  container.remove();
});


it("awaits server deletion before changing the selected conversation", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  let finish!: () => void;
  const pending = new Promise<void>(resolve => { finish = resolve; });
  const rows: ContentConversation[] = [{ id: "saved-task", title: "待删除聊天", purpose: "content_production", status: "completed", createdAt: 1, updatedAt: 1, messages: [] }];
  const client: ContentBusinessClient = {
    list: vi.fn(async () => rows), readSubjectWorkspace: vi.fn(async () => ({schemaVersion:1 as const,revision:0,folders:[],bindings:{}})),
    saveSubjectWorkspace: vi.fn(async value => value), save: vi.fn(async value => value),
    remove: vi.fn(() => pending), upload: vi.fn(async () => ({fileId:"unused",filename:"unused"})),
    dispatch: vi.fn(async () => { throw new Error("Unexpected dispatch"); }), task: vi.fn(async () => { throw new Error("Unexpected task"); }), stop: vi.fn(async () => {}),
  };
  localStorage.setItem("frontmind-content-active:delete-await","saved-task");
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ModuleWorkspace client={client} context={{module:"content",workspace:{id:"delete-await",ownerUserId:1},marketEdition:"test",capabilities:[]}} />));
    const button = container.querySelector<HTMLButtonElement>("button")!;
    await act(async () => { button.click(); await Promise.resolve(); });
    expect(client.remove).toHaveBeenCalledWith("saved-task");
    expect(container.querySelector("[data-active]")?.getAttribute("data-active")).toBe("saved-task");
    await act(async () => finish());
    expect(container.querySelector("[data-active]")?.getAttribute("data-active")).toBe("");
  } finally { await act(async () => root.unmount()); container.remove(); }
});

it("keeps the conversation selected and surfaces the server message when deletion is protected", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const rows: ContentConversation[] = [{ id: "saved-task", title: "受保护聊天", purpose: "content_production", status: "completed", createdAt: 1, updatedAt: 1, messages: [] }];
  const client: ContentBusinessClient = {
    list: vi.fn(async () => rows), readSubjectWorkspace: vi.fn(async () => ({schemaVersion:1 as const,revision:0,folders:[],bindings:{}})),
    saveSubjectWorkspace: vi.fn(async value => value), save: vi.fn(async value => value),
    remove: vi.fn(async () => { throw new Error("该聊天是已确认资料包版本的来源，不能删除。"); }),
    upload: vi.fn(async () => ({fileId:"unused",filename:"unused"})),
    dispatch: vi.fn(async () => { throw new Error("Unexpected dispatch"); }), task: vi.fn(async () => { throw new Error("Unexpected task"); }), stop: vi.fn(async () => {}),
  };
  localStorage.setItem("frontmind-content-active:delete-protected","saved-task");
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ModuleWorkspace client={client} context={{module:"content",workspace:{id:"delete-protected",ownerUserId:1},marketEdition:"test",capabilities:[]}} />));
    await act(async () => container.querySelector<HTMLButtonElement>("button")!.click());
    expect(container.querySelector("[data-active]")?.getAttribute("data-active")).toBe("saved-task");
    expect(container.textContent).toContain("该聊天是已确认资料包版本的来源，不能删除。");
  } finally { await act(async () => root.unmount()); container.remove(); }
});
