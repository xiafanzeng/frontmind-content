// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { expect, it, vi } from "vitest";
import Workspace from "../client/ContentProductionWorkspace";
import { ContentWorkspaceHostProvider, type ContentConversation, type ContentWorkspaceHost, type ContentHomeProps, type TaskResponse } from "../client/host";
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
  const conversation: ContentConversation = { id: "conversation-1", taskId: "task-1", title: "合成测试任务", status: options.status ?? "awaiting_input", messages: [{id:"history-0",role:"user",content:"企业材料",contentPhase:0,timestamp:1}], createdAt: 1, updatedAt: 1 };
  let task: TaskResponse = { id: "task-1", purpose: "content_production", status: conversation.status, contentProduction: options.progress ?? progress };
  const send = vi.fn(options.send ?? (async () => true));
  const retrieveTask = vi.fn(async () => structuredClone(task));
  let homeProps:ContentHomeProps;
  const host: ContentWorkspaceHost = {
    connections: { publishedKnowledge: false },
    ConversationPurposeProvider: ({ children }) => <>{children}</>,
    useConversation: () => ({ state: { conversations: [conversation] }, activeConversation: conversation, hydrated: true, createConversation: () => "", setActive() {}, deleteConversation() {} }),
    useSendMessage: () => ({ sendMessage: send }), retrieveTask,
    captureWorkspaceRestOperation: (signal = new AbortController().signal) => ({ signal, assertActive: () => signal.throwIfAborted(), fetch }),
    useWorkspaceDraftGuard() {}, requestWorkspaceNavigation: action => action(),
    Home: props => {homeProps=props;return <div>{props.conversationFooter}</div>;}, FilePreview: () => null,
    WorkbenchTaskToolbar: () => null, BusinessWorkspaceInspector: () => null,
    AgentWorkbenchShell: ({ main, auxiliary }) => <>{main}{auxiliary}</>,
  };
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  await act(async () => root.render(<ContentWorkspaceHostProvider value={host}><Workspace workbench /></ContentWorkspaceHostProvider>));
  return { container, send, retrieveTask, navigation:()=>homeProps.transcriptNavigation,home:()=>homeProps, setTask: (value: TaskResponse) => { task = value; },
    updateConversation: async (changes: Partial<ContentConversation>) => {
      Object.assign(conversation, changes);
      await act(async () => root.render(<ContentWorkspaceHostProvider value={host}><Workspace workbench /></ContentWorkspaceHostProvider>));
    },
    cleanup: async () => { await act(async () => root.unmount()); container.remove(); } };
}
function confirmButton(container: HTMLElement) {
  return [...container.querySelectorAll("button")].find(button => button.textContent === "确认提交")!;
}

it("consumes an accepted confirmation, refreshes state, and allows a new revision", async () => {
  const view = await mount();
  try {
    expect(view.container.querySelector(".cp-composer-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-composer-confirmation-heading")?.textContent).toContain("本轮问题");
    await act(async()=>{void view.home().onComposerSubmit!("确认写作方案",[]);});
    await act(async () => confirmButton(view.container).click());
    expect(view.send).toHaveBeenCalledWith(expect.any(String), [], { contentProductionAction: { kind: "confirm_blueprint", revision: 7 }, contentWorkflowPosition:18 });
    expect(view.retrieveTask).toHaveBeenCalledTimes(2);
    // A stale snapshot of the accepted revision must not reopen its controls.
    expect(view.container.querySelector(".cp-composer-confirmation")).toBeNull();
    view.setTask({ id: "task-1", purpose: "content_production", status: "awaiting_input", contentProduction: { ...progress, runnerRevision: 8 } });
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新制作阶段"]')!.click());
    expect(view.container.querySelector(".cp-composer-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-composer-confirmation-heading")?.textContent).toContain("本轮问题");
  } finally { await view.cleanup(); }
});

it("keeps a rejected confirmation available for retry", async () => {
  const view = await mount({ send: async () => false });
  try {
    await act(async()=>{void view.home().onComposerSubmit!("确认写作方案",[]);});
    await act(async () => confirmButton(view.container).click());
    expect(view.container.querySelector(".cp-composer-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-composer-confirmation-heading")?.textContent).toContain("待提交");
    expect(view.container.querySelector(".cp-composer-confirmation-text")?.textContent).toBe("确认写作方案");
    expect(confirmButton(view.container).disabled).toBe(false);
    expect(view.container.textContent).toContain("本轮提交尚未确认成功");
    expect(view.retrieveTask).toHaveBeenCalledTimes(1);
  } finally { await view.cleanup(); }
});

