// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ContentBusinessClient } from "../client/runtime";
const probes = vi.hoisted(() => ({ subject: vi.fn(), legacy: vi.fn() }));
vi.mock("../client/ContentSubjectWorkspace", () => ({ default: () => { probes.subject(); return <div>新版主体入口</div>; } }));
vi.mock("../client/ContentProductionWorkspace", () => ({ default: () => { probes.legacy(); return <div>旧工作区不应出现</div>; } }));
import { ModuleWorkspace } from "../client/runtime";
let container: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => { vi.clearAllMocks(); (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true; container = document.createElement("div"); document.body.append(container); root = createRoot(container); });
afterEach(async () => { await act(async () => root.unmount()); container.remove(); localStorage.clear(); });
const context = { module: "content", workspace: { id: "capability-test", ownerUserId: 1 }, marketEdition: "cn", capabilities: [] };
function fixture() {
  const blocked = vi.fn(async (): Promise<never> => { throw new Error("不能执行或写入"); });
  const client: ContentBusinessClient = { list: vi.fn(async () => []), save: blocked, remove: blocked, upload: blocked, dispatch: blocked, task: blocked, stop: blocked,
    readSubjectWorkspace: async () => ({ schemaVersion: 1, revision: 0, folders: [], bindings: {} }), saveSubjectWorkspace: blocked };
  return { client, blocked };
}
it.each(["read", "save", "both"])("缺少%s主体接口时只报错，不挂载旧UI或启动任务读取", async missing => {
  const { client, blocked } = fixture();
  if (missing !== "save") client.readSubjectWorkspace = undefined;
  if (missing !== "read") client.saveSubjectWorkspace = undefined;
  await act(async () => root.render(<ModuleWorkspace context={context} client={client} />));
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("缺少主体资料库接口");
  expect(probes.legacy).not.toHaveBeenCalled(); expect(probes.subject).not.toHaveBeenCalled();
  expect(client.list).not.toHaveBeenCalled(); expect(blocked).not.toHaveBeenCalled();
});
it("完整能力只挂载新主体入口，保持正常客户端与收件验收行为", async () => {
  const { client, blocked } = fixture();
  await act(async () => root.render(<ModuleWorkspace context={context} client={client} />));
  expect(container.textContent).toContain("新版主体入口"); expect(probes.legacy).not.toHaveBeenCalled();
  expect(client.list).toHaveBeenCalledOnce(); expect(blocked).not.toHaveBeenCalled();
});
