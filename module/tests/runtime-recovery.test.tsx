// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useContentWorkspaceHost } from "../client/host";
import type { ContentConversation } from "../client/host";

vi.mock("../client/ContentProductionWorkspace", () => ({ default: () => {
  const state = useContentWorkspaceHost().useConversation();
  return <div data-active={state.activeConversation?.id}>{String(state.hydrated)}</div>;
} }));
import { ModuleWorkspace } from "../client/runtime";

afterEach(() => { localStorage.clear(); document.body.innerHTML = ""; });
it("keeps the remembered task while loading and restores it after remount", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const key = "frontmind-content-active:synthetic-workspace";
  localStorage.setItem(key, "saved-task");
  const rows: ContentConversation[] = [{ id: "saved-task", title: "合成测试任务", purpose: "content_production", status: "completed", createdAt: 1, updatedAt: 1, messages: [] }];
  let finish!: (rows: ContentConversation[]) => void;
  const pending = new Promise<ContentConversation[]>(resolve => { finish = resolve; });
  const reject = vi.fn(async (): Promise<never> => { throw new Error("Unexpected write"); });
  const client = { list: vi.fn(() => pending), save: reject, remove: reject, upload: reject, dispatch: reject, task: reject, stop: reject };
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
