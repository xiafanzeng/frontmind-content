import { describe, expect, it } from "vitest";
import {
  acknowledgeSubjectChatRestart, bindSubjectChat, boundSubjectPack, createSubjectFolder,
  emptySubjectWorkspace, latestSubjectPack, parseSubjectWorkspace, publishSubjectPack,
  subjectPackUpdateAvailable, switchSubjectPack, updateSubjectChatMetadata,
  type ContentSubjectWorkspace,
} from "../contracts/content-subject-workspace";

const time = "2026-10-23T08:00:00.000Z";
const file = (id: string) => ({ fileUrl: `/artifacts/${id}`, fileName: `${id}.zip`, mimeType: "application/zip" });

function initial() {
  let state = createSubjectFolder(emptySubjectWorkspace(), "仁南", "rennan");
  state = bindSubjectChat(state, { conversationId: "pack", folderId: "rennan", kind: "pack" });
  return state;
}

function publish(state: ContentSubjectWorkspace, id = "v1", includesP0 = false) {
  return publishSubjectPack(state, { folderId: "rennan", sourceConversationId: "pack", sourceTaskId: "job-one", file: file(id), includesP0, confirmed: true, id, createdAt: time });
}

describe("主体资料包引用与版本", () => {
  it("拒绝去除首尾空格和大小写归一后同名的主体，不改变原状态", () => {
    const state = createSubjectFolder(emptySubjectWorkspace(), "  FrontMind  ", "one");
    expect(state.folders[0].name).toBe("FrontMind");
    expect(() => createSubjectFolder(state, " frontmind ", "two")).toThrow("该主体文件夹已存在");
    expect(state.folders).toHaveLength(1);
    expect(() => createSubjectFolder(initial(), " 仁南 ", "other")).toThrow("该主体文件夹已存在");
  });

  it("新文章自动引用最新已确认版本；旧文章保持原版本，仅提示新版", () => {
    let state = publish(initial());
    state = bindSubjectChat(state, { conversationId: "old-article", folderId: "rennan", kind: "article" });
    state = publish(state, "v2", true);
    state = bindSubjectChat(state, { conversationId: "new-article", folderId: "rennan", kind: "article" });
    expect(boundSubjectPack(state, "old-article")?.id).toBe("v1");
    expect(boundSubjectPack(state, "new-article")?.id).toBe("v2");
    expect(subjectPackUpdateAvailable(state, "old-article")?.id).toBe("v2");
    expect(subjectPackUpdateAvailable(state, "new-article")).toBeNull();
    expect(latestSubjectPack(state, "rennan")?.includesP0).toBe(true);
    expect(parseSubjectWorkspace(state)).toEqual(state);
  });

  it("首次无资料包的文章不在后台自动换版，重复绑定也不会改其引用", () => {
    let state = bindSubjectChat(initial(), { conversationId: "article", folderId: "rennan", kind: "article" });
    state = publish(state);
    const rebound = bindSubjectChat(state, { conversationId: "article", folderId: "rennan", kind: "article" });
    expect(rebound).toBe(state);
    expect(boundSubjectPack(state, "article")).toBeNull();
    expect(subjectPackUpdateAvailable(state, "article")?.id).toBe("v1");
  });

  it("切换版本显式变更代际，有旧任务时要求重建上下文", () => {
    let state = publish(initial());
    state = bindSubjectChat(state, { conversationId: "article", folderId: "rennan", kind: "article" });
    state = publish(state, "v2", true);
    const previous = structuredClone(state);
    const next = switchSubjectPack(state, { conversationId: "article", versionId: "v2", hasTask: true });
    expect(state).toEqual(previous);
    expect(next.bindings.article).toMatchObject({ packVersionId: "v2", generation: 1, restartRequired: true });
    expect(next.revision).toBe(state.revision + 1);
    expect(subjectPackUpdateAvailable(next, "article")).toBeNull();
    expect(switchSubjectPack(next, { conversationId: "article", versionId: "v2", hasTask: true })).toBe(next);
    expect(() => acknowledgeSubjectChatRestart(next, "article", 0)).toThrow("聊天引用已更新");
    expect(acknowledgeSubjectChatRestart(next, "article", 1).bindings.article.restartRequired).toBe(false);
  });

  it("尚无旧任务时切换资料包可直接用于首次运行", () => {
    let state = publish(initial());
    state = bindSubjectChat(state, { conversationId: "article", folderId: "rennan", kind: "article" });
    state = publish(state, "v2");
    const next = switchSubjectPack(state, { conversationId: "article", versionId: "v2", hasTask: false });
    expect(next.bindings.article).toMatchObject({ packVersionId: "v2", generation: 1 });
    expect(next.bindings.article.restartRequired).toBeUndefined();
  });

  it("跨主体版本、来源和会话重新归属均被拒绝", () => {
    let state = createSubjectFolder(publish(initial()), "其他主体", "other");
    state = bindSubjectChat(state, { conversationId: "other-article", folderId: "other", kind: "article" });
    expect(() => switchSubjectPack(state, { conversationId: "other-article", versionId: "v1", hasTask: false })).toThrow("其他主体");
    expect(() => publishSubjectPack(state, { folderId: "other", sourceConversationId: "pack", file: file("other"), includesP0: false, confirmed: true, id: "other", createdAt: time })).toThrow("来源不属于");
    expect(() => bindSubjectChat(state, { conversationId: "pack", folderId: "other", kind: "pack" })).toThrow("已归入其他主体");
  });

  it("未确认资料包不能登记；同一产物轮询去重；同一任务交付 P0 新包可升级", () => {
    const state = initial();
    const input = { folderId: "rennan", sourceConversationId: "pack", sourceTaskId: "job-one", file: file("v1"), includesP0: false, confirmed: true as const, id: "v1", createdAt: time };
    expect(() => publishSubjectPack(state, { ...input, confirmed: false } as unknown as typeof input)).toThrow("尚未完成确认");
    const first = publishSubjectPack(state, input);
    const duplicate = publishSubjectPack(first, { ...input, id: "poll-retry" });
    expect(duplicate).toBe(first);
    expect(first.folders[0].versions).toHaveLength(1);
    const p0 = publish(first, "v2", true);
    expect(p0.folders[0].versions.map((version) => [version.version, version.sourceTaskId, version.includesP0])).toEqual([[1, "job-one", false], [2, "job-one", true]]);
    expect(state.folders[0].versions).toEqual([]);
  });

  it("资料包也可由同主体文章的确认交付登记，不会修改历史文章输入", () => {
    let state = bindSubjectChat(publish(initial()), { conversationId: "p0", folderId: "rennan", kind: "article" });
    state = publishSubjectPack(state, { folderId: "rennan", sourceConversationId: "p0", file: file("p0-v2"), includesP0: true, confirmed: true, id: "p0-v2", createdAt: time });
    expect(latestSubjectPack(state, "rennan")?.id).toBe("p0-v2");
    expect(boundSubjectPack(state, "p0")?.id).toBe("v1");
  });

  it("置顶和归档更新不影响资料包版本和工作流代际", () => {
    const state = bindSubjectChat(publish(initial()), { conversationId: "article", folderId: "rennan", kind: "article" });
    const next = updateSubjectChatMetadata(state, "article", { pinned: true, archived: true });
    expect(next.bindings.article).toEqual({ ...state.bindings.article, pinned: true, archived: true });
    expect(next.folders).toEqual(state.folders);
    expect(updateSubjectChatMetadata(next, "article", { pinned: true })).toBe(next);
    expect(state.bindings.article.pinned).toBeUndefined();
  });

  it("解析拒绝错误版本、重复标识、串主体引用和不属于主体的来源聊天", () => {
    const state = publish(initial());
    expect(() => parseSubjectWorkspace({ ...state, schemaVersion: 2 })).toThrow();
    expect(() => parseSubjectWorkspace({ ...state, folders: [...state.folders, ...state.folders] })).toThrow();
    expect(() => parseSubjectWorkspace({ ...state, bindings: { ...state.bindings, bad: { folderId: "rennan", kind: "article", packVersionId: "missing", generation: 0 } } })).toThrow();
    expect(() => parseSubjectWorkspace({ ...state, bindings: {} })).toThrow();
    expect(() => createSubjectFolder(state, "  ", "empty")).toThrow();
    expect(() => createSubjectFolder(state, "重名标识", "rennan")).toThrow("主体标识已存在");
    expect(() => switchSubjectPack(state, { conversationId: "pack", versionId: "missing", hasTask: false })).toThrow("找不到该资料包版本");
  });
});
