// 纯本机合成演示：浏览器存储中持久化，不调用业务接口或模型。
import type {ContentBusinessClient, ModuleContext} from "../module/client/runtime";
import type {ContentConversation, ContentMessage, TaskResponse} from "../module/client/host";
import {parseSubjectWorkspace, type ContentSubjectWorkspace} from "../module/contracts/content-subject-workspace";
import {
  CONTENT_PRODUCTION_CONFIRMATION_ACTIONS,
  contentProductionActionSchema,
  contentProductionConfirmationSchema,
  contentProductionInputSchema,
  contentProductionStagePosition,
  type ContentProductionAction,
  type ContentProductionDto,
} from "../module/contracts/content-production";

const STORAGE_KEY = "frontmind-content-folder-demo-v1";
const WORKSPACE_ID = "local-offline-subject-folders";
const LOCAL_ATTACHMENT_LIMIT = 2 * 1024 * 1024;
const LOCAL_ATTACHMENT_HINT = "离线演示单个附件限 2 MB；请使用小型合成资料。文件只保存在当前浏览器，不会上传到服务器。";
const validateDemoAttachment = (file: File): string | null => file.size > LOCAL_ATTACHMENT_LIMIT ? LOCAL_ATTACHMENT_HINT : null;
type WorkspaceClient = ContentBusinessClient & {
  readSubjectWorkspace(): Promise<ContentSubjectWorkspace>;
  saveSubjectWorkspace(value: ContentSubjectWorkspace): Promise<ContentSubjectWorkspace>;
  localAsset(fileId: string): {dataUrl: string; filename: string; mimeType: string} | null;
  validateAttachment(file: File): string | null;
  attachmentHint: string;
};
type DemoTask = {
  conversationId: string;
  generation: number;
  initialized: boolean;
  status: string;
  progress: ContentProductionDto;
  selections: Record<string, string>;
  deliveredPackVersionId?: string;
};
type DemoAsset = {id: string; name: string; mimeType: string; dataUrl: string};
type DemoStore = {
  schemaVersion: 1;
  subjectWorkspace: ContentSubjectWorkspace;
  conversations: ContentConversation[];
  tasks: Record<string, DemoTask>;
  requests: Record<string, {signature: string; response: TaskResponse}>;
  assets: Record<string, DemoAsset>;
};

const copy = <T,>(value: T): T => structuredClone(value);
const textFile = (name: string, content: string) => ({
  fileUrl: `data:text/plain;charset=utf-8,${encodeURIComponent(content)}`,
  fileName: name,
  mimeType: "text/plain",
});
const stageTitles: Record<string, string> = {
  awaiting_reference_pack_input: "提供主体资料",
  awaiting_competitor_selection: "确认比较范围",
  awaiting_core_positioning_direction: "选择核心定位方向",
  awaiting_core_positioning_confirmation: "确认核心定位",
  positioning_ready: "资料包已确认",
  awaiting_p0_route: "选择品牌长文制作方式",
  awaiting_p0_example_confirmation: "选择品牌长文例文",
  awaiting_p0_blueprint_confirmation: "确认 P0 写作蓝图",
  p0_ready: "品牌长文交付结构示意",
  awaiting_question_research_inputs: "导入监控问答与信源",
  awaiting_question_selection: "选择本轮问题",
  awaiting_response_brief: "确认应答要求与品牌认知",
  awaiting_pattern_confirmation: "选择文章类型",
  awaiting_example_confirmation: "分别选择文风与构思参考",
  awaiting_question_positioning_confirmation: "确认本题定位",
  awaiting_blueprint_confirmation: "确认写作蓝图",
  completed: "交付结构示意已保存",
};

function progressFor(name: string, kind: "reference_pack" | "p0" | "article", status: string, revision = 0): ContentProductionDto {
  const confirmation = contentProductionConfirmationSchema.safeParse(status);
  const position = contentProductionStagePosition(null, status);
  const articleCompetitors = kind === "article" && status === "awaiting_competitor_selection";
  return {
    mode: kind === "reference_pack" ? "new_reference_pack" : kind === "p0" ? "p0" : "single_article",
    enterpriseName: name,
    workflowVersion: "4.13.2-v16.8-app1",
    workflowStatus: status,
    currentStage: status,
    jobKind: kind,
    runnerRevision: revision,
    pauseTitle: confirmation.success ? articleCompetitors ? "确认本题两家比较对象" : stageTitles[status] ?? "当前内容确认" : null,
    choices: status === "awaiting_example_confirmation"
      ? ["文风方案 A：参考匹配例文写法", "文风方案 B：工作流写作规范", "构思参考文章池：1、5；选 1—2 篇或明确不采用。文风和构思参考分别选择后统一确认。"]
      : articleCompetitors
        ? ["P02 请按顺序填写两家不同的比较对象，不包含本主体。", "本题比较对象与资料包中的整体比较范围分别保存；确认本题对象不会修改资料包定位。"]
      : status === "awaiting_question_selection"
        ? [`1. 如何了解${name}？`, `2. ${name}的服务或产品有哪些特点？`, "离线演示监控期次：2026-10-10；可输入自己的完整问题。"]
        : status === "awaiting_core_positioning_direction"
          ? ["方向 A：以有材料依据的服务范围为中心", "方向 B：以适用场景与表达边界为中心"]
          : [],
    productionStep: null,
    confirmation: confirmation.success ? confirmation.data : null,
    progressPosition: position,
    completedConfirmations: [],
    availableActions: confirmation.success ? [...CONTENT_PRODUCTION_CONFIRMATION_ACTIONS[confirmation.data]] : [],
    knowledgeBase: null,
    source: "runner_job_state",
  };
}

