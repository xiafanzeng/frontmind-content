// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import Workspace from "../client/ContentProductionWorkspace";
import { ContentWorkspaceHostProvider, type ContentConversation, type ContentWorkspaceHost, type TaskResponse } from "../client/host";
import type { ContentProductionDto } from "../contracts/content-production";

const progress: ContentProductionDto = {
  mode: "single_article", enterpriseName: "合成测试品牌", workflowVersion: "4.13.2",
  workflowStatus: "awaiting_blueprint_confirmation", currentStage: "awaiting_blueprint_confirmation", jobKind: "article",
  runnerRevision: 7, pauseTitle: "确认写作方案", choices: [], productionStep: null,
  confirmation: "awaiting_blueprint_confirmation", progressPosition: 18, completedConfirmations: [],
  availableActions: ["confirm_blueprint"], knowledgeBase: null, source: "runner_job_state",
};

async function mount(options: { status?: string; progress?: ContentProductionDto; send?: () => Promise<boolean> } = {}) {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  const conversation: ContentConversation = { id: "conversation-1", taskId: "task-1", title: "合成测试任务", status: options.status ?? "awaiting_input", messages: [], createdAt: 1, updatedAt: 1 };
  let task: TaskResponse = { id: "task-1", purpose: "content_production", status: conversation.status, contentProduction: options.progress ?? progress };
  const send = vi.fn(options.send ?? (async () => true));
  const retrieveTask = vi.fn(async () => structuredClone(task));
  const host: ContentWorkspaceHost = {
    connections: { publishedKnowledge: false },
    ConversationPurposeProvider: ({ children }) => <>{children}</>,
    useConversation: () => ({ state: { conversations: [conversation] }, activeConversation: conversation, hydrated: true, createConversation: () => "", setActive() {}, deleteConversation() {} }),
    useSendMessage: () => ({ sendMessage: send }), retrieveTask,
    captureWorkspaceRestOperation: (signal = new AbortController().signal) => ({ signal, assertActive: () => signal.throwIfAborted(), fetch }),
    useWorkspaceDraftGuard() {}, requestWorkspaceNavigation: action => action(),
    Home: ({ conversationFooter }) => <div>{conversationFooter}</div>, FilePreview: () => null,
    WorkbenchTaskToolbar: () => null, BusinessWorkspaceInspector: () => null,
    AgentWorkbenchShell: ({ main, auxiliary }) => <>{main}{auxiliary}</>,
  };
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(<ContentWorkspaceHostProvider value={host}><Workspace workbench /></ContentWorkspaceHostProvider>));
  return { container, send, retrieveTask, setTask: (value: TaskResponse) => { task = value; },
    updateConversation: async (changes: Partial<ContentConversation>) => {
      Object.assign(conversation, changes);
      await act(async () => root.render(<ContentWorkspaceHostProvider value={host}><Workspace workbench /></ContentWorkspaceHostProvider>));
    },
    cleanup: async () => { await act(async () => root.unmount()); container.remove(); } };
}
function confirmButton(container: HTMLElement) {
  return [...container.querySelectorAll("button")].find(button => button.textContent === "确认写作方案，开始正文")!;
}

it("consumes an accepted confirmation, refreshes state, and allows a new revision", async () => {
  const view = await mount();
  try {
    expect(view.container.querySelector(".cp-inline-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-inline-confirmation-heading")?.textContent).toContain("当前需要确认");
    await act(async () => confirmButton(view.container).click());
    expect(view.send).toHaveBeenCalledWith(expect.any(String), [], { contentProductionAction: { kind: "confirm_blueprint", revision: 7 } });
    expect(view.retrieveTask).toHaveBeenCalledTimes(2);
    // A stale snapshot of the accepted revision must not reopen its controls.
    expect(view.container.querySelector(".cp-inline-confirmation")).toBeNull();
    view.setTask({ id: "task-1", purpose: "content_production", status: "awaiting_input", contentProduction: { ...progress, runnerRevision: 8 } });
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新制作阶段"]')!.click());
    expect(view.container.querySelector(".cp-inline-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-inline-confirmation-heading")?.textContent).toContain("当前需要确认");
  } finally { await view.cleanup(); }
});

it("keeps a rejected confirmation available for retry", async () => {
  const view = await mount({ send: async () => false });
  try {
    await act(async () => confirmButton(view.container).click());
    expect(view.container.querySelector(".cp-inline-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-inline-confirmation-heading")?.textContent).toContain("当前需要确认");
    expect(confirmButton(view.container).disabled).toBe(false);
    expect(view.container.textContent).toContain("本轮提交尚未确认成功");
    expect(view.retrieveTask).toHaveBeenCalledTimes(1);
  } finally { await view.cleanup(); }
});

it("reopens the same confirmation when an accepted asynchronous command fails", async () => {
  const view = await mount();
  try {
    await act(async () => confirmButton(view.container).click());
    expect(view.container.querySelector(".cp-inline-confirmation")).toBeNull();
    view.setTask({ id: "task-1", purpose: "content_production", status: "error", contentProduction: progress });
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新制作阶段"]')!.click());
    expect(view.container.querySelector(".cp-inline-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-inline-confirmation-heading")?.textContent).toContain("当前需要确认");
    expect(confirmButton(view.container).disabled).toBe(false);
  } finally { await view.cleanup(); }
});

it("advances the stage when polling updates a running conversation without a new message", async () => {
  const view = await mount({ status: "running", progress });
  try {
    expect(view.container.querySelector(".cp-inline-confirmation-heading strong")?.textContent).toContain("确认写作方案");
    expect(view.container.querySelector(".cp-six-progress-status")?.textContent).toContain("确认文章写作方案");
    expect(view.container.querySelector(".cp-six-progress-status")?.textContent).toContain("等待：确认写作方案");
    view.setTask({ id: "task-1", purpose: "content_production", status: "running", contentProduction: {
      ...progress, workflowStatus: "running_article_production", currentStage: "article_production",
      confirmation: null, availableActions: [], progressPosition: 19, productionStep: "draft",
    } });
    await view.updateConversation({ updatedAt: 2 });
    expect(view.container.querySelector('[aria-current="step"]')?.textContent).toContain("正文与最终交付");
    expect(view.container.querySelector(".cp-inline-confirmation")).toBeNull();
  } finally { await view.cleanup(); }
});

it.each([
  { status: "running", progress },
  { status: "completed", progress: { ...progress, confirmation: null, availableActions: [] } },
])("does not leave an empty or stale confirmation disclosure when status is $status", async options => {
  const view = await mount(options);
  try { expect(view.container.querySelector(".cp-inline-confirmation")).toBeNull(); }
  finally { await view.cleanup(); }
});
