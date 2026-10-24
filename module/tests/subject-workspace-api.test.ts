import express from "express";
import { once } from "node:events";
import { request as httpRequest } from "node:http";
import { describe, expect, it } from "vitest";
import {
  bindSubjectChat, createSubjectFolder, emptySubjectWorkspace, publishSubjectPack,
  switchSubjectPack, updateSubjectChatMetadata, type ContentSubjectWorkspace,
} from "../contracts/content-subject-workspace";
import {
  createContentSubjectWorkspaceRouter, validateSubjectWorkspaceUpdate, ContentSubjectWorkspaceHttpError,
  type ContentSubjectWorkspaceAuthority, type ContentSubjectWorkspaceStore,
} from "../server/subject-workspace";
import { createModuleHttpApi, type ModuleHttpCore } from "../server/http-api";

const authority = (ids: string[], taskId?: string): ContentSubjectWorkspaceAuthority => ({
  async conversation(id) { return ids.includes(id) ? { id, purpose: "content_production", taskId } : null; },
});
const folder = () => createSubjectFolder(emptySubjectWorkspace(), "合成样例主体", "sample");
function published() {
  let state = bindSubjectChat(folder(), { conversationId: "pack", folderId: "sample", kind: "pack" });
  state = publishSubjectPack(state, {
    id: "version-one", folderId: "sample", sourceConversationId: "pack", sourceTaskId: "server-task",
    confirmed: true, includesP0: false, createdAt: "2026-10-24T08:00:00.000Z",
    file: { fileUrl: "/api/frontmind/v2/artifacts/real-one/content", fileName: "资料包.zip", mimeType: "application/zip" },
  });
  state = bindSubjectChat(state, { conversationId: "article", folderId: "sample", kind: "article" });
  return publishSubjectPack(state, {
    id: "version-two", folderId: "sample", sourceConversationId: "pack", sourceTaskId: "server-task",
    confirmed: true, includesP0: true, createdAt: "2026-10-24T09:00:00.000Z",
    file: { fileUrl: "/api/frontmind/v2/artifacts/real-two/content", fileName: "资料包更新.zip", mimeType: "application/zip" },
  });
}