function seed(): DemoStore {
  const at = Date.now() - 600_000;
  const pack = (id: string, version: number, includesP0: boolean) => ({
    id, folderId: "tx", version, sourceConversationId: "tx-pack", sourceTaskId: "demo-task-tx-pack",
    file: textFile(`台心医美_资料包_v${version}_离线演示.txt`, `【离线演示，合成材料】\n主体：台心医美\n资料包版本：v${version}\n包含 P0 示例：${includesP0 ? "是" : "否"}\n这是结构与引用关系示例，不含真实企业资料或生成结果。`),
    createdAt: new Date(at + version).toISOString(), includesP0,
  });
  const subjectWorkspace: ContentSubjectWorkspace = {
    schemaVersion: 1, revision: 0,
    folders: [{id: "tx", name: "台心医美", versions: [pack("tx-v1", 1, false), pack("tx-v2", 2, true)]}, {id: "rn", name: "仁南医生", versions: []}],
    bindings: {
      "tx-pack": {folderId: "tx", kind: "pack", packVersionId: "tx-v2", generation: 0},
      "tx-article": {folderId: "tx", kind: "article", packVersionId: "tx-v1", generation: 0},
      "tx-article2": {folderId: "tx", kind: "article", packVersionId: "tx-v2", generation: 0},
      "rn-pack": {folderId: "rn", kind: "pack", packVersionId: null, generation: 0},
    },
  };
  const message = (id: string, content: string, position: number, offset: number, role: "user" | "assistant" = "assistant"): ContentMessage => ({id, role, content, contentWorkflowPosition: position, contentWorkflowGeneration: 0,
    contentWorkflowKind: position <= 7 ? "reference_pack" : position <= 12 ? "p0" : "article",
    contentWorkflowStatus: ({1: "awaiting_reference_pack_input", 5: "awaiting_core_positioning_direction", 7: "positioning_ready", 8: "awaiting_p0_route", 9: "awaiting_p0_example_confirmation", 10: "awaiting_p0_blueprint_confirmation", 13: "awaiting_question_selection", 14: "awaiting_response_brief", 15: "awaiting_pattern_confirmation", 16: "awaiting_example_confirmation"} as Record<number, string>)[position], timestamp: at + offset});
  const rows: ContentConversation[] = [
    {id: "tx-pack", title: "品牌资料包", taskId: "demo-task-tx-pack", purpose: "content_production", status: "completed", createdAt: at, updatedAt: at + 3,
      messages: [message("tx-materials", "【离线演示】已登记合成主体简介与产品服务材料。", 1, 1), message("tx-positioning", "【离线演示】已确认比较范围与核心定位的结构示例。", 5, 2), {...message("tx-pack-ready", "【离线演示】资料包 v1、v2 已保存。新文章默认引用 v2；已有文章继续保留原引用版本。", 7, 3), outputFiles: [subjectWorkspace.folders[0].versions[1].file]}]},
    {id: "tx-article", title: "品牌深度文章 · 示例 A", taskId: "demo-task-tx-article", purpose: "content_production", status: "awaiting_input", createdAt: at + 10, updatedAt: at + 13,
      messages: [message("tx-a-input", "为台心医美制作品牌长文，使用本篇已绑定的资料包 v1。", 8, 10, "user"), message("tx-a-examples", "【离线演示】已采用工作流写作规范；不生成真实例文或内容。", 9, 11), {...message("tx-a-blueprint", "【离线演示】请确认 P0 蓝图：主体与业务范围、服务展开、适用场景、表达边界。当前绑定 v1；切换资料包须手动确认并重新核对。", 10, 13), outputFiles: [textFile("P0_写作蓝图_离线演示.txt", "【离线演示】P0 蓝图结构\n主体与业务范围\n服务或产品展开\n适用场景和证据边界\n本文件不是模型生成的真实写作蓝图。")]}]},
    {id: "tx-article2", title: "服务范围介绍 · 示例 B", taskId: "demo-task-tx-article2", purpose: "content_production", status: "awaiting_input", createdAt: at + 20, updatedAt: at + 24,
      messages: [message("tx-b-question", "选择问题：如何了解台心医美？", 13, 20, "user"), message("tx-b-response", "【离线演示】已记录：无额外要求；品牌认知不充分。", 14, 21), message("tx-b-pattern", "【离线演示】文章类型 P01，只介绍本主体。", 15, 22), message("tx-b-style", "【离线演示】先分别选文风 A/B 和构思参考，再统一核对提交。参考只决定构思用途，不能代替文风确认。", 16, 24)]},
    {id: "rn-pack", title: "建立品牌资料包", taskId: "demo-task-rn-pack", purpose: "content_production", status: "awaiting_input", createdAt: at + 30, updatedAt: at + 30,
      messages: [message("rn-materials", "【离线演示】当前文件夹还没有资料包。可在底部输入合成主体简介，或选择小型示例文件；所有数据只保存在当前浏览器。", 1, 30)]},
  ];
  const makeTask = (conversationId: string, kind: "reference_pack" | "p0" | "article", status: string, revision: number): DemoTask => ({conversationId, generation: 0, initialized: true, status: ["positioning_ready", "p0_ready", "completed"].includes(status) ? "completed" : "awaiting_input", progress: progressFor(conversationId === "rn-pack" ? "仁南医生" : "台心医美", kind, status, revision), selections: {}});
  return {schemaVersion: 1, subjectWorkspace, conversations: rows, tasks: {
    "demo-task-tx-pack": makeTask("tx-pack", "reference_pack", "positioning_ready", 8),
    "demo-task-tx-article": makeTask("tx-article", "p0", "awaiting_p0_blueprint_confirmation", 11),
    "demo-task-tx-article2": {...makeTask("tx-article2", "article", "awaiting_example_confirmation", 7), selections: {question: "如何了解台心医美？", pattern: "P01", requirements: "无额外要求", recognition: "insufficient"}},
    "demo-task-rn-pack": makeTask("rn-pack", "reference_pack", "awaiting_reference_pack_input", 0),
  }, requests: {}, assets: {}};
}

