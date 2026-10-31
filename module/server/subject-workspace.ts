import { Router, type Request } from "express";
import { z } from "zod";
import {
  ContentSubjectWorkspaceSchema,
  latestSubjectPack,
  type ContentSubjectWorkspace,
} from "../contracts/content-subject-workspace";

export type SubjectConversationAuthority = {
  id: string;
  purpose: string;
  taskId?: string;
};

/** 实现必须从服务器固定的账号/企业项目读取，不能接受浏览器传来的归属。 */
export interface ContentSubjectWorkspaceAuthority {
  conversation(id: string): Promise<SubjectConversationAuthority | null>;
}

/**
 * update 必须在真实数据库的同一事务及 workspace 行锁内调用 operation，
 * 并原子保存它的返回值。回调抛错时必须回滚；不得用本机 JSON 替代。
 */
export interface ContentSubjectWorkspaceStore {
  read(request: Request): Promise<ContentSubjectWorkspace>;
  update(
    request: Request,
    operation: (
      current: ContentSubjectWorkspace,
      authority: ContentSubjectWorkspaceAuthority,
    ) => Promise<ContentSubjectWorkspace>,
  ): Promise<ContentSubjectWorkspace>;
}

export class ContentSubjectWorkspaceHttpError extends Error {
  constructor(public readonly code: string, public readonly status: number, message: string) {
    super(message);
    this.name = "ContentSubjectWorkspaceHttpError";
  }
}

const fail = (code: string, status: number, message: string): never => {
  throw new ContentSubjectWorkspaceHttpError(code, status, message);
};

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  }
  return JSON.stringify(value) ?? "undefined";
}

function parseBoundedWorkspace(value: unknown): ContentSubjectWorkspace {
  if (Buffer.byteLength(JSON.stringify(value) ?? "", "utf8") > 100_000) {
    return fail("CONTENT_SUBJECT_WORKSPACE_TOO_LARGE", 413, "主体资料库过大，请分批整理后重试。");
  }
  const state = ContentSubjectWorkspaceSchema.strict().parse(value);
  if (state.folders.length > 200 || Object.keys(state.bindings).length > 2_000
    || state.folders.some(folder => folder.versions.length > 500)) {
    return fail("CONTENT_SUBJECT_WORKSPACE_TOO_LARGE", 413, "主体、聊天或资料包版本数量超过上限。");
  }
  const names = state.folders.map(folder => folder.name.toLowerCase());
  if (new Set(names).size !== names.length) {
    return fail("CONTENT_SUBJECT_FOLDER_NAME_CONFLICT", 409, "同名主体文件夹已存在，请使用已有主体。");
  }
  return state;
}

/**
 * 浏览器只拥有主体导航、聊天绑定及已确认版本的选择；资料包交付事实由服务器维护。
 * 此函数只能在 Store.update 的锁内执行，避免先读后写绕过修订号检查。
 */