describe("正式主体接口的业务写入校验", () => {
  it("创建主体并绑定当前企业项目的真实内容聊天，首次新文章自动引用最新确认版本", async () => {
    expect(await validateSubjectWorkspaceUpdate(emptySubjectWorkspace(), folder(), authority([]))).toEqual(folder());
    const state = published();
    const next = bindSubjectChat(state, { conversationId: "new-article", folderId: "sample", kind: "article" });
    expect((await validateSubjectWorkspaceUpdate(state, next, authority(["pack", "article", "new-article"])))
      .bindings["new-article"].packVersionId).toBe("version-two");
  });

  it("拒绝跨项目或不同业务会话，客户端purpose不能作为归属证明", async () => {
    const state = folder(), next = bindSubjectChat(state, { conversationId: "foreign", folderId: "sample", kind: "pack" });
    await expect(validateSubjectWorkspaceUpdate(state, next, authority([]))).rejects.toMatchObject({ status: 403, code: "CONTENT_SUBJECT_CONVERSATION_NOT_OWNED" });
    await expect(validateSubjectWorkspaceUpdate(state, next, { conversation: async id => ({ id, purpose: "enterprise_qa" }) })).rejects.toMatchObject({ status: 403 });
  });

  it("丢失响应后的相同快照重试幂等，过期快照冲突不会覆盖", async () => {
    const state = folder();
    expect(await validateSubjectWorkspaceUpdate(state, structuredClone(state), authority([]))).toEqual(state);
    await expect(validateSubjectWorkspaceUpdate(state, { ...state, revision: 1, folders: [] }, authority([])))
      .rejects.toMatchObject({ code: "CONTENT_SUBJECT_REVISION_CONFLICT", status: 409 });
  });

  it("浏览器不能伪造、修改、删除已确认交付版本或资料包来源", async () => {
    const state = published(), next = updateSubjectChatMetadata(state, "article", { pinned: true });
    const forged = structuredClone(next); forged.folders[0].versions[0].file.fileUrl = "https://example.invalid/fake.zip";
    await expect(validateSubjectWorkspaceUpdate(state, forged, authority(["pack", "article"]))).rejects.toMatchObject({ code: "CONTENT_SUBJECT_PACK_FACTS_SERVER_OWNED" });
    const missing = structuredClone(next); missing.folders[0].versions.shift(); missing.bindings.article.packVersionId = "version-two";
    await expect(validateSubjectWorkspaceUpdate(state, missing, authority(["pack", "article"]))).rejects.toMatchObject({ code: "CONTENT_SUBJECT_PACK_FACTS_SERVER_OWNED" });
    const fabricated = structuredClone(state); fabricated.revision = 1;
    await expect(validateSubjectWorkspaceUpdate(emptySubjectWorkspace(), fabricated, authority(["pack", "article"]))).rejects.toMatchObject({ code: "CONTENT_SUBJECT_PACK_FACTS_SERVER_OWNED" });
  });

  it("服务器依据真实任务绑定要求换版后重建上下文，不能伪称没有任务", async () => {
    const state = published();
    const incorrect = switchSubjectPack(state, { conversationId: "article", versionId: "version-two", hasTask: false });
    await expect(validateSubjectWorkspaceUpdate(state, incorrect, authority(["pack", "article"], "running-task")))
      .rejects.toMatchObject({ code: "CONTENT_SUBJECT_RESTART_SERVER_OWNED" });
    const correct = switchSubjectPack(state, { conversationId: "article", versionId: "version-two", hasTask: true });
    expect((await validateSubjectWorkspaceUpdate(state, correct, authority(["pack", "article"], "running-task"))).bindings.article.restartRequired).toBe(true);
    const forgedAck = structuredClone(correct); forgedAck.revision++; forgedAck.bindings.article.restartRequired = false;
    await expect(validateSubjectWorkspaceUpdate(correct, forgedAck, authority(["pack", "article"], "running-task")))
      .rejects.toMatchObject({ code: "CONTENT_SUBJECT_RESTART_SERVER_OWNED" });
  });

  it("拒绝初始代际伪造、重复主体名、聊天重新归属及删除绑定", async () => {
    const state = folder(), next = bindSubjectChat(state, { conversationId: "pack", folderId: "sample", kind: "pack" });
    next.bindings.pack.generation = 5;
    await expect(validateSubjectWorkspaceUpdate(state, next, authority(["pack"]))).rejects.toMatchObject({ code: "CONTENT_SUBJECT_BINDING_INVALID" });
    const duplicate = { ...state, revision: state.revision + 1, folders: [...state.folders, { id: "other", name: "合成样例主体", versions: [] }] };
    await expect(validateSubjectWorkspaceUpdate(state, duplicate, authority([]))).rejects.toMatchObject({ code: "CONTENT_SUBJECT_FOLDER_NAME_CONFLICT" });
    const bound = bindSubjectChat(state, { conversationId: "pack", folderId: "sample", kind: "pack" });
    const removed = { ...bound, revision: bound.revision + 1, bindings: {} };
    await expect(validateSubjectWorkspaceUpdate(bound, removed, authority(["pack"]))).rejects.toMatchObject({ code: "CONTENT_SUBJECT_BINDING_IMMUTABLE" });
    const retyped = structuredClone(bound); retyped.revision++; retyped.bindings.pack.kind = "article";
    await expect(validateSubjectWorkspaceUpdate(bound, retyped, authority(["pack"]))).rejects.toMatchObject({ code: "CONTENT_SUBJECT_BINDING_IMMUTABLE" });
  });
});

async function send(url: string, method = "GET", body?: unknown) {
  return new Promise<{ status: number; value: any; cache: string | undefined }>((resolve, reject) => {
    const request = httpRequest(url, { method, headers: { "content-type": "application/json" } }, response => {
      const chunks: Buffer[] = []; response.on("data", chunk => chunks.push(chunk));
      response.on("end", () => resolve({ status: response.statusCode!, value: JSON.parse(Buffer.concat(chunks).toString()), cache: response.headers["cache-control"] }));
    });
    request.on("error", reject); request.end(body === undefined ? undefined : JSON.stringify(body));
  });
}

