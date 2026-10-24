// @vitest-environment jsdom
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, expect, it, vi } from "vitest";
import { useContentWorkspaceHost, type ContentConversation } from "../client/host";

vi.mock("../client/ContentProductionWorkspace", () => ({ default: () => {
  const host = useContentWorkspaceHost();
  const { activeConversation } = host.useConversation();
  const Home = host.Home;
  const PurposeProvider = host.ConversationPurposeProvider;
  return <PurposeProvider purpose="content_production">{activeConversation ? <Home purpose="content_production" /> : null}</PurposeProvider>;
} }));
vi.mock("@frontmind/module-ui/components/BusinessChatInput", () => ({ default: () => null }));
import { ModuleWorkspace } from "../client/runtime";

afterEach(() => { vi.useRealTimers(); localStorage.clear(); document.body.innerHTML = ""; });

it("收件验收查看已有任务时不会查询、停止或派发任务", async () => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers(); localStorage.setItem("frontmind-content-active:intake-read", "existing");
  const unexpected = vi.fn(async (): Promise<never> => { throw new Error("验收禁止执行入口"); });
  const client = { list: vi.fn(async () => [{ id: "existing", taskId: "old-task", title: "既有任务", purpose: "content_production", status: "running", messages: [], createdAt: 1, updatedAt: 1 }]),
    submitIntake: unexpected, task: unexpected, dispatch: unexpected, stop: unexpected, save: unexpected, remove: unexpected, upload: unexpected };
  const container = document.createElement("div"); document.body.append(container); const root = createRoot(container);
  try {
    await act(async () => root.render(<ModuleWorkspace client={client} context={{ module: "content", workspace: { id: "intake-read", ownerUserId: 1 }, marketEdition: "cn", capabilities: [] }} />));
    await act(async () => vi.advanceTimersByTimeAsync(12_000));
    expect(client.list).toHaveBeenCalledOnce(); expect(unexpected).not.toHaveBeenCalled();
  } finally { await act(async () => root.unmount()); container.remove(); }
});

it.each(["polling", "parent render"])("keeps the rendered message mounted across %s", async update => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  localStorage.setItem("frontmind-content-active:polling-test", "conversation-1");
  const rows: ContentConversation[] = [{
    id: "conversation-1", taskId: "task-1", title: "合成确认任务", purpose: "content_production",
    status: "awaiting_input", createdAt: 1, updatedAt: 1,
    messages: [{ id: "message-1", role: "assistant", content: "请确认写作方案。", timestamp: 1 }],
  }];
  const reject = vi.fn(async (): Promise<never> => { throw new Error("Unexpected write"); });
  const client = {
    list: vi.fn(async () => structuredClone(rows)),
    task: vi.fn(async () => ({ id: "task-1", status: "awaiting_input" })),
    save: reject, remove: reject, upload: reject, dispatch: reject, stop: reject,
  };
  const container = document.createElement("div"); document.body.append(container);
  const root = createRoot(container);
  const render = () => root.render(<ModuleWorkspace client={client} context={{ module: "content", workspace: { id: "polling-test", ownerUserId: 1 }, marketEdition: "cn", capabilities: [] }} />);
  try {
    await act(async () => render());
    const message = container.querySelector('[data-message-role="assistant"]');
    expect(message).not.toBeNull();
    if (update === "polling") {
      const reads = client.list.mock.calls.length;
      await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
      expect(client.list.mock.calls.length).toBeGreaterThan(reads);
    } else {
      await act(async () => render());
    }
    expect(container.querySelector('[data-message-role="assistant"]')).toBe(message);
    expect(reject).not.toHaveBeenCalled();
  } finally { await act(async () => root.unmount()); }
});

it("keeps chronological summary rows mounted during repeated polls and final delivery",async()=>{
 (globalThis as {IS_REACT_ACT_ENVIRONMENT?:boolean}).IS_REACT_ACT_ENVIRONMENT=true;vi.useFakeTimers();localStorage.setItem("frontmind-content-active:process-poll","conversation");
 const rows:ContentConversation[]=[{id:"conversation",taskId:"task",title:"离线过程测试",status:"running",createdAt:1,updatedAt:1,messages:[{id:"user",role:"user",content:"开始",timestamp:1}],processes:[{id:"process",userMessageId:"user",startedAt:1,status:"running",thinking:[{id:"thought",timestamp:2,text:"正在处理：问题文章方案。",status:"recorded"}],tools:[{id:"tool",timestamp:3,text:"正在读取登记材料。",status:"running"}]}]}];
 const unexpected=async():Promise<never>=>{throw new Error("Unexpected write");};const client={list:async()=>structuredClone(rows),task:async()=>({id:"task",status:rows[0].status}),save:unexpected,upload:unexpected,dispatch:unexpected,remove:unexpected,stop:unexpected};
 const container=document.createElement("div");document.body.append(container);const root=createRoot(container);
 try{await act(async()=>root.render(<ModuleWorkspace client={client} context={{module:"content",workspace:{id:"process-poll",ownerUserId:0},marketEdition:"cn",capabilities:[]}}/>));const process=container.querySelector("[data-process-id]"),tool=container.querySelector('[data-summary-id="tool"]');expect(process).not.toBeNull();expect(container.querySelector("h3")).toBeNull();expect(container.textContent).not.toContain("工具汇总");
 rows[0].status="completed";rows[0].processes![0].status="completed";rows[0].processes![0].tools[0]={id:"tool",timestamp:3,text:"已完成读取登记材料。",status:"completed"};rows[0].messages.push({id:"final",role:"assistant",content:"最终答复与交付",timestamp:4});await act(async()=>vi.advanceTimersByTimeAsync(3000));expect(container.querySelector("[data-process-id]")).toBe(process);expect(container.querySelector('[data-summary-id="tool"]')).toBe(tool);expect((tool as HTMLElement).hidden).toBe(true);expect(container.textContent).toContain("最终答复与交付");
 await act(async()=>container.querySelector<HTMLButtonElement>(".cp-process-toggle")!.click());await act(async()=>vi.advanceTimersByTimeAsync(3000));expect((tool as HTMLElement).hidden).toBe(false);expect(container.querySelector('[data-summary-id="tool"]')).toBe(tool);
 }finally{await act(async()=>root.unmount());}
});
