import { z } from "zod";

const identifier = z.string().min(1).max(256).refine((value) => value.trim().length > 0, "标识不能为空");

export const ReferencePackFileSchema = z.object({
  fileUrl: z.string().trim().min(1),
  fileName: z.string().trim().min(1),
  mimeType: z.string().trim().min(1),
});

export const ReferencePackVersionSchema = z.object({
  id: identifier,
  folderId: identifier,
  version: z.number().int().positive(),
  sourceConversationId: identifier,
  sourceTaskId: identifier.optional(),
  file: ReferencePackFileSchema,
  createdAt: z.string().datetime({ offset: true }),
  includesP0: z.boolean(),
});

export const SubjectFolderSchema = z.object({
  id: identifier,
  name: z.string().trim().min(1).max(128),
  expanded: z.boolean().optional(),
  versions: z.array(ReferencePackVersionSchema),
});

export const SubjectChatBindingSchema = z.object({
  folderId: identifier,
  kind: z.enum(["pack", "article"]),
  packVersionId: identifier.nullable(),
  pinned: z.boolean().optional(),
  archived: z.boolean().optional(),
  generation: z.number().int().nonnegative(),
  restartRequired: z.boolean().optional(),
});

export const ContentSubjectWorkspaceSchema = z.object({
  schemaVersion: z.literal(1),
  revision: z.number().int().nonnegative(),
  folders: z.array(SubjectFolderSchema),
  bindings: z.record(identifier, SubjectChatBindingSchema),
}).superRefine((state, context) => {
  const folders = new Map<string, z.infer<typeof SubjectFolderSchema>>();
  const versions = new Map<string, z.infer<typeof ReferencePackVersionSchema>>();
  for (const [folderIndex, folder] of state.folders.entries()) {
    if (folders.has(folder.id)) {
      context.addIssue({ code: "custom", path: ["folders", folderIndex, "id"], message: "主体标识重复" });
    }
    folders.set(folder.id, folder);
    const numbers = new Set<number>();
    for (const [versionIndex, version] of folder.versions.entries()) {
      if (version.folderId !== folder.id || versions.has(version.id) || numbers.has(version.version)) {
        context.addIssue({ code: "custom", path: ["folders", folderIndex, "versions", versionIndex], message: "资料包版本归属或标识无效" });
      }
      numbers.add(version.version);
      versions.set(version.id, version);
    }
  }
  for (const [conversationId, binding] of Object.entries(state.bindings)) {
    const version = binding.packVersionId === null ? null : versions.get(binding.packVersionId);
    if (!folders.has(binding.folderId) || (binding.packVersionId !== null && (!version || version.folderId !== binding.folderId))) {
      context.addIssue({ code: "custom", path: ["bindings", conversationId], message: "聊天引用了不存在或其他主体的资料包" });
    }
  }
  for (const version of versions.values()) {
    if (state.bindings[version.sourceConversationId]?.folderId !== version.folderId) {
      context.addIssue({ code: "custom", path: ["bindings", version.sourceConversationId], message: "资料包来源聊天必须属于同一主体" });
    }
  }
});

export type ReferencePackFile = z.infer<typeof ReferencePackFileSchema>;
export type ReferencePackVersion = z.infer<typeof ReferencePackVersionSchema>;
export type SubjectFolder = z.infer<typeof SubjectFolderSchema>;
export type SubjectChatBinding = z.infer<typeof SubjectChatBindingSchema>;
export type ContentSubjectWorkspace = z.infer<typeof ContentSubjectWorkspaceSchema>;

export class ContentSubjectWorkspaceError extends Error {
  constructor(public readonly code: string, message: string) {
    super(message);
    this.name = "ContentSubjectWorkspaceError";
  }
}

/** 所有状态操作均为纯函数；调用方负责持久化和并发修订检查。 */
export function emptySubjectWorkspace(): ContentSubjectWorkspace {
  return { schemaVersion: 1, revision: 0, folders: [], bindings: {} };
}

/** 无效或串主体的存储数据直接拒绝，由调用方决定如何提示或恢复。 */
export function parseSubjectWorkspace(value: unknown): ContentSubjectWorkspace {
  return ContentSubjectWorkspaceSchema.parse(value);
}