describe("主体HTTP端口契约（内存仅用于单元测试，不代表正式持久化验收）", () => {
  it("修改在store事务回调中校验，刷新读取已保存值；没有存储时明确失败", async () => {
    let state: ContentSubjectWorkspace = emptySubjectWorkspace();
    const store: ContentSubjectWorkspaceStore = {
      async read() { return state; },
      async update(_request, operation) { const saved = await operation(state, authority([])); state = saved; return saved; },
    };
    const app = express(); app.use(express.json()); app.use(createContentSubjectWorkspaceRouter(store));
    const server = app.listen(0, "127.0.0.1"); await once(server, "listening");
    const url = `http://127.0.0.1:${(server.address() as { port: number }).port}/subject-workspace`;
    try {
      expect(await send(url, "PUT", folder())).toMatchObject({ status: 200, value: folder(), cache: "no-store" });
      expect(await send(url)).toMatchObject({ status: 200, value: folder() });
      expect(await send(url, "PUT", { ...folder(), revision: 0 })).toMatchObject({ status: 409, value: { error: { code: "CONTENT_SUBJECT_REVISION_CONFLICT" } } });
      store.read = async () => { throw new Error("mysql://private:secret@internal"); };
      const failure = await send(url); expect(failure.status).toBe(503); expect(JSON.stringify(failure.value)).not.toContain("secret");
    } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
  });

  it("同一正式命名空间接主体、聊天与只收件端口，拒绝身份未绑定的请求", async () => {
    let authenticated = true, accepts = 0;
    let state: ContentSubjectWorkspace = emptySubjectWorkspace();
    const core: ModuleHttpCore = {
      context() {
        if (!authenticated) throw new Error("AUTH_REQUIRED");
        return { accountUserId: 7, actorUserId: 7, enterpriseProjectId: "fixed-project", businessOwnerId: "7", businessActorId: "7" };
      },
      database: async () => { throw new Error("本测试不连接数据库"); }, environment: {},
      content: {
        intakeOnly: true,
        subjectWorkspace: { read: async () => state, update: async (_req, operation) => state = await operation(state, authority(["draft"])) },
        conversations: { list: async () => [{ id: "draft", purpose: "content_production", messages: [] }], save: async (_req, row) => row, delete: async () => ({ success: true }) },
        intake: { accept: async (_req, input) => {
          accepts++;
          if ((input as { reject?: boolean }).reject) throw new ContentSubjectWorkspaceHttpError("CONTENT_INTAKE_INVALID", 400, "请检查待提交材料。");
          return { id: "unit-test-only", status: "received", executionStarted: false };
        } },
      },
    };
    const app = express(); app.use(express.json()); app.use("/api/modules/content", createModuleHttpApi(core));
    const server = app.listen(0, "127.0.0.1"); await once(server, "listening");
    const url = `http://127.0.0.1:${(server.address() as { port: number }).port}/api/modules/content`;
    try {
      expect(await send(`${url}/capabilities`)).toMatchObject({ status: 200, value: { intakeOnly: true, workspaceId: "fixed-project", features: expect.arrayContaining(["subject_workspace", "conversations", "intake"]) } });
      expect(await send(`${url}/subject-workspace`, "PUT", folder())).toMatchObject({ status: 200 });
      expect(await send(`${url}/conversations`)).toMatchObject({ status: 200, value: [{ id: "draft" }] });
      expect(await send(`${url}/intake`, "POST", { conversationId: "draft" })).toMatchObject({ status: 200, value: { status: "received", executionStarted: false } });
      expect(await send(`${url}/intake`, "POST", { reject: true })).toMatchObject({ status: 400, value: { error: { code: "CONTENT_INTAKE_INVALID" } } });
      expect(await send(`${url}/conversations/draft`, "PUT", { id: "draft", purpose: "enterprise_qa", messages: [] })).toMatchObject({ status: 403 });
      core.content!.conversations.save = async () => { throw Object.assign(new Error("当前聊天已在其他窗口更新。"), { code: "CONFLICT" }); };
      expect(await send(`${url}/conversations/draft`, "PUT", { id: "draft", purpose: "content_production", messages: [] })).toMatchObject({ status: 409, value: { error: { code: "CONFLICT" } } });
      authenticated = false;
      expect(await send(`${url}/intake`, "POST", {})).toMatchObject({ status: 401 }); expect(accepts).toBe(2);
      expect(await send(`${url}/subject-workspace`)).toMatchObject({ status: 401 });
      authenticated = true;
      core.content!.conversations.list = async () => { throw Object.assign(new Error("mysql://private:secret@internal"), { code: "ER_ACCESS_DENIED_ERROR" }); };
      const unavailable = await send(`${url}/conversations`);
      expect(unavailable.status).toBe(503); expect(JSON.stringify(unavailable.value)).not.toContain("secret");
    } finally { await new Promise<void>((resolve, reject) => server.close(error => error ? reject(error) : resolve())); }
  });
});
