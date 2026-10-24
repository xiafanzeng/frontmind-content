// 本机离线持久化与原生停点契约；不启动页面、接口或模型。
import {beforeEach, describe, expect, it, vi} from "vitest";
import {folderDemoClient} from "./folder-demo-client";
import {bindSubjectChat, createSubjectFolder, switchSubjectPack} from "../module/contracts/content-subject-workspace";
import type {ContentConversation} from "../module/client/host";
import type {ContentProductionAction} from "../module/contracts/content-production";

function memoryStorage(): Storage {
  const map = new Map<string, string>();
  return {getItem: key => map.get(key) ?? null, setItem: (key, value) => {map.set(key, String(value));}, removeItem: key => {map.delete(key);}, clear: () => {map.clear();}, key: index => [...map.keys()][index] ?? null, get length() {return map.size;}};
}
function conversation(id: string): ContentConversation {return {id, title: "合成测试聊天", purpose: "content_production", status: "idle", messages: [], createdAt: Date.now(), updatedAt: Date.now()};}

describe("主体文件夹持久离线客户端", () => {
  let storage: Storage;
  beforeEach(() => {storage = memoryStorage();});

  it("刷新恢复聊天、主体、明确锁定的不同资料包版本", async () => {
    const first = folderDemoClient(storage).client;
    const state = await first.readSubjectWorkspace();
    expect(state.bindings["tx-article"].packVersionId).toBe("tx-v1");
    expect(state.bindings["tx-article2"].packVersionId).toBe("tx-v2");
    const rows = await first.list(); rows[0].title = "已修改且持久保存"; await first.save(rows[0]);
    const restored = folderDemoClient(storage).client;
    expect((await restored.list()).find(row => row.id === rows[0].id)?.title).toBe("已修改且持久保存");
    expect(await restored.readSubjectWorkspace()).toEqual(state);
  });

  it("只在原生停点接收匹配修订号与严格动作结构", async () => {
    const client = folderDemoClient(storage).client;
    const input = {conversationId: "tx-article2", prompt: "确认写作方案"};
    await expect(client.dispatch({...input, clientRequestId: "skip", contentProductionAction: {kind: "confirm_blueprint", revision: 7}}, "demo-task-tx-article2")).rejects.toThrow("停点");
    await expect(client.dispatch({...input, clientRequestId: "stale", contentProductionAction: {kind: "choose_examples", route: "A", revision: 6}}, "demo-task-tx-article2")).rejects.toThrow("修订号");
    await expect(client.dispatch({...input, clientRequestId: "extra", contentProductionAction: {kind: "choose_examples", route: "A", revision: 7, autoConfirm: true}}, "demo-task-tx-article2")).rejects.toThrow();
    expect((await client.task("demo-task-tx-article2")).contentProduction?.workflowStatus).toBe("awaiting_example_confirmation");
  });

  it.each(["A", "B"] as const)("文风 %s 与构思参考单独明确，统一确认保留两者", async route => {
    const client = folderDemoClient(storage).client;
    await expect(client.dispatch({conversationId: "tx-article2", clientRequestId: "style-only", prompt: `文风：${route}`, contentProductionAction: {kind: "choose_examples", route, revision: 7}}, "demo-task-tx-article2")).rejects.toThrow("构思参考");
    const result = await client.dispatch({conversationId: "tx-article2", clientRequestId: "complete", prompt: `文风：${route}；文章池：1、5`, contentProductionAction: {kind: "choose_examples", route, revision: 7}}, "demo-task-tx-article2");
    expect(result.contentProduction?.workflowStatus).toBe("awaiting_question_positioning_confirmation");
    const reply = (await client.list()).find(row => row.id === "tx-article2")?.messages.at(-1);
    expect(reply?.content).toContain(`文风：${route}`); expect(reply?.content).toContain("构思参考：1、5");
  });

  it("同一请求只应用一次，重试不重复助手消息，异文复用编号被拒绝", async () => {
    const client = folderDemoClient(storage).client;
    const input = {conversationId: "tx-article2", clientRequestId: "dedup", prompt: "文风：B；文章池：不采用", contentProductionAction: {kind: "choose_examples", route: "B", revision: 7}};
    const first = await client.dispatch(input, "demo-task-tx-article2");
    expect(await client.dispatch(input, "demo-task-tx-article2")).toEqual(first);
    const restored = folderDemoClient(storage).client;
    expect(await restored.dispatch(input, "demo-task-tx-article2")).toEqual(first);
    expect((await restored.list()).find(row => row.id === "tx-article2")?.messages.filter(message => message.id === "demo-reply-dedup")).toHaveLength(1);
    await expect(client.dispatch({...input, prompt: "文风：A；文章池：1、5"}, "demo-task-tx-article2")).rejects.toThrow("不同内容");
  });

  it("迟到的聊天 save 保留 dispatch 新回复与原输入", async () => {
    const client = folderDemoClient(storage).client;
    const old = (await client.list()).find(row => row.id === "tx-article2")!;
    await client.dispatch({conversationId: old.id, clientRequestId: "new-response", prompt: "文风：A；文章池：不采用", contentProductionAction: {kind: "choose_examples", route: "A", revision: 7}}, old.taskId);
    await client.save(old);
    const messages = (await client.list()).find(row => row.id === old.id)!.messages;
    expect(messages.some(message => message.id === "new-response")).toBe(true);
    expect(messages.some(message => message.id === "demo-reply-new-response")).toBe(true);
  });

  it("手动换版重置原生起点，任务编号与旧消息保留，清除重启标记", async () => {
    const client = folderDemoClient(storage).client;
    const before = (await client.list()).find(row => row.id === "tx-article")!;
    const state = switchSubjectPack(await client.readSubjectWorkspace(), {conversationId: before.id, versionId: "tx-v2", hasTask: true});
    const saved = await client.saveSubjectWorkspace(state);
    expect(saved.revision).toBe(state.revision); expect(saved.bindings[before.id].restartRequired).toBe(false);
    expect((await client.task(before.taskId!)).contentProduction?.workflowStatus).toBe("awaiting_question_selection");
    const row = (await client.list()).find(item => item.id === before.id)!;
    expect(row.taskId).toBe(before.taskId); expect(row.messages.length).toBe(before.messages.length + 1);
    expect(row.messages.slice(0, before.messages.length).every(message => message.contentWorkflowGeneration === 0)).toBe(true);
    expect(row.messages.at(-1)?.contentWorkflowGeneration).toBe(1);
    expect(row.messages.at(-1)?.content).toContain("旧交付仅作为历史记录");
    expect((await folderDemoClient(storage).client.task(before.taskId!)).contentProduction?.workflowStatus).toBe("awaiting_question_selection");
  });

  it("拒绝覆盖较新主体状态、跨主体引用、伪造资料包和只换徽标", async () => {
    const client = folderDemoClient(storage).client;
    const state = await client.readSubjectWorkspace();
    const changed = structuredClone(state); changed.revision++; changed.folders[0].name = "示例品牌示例";
    await client.saveSubjectWorkspace(changed);
    await expect(client.saveSubjectWorkspace(changed)).rejects.toThrow("已变化");
    const cross = await client.readSubjectWorkspace(); cross.revision++; cross.bindings["tx-article"].folderId = "rn";
    await expect(client.saveSubjectWorkspace(cross)).rejects.toThrow();
    const fake = await client.readSubjectWorkspace(); fake.revision++; fake.folders[0].versions.push({...fake.folders[0].versions[0], id: "forged", version: 99});
    await expect(client.saveSubjectWorkspace(fake)).rejects.toThrow("原生确认");
    const badge = await client.readSubjectWorkspace(); badge.revision++; badge.bindings["tx-article"].packVersionId = "tx-v2";
    await expect(client.saveSubjectWorkspace(badge)).rejects.toThrow("运行代次");
  });

  it("另一个标签页的较新修订不会被旧客户端覆盖", async () => {
    const first = folderDemoClient(storage).client;
    const second = folderDemoClient(storage).client;
    const stale = await first.readSubjectWorkspace(); stale.revision++; stale.folders[0].name = "旧标签页改名";
    const newer = await second.readSubjectWorkspace(); newer.revision++; newer.folders[0].name = "新标签页改名";
    await second.saveSubjectWorkspace(newer);
    await expect(first.saveSubjectWorkspace(stale)).rejects.toThrow("已变化");
    expect((await first.readSubjectWorkspace()).folders[0].name).toBe("新标签页改名");
  });

  it("新文章默认最新资料包，不能新建旧版引用后直接提交", async () => {
    const client = folderDemoClient(storage).client;
    let state = bindSubjectChat(await client.readSubjectWorkspace(), {conversationId: "new-article", folderId: "tx", kind: "article"});
    expect(state.bindings["new-article"].packVersionId).toBe("tx-v2");
    const invalid = structuredClone(state); invalid.bindings["new-article"].packVersionId = "tx-v1";
    await expect(client.saveSubjectWorkspace(invalid)).rejects.toThrow("最新");
    state = await client.saveSubjectWorkspace(state); await client.save(conversation("new-article"));
    const task = await client.task("demo-task-new-article"); expect(task.contentProduction?.workflowStatus).toBe("awaiting_question_selection");
  });

  it("确认资料包后只自动绑定同主体等待文章，原有版本文章保持锁定", async () => {
    const client = folderDemoClient(storage).client;
    let state = bindSubjectChat(await client.readSubjectWorkspace(), {conversationId: "rn-waiting", folderId: "rn", kind: "article"});
    state = await client.saveSubjectWorkspace(state); expect(state.bindings["rn-waiting"].packVersionId).toBeNull();
    await client.save(conversation("rn-waiting"));
    await expect(client.dispatch({conversationId: "rn-waiting", clientRequestId: "missing", prompt: "开始"}, "demo-task-rn-waiting")).rejects.toThrow("资料包");
    const taskId = "demo-task-rn-pack";
    const actions: Array<Omit<ContentProductionAction, "revision">> = [
      {kind: "provide_reference_pack_inputs"}, {kind: "confirm_competitors"}, {kind: "choose_core_positioning_direction", direction: "方向 A"} as Omit<ContentProductionAction, "revision">, {kind: "confirm_core_positioning"},
    ];
    for (const [index, action] of actions.entries()) {const task = await client.task(taskId); await client.dispatch({conversationId: "rn-pack", clientRequestId: `pack-${index}`, prompt: "资料：合成主体材料；离线明确确认", contentProductionAction: {...action, revision: task.contentProduction!.runnerRevision}}, taskId);}
    const saved = await client.readSubjectWorkspace();
    expect(saved.folders.find(folder => folder.id === "rn")?.versions).toHaveLength(1);
    expect(saved.bindings["rn-waiting"].packVersionId).toBe(saved.folders.find(folder => folder.id === "rn")!.versions[0].id);
    expect(saved.bindings["tx-article"].packVersionId).toBe("tx-v1");
    expect((await client.task("demo-task-rn-waiting")).contentProduction?.workflowStatus).toBe("awaiting_p0_route");
    expect((await client.list()).find(row => row.id === "rn-waiting")?.messages.at(-1)?.contentWorkflowGeneration).toBe(saved.bindings["rn-waiting"].generation);
  });

  it("交付结构与版本登记明确标注离线，运行期间无网络或模型调用", async () => {
    const fetchMock = vi.fn(() => {throw new Error("测试中禁止网络");}); vi.stubGlobal("fetch", fetchMock);
    try {
      const client = folderDemoClient(storage).client;
      await client.dispatch({conversationId: "tx-article", clientRequestId: "p0-delivery", prompt: "确认 P0 写作方案", contentProductionAction: {kind: "confirm_p0_blueprint", revision: 11}}, "demo-task-tx-article");
      const state = await client.readSubjectWorkspace(); const latest = state.folders[0].versions.at(-1)!;
      expect(latest.includesP0).toBe(true); expect(latest.file.fileName).toContain("离线演示");
      const reply = (await client.list()).find(row => row.id === "tx-article")!.messages.at(-1)!;
      expect(reply.content).toContain("未运行模型"); expect(fetchMock).not.toHaveBeenCalled();
    } finally {vi.unstubAllGlobals();}
  });

  it("P0 交付只登记新输出，文章输入保留旧版；显式接续只带入本 Job 交付包", async () => {
    const client = folderDemoClient(storage).client;
    await client.dispatch({conversationId: "tx-article", clientRequestId: "p0-own", prompt: "确认 P0 写作方案", contentProductionAction: {kind: "confirm_p0_blueprint", revision: 11}}, "demo-task-tx-article");
    const delivered = await client.readSubjectWorkspace();
    const own = delivered.folders[0].versions.at(-1)!;
    expect(own.includesP0).toBe(true); expect(own.sourceTaskId).toBe("demo-task-tx-article");
    expect(delivered.bindings["tx-article"].packVersionId).toBe("tx-v1");
    expect(delivered.bindings["tx-article2"].packVersionId).toBe("tx-v2");
    // 在同主体另一个原生任务登记更晚输出，接续时不得误用它。
    const state = bindSubjectChat(delivered, {conversationId: "other-p0", folderId: "tx", kind: "article"});
    await client.saveSubjectWorkspace(state); await client.save(conversation("other-p0"));
    await client.dispatch({conversationId: "other-p0", clientRequestId: "other-start", prompt: "制作品牌长文", contentProduction: {mode: "p0", enterpriseName: "示例品牌", knowledgeSource: "files"}}, "demo-task-other-p0");
    for (const [index, action] of [{kind: "choose_p0_route", route: "create"}, {kind: "choose_p0_examples", route: "workflow"}, {kind: "confirm_p0_blueprint"}].entries()) {
      const task = await client.task("demo-task-other-p0");
      await client.dispatch({conversationId: "other-p0", clientRequestId: `other-${index}`, prompt: "离线明确确认", contentProductionAction: {...action, revision: task.contentProduction!.runnerRevision}}, task.id);
    }
    expect((await client.readSubjectWorkspace()).folders[0].versions.at(-1)!.id).not.toBe(own.id);
    await client.dispatch({conversationId: "tx-article", clientRequestId: "continue-own", prompt: "继续问题文章"}, "demo-task-tx-article");
    const continued = await client.readSubjectWorkspace();
    expect(continued.bindings["tx-article"].packVersionId).toBe(own.id);
    expect(continued.bindings["tx-article2"].packVersionId).toBe("tx-v2");
    expect((await client.task("demo-task-tx-article")).contentProduction?.workflowStatus).toBe("awaiting_question_selection");
  });

  it("P02 必须先分别选择并确认两家对象，保留顺序且不改资料包范围", async () => {
    const client = folderDemoClient(storage).client;
    const switched = switchSubjectPack(await client.readSubjectWorkspace(), {conversationId: "tx-article", versionId: "tx-v2", hasTask: true});
    await client.saveSubjectWorkspace(switched);
    const taskId = "demo-task-tx-article";
    let serial = 0;
    const act = async (action: Record<string, unknown>) => {const task = await client.task(taskId); return client.dispatch({conversationId: "tx-article", clientRequestId: `p02-${serial++}`, prompt: "离线明确选择", contentProductionAction: {...action, revision: task.contentProduction!.runnerRevision}}, taskId);};
    await act({kind: "choose_question", selection: "如何了解本主体及同类选择？"});
    await act({kind: "submit_response_brief", noExtraRequirements: true, aiBrandRecognition: "insufficient"});
    const pattern = await act({kind: "confirm_pattern", selectedPattern: "P02"});
    expect(pattern.contentProduction?.workflowStatus).toBe("awaiting_competitor_selection");
    expect(pattern.contentProduction?.jobKind).toBe("article");
    expect(pattern.contentProduction?.pauseTitle).toContain("本题两家");
    await expect(act({kind: "confirm_competitors"})).rejects.toThrow("恰好两家");
    for (const selection of ["示例 A", "示例 A、示例 A", "示例品牌、示例 B", "示例 A、示例 B、示例 C"]) await expect(act({kind: "update_competitor_selection", selection})).rejects.toThrow();
    await act({kind: "update_competitor_selection", selection: '["示例 B", "示例 A"]'});
    expect((await client.task(taskId)).contentProduction?.workflowStatus).toBe("awaiting_competitor_selection");
    const latest = (await client.list()).find(row => row.id === "tx-article")!.messages.at(-1)!;
    expect(latest.content).toContain("本题比较对象（按输入顺序）：示例 B、示例 A");
    expect(latest.content).toContain("独立保存"); expect(latest.contentWorkflowKind).toBe("article");
    const confirmed = await act({kind: "confirm_competitors"});
    expect(confirmed.contentProduction?.workflowStatus).toBe("awaiting_example_confirmation");
    expect((await client.readSubjectWorkspace()).folders[0].versions).toHaveLength(2);
  });

  it("真正新建资料包首个原生动作完成初始化，整链结束后一次接续即进入 P0", async () => {
    const client = folderDemoClient(storage).client;
    const folderId = "brand-new-subject", chatId = "brand-new-pack";
    await client.saveSubjectWorkspace(createSubjectFolder(await client.readSubjectWorkspace(), "全新离线主体", folderId));
    // 与实际界面顺序一致：先保存空聊天，再将它绑定到新主体的资料包用途。
    const row = await client.save(conversation(chatId));
    await client.saveSubjectWorkspace(bindSubjectChat(await client.readSubjectWorkspace(), {conversationId: chatId, folderId, kind: "pack"}));
    const taskId = row.taskId!;
    expect((await client.task(taskId)).contentProduction?.workflowStatus).toBe("awaiting_reference_pack_input");
    const beforeFailure = storage.getItem("frontmind-content-folder-demo-v1");
    await expect(client.dispatch({conversationId: chatId, clientRequestId: "new-pack-illegal", prompt: "跳过资料直接确认", contentProductionAction: {kind: "confirm_core_positioning", revision: 0}}, taskId)).rejects.toThrow("停点");
    expect(storage.getItem("frontmind-content-folder-demo-v1")).toBe(beforeFailure);
    expect(JSON.parse(storage.getItem("frontmind-content-folder-demo-v1")!).tasks[taskId].initialized).toBe(false);
    const actions = [{kind: "provide_reference_pack_inputs"}, {kind: "confirm_competitors"}, {kind: "choose_core_positioning_direction", direction: "方向 A"}, {kind: "confirm_core_positioning"}];
    for (const [index, action] of actions.entries()) {
      const task = await client.task(taskId);
      await client.dispatch({conversationId: chatId, clientRequestId: `new-pack-${index}`, prompt: index === 0 ? "资料：全新离线主体的合成介绍与服务范围" : "离线明确确认当前原生停点", contentProductionAction: {...action, revision: task.contentProduction!.runnerRevision}}, taskId);
      expect(JSON.parse(storage.getItem("frontmind-content-folder-demo-v1")!).tasks[taskId].initialized).toBe(true);
    }
    expect((await client.task(taskId)).contentProduction?.workflowStatus).toBe("positioning_ready");
    const continued = await client.dispatch({conversationId: chatId, clientRequestId: "new-pack-continue-once", prompt: "继续 P0"}, taskId);
    expect(continued.contentProduction?.workflowStatus).toBe("awaiting_p0_route");
    expect(continued.id).toBe(taskId);
    expect((await client.readSubjectWorkspace()).folders.find(folder => folder.id === folderId)?.versions).toHaveLength(1);
    expect((await folderDemoClient(storage).client.task(taskId)).contentProduction?.workflowStatus).toBe("awaiting_p0_route");
  });

  it("生成确认卡前可校验演示附件大小，上传沿用同一个 2 MB 限制", async () => {
    const client = folderDemoClient(storage).client;
    const large = {size: 2 * 1024 * 1024 + 1, name: "超限合成资料.txt"} as File;
    const small = {size: 1024, name: "小型合成资料.txt"} as File;
    const boundary = {size: 2 * 1024 * 1024, name: "边界合成资料.txt"} as File;
    expect(client.attachmentHint).toContain("离线演示"); expect(client.attachmentHint).toContain("2 MB");
    expect(client.validateAttachment(large)).toBe(client.attachmentHint);
    expect(client.validateAttachment(small)).toBeNull(); expect(client.validateAttachment(boundary)).toBeNull();
    const before = storage.getItem("frontmind-content-folder-demo-v1");
    await expect(client.upload(large)).rejects.toThrow(client.attachmentHint);
    expect(storage.getItem("frontmind-content-folder-demo-v1")).toBe(before);
  });
});
