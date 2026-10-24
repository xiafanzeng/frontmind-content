import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { bindSubjectChat, createSubjectFolder, emptySubjectWorkspace } from "../contracts/content-subject-workspace";
import { NATIVE_PACK_REQUIRED_MEMBERS, projectConfirmedNativePack, type ConfirmedNativePackInput } from "../server/confirmed-native-pack";
import { parseContentRunnerState } from "../server/state";

const sha = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");

/** 纯投影单测注入宿主验证端口的合成事实；不将其冒充完整ZIP/原生validator集成测试。 */
function fixture(p0 = false, route: "create" | "import" = "create"): ConfirmedNativePackInput {
  let workspace = createSubjectFolder(emptySubjectWorkspace(), "合成样例主体", "sample");
  workspace = bindSubjectChat(workspace, { conversationId: "chat", folderId: "sample", kind: "pack" });
  const packBytes = Buffer.from(`合成的已验证归档字节 ${p0} ${route}`);
  const packHash = sha(packBytes);
  const positioningConfirmation = {
    schema_version: "4.11", artifact_type: "frontmind_core_positioning_confirmation",
    confirmed: true, confirmed_at: "2026-10-24T08:00:00.000Z", pack_id: "rp_0123456789abcdef",
    source_pack_version: 1, positioning_revision: 5,
  };
  const readiness = { positioning_ready: true, p0_ready: p0 };
  const state = {
    schema_version: "4.11", artifact_type: "frontmind_content_job_state", workflow_version: "4.11",
    job_id: "native-job", job_kind: p0 ? "p0" : "reference_pack", updated_at: "2026-10-24T09:00:00.000Z",
    stage: "reference_pack", status: p0 ? "p0_ready" : "positioning_ready", revision: 12,
    current_pause: null, pending_action: null, flags: {}, p0_route: p0 ? route : null,
    decisions: {
      core_positioning_confirmation: positioningConfirmation,
      ...(p0 && route === "create" ? { p0_blueprint_confirmation: { revision: 8, confirmed_at: "2026-10-24T08:30:00.000Z" } } : {}),
    },
    metadata: { reference_pack_delivery: {
      pack_id: positioningConfirmation.pack_id, pack_version: p0 ? 2 : 1, brand_name: "合成样例主体",
      portable_zip_path: "/sandbox/jobs/native-job/deliverables/pack.zip", portable_zip_sha256: `sha256:${packHash}`, readiness,
    } },
  };
  const bytes = Buffer.from(JSON.stringify(state));
  const stateId = `artifact_${"a".repeat(64)}`;
  const manifest = { schema_version: "4.1", profile: "frontmind-content-reference-pack", pack_id: positioningConfirmation.pack_id,
    pack_version: p0 ? 2 : 1, brand_name: "合成样例主体", readiness };
  return {
    workspace, scope: { ownerUserId: 7, projectId: "project", conversationId: "chat", taskId: "task", operationId: "operation" },
    conversation: { id: "chat", purpose: "content_production", taskId: "task" },
    task: { id: "task", operationId: "operation", ownerUserId: 7, projectId: "project", context: {
      revision: 1, accountUserId: 7, enterpriseProjectId: "project", purpose: "content_production", knowledgeBase: null, knowledgeText: null,
      contentProduction: { mode: "new_reference_pack", enterpriseName: "合成样例主体", knowledgeSource: "files", monitoringAnswerAssetIds: [] },
    } },
    observation: { artifactId: stateId, sha256: sha(bytes), eventId: "state-event", providerRank: 8, state: parseContentRunnerState(bytes)! },
    stateArtifact: { id: stateId, taskId: "task", operationId: "operation", sourceEventId: "state-event", validationState: "valid", contentSha256: sha(bytes), sizeBytes: bytes.length, filename: "state.json", bytes },
    packArtifact: { id: `artifact_${"b".repeat(64)}`, taskId: "task", operationId: "operation", sourceEventId: "pack-event", validationState: "valid", contentSha256: packHash, sizeBytes: packBytes.length, filename: "真实资料包.zip", bytes: packBytes },
    pack: { validatedZipSha256: packHash, manifest, positioningConfirmation,
      validation: { validator: "v4.11_reference_pack_4.1", status: "pass", errors: [], pack_id: manifest.pack_id, pack_version: manifest.pack_version, readiness },
      ...(p0 ? { p0Record: { artifact_type: "frontmind_p0_record", pack_id: manifest.pack_id, pack_version: 2, source_pack_version: 1,
        route, p0_revision: 11, created_at: "2026-10-24T08:59:00.000Z", paths: { markdown: "p0/p0_brand_article.md", html: "p0/p0.html", docx: "p0/p0.docx", title_map: "p0/p0_title_map.json" } } } : {}),
    },
  };
}

function replaceRawState(input: ConfirmedNativePackInput, edit: (state: any) => void) {
  const state = JSON.parse(input.stateArtifact.bytes.toString()); edit(state);
  const bytes = Buffer.from(JSON.stringify(state)); input.stateArtifact.bytes = bytes;
  input.stateArtifact.sizeBytes = bytes.length; input.stateArtifact.contentSha256 = sha(bytes); input.observation.sha256 = sha(bytes);
  const parsed = parseContentRunnerState(bytes); if (parsed) input.observation.state = parsed;
}

