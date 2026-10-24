// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import Workspace from "../client/ContentProductionWorkspace";
import { ContentWorkspaceHostProvider, type ContentWorkspaceHost, type TaskResponse } from "../client/host";

it.each(["running", "completed"])("shows market research failure when the outer agent reports %s", async (status) => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const task: TaskResponse = { id: "synthetic-task", purpose: "content_production", status, contentProduction: {
    mode: "new_reference_pack", enterpriseName: "合成企业", workflowVersion: "4.13.2-v16.2",
    workflowStatus: "running_positioning_market_research", currentStage: "positioning_research", jobKind: "reference_pack",
    runnerRevision: 7, pauseTitle: null, choices: [], productionStep: null, confirmation: null, progressPosition: 3,
    completedConfirmations: [], availableActions: [], knowledgeBase: null, source: "runner_job_state",
    executionFailure: { action: "positioning_market_research", code: "tool_call_source_mismatch", attemptId: "synthetic-attempt" },
  } };
  const conversation = { id: "synthetic-conversation", taskId: task.id, title: "合成企业", purpose: "content_production" as const,
    status, messages: [], createdAt: 1, updatedAt: 1 };
  const unused = vi.fn();
  const host: ContentWorkspaceHost = {
    ConversationPurposeProvider: ({ children }) => <>{children}</>,
    useConversation: () => ({ state: { conversations: [conversation] }, activeConversation: conversation, hydrated: true,
      createConversation: () => "unused", setActive: unused, deleteConversation: unused }),
    useSendMessage: () => ({ sendMessage: vi.fn() }),
    retrieveTask: vi.fn(async () => task),
    captureWorkspaceRestOperation: (signal) => ({ signal: signal ?? new AbortController().signal, assertActive: unused, fetch }),
    useWorkspaceDraftGuard: unused, requestWorkspaceNavigation: unused,
    Home: () => null, FilePreview: () => null, WorkbenchTaskToolbar: () => null,
    AgentWorkbenchShell: ({ main, auxiliary, status }) => <div><span data-testid="shell-status">{status}</span>{main}{auxiliary}</div>,
    BusinessWorkspaceInspector: () => null,
  };
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  try {
    await act(async () => root.render(<ContentWorkspaceHostProvider value={host}><Workspace workbench /></ContentWorkspaceHostProvider>));
    expect(container.querySelector('[data-testid="shell-status"]')?.textContent).toBe("本轮执行失败");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("市场研究执行失败");
    expect(container.querySelector('[role="alert"]')?.textContent).toContain("tool_call_source_mismatch");
    expect(container.querySelector('[data-testid="shell-status"]')?.textContent).not.toContain("正在执行");
    expect(container.querySelector('.cp-progress > summary')?.textContent).toContain("本轮执行失败");
    expect(container.querySelector('.cp-progress > summary')?.textContent).not.toContain("正在处理");
    expect(container.querySelector('.cp-composer-confirmation')).toBeNull();
    expect([...container.querySelectorAll('button')].some(button => /^(?:确认提交|继续制作品牌长文|继续问题与监控数据)$/u.test(button.textContent ?? ""))).toBe(false);
    expect(host.retrieveTask).toHaveBeenCalledWith("synthetic-task", expect.any(Object));
  } finally { await act(async () => root.unmount()); container.remove(); }
});