it("reopens the same confirmation when an accepted asynchronous command fails", async () => {
  const view = await mount();
  try {
    await act(async()=>{void view.home().onComposerSubmit!("确认写作方案",[]);});
    await act(async () => confirmButton(view.container).click());
    expect(view.container.querySelector(".cp-composer-confirmation")).toBeNull();
    view.setTask({ id: "task-1", purpose: "content_production", status: "error", contentProduction: progress });
    await act(async () => view.container.querySelector<HTMLButtonElement>('[aria-label="刷新制作阶段"]')!.click());
    expect(view.container.querySelector(".cp-composer-confirmation")).not.toBeNull();
    expect(view.container.querySelector(".cp-composer-confirmation-heading")?.textContent).toContain("本轮问题");
    // 已接受的旧输入不应自动重新发送；恢复本轮提问后，由底部输入再次建卡。
    expect(confirmButton(view.container)).toBeUndefined();
    await act(async()=>{void view.home().onComposerSubmit!("确认写作方案",[]);});
    expect(confirmButton(view.container).disabled).toBe(false);
    await act(async()=>confirmButton(view.container).click());
    expect(view.send).toHaveBeenCalledTimes(2);
  } finally { await view.cleanup(); }
});

it("advances the stage when polling updates a running conversation without a new message", async () => {
  const view = await mount({ status: "running", progress });
  try {
    // confirmationView is gated off while the task status is running (baseline behavior);
    // 当前节点只在右侧统一泳道中保留，不占用对话区。
    expect(view.container.querySelector(".cp-results .cp-lane")?.textContent).toContain("确认文章写作方案");
    expect(view.container.querySelector(".cp-results .cp-lane")?.textContent).toContain("确认文章写作方案");
    view.setTask({ id: "task-1", purpose: "content_production", status: "running", contentProduction: {
      ...progress, workflowStatus: "running_article_production", currentStage: "article_production",
      confirmation: null, availableActions: [], progressPosition: 19, productionStep: "draft",
    } });
    await view.updateConversation({ updatedAt: 2 });
    expect(view.container.querySelector('[aria-current="step"]')?.textContent).toContain("正文与最终交付");
    expect(view.container.querySelector(".cp-composer-confirmation")).toBeNull();
  } finally { await view.cleanup(); }
});

it.each([
  { status: "running", progress },
  { status: "completed", progress: { ...progress, confirmation: null, availableActions: [] } },
])("does not leave an empty or stale confirmation disclosure when status is $status", async options => {
  const view = await mount(options);
  try { expect(view.container.querySelector(".cp-composer-confirmation")).toBeNull(); }
  finally { await view.cleanup(); }
});


it("右侧只保留当前任务的泳道，不显示历史确认计数", async () => {
  const view = await mount({ progress: { ...progress, completedConfirmations: ["awaiting_core_positioning_confirmation"] } });
  try {
    expect(view.container.querySelector(".cp-dialogue .cp-six-progress")).toBeNull();
    expect(view.container.querySelector(".cp-dialogue .cp-lane")).toBeNull();
    expect(view.container.querySelectorAll(".cp-results .cp-lane")).toHaveLength(1);
    expect(view.container.querySelectorAll(".cp-results .cp-lane > li")).toHaveLength(7);
    expect(view.container.querySelector(".cp-results .cp-lane [aria-current=step]")?.textContent).toContain("确认文章写作方案");
    expect(view.container.textContent).not.toContain("已完成的确认节点");
    expect(view.container.querySelector(".cp-dialogue .cp-confirmed-context")).toBeNull();
  } finally { await view.cleanup(); }
});

const p0Titles=["选择品牌资料包","制作品牌深度文章","选择例文","确认品牌文章写作方案","正文与编辑","交付品牌文章与资料包"];
function laneTitles(container:HTMLElement){return [...container.querySelectorAll(".cp-lane > li strong")].map(node=>node.textContent);}

it("P0 泳道保留线上截图的六个节点和原文说明",async()=>{
  const view=await mount({progress:{...progress,mode:"p0",jobKind:"p0",workflowStatus:"awaiting_p0_example_confirmation",currentStage:"p0_examples",confirmation:"awaiting_p0_example_confirmation",availableActions:["choose_p0_examples"],progressPosition:9}});
  try{
    expect(laneTitles(view.container)).toEqual(p0Titles);
    const details=[...view.container.querySelectorAll(".cp-lane > li")].map(node=>node.querySelector("p")?.textContent);
    expect(details).toEqual(["明确使用已有资料包或先创建新资料包","使用已确认的定位与比较范围","选择例文文风或默认写作规范","确认结构、材料与已有文章的编辑方案","完成品牌文章与候选标题","正文文档、网页和新版品牌资料包"]);
    expect(view.container.querySelector('[aria-current="step"] strong')?.textContent).toBe("选择例文");
    expect(view.container.querySelectorAll(".cp-lane button")).toHaveLength(0);
  }finally{await view.cleanup();}
});