describe("确认资料包的服务器纯证据投影", () => {
  it("定位确认及真实交付证据齐全才登记，保留来源和受鉴权下载路径", () => {
    const input = fixture(), original = structuredClone(input.workspace);
    const saved = projectConfirmedNativePack(input);
    expect(saved.revision).toBe(input.workspace.revision + 1);
    expect(saved.folders[0].versions[0]).toMatchObject({ includesP0: false, sourceConversationId: "chat", sourceTaskId: "task", file: { fileUrl: `/api/frontmind/v2/artifacts/${input.packArtifact.id}/content` } });
    expect(input.workspace).toEqual(original);
  });

  it("P0新建须有蓝图确认；导入沿用明确import路由，不伪造蓝图确认", () => {
    expect(projectConfirmedNativePack(fixture(true)).folders[0].versions[0].includesP0).toBe(true);
    expect(projectConfirmedNativePack(fixture(true, "import")).folders[0].versions[0].includesP0).toBe(true);
    const bad = fixture(true); replaceRawState(bad, state => { delete state.decisions.p0_blueprint_confirmation; });
    expect(projectConfirmedNativePack(bad)).toBe(bad.workspace);
  });

  it("轮询与同内容不同产物事件幂等，不增加版本", () => {
    const input = fixture(), saved = projectConfirmedNativePack(input); input.workspace = saved;
    expect(projectConfirmedNativePack(input)).toBe(saved);
    input.packArtifact.id = `artifact_${"c".repeat(64)}`;
    expect(projectConfirmedNativePack(input)).toBe(saved);
  });

  it("MySQL JSON键顺序变化不影响原始状态核验", () => {
    const input = fixture(); input.observation.state = Object.fromEntries(Object.entries(input.observation.state).reverse()) as typeof input.observation.state;
    expect(projectConfirmedNativePack(input).folders[0].versions).toHaveLength(1);
  });

  it("冻结原CLI交付证明有独立来源绑定，不能伪造validator pass或省略canonical成员", () => {
    const input = fixture();
    input.task.context!.contentWorkflow = { version: "4.13.2-v16.8.3", filename: "workflow.zip", rootDirectory: "workflow", sha256: "e".repeat(64), runtime: "native_content_v1" };
    replaceRawState(input, state => { state.metadata.reference_pack_delivery.status = "created"; });
    input.pack.validation = { source: "frozen_native_cli_delivery", workflowSha256: "e".repeat(64), stateArtifactSha256: input.stateArtifact.contentSha256, zipSha256: input.packArtifact.contentSha256, members: [...NATIVE_PACK_REQUIRED_MEMBERS] };
    expect(projectConfirmedNativePack(input).folders[0].versions).toHaveLength(1);
    (input.pack.validation as any).workflowSha256 = "f".repeat(64);
    expect(projectConfirmedNativePack(input)).toBe(input.workspace);
    (input.pack.validation as any).workflowSha256 = "e".repeat(64); (input.pack.validation as any).members.pop();
    expect(projectConfirmedNativePack(input)).toBe(input.workspace);
  });

  it.each([
    ["账号", (value: ConfirmedNativePackInput) => { value.task.ownerUserId = 8; }],
    ["企业项目", (value: ConfirmedNativePackInput) => { value.task.projectId = "foreign"; }],
    ["聊天绑定任务", (value: ConfirmedNativePackInput) => { value.conversation.taskId = "foreign"; }],
    ["冻结目的", (value: ConfirmedNativePackInput) => { value.task.context!.purpose = "enterprise_qa"; }],
    ["产物所属任务", (value: ConfirmedNativePackInput) => { value.packArtifact.taskId = "foreign"; }],
    ["产物所属operation", (value: ConfirmedNativePackInput) => { value.packArtifact.operationId = "foreign"; }],
    ["未验证产物", (value: ConfirmedNativePackInput) => { value.packArtifact.validationState = "staged"; }],
    ["ZIP字节篡改", (value: ConfirmedNativePackInput) => { value.packArtifact.bytes = Buffer.from("被替换的字节"); }],
    ["状态事件不匹配", (value: ConfirmedNativePackInput) => { value.stateArtifact.sourceEventId = "foreign"; }],
    ["ZIP验证报告绑定错误", (value: ConfirmedNativePackInput) => { value.pack.validatedZipSha256 = "d".repeat(64); }],
    ["包系列不一致", (value: ConfirmedNativePackInput) => { (value.pack.manifest as any).pack_id = "rp_ffffffffffffffff"; }],
    ["未确认定位", (value: ConfirmedNativePackInput) => { (value.pack.positioningConfirmation as any).confirmed = false; }],
    ["验证失败", (value: ConfirmedNativePackInput) => { (value.pack.validation as any).status = "fail"; }],
  ])("%s证据不足时不登记、不误报已确认", (_label, edit) => {
    const input = fixture(); edit(input); expect(projectConfirmedNativePack(input)).toBe(input.workspace);
  });

  it("交付状态名或文件名不能替代原始交付哈希和确认事实", () => {
    const missing = fixture(); replaceRawState(missing, state => { delete state.metadata.reference_pack_delivery; });
    expect(projectConfirmedNativePack(missing)).toBe(missing.workspace);
    const noConfirm = fixture(); replaceRawState(noConfirm, state => { state.decisions.core_positioning_confirmation.confirmed = false; });
    expect(projectConfirmedNativePack(noConfirm)).toBe(noConfirm.workspace);
    const p0Mismatch = fixture(true); (p0Mismatch.pack.p0Record as any).pack_version = 99;
    expect(projectConfirmedNativePack(p0Mismatch)).toBe(p0Mismatch.workspace);
  });
});