function requireFolder(state: ContentSubjectWorkspace, folderId: string): SubjectFolder {
  const folder = state.folders.find((item) => item.id === folderId);
  if (!folder) throw new ContentSubjectWorkspaceError("folder_not_found", "找不到该主体文件夹");
  return folder;
}

function requireBinding(state: ContentSubjectWorkspace, conversationId: string): SubjectChatBinding {
  const binding = Object.hasOwn(state.bindings, conversationId) ? state.bindings[conversationId] : undefined;
  if (!binding) throw new ContentSubjectWorkspaceError("chat_not_bound", "聊天尚未归入主体文件夹");
  return binding;
}

export function createSubjectFolder(state: ContentSubjectWorkspace, name: string, id: string): ContentSubjectWorkspace {
  const next = parseSubjectWorkspace(state);
  const folder = SubjectFolderSchema.parse({ id, name, expanded: true, versions: [] });
  if (next.folders.some((item) => item.id === folder.id)) {
    throw new ContentSubjectWorkspaceError("folder_exists", "主体标识已存在");
  }
  if (next.folders.some((item) => item.name.trim().toLowerCase() === folder.name.toLowerCase())) {
    throw new ContentSubjectWorkspaceError("folder_name_exists", "该主体文件夹已存在，请使用已有主体");
  }
  next.folders.unshift(folder);
  next.revision += 1;
  return next;
}

/** 新文章只在首次绑定时引用最新已确认版本，已有聊天不会悄悄换版。 */
export function bindSubjectChat(state: ContentSubjectWorkspace, input: {
  conversationId: string;
  folderId: string;
  kind: SubjectChatBinding["kind"];
}): ContentSubjectWorkspace {
  const next = parseSubjectWorkspace(state);
  identifier.parse(input.conversationId);
  z.enum(["pack", "article"]).parse(input.kind);
  requireFolder(next, input.folderId);
  const previous = Object.hasOwn(next.bindings, input.conversationId) ? next.bindings[input.conversationId] : undefined;
  if (previous) {
    if (previous.folderId !== input.folderId || previous.kind !== input.kind) {
      throw new ContentSubjectWorkspaceError("chat_already_bound", "聊天已归入其他主体或用途");
    }
    return state;
  }
  // defineProperty 避免外部会话标识成为对象原型赋值。
  Object.defineProperty(next.bindings, input.conversationId, {
    value: { folderId: input.folderId, kind: input.kind, packVersionId: input.kind === "article" ? latestSubjectPack(next, input.folderId)?.id ?? null : null, generation: 0 },
    enumerable: true, configurable: true, writable: true,
  });
  next.revision += 1;
  return next;
}

export function latestSubjectPack(state: ContentSubjectWorkspace, folderId: string): ReferencePackVersion | null {
  const folder = requireFolder(state, folderId);
  return folder.versions.reduce<ReferencePackVersion | null>((latest, version) => !latest || version.version > latest.version ? version : latest, null);
}

export function boundSubjectPack(state: ContentSubjectWorkspace, conversationId: string): ReferencePackVersion | null {
  const binding = requireBinding(state, conversationId);
  return requireFolder(state, binding.folderId).versions.find((version) => version.id === binding.packVersionId) ?? null;
}

/** 有新版仅给提示，绝不修改已有文章所绑定的版本。 */
export function subjectPackUpdateAvailable(state: ContentSubjectWorkspace, conversationId: string): ReferencePackVersion | null {
  const binding = requireBinding(state, conversationId);
  const latest = latestSubjectPack(state, binding.folderId);
  return latest && latest.id !== binding.packVersionId ? latest : null;
}

