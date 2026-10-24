// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
const probe = vi.hoisted(() => ({ clients: [] as unknown[], live: { name: "normal-client" }, verified: { name: "intake-client" }, factory: vi.fn() }));
vi.mock("@frontmind/module-ui/dashboard/ModuleShell", () => ({ ModuleShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock("../../module/client/runtime", () => ({ liveContentClient: probe.live, ModuleWorkspace: ({ client }: { client: unknown }) => { probe.clients.push(client); return <div>工作区已连接</div>; } }));
vi.mock("../../module/client/intake-verification-client", async original => ({ ...await original<typeof import("../../module/client/intake-verification-client")>(), createIntakeVerificationClient: probe.factory }));
vi.mock("../preview", () => ({ previewContentClient: () => ({ name: "preview-client" }) }));
import App from "../App";
let container: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  probe.clients.length = 0; probe.factory.mockReset().mockResolvedValue(probe.verified);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ module: "content", workspace: { id: "workspace", ownerUserId: 1 }, marketEdition: "cn", capabilities: ["content"] }) }));
  container = document.createElement("div"); document.body.append(container); root = createRoot(container);
});
afterEach(async () => { await act(async () => root.unmount()); container.remove(); history.replaceState(null, "", "/"); vi.unstubAllGlobals(); });
it("默认页面保留同一个正常客户端，完全不进入收件验收工厂", async () => {
  history.replaceState(null, "", "/"); await act(async () => root.render(<App />));
  expect(probe.clients.at(-1)).toBe(probe.live); expect(probe.factory).not.toHaveBeenCalled();
});
it("显式验收在能力验证完成前不挂载任何工作区", async () => {
  history.replaceState(null, "", "/?verify=intake");
  let finish!: (value: unknown) => void; probe.factory.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  await act(async () => root.render(<App />)); expect(probe.clients).toHaveLength(0);
  await act(async () => finish(probe.verified)); expect(probe.clients.at(-1)).toBe(probe.verified);
});
it("没有正式收件能力时只显示错误，绝不挂载默认生成客户端", async () => {
  history.replaceState(null, "", "/?verify=intake"); probe.factory.mockRejectedValue(new Error("当前没有正式收件能力"));
  await act(async () => root.render(<App />));
  expect(container.querySelector('[role="alert"]')?.textContent).toBe("当前没有正式收件能力"); expect(probe.clients).toHaveLength(0);
});
it("规范化旧页面地址时保留验收参数，刷新仍为验收入口", async () => {
  history.replaceState(null, "", "/old-page?verify=intake"); await act(async () => root.render(<App />));
  expect(location.pathname).toBe("/"); expect(location.search).toBe("?verify=intake"); expect(probe.clients.at(-1)).toBe(probe.verified);
});
it("演示页不能被当成真实收件入口", async () => {
  history.replaceState(null, "", "/?verify=intake"); await act(async () => root.render(<App preview />));
  expect(container.querySelector('[role="alert"]')?.textContent).toContain("演示页不能验证真实收件"); expect(probe.clients).toHaveLength(0); expect(fetch).not.toHaveBeenCalled();
});