export async function validateSubjectWorkspaceUpdate(
  current: ContentSubjectWorkspace,
  input: unknown,
  authority: ContentSubjectWorkspaceAuthority,
): Promise<ContentSubjectWorkspace> {
  const previous = parseBoundedWorkspace(current);
  const requested = parseBoundedWorkspace(input);
  // 丢失响应后重试完全相同的快照可以复用保存结果，不能再增加修订号。
  if (canonical(requested) === canonical(previous)) return previous;
  if (requested.revision !== previous.revision + 1) {
    return fail("CONTENT_SUBJECT_REVISION_CONFLICT", 409, "主体资料库已在其他窗口更新，请刷新后重试。");
  }

  const previousFolders = new Map(previous.folders.map(folder => [folder.id, folder]));
  const nextFolders = new Map(requested.folders.map(folder => [folder.id, folder]));
  for (const folder of previous.folders) {
    const next = nextFolders.get(folder.id);
    if (!next) {
      // 零版本的文件夹允许从快照移除；快照 schema 保证任何绑定都不会指向不存在的文件夹，
      // 因此"仍被绑定引用"的组合会先被结构校验拒绝，无需在此单独拦截。
      // 残留的死绑定（会话已不存在）由下方绑定校验按会话死活放行自愈清除。
      if (folder.versions.length) {
        return fail("CONTENT_SUBJECT_PACK_FACTS_SERVER_OWNED", 403, "已确认资料包版本由服务器维护，不能通过页面改写或删除。");
      }
      continue;
    }
    if (canonical(next.versions) !== canonical(folder.versions)) {
      return fail("CONTENT_SUBJECT_PACK_FACTS_SERVER_OWNED", 403, "已确认资料包版本由服务器维护，不能通过页面改写或删除。");
    }
  }
  for (const folder of requested.folders) {
    if (!previousFolders.has(folder.id) && folder.versions.length) {
      return fail("CONTENT_SUBJECT_PACK_FACTS_SERVER_OWNED", 403, "新增主体不能携带未经服务器确认的资料包版本。");
    }
  }

  // 所有会话均由宿主在当前账号/企业项目内读取，不以界面提交的 purpose 作为证明。
  const conversations = new Map<string, SubjectConversationAuthority>();
  for (const id of Object.keys(requested.bindings)) {
    if (id.length > 128) return fail("CONTENT_SUBJECT_CONVERSATION_INVALID", 400, "聊天标识无效。");
    const conversation = await authority.conversation(id);
    if (!conversation || conversation.id !== id || conversation.purpose !== "content_production") {
      return fail("CONTENT_SUBJECT_CONVERSATION_NOT_OWNED", 403, "聊天不属于当前企业项目的内容制作流程。");
    }
    conversations.set(id, conversation);
  }
  for (const id of Object.keys(previous.bindings)) {
    if (!Object.hasOwn(requested.bindings, id)) {
      // 会话已不存在的死绑定允许随快照清除（自愈）；活绑定的删除仍只走会话删除接口。
      const conversation = await authority.conversation(id);
      if (conversation && conversation.id === id) {
        return fail("CONTENT_SUBJECT_BINDING_IMMUTABLE", 409, "聊天归属不能通过主体快照删除，请使用聊天归档。");
      }
    }
  }
  for (const [id, binding] of Object.entries(requested.bindings)) {
    const old = Object.hasOwn(previous.bindings, id) ? previous.bindings[id] : undefined;
    const hasTask = Boolean(conversations.get(id)!.taskId);
    if (!old) {
      const expectedPack = binding.kind === "article" ? latestSubjectPack(requested, binding.folderId)?.id ?? null : null;
      if (binding.packVersionId !== expectedPack || binding.generation !== 0 || binding.restartRequired) {
        return fail("CONTENT_SUBJECT_BINDING_INVALID", 409, "新聊天必须引用当前主体最新的已确认资料包。");
      }
      continue;
    }
    if (binding.folderId !== old.folderId || binding.kind !== old.kind) {
      return fail("CONTENT_SUBJECT_BINDING_IMMUTABLE", 409, "聊天已经绑定主体与用途，不能重新归属。");
    }
    const packChanged = binding.packVersionId !== old.packVersionId;
    if (binding.kind === "pack" && binding.packVersionId !== null) {
      return fail("CONTENT_SUBJECT_BINDING_INVALID", 409, "资料包聊天不能引用另一资料包版本。");
    }
    if (binding.generation !== old.generation + Number(packChanged)) {
      return fail("CONTENT_SUBJECT_GENERATION_CONFLICT", 409, "资料包引用代际不一致，请刷新后重试。");
    }
    const expectedRestart = Boolean(old.restartRequired) || (packChanged && hasTask);
    if (Boolean(binding.restartRequired) !== expectedRestart) {
      return fail("CONTENT_SUBJECT_RESTART_SERVER_OWNED", 409, "更换资料包后的运行上下文必须由服务器重新绑定。");
    }
  }
  return requested;
}

function sendFailure(response: import("express").Response, error: unknown) {
  if (error instanceof ContentSubjectWorkspaceHttpError) {
    response.status(error.status).json({ error: { code: error.code, message: error.message } });
  } else if (error instanceof z.ZodError) {
    response.status(400).json({ error: { code: "CONTENT_SUBJECT_WORKSPACE_INVALID", message: "主体资料库结构无效，请刷新后重试。" } });
  } else {
    // 原始数据库错误可能带连接信息，不向浏览器回传。
    response.status(503).json({ error: { code: "CONTENT_SUBJECT_WORKSPACE_UNAVAILABLE", message: "主体资料库暂时不可用，修改尚未确认保存。" } });
  }
}

/** 挂载在经过真实宿主鉴权的 /api/modules/content，不提供匿名或文件缓存回退。 */
export function createContentSubjectWorkspaceRouter(store: ContentSubjectWorkspaceStore): Router {
  const router = Router();
  router.use((_request, response, next) => { response.setHeader("Cache-Control", "no-store"); next(); });
  router.get("/subject-workspace", async (request, response) => {
    try { response.json(parseBoundedWorkspace(await store.read(request))); }
    catch (error) { sendFailure(response, error); }
  });
  router.put("/subject-workspace", async (request, response) => {
    try {
      const requested = parseBoundedWorkspace(request.body);
      const saved = await store.update(request, (current, authority) => validateSubjectWorkspaceUpdate(current, requested, authority));
      response.json(parseBoundedWorkspace(saved));
    } catch (error) { sendFailure(response, error); }
  });
  return router;
}