it("品牌资料包任务保持自身五个阶段",async()=>{
  const view=await mount({progress:{...progress,mode:"new_reference_pack",jobKind:"reference_pack",workflowStatus:"awaiting_core_positioning_confirmation",currentStage:"positioning",confirmation:"awaiting_core_positioning_confirmation",availableActions:["confirm_core_positioning"],progressPosition:6}});
  try{
    expect(laneTitles(view.container)).toEqual(["企业资料","市场研究","确认比较对象","确认核心定位","交付品牌资料包"]);
    expect(view.container.querySelector('[aria-current="step"] strong')?.textContent).toBe("确认核心定位");
  }finally{await view.cleanup();}
});

it("原会话从资料包接续 P0 后，按当前 jobKind 展示 P0 六阶段",async()=>{
  const view=await mount({progress:{...progress,mode:"new_reference_pack",jobKind:"p0",workflowVersion:"4.13.2-v16.8-app1",workflowStatus:"awaiting_p0_route",currentStage:"p0_route",confirmation:"awaiting_p0_route",availableActions:["choose_p0_route"],progressPosition:8}});
  try{
    expect(laneTitles(view.container)).toEqual(p0Titles);
    expect(view.container.querySelector('[aria-current="step"] strong')?.textContent).toBe("制作品牌深度文章");
    expect(view.send).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it("统一底部输入先整理卡片，泳道回看不提交，返回修改保留原草稿", async () => {
  const view=await mount();
  try {
    expect(view.container.querySelectorAll(".cp-lane button")).toHaveLength(0);
    expect(view.container.querySelector(".cp-results .cp-composer-confirmation")).toBeNull();
    expect(view.container.querySelector(".cp-results-scroll")?.firstElementChild?.classList.contains("cp-progress")).toBe(true);
    let staged!:Promise<boolean|void>;
    await act(async()=>{staged=view.home().onComposerSubmit!("确认写作方案",[]);});
    expect(view.send).not.toHaveBeenCalled();
    expect(view.container.querySelector(".cp-composer-confirmation-text")?.textContent).toBe("确认写作方案");
    expect(view.container.querySelectorAll(".cp-composer-confirmation input,.cp-composer-confirmation textarea")).toHaveLength(0);
    await act(async()=>view.container.querySelector<HTMLAnchorElement>('[data-lane-index="0"]')!.click());
    expect(view.navigation()).toMatchObject({conversationId:"conversation-1",messageId:"history-0"});
    expect(view.container.querySelector('.cp-composer-confirmation')?.parentElement?.hidden).toBe(true);
    await act(async()=>view.container.querySelector<HTMLAnchorElement>('[data-lane-index="5"]')!.click());
    expect(view.navigation()).toMatchObject({conversationId:"conversation-1",latest:true});
    expect(view.container.querySelector('.cp-composer-confirmation-text')?.textContent).toBe("确认写作方案");
    await act(async()=>[...view.container.querySelectorAll('button')].find(button=>button.textContent==="返回修改")!.click());
    expect(await staged).toBe(false);
    expect(view.send).not.toHaveBeenCalled();
  }finally{await view.cleanup();}
});

it("新流程的已交付资料包在原会话内接续，不创建新会话", async () => {
  const view = await mount({progress:{...progress,mode:"new_reference_pack",jobKind:"reference_pack",workflowVersion:"4.13.2-v16.8-app1",workflowStatus:"positioning_ready",currentStage:"reference_pack",confirmation:null,availableActions:[]}});
  try {
    const next = [...view.container.querySelectorAll<HTMLButtonElement>("button")].find(button=>button.textContent==="继续制作品牌长文")!;
    expect(next).toBeDefined();
    await act(async () => next.click());
    expect(view.send).toHaveBeenCalledTimes(1);
    expect(view.send).toHaveBeenCalledWith(expect.stringContaining("原会话、原 Job"),[]);
    expect(view.container.querySelector(".cp-task-center-dialog")).toBeNull();
  } finally { await view.cleanup(); }
});
