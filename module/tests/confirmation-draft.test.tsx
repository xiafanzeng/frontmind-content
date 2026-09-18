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