/** 合并独立的聊天写入；迟到的 save 不能覆盖 dispatch 刚追加的助手回复。 */
function mergeMessages(current: ContentMessage[], incoming: ContentMessage[]): ContentMessage[] {
  const map = new Map(current.map(message => [message.id, message]));
  for (const message of incoming) {
    const previous = map.get(message.id);
    const merged = {...previous, ...message};
    if (!message.generalChatDispatch) delete merged.generalChatDispatch;
    map.set(message.id, merged);
  }
  return [...map.values()].sort((a, b) => a.timestamp - b.timestamp);
}

export function folderDemoClient(storage: Storage = localStorage): {client: WorkspaceClient; context: ModuleContext} {
  let store: DemoStore;
  const persisted = storage.getItem(STORAGE_KEY);
  if (persisted) {
    try {
      const value = JSON.parse(persisted) as DemoStore;
      if (value.schemaVersion !== 1 || value.subjectWorkspace?.schemaVersion !== 1 || !Array.isArray(value.conversations) || !value.tasks || !value.requests || !value.assets) throw new Error("格式不兼容");
      value.subjectWorkspace = parseSubjectWorkspace(value.subjectWorkspace);
      store = value;
    } catch { throw new Error("本地离线示例存储损坏，已停止读取，未覆盖原数据。请备份后清理此站点的离线示例存储再重试。"); }
  } else {
    store = seed();
    storage.setItem(STORAGE_KEY, JSON.stringify(store));
  }
  function refreshStore() {
    const latest = storage.getItem(STORAGE_KEY);
    if (!latest) throw new Error("本地演示存储已被移除，请刷新页面重新初始化。");
    const value = JSON.parse(latest) as DemoStore;
    if (value.schemaVersion !== 1 || !Array.isArray(value.conversations) || !value.tasks || !value.requests || !value.assets) throw new Error("本地离线存储格式已变化，已停止写入。");
    value.subjectWorkspace = parseSubjectWorkspace(value.subjectWorkspace);
    store = value;
  }
  function transaction<T>(change: (next: DemoStore) => T): T {
    // 同站点另一个演示标签页可能刚保存了更高修订，写前重新读取再比较。
    refreshStore();
    const next = copy(store);
    const result = change(next);
    next.subjectWorkspace = parseSubjectWorkspace(next.subjectWorkspace);
    try { storage.setItem(STORAGE_KEY, JSON.stringify(next)); }
    catch { throw new Error("浏览器存储空间不足，本次操作没有保存。请减少演示附件大小后重试。"); }
    store = next;
    return copy(result);
  }
  function taskIdFor(conversationId: string) { return `demo-task-${conversationId}`; }
  function makeTask(next: DemoStore, conversationId: string): DemoTask {
    const binding = next.subjectWorkspace.bindings[conversationId];
    const folder = next.subjectWorkspace.folders.find(item => item.id === binding?.folderId);
    const selected = folder?.versions.find(version => version.id === binding?.packVersionId);
    const kind = binding?.kind === "pack" ? "reference_pack" : selected?.includesP0 ? "article" : "p0";
    return {conversationId, generation: binding?.generation ?? 0, initialized: false, status: "awaiting_input", progress: progressFor(folder?.name ?? "离线示例主体", kind, kind === "reference_pack" ? "awaiting_reference_pack_input" : kind === "article" ? "awaiting_question_selection" : "awaiting_p0_route"), selections: {}};
  }
  function response(id: string, task: DemoTask): TaskResponse { return {id, purpose: "content_production", status: task.status, contentProduction: copy(task.progress)}; }
  function resetForBoundPack(next: DemoStore, conversationId: string, reason: string) {
    const binding = next.subjectWorkspace.bindings[conversationId];
    const folder = next.subjectWorkspace.folders.find(item => item.id === binding.folderId)!;
    const selected = folder.versions.find(version => version.id === binding.packVersionId);
    const row = next.conversations.find(item => item.id === conversationId);
    const task = row?.taskId ? next.tasks[row.taskId] : undefined;
    if (task) {
      const kind = binding.kind === "pack" ? "reference_pack" : selected?.includesP0 ? "article" : "p0";
      task.generation = binding.generation;
      task.progress = progressFor(folder.name, kind, kind === "reference_pack" ? "awaiting_reference_pack_input" : kind === "article" ? "awaiting_question_selection" : "awaiting_p0_route", (task.progress.runnerRevision ?? 0) + 1);
      task.status = "awaiting_input"; task.selections = {};
      delete task.deliveredPackVersionId;
      if (row) {row.status = "awaiting_input"; row.updatedAt = Date.now(); row.messages.push({id: `demo-pack-switch-${conversationId}-${binding.generation}`, role: "assistant", timestamp: Date.now(), contentWorkflowPosition: contentProductionStagePosition(null, task.progress.workflowStatus), contentWorkflowStatus: task.progress.workflowStatus!, contentWorkflowGeneration: task.generation, contentWorkflowKind: task.progress.jobKind ?? undefined, content: `【离线演示】${reason}本主体资料包 v${selected?.version}。后续定位和蓝图需重新确认；旧交付仅作为历史记录保留，不会直接沿用。`});}
    }
    binding.restartRequired = false;
  }
  function bindWaitingArticles(next: DemoStore, folderId: string) {
    const folder = next.subjectWorkspace.folders.find(item => item.id === folderId)!;
    const latest = folder.versions.reduce<typeof folder.versions[number] | undefined>((result, version) => !result || version.version > result.version ? version : result, undefined);
    if (!latest) return;
    for (const [conversationId, binding] of Object.entries(next.subjectWorkspace.bindings)) {
      if (binding.folderId !== folderId || binding.kind !== "article" || binding.packVersionId !== null) continue;
      binding.packVersionId = latest.id; binding.generation++;
      resetForBoundPack(next, conversationId, "等待的资料包已确认，已自动带入");
    }
  }
  function setStage(task: DemoTask, status: string) {
    const previous = task.progress;
    const current = progressFor(previous.enterpriseName, previous.jobKind as "reference_pack" | "p0" | "article", status, (previous.runnerRevision ?? 0) + 1);
    current.mode = previous.mode;
    current.completedConfirmations = [...previous.completedConfirmations];
    if (previous.confirmation && previous.workflowStatus !== status) current.completedConfirmations = [...new Set([...current.completedConfirmations, previous.confirmation])];
    current.progressPosition = Math.max(previous.progressPosition, current.progressPosition);
    task.progress = current;
    task.status = ["positioning_ready", "p0_ready", "completed"].includes(status) ? "completed" : "awaiting_input";
  }
  function publishDemoPack(next: DemoStore, task: DemoTask, taskId: string) {
    const binding = next.subjectWorkspace.bindings[task.conversationId];
    const folder = next.subjectWorkspace.folders.find(item => item.id === binding?.folderId);
    if (!binding || !folder) throw new Error("当前聊天尚未绑定主体文件夹。");
    const version = Math.max(0, ...folder.versions.map(item => item.version)) + 1;
    const packVersion = {id: `${folder.id}-demo-v${version}-${task.progress.runnerRevision}`, folderId: folder.id, version, sourceConversationId: task.conversationId, sourceTaskId: taskId,
      file: textFile(`${folder.name}_资料包_v${version}_离线演示.txt`, `【离线演示，合成资料包】\n主体：${folder.name}\n版本：v${version}\n本轮说明：${task.selections.modification ?? "合成主体资料、比较范围和核心定位的确认结构。"}\n仅演示资料归档与版本引用；未执行模型研究或正文生成。`), createdAt: new Date().toISOString(), includesP0: task.progress.workflowStatus === "p0_ready"};
    folder.versions.push(packVersion);
    // P0 产物是新输出版本；来源文章的输入引用保持锁定，直到显式接续。
    if (binding.kind === "pack") binding.packVersionId = packVersion.id;
    if (task.progress.workflowStatus === "p0_ready") task.deliveredPackVersionId = packVersion.id;
    bindWaitingArticles(next, folder.id);
    next.subjectWorkspace.revision++;
    return packVersion.file;
  }
  function applyAction(next: DemoStore, task: DemoTask, action: ContentProductionAction, prompt: string, assets: string[]) {
    function articleComparators(selection: string): string[] {
      let values: unknown;
      try {
        const parsed: unknown = JSON.parse(selection);
        values = Array.isArray(parsed) ? parsed : parsed && typeof parsed === "object" ? (parsed as {competitors?: unknown}).competitors : null;
      } catch {values = selection.split(/[、,，\n]+/u);}
      if (!Array.isArray(values) || values.length !== 2 || values.some(value => typeof value !== "string" || !value.trim() || value.trim().length > 200)) throw new Error("P02 本题需要恰好两家不同的比较对象，请按顺序用顿号、逗号或 JSON 数组填写。");
      const names = (values as string[]).map(value => value.trim());
      const normalize = (value: string) => value.normalize("NFKC").toLocaleLowerCase().replace(/\s+/gu, "");
      const normalized = names.map(normalize);
      if (new Set(normalized).size !== 2) throw new Error("P02 两家比较对象不能重复，顺序将按输入保留。");
      const subject = normalize(task.progress.enterpriseName);
      if (subject && normalized.some(value => value.includes(subject))) throw new Error("P02 的两家比较对象不能包含本主体，请填写另外两家。");
      return names;
    }
    switch (action.kind) {
      case "provide_reference_pack_inputs":
        if (!assets.length && !prompt.trim()) throw new Error("请先提供合成主体资料或演示附件。");
        setStage(task, "awaiting_competitor_selection"); break;
      case "choose_reference_pack_route": setStage(task, action.route === "create" ? "awaiting_reference_pack_input" : task.progress.jobKind === "p0" ? "awaiting_p0_route" : "awaiting_question_selection"); break;
      case "update_competitor_selection": task.selections.competitors = task.progress.jobKind === "article" ? articleComparators(action.selection).join("、") : action.selection; setStage(task, "awaiting_competitor_selection"); break;
      case "confirm_competitors":
        if (task.progress.jobKind === "article") {articleComparators(task.selections.competitors ?? ""); setStage(task, "awaiting_example_confirmation");}
        else setStage(task, "awaiting_core_positioning_direction");
        break;
      case "choose_core_positioning_direction": task.selections.direction = action.direction; setStage(task, "awaiting_core_positioning_confirmation"); break;
      case "confirm_core_positioning": setStage(task, "positioning_ready"); break;
      case "choose_p0_route":
        if (action.route === "import" && !assets.length) throw new Error("导入 P0 需要附上本地演示文件。");
        task.selections.p0Route = action.route; setStage(task, "awaiting_p0_example_confirmation"); break;
      case "choose_p0_examples": task.selections.p0Examples = action.route; setStage(task, "awaiting_p0_blueprint_confirmation"); break;
      case "confirm_p0_blueprint":
        if (action.blueprintEdits) {task.selections.modification = action.blueprintEdits; setStage(task, "awaiting_p0_blueprint_confirmation");}
        else setStage(task, "p0_ready");
        break;
      case "provide_question_research_inputs":
        if (!assets.length && !prompt.trim()) throw new Error("请提供合成监控问答或演示附件。");
        setStage(task, "awaiting_question_selection"); break;
      case "choose_question": task.selections.question = action.selection; setStage(task, "awaiting_response_brief"); break;
      case "submit_response_brief": task.selections.requirements = action.noExtraRequirements ? "无额外要求" : action.requirements!; task.selections.recognition = action.aiBrandRecognition; setStage(task, "awaiting_pattern_confirmation"); break;
      case "confirm_pattern":
        task.selections.pattern = action.selectedPattern ?? "P01";
        if (task.selections.pattern === "P02") {delete task.selections.competitors; setStage(task, "awaiting_competitor_selection");}
        else setStage(task, "awaiting_example_confirmation");
        break;
      case "choose_examples": {
        const style = /(?:^|[；;\n])\s*文风\s*[:：]\s*([AB])\s*(?=$|[；;\n])/iu.exec(prompt);
        if (!style || style[1].toUpperCase() !== action.route) throw new Error("文风确认与原输入不一致，请分别核对文风和构思参考。");
        const match = /(?:文章池|构思参考)(?:构思参考|选择)?\s*[:：]\s*([^；;\n]+)/u.exec(prompt);
        const pool = match?.[1].trim();
        if (!pool) throw new Error("请分别选择文风与构思参考，确认时保留“文章池：1、5”或“文章池：不采用”。");
        if (pool !== "不采用") {
          const ids = pool.split(/[、,，\s]+/u).filter(Boolean);
          if (!ids.length || ids.length > 2 || ids.some(id => !/^[1-9]\d{0,3}$/u.test(id)) || new Set(ids).size !== ids.length) throw new Error("构思参考须为 1—2 个不同编号，或明确不采用。");
        }
        task.selections.style = action.route; task.selections.references = pool;
        setStage(task, "awaiting_question_positioning_confirmation"); break;
      }
      case "confirm_question_positioning": setStage(task, "awaiting_blueprint_confirmation"); break;
      case "confirm_blueprint":
        if (action.blueprintEdits) {task.selections.modification = action.blueprintEdits; setStage(task, "awaiting_blueprint_confirmation");}
        else setStage(task, "completed");
        break;
      case "revise_current_step": task.selections.modification = action.instructions; setStage(task, task.progress.workflowStatus!); break;
      case "repair_article_facts": throw new Error("离线演示没有真实正文和事实校验，不执行事实返工。");
    }
  }
  const client: WorkspaceClient = {
    attachmentHint: LOCAL_ATTACHMENT_HINT,
    validateAttachment: validateDemoAttachment,
    list: async () => {refreshStore(); return copy(store.conversations);},
    save: async value => transaction(next => {
      const existing = next.conversations.find(item => item.id === value.id);
      const taskId = existing?.taskId ?? value.taskId ?? taskIdFor(value.id);
      if (existing?.taskId && value.taskId && value.taskId !== existing.taskId) throw new Error("同一离线聊天不能替换任务编号。");
      const row: ContentConversation = {...existing, ...copy(value), taskId, purpose: "content_production", updatedAt: Math.max(existing?.updatedAt ?? 0, value.updatedAt), messages: mergeMessages(existing?.messages ?? [], value.messages)};
      if (!next.tasks[taskId]) next.tasks[taskId] = makeTask(next, row.id);
      row.status = next.tasks[taskId].status;
      next.conversations = [row, ...next.conversations.filter(item => item.id !== row.id)];
      return row;
    }),
    remove: async id => { transaction(next => {
      if (next.subjectWorkspace.folders.some(folder => folder.versions.some(version => version.sourceConversationId === id))) throw new Error("此聊天是已确认资料包的来源，请使用归档以保留版本依据。");
      const row = next.conversations.find(item => item.id === id);
      next.conversations = next.conversations.filter(item => item.id !== id);
      if (row?.taskId) delete next.tasks[row.taskId];
      delete next.subjectWorkspace.bindings[id]; next.subjectWorkspace.revision++;
    }); },
    upload: async file => {
      const invalid = validateDemoAttachment(file);
      if (invalid) throw new Error(invalid);
      const dataUrl = await new Promise<string>((resolve, reject) => {const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error("读取本地演示文件失败。")); reader.readAsDataURL(file);});
      return transaction(next => {const fileId = crypto.randomUUID(); next.assets[fileId] = {id: fileId, name: file.name, mimeType: file.type || "application/octet-stream", dataUrl}; return {fileId, filename: `${file.name}（本地模拟）`};});
    },
    task: async id => {
      refreshStore();
      const task = store.tasks[id];
      if (!task) throw new Error("未找到此聊天的本地演示任务。");
      return response(id, task);
    },
    stop: async id => { transaction(next => {const task = next.tasks[id]; if (!task) throw new Error("演示任务不存在。"); task.status = "cancelled"; const row = next.conversations.find(item => item.id === task.conversationId); if (row) row.status = "cancelled";}); },
    dispatch: async (input, requestedTaskId) => transaction(next => {
      const conversationId = typeof input.conversationId === "string" ? input.conversationId : "";
      const requestId = typeof input.clientRequestId === "string" ? input.clientRequestId : "";
      if (!conversationId || !requestId) throw new Error("离线提交缺少会话或请求编号。");
      const signature = JSON.stringify({input, requestedTaskId: requestedTaskId ?? null});
      const replay = next.requests[requestId];
      if (replay) {if (replay.signature !== signature) throw new Error("同一请求编号不能提交不同内容。"); return replay.response;}
      const row = next.conversations.find(item => item.id === conversationId);
      if (!row) throw new Error("请先保存本地聊天。");
      const binding = next.subjectWorkspace.bindings[conversationId];
      if (!binding) throw new Error("聊天尚未归属主体文件夹。");
      const folder = next.subjectWorkspace.folders.find(item => item.id === binding.folderId);
      if (!folder) throw new Error("主体文件夹不存在。");
      if (binding.kind === "article" && !folder.versions.some(item => item.id === binding.packVersionId)) throw new Error("本篇还没有绑定已确认资料包，请先完成同文件夹的资料包。");
      const taskId = row.taskId ?? taskIdFor(conversationId);
      if (requestedTaskId && requestedTaskId !== taskId) throw new Error("请求任务编号与当前聊天不匹配。");
      const task = next.tasks[taskId] ?? (next.tasks[taskId] = makeTask(next, conversationId));
      if (task.generation !== binding.generation) throw new Error("资料包引用已变化，请刷新并重新确认当前阶段。");
      if (!task.initialized && binding.kind === "article") {
        const latest = folder.versions.reduce((result, version) => version.version > result.version ? version : result, folder.versions[0]);
        if (binding.packVersionId !== latest?.id) throw new Error("新文章须先引用当前主体最新已确认资料包，再开始原生流程。");
      }
      const prompt = typeof input.prompt === "string" ? input.prompt : "";
      const assets = Array.isArray(input.localAssetIds) ? input.localAssetIds.filter((id): id is string => typeof id === "string") : [];
      if (assets.some(id => !next.assets[id])) throw new Error("本地演示附件已丢失，请重新选择文件。");
      if (input.contentProductionAction !== undefined) {
        const action = contentProductionActionSchema.parse(input.contentProductionAction);
        if (action.revision !== task.progress.runnerRevision || !task.progress.availableActions.includes(action.kind)) throw new Error("当前原生停点或修订号已变化，请刷新后按当前选项确认。");
        applyAction(next, task, action, prompt, assets);
      } else if (!task.initialized) {
        if (input.contentProduction) {
          const fields = contentProductionInputSchema.parse(input.contentProduction);
          const kind = binding.kind === "pack" ? "reference_pack" : fields.mode === "single_article" ? "article" : "p0";
          task.progress = progressFor(folder.name, kind, kind === "reference_pack" ? "awaiting_reference_pack_input" : kind === "article" ? "awaiting_question_selection" : "awaiting_p0_route");
        }
        task.initialized = true;
      } else if (task.progress.workflowStatus === "positioning_ready" && /继续\s*(?:P0|制作品牌长文|品牌长文)/iu.test(prompt)) {
        task.progress.jobKind = "p0"; task.progress.mode = "p0"; setStage(task, "awaiting_p0_route");
      } else if (task.progress.workflowStatus === "p0_ready" && /继续(?:选择问题并写文章|问题文章|问题与监控数据)/u.test(prompt)) {
        const produced = folder.versions.find(version => version.id === task.deliveredPackVersionId && version.includesP0 && version.sourceConversationId === conversationId && version.sourceTaskId === taskId);
        if (!produced) throw new Error("未找到当前 P0 原任务实际交付的含 P0 资料包，不能用文件夹任意最新版本代替。");
        binding.packVersionId = produced.id; binding.generation++; binding.restartRequired = false;
        task.generation = binding.generation; next.subjectWorkspace.revision++;
        task.progress.jobKind = "article"; task.progress.mode = "single_article"; setStage(task, "awaiting_question_selection");
      } else if (task.progress.workflowStatus === "positioning_ready" && /^(?:修改|更新)资料包[。！!]?$/u.test(prompt.trim())) {
        task.progress.jobKind = "reference_pack"; task.progress.mode = "refresh_reference_pack"; setStage(task, "awaiting_reference_pack_input");
      } else throw new Error("此阶段需要当前原生确认操作；离线演示不会根据普通文本跳过确认或自动生成。");
      task.initialized = true;
      const status = task.progress.workflowStatus!;
      const files = ["positioning_ready", "p0_ready"].includes(status) && task.progress.runnerRevision !== 0 ? [publishDemoPack(next, task, taskId)] : [];
      const detail = Object.entries(task.selections).map(([key, value]) => `${({style: "文风", references: "构思参考", question: "本轮问题", pattern: "文章类型", requirements: "应答要求", recognition: "品牌认知", modification: "修改说明", direction: "定位方向", competitors: task.progress.jobKind === "article" ? "本题比较对象（按输入顺序）" : "比较范围", p0Route: "P0 路径", p0Examples: "P0 例文"} as Record<string, string>)[key] ?? key}：${value}`).join("\n");
      const terminal = ["p0_ready", "completed"].includes(status);
      const articleComparison = task.progress.jobKind === "article" && status === "awaiting_competitor_selection";
      const reply: ContentMessage = {id: `demo-reply-${requestId}`, role: "assistant", timestamp: Date.now() + 1, contentWorkflowPosition: contentProductionStagePosition(null, status), contentWorkflowStatus: status, contentWorkflowGeneration: task.generation, contentWorkflowKind: task.progress.jobKind ?? undefined,
        content: `【离线演示】${articleComparison ? "请先填写并确认本题两家比较对象" : stageTitles[status] ?? "本轮选择已保存"}。\n${detail ? `${detail}\n` : ""}${articleComparison ? "本题比较对象与资料包整体比较范围独立保存；请保留顺序，不包含本主体。\n" : ""}${terminal ? "已保存交付结构示意，未运行模型、研究、编辑、标题生成或真实正文。" : "请按当前停点继续确认；本页只保存合成示例数据。"}`,
        ...(files.length ? {outputFiles: files} : {})};
      row.taskId = taskId; row.status = task.status; row.updatedAt = Date.now();
      // 直接调用演示客户端也保留输入；Runtime 已保存过时按请求编号去重。
      if (!row.messages.some(message => message.id === requestId)) row.messages.push({id: requestId, role: "user", content: prompt, timestamp: Date.now(), contentWorkflowPosition: reply.contentWorkflowPosition, contentWorkflowStatus: status, contentWorkflowGeneration: task.generation, contentWorkflowKind: task.progress.jobKind ?? undefined,
        attachments: assets.map(id => ({id, fileId: id, type: "file", name: `${next.assets[id].name}（本地模拟）`}))});
      row.messages = mergeMessages(row.messages, [reply]);
      const result = response(taskId, task);
      next.requests[requestId] = {signature, response: result};
      return result;
    }),
    readSubjectWorkspace: async () => {refreshStore(); return copy(store.subjectWorkspace);},
    saveSubjectWorkspace: async raw => transaction(next => {
      const value = parseSubjectWorkspace(raw);
      if (value.schemaVersion !== 1 || value.revision !== next.subjectWorkspace.revision + 1) throw new Error("主体资料已变化，请刷新后重新保存，本次没有覆盖较新数据。");
      for (const oldFolder of next.subjectWorkspace.folders) {
        const updated = value.folders.find(folder => folder.id === oldFolder.id);
        for (const version of oldFolder.versions) if (!updated || !updated.versions.some(item => JSON.stringify(item) === JSON.stringify(version))) throw new Error("已确认资料包历史版本不能被改写或删除。");
      }
      const confirmedIds = new Set(next.subjectWorkspace.folders.flatMap(folder => folder.versions.map(version => version.id)));
      if (value.folders.some(folder => folder.versions.some(version => !confirmedIds.has(version.id)))) throw new Error("新资料包只能由当前原生确认完成后登记，不能从界面存储伪造确认。");
      const ids = new Set<string>();
      for (const folder of value.folders) {
        if (!folder.id || !folder.name.trim() || ids.has(folder.id)) throw new Error("主体文件夹名称或编号无效。");
        ids.add(folder.id);
        for (const version of folder.versions) if (version.folderId !== folder.id || !Number.isInteger(version.version) || version.version < 1) throw new Error("资料包版本与主体文件夹不匹配。");
      }
      for (const [conversationId, binding] of Object.entries(value.bindings)) {
        const folder = value.folders.find(item => item.id === binding.folderId);
        if (!folder || !["pack", "article"].includes(binding.kind) || !Number.isInteger(binding.generation) || binding.generation < 0 || binding.packVersionId && !folder.versions.some(version => version.id === binding.packVersionId)) throw new Error("聊天引用的资料包版本无效或不属于当前主体。");
        const old = next.subjectWorkspace.bindings[conversationId];
        if (old && (old.folderId !== binding.folderId || old.kind !== binding.kind)) throw new Error("已有聊天不能改为其他主体或用途。");
        if (!old && binding.kind === "article") {
          const latest = folder.versions.reduce<typeof folder.versions[number] | undefined>((result, version) => !result || version.version > result.version ? version : result, undefined);
          if (binding.packVersionId !== (latest?.id ?? null)) throw new Error("新文章必须引用当前文件夹最新已确认资料包。");
        }
        const taskId = next.conversations.find(item => item.id === conversationId)?.taskId;
        const task = taskId ? next.tasks[taskId] : undefined;
        if (old && old.packVersionId !== binding.packVersionId && binding.generation !== old.generation + 1) throw new Error("已有聊天换版必须显式更新运行代次。");
        if (old && task && binding.generation !== old.generation) {
          if (binding.generation !== old.generation + 1) throw new Error("聊天重启代次必须连续递增。");
          if (!binding.restartRequired) throw new Error("已有任务换版须先显式确认重新核对后续阶段。");
        }
      }
      const previous = next.subjectWorkspace;
      next.subjectWorkspace = copy(value);
      for (const [conversationId, binding] of Object.entries(next.subjectWorkspace.bindings)) {
        const old = previous.bindings[conversationId];
        if (old && binding.generation !== old.generation) resetForBoundPack(next, conversationId, "已切换至");
        else if (!old) {
          const row = next.conversations.find(item => item.id === conversationId);
          if (row?.taskId && next.tasks[row.taskId] && !next.tasks[row.taskId].initialized) next.tasks[row.taskId] = makeTask(next, conversationId);
        }
      }
      for (const folder of next.subjectWorkspace.folders) bindWaitingArticles(next, folder.id);
      return next.subjectWorkspace;
    }),
    localAsset: fileId => {refreshStore(); const asset = store.assets[fileId]; return asset ? {dataUrl: asset.dataUrl, filename: asset.name, mimeType: asset.mimeType} : null;},
  };
  const activeKey = `frontmind-content-active:${WORKSPACE_ID}`;
  if (!store.conversations.some(row => row.id === storage.getItem(activeKey))) storage.setItem(activeKey, "tx-article");
  return {client, context: {module: "content", workspace: {id: WORKSPACE_ID, ownerUserId: 0}, marketEdition: "cn", capabilities: ["content"]}};
}
