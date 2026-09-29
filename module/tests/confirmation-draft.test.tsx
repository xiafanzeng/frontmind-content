// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import Confirmation from "../client/ContentProductionConfirmation";
import { ContentWorkspaceHostProvider, type ContentWorkspaceHost } from "../client/host";
import type { ContentProductionDto } from "../contracts/content-production";

it("registers unfinished confirmation input with the actual module host", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const guard = vi.fn();
  const host = { useWorkspaceDraftGuard: guard } as unknown as ContentWorkspaceHost;
  const progress = {
    confirmation: "awaiting_blueprint_confirmation", availableActions: ["confirm_blueprint"],
    runnerRevision: 7, choices: [],
  } as unknown as ContentProductionDto;
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ContentWorkspaceHostProvider value={host}><Confirmation progress={progress} busy={false} onAction={async () => true} onNotice={() => {}} /></ContentWorkspaceHostProvider>));
    expect(guard).toHaveBeenLastCalledWith({ dirty: false, label: "内容阶段确认" });
    const input = container.querySelector("textarea")!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(input, "保留这份未提交的修改");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(guard).toHaveBeenLastCalledWith({ dirty: true, label: "内容阶段确认" });
  } finally { await act(async () => root.unmount()); container.remove(); }
});

it("submits the selected question with the displayed revision and preserves a rejected draft", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const host = { useWorkspaceDraftGuard: vi.fn() } as unknown as ContentWorkspaceHost;
  const progress = { confirmation: "awaiting_question_selection", availableActions: ["choose_question"], runnerRevision: 12, choices: ["1. 合成问题"] } as unknown as ContentProductionDto;
  const action = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  const notice = vi.fn();
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ContentWorkspaceHostProvider value={host}><Confirmation progress={progress} busy={false} onAction={action} onNotice={notice} /></ContentWorkspaceHostProvider>));
    const input = container.querySelector<HTMLInputElement>('input[aria-label="本次优化的问题"]')!;
    const button = [...container.querySelectorAll("button")].find(item => item.textContent === "确认选择的问题")!;
    await act(async () => button.click());
    expect(action).not.toHaveBeenCalled();
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "1");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await act(async () => button.click());
    expect(action).toHaveBeenLastCalledWith(expect.any(String), [], { kind: "choose_question", selection: "1", revision: 12 });
    expect(input.value).toBe("1");
    expect(notice).toHaveBeenLastCalledWith("本轮提交未确认成功，请查看任务回复。");
    await act(async () => button.click());
    expect(input.value).toBe("");
  } finally { await act(async () => root.unmount()); container.remove(); }
});