/** 只有工作流确认后的真实资料包产物才可登记；界面标签不能当作确认依据。 */
export function publishSubjectPack(state: ContentSubjectWorkspace, input: {
  folderId: string;
  sourceConversationId: string;
  sourceTaskId?: string;
  file: ReferencePackFile;
  includesP0: boolean;
  confirmed: true;
  id: string;
  createdAt: string;
}): ContentSubjectWorkspace {
  const next = parseSubjectWorkspace(state);
  if (input.confirmed !== true) {
    throw new ContentSubjectWorkspaceError("pack_not_confirmed", "资料包尚未完成确认，不能登记为可引用版本");
  }
  const folder = requireFolder(next, input.folderId);
  const source = requireBinding(next, input.sourceConversationId);
  if (source.folderId !== folder.id) {
    throw new ContentSubjectWorkspaceError("cross_subject_pack", "资料包来源不属于当前主体");
  }
  const file = ReferencePackFileSchema.parse(input.file);
  // 同一聊天同一产物的轮询和重试不产生新版；同一 Job 的 P0 新产物仍可登记。
  const duplicate = folder.versions.find((version) => version.sourceConversationId === input.sourceConversationId && version.file.fileUrl === file.fileUrl);
  if (duplicate) return state;
  if (next.folders.some((item) => item.versions.some((version) => version.id === input.id))) {
    throw new ContentSubjectWorkspaceError("pack_version_exists", "资料包版本标识已存在");
  }
  const version = ReferencePackVersionSchema.parse({
    id: input.id, folderId: folder.id, version: (latestSubjectPack(next, folder.id)?.version ?? 0) + 1,
    sourceConversationId: input.sourceConversationId, sourceTaskId: input.sourceTaskId,
    file, includesP0: input.includesP0, createdAt: input.createdAt,
  });
  folder.versions.push(version);
  next.revision += 1;
  return next;
}

/** 已有运行任务时必须重建运行上下文，不能只换界面徽标继续投递到旧任务。 */
export function switchSubjectPack(state: ContentSubjectWorkspace, input: {
  conversationId: string;
  versionId: string;
  hasTask: boolean;
}): ContentSubjectWorkspace {
  const next = parseSubjectWorkspace(state);
  z.boolean().parse(input.hasTask);
  const binding = requireBinding(next, input.conversationId);
  const version = next.folders.flatMap((folder) => folder.versions).find((item) => item.id === input.versionId);
  if (!version) throw new ContentSubjectWorkspaceError("pack_version_not_found", "找不到该资料包版本");
  if (version.folderId !== binding.folderId) {
    throw new ContentSubjectWorkspaceError("cross_subject_pack", "不能引用其他主体的资料包");
  }
  if (binding.packVersionId === version.id) return state;
  binding.packVersionId = version.id;
  binding.generation += 1;
  if (input.hasTask) binding.restartRequired = true;
  next.revision += 1;
  return next;
}

/** 仅可在对应代际的旧任务上下文已解绑后调用，防止迟到回复清除新的重建标记。 */
export function acknowledgeSubjectChatRestart(state: ContentSubjectWorkspace, conversationId: string, expectedGeneration: number): ContentSubjectWorkspace {
  const next = parseSubjectWorkspace(state);
  const binding = requireBinding(next, conversationId);
  if (binding.generation !== expectedGeneration) {
    throw new ContentSubjectWorkspaceError("stale_generation", "聊天引用已更新，请刷新后重试");
  }
  if (!binding.restartRequired) return state;
  binding.restartRequired = false;
  next.revision += 1;
  return next;
}

export function updateSubjectChatMetadata(state: ContentSubjectWorkspace, conversationId: string, patch: {
  pinned?: boolean;
  archived?: boolean;
}): ContentSubjectWorkspace {
  const next = parseSubjectWorkspace(state);
  const binding = requireBinding(next, conversationId);
  const validated = z.object({ pinned: z.boolean().optional(), archived: z.boolean().optional() }).strict().parse(patch);
  let changed = false;
  for (const key of ["pinned", "archived"] as const) {
    if (validated[key] !== undefined && binding[key] !== validated[key]) {
      binding[key] = validated[key];
      changed = true;
    }
  }
  if (!changed) return state;
  next.revision += 1;
  return next;
}

/** Only empty folders without versions or chat bindings may be removed locally. */
export function deleteSubjectFolder(state: ContentSubjectWorkspace, folderId: string): ContentSubjectWorkspace {
  const next = parseSubjectWorkspace(state);
  const folder = requireFolder(next, folderId);
  if (folder.versions.length) throw new ContentSubjectWorkspaceError("folder_has_versions", "该文件夹包含已确认资料包版本，暂不支持删除");
  if (Object.values(next.bindings).some(binding => binding.folderId === folderId)) throw new ContentSubjectWorkspaceError("folder_has_bindings", "该文件夹仍有绑定聊天，暂不支持删除");
  next.folders = next.folders.filter(item => item.id !== folderId);
  next.revision += 1;
  return next;
}

/** 删除无版本且无聊天绑定的空主体文件夹。 */
export 