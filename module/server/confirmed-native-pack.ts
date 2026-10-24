import { createHash } from "node:crypto";
import { parseContentRunnerState, type ContentRunnerObservation } from "./state";
import { publishSubjectPack, type ContentSubjectWorkspace } from "../contracts/content-subject-workspace";
import type { FrozenContentTaskContext } from "../contracts/task-context";

export interface NativePackArtifactEvidence {
  id: string;
  taskId: string;
  operationId: string;
  sourceEventId: string;
  validationState: string;
  contentSha256: string;
  sizeBytes: number;
  filename: string;
  bytes: Buffer;
}

/**
 * 只能由 Core 对同一已校验 ZIP 调用原生离线 validator 并读取固定成员后构造。
 * validatedZipSha256 绑定实际 ZIP；此对象从不接受浏览器请求字段。
 */
export interface ValidatedNativePackFacts {
  validatedZipSha256: string;
  validation: unknown;
  manifest: unknown;
  positioningConfirmation: unknown;
  p0Record?: unknown;
}

/** 原CLI已经完成完整校验后才生成delivery；宿主仍须核冻结脚本、实际ZIP及固定成员。 */
export const NATIVE_PACK_REQUIRED_MEMBERS = [
  "reference_pack.json", "materials/index.json", "registries/knowledge_registry.json",
  "registries/source_registry.json", "registries/claim_registry.json", "registries/image_registry.json",
  "research/brand_market/competitive_choice_map.json", "research/brand_market/competitive_choice_map.md",
  "research/brand_market/positioning_research_review.md", "research/brand_market/brand_reality.md",
  "research/brand_market/audience_choice_logic.md", "research/brand_market/competitor_landscape.md",
  "research/brand_market/market_opportunities.md", "research/brand_market/ai_semantic_context.md",
  "research/brand_market/source_index.json", "strategy/positioning_brief.md", "strategy/positioning_directions.json",
  "strategy/positioning_direction_decision.json", "strategy/core_positioning.md", "strategy/core_positioning.json",
  "strategy/positioning_writing_guidance.md", "strategy/core_positioning_confirmation.json",
] as const;
export const NATIVE_PACK_P0_MEMBERS = ["p0/p0_brand_article.md", "p0/p0.html", "p0/p0.docx", "p0/p0_title_map.json", "p0/p0_record.json"] as const;

export interface ConfirmedNativePackInput {
  workspace: ContentSubjectWorkspace;
  scope: { ownerUserId: number; projectId: string | null; conversationId: string; taskId: string; operationId: string };
  conversation: { id: string; purpose?: string; taskId?: string };
  task: { id: string; operationId: string; ownerUserId: number; projectId: string | null; context: FrozenContentTaskContext | null };
  observation: ContentRunnerObservation;
  stateArtifact: NativePackArtifactEvidence;
  packArtifact: NativePackArtifactEvidence;
  pack: ValidatedNativePackFacts;
}

export class ConfirmedNativePackError extends Error {
  constructor(public readonly code: string) { super(code); this.name = "ConfirmedNativePackError"; }
}
const reject = (code: string): never => { throw new ConfirmedNativePackError(code); };
const object = (value: unknown): Record<string, any> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, any> : {};
const sha = (bytes: Buffer) => createHash("sha256").update(bytes).digest("hex");
const integer = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0;
const date = (value: unknown) => typeof value === "string" && Number.isFinite(Date.parse(value));
const text = (value: unknown) => typeof value === "string" ? value.trim() : "";
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value) ?? "undefined";
}

function verifyArtifact(artifact: NativePackArtifactEvidence, scope: ConfirmedNativePackInput["scope"]) {
  if (!/^artifact_[a-f0-9]{64}$/u.test(artifact.id) || artifact.taskId !== scope.taskId
    || artifact.operationId !== scope.operationId || artifact.validationState !== "valid"
    || artifact.sizeBytes !== artifact.bytes.length || !/^[a-f0-9]{64}$/u.test(artifact.contentSha256)
    || sha(artifact.bytes) !== artifact.contentSha256) reject("CONTENT_NATIVE_PACK_ARTIFACT_UNVERIFIED");
}

/**
 * 纯投影：验证服务器证据后返回新主体状态，不读写数据库、不联网、不运行工作流。
 * Core 必须在 workspace 行锁事务内调用，并用真实 owner/project 查询构造所有证据。
 */
function verifyConfirmedNativePack(input: ConfirmedNativePackInput): ContentSubjectWorkspace {
  const { scope, task, conversation, observation, stateArtifact, packArtifact } = input;
  const context = task.context;
  if (task.id !== scope.taskId || task.operationId !== scope.operationId || task.ownerUserId !== scope.ownerUserId
    || task.projectId !== scope.projectId || context?.purpose !== "content_production"
    || context.accountUserId !== scope.ownerUserId || (context.enterpriseProjectId ?? null) !== scope.projectId
    || conversation.id !== scope.conversationId || conversation.taskId !== scope.taskId || conversation.purpose !== "content_production") {
    return reject("CONTENT_NATIVE_PACK_SCOPE_MISMATCH");
  }
  const binding = Object.hasOwn(input.workspace.bindings, conversation.id) ? input.workspace.bindings[conversation.id] : undefined;
  const folder = input.workspace.folders.find(value => value.id === binding?.folderId);
  if (!binding || !folder || folder.name.trim() !== context.contentProduction?.enterpriseName.trim()) {
    return reject("CONTENT_NATIVE_PACK_SUBJECT_MISMATCH");
  }
  verifyArtifact(stateArtifact, scope); verifyArtifact(packArtifact, scope);
  if (stateArtifact.id !== observation.artifactId || stateArtifact.sourceEventId !== observation.eventId
    || stateArtifact.contentSha256 !== observation.sha256) reject("CONTENT_NATIVE_PACK_STATE_IDENTITY_MISMATCH");
  const parsed = parseContentRunnerState(stateArtifact.bytes);
  if (!parsed || canonical(parsed) !== canonical(observation.state)) reject("CONTENT_NATIVE_PACK_STATE_IDENTITY_MISMATCH");
  const state = object(JSON.parse(stateArtifact.bytes.toString("utf8")));
  const p0 = state.status === "p0_ready" && state.job_kind === "p0";
  const positioning = state.status === "positioning_ready" && ["reference_pack", "reference_pack_refresh"].includes(state.job_kind);
  if ((!p0 && !positioning) || state.stage !== "reference_pack" || state.pending_action !== null || state.current_pause !== null) {
    return reject("CONTENT_NATIVE_PACK_NOT_DELIVERED");
  }
  const delivery = object(object(state.metadata).reference_pack_delivery);
  const manifest = object(input.pack.manifest), validation = object(input.pack.validation);
  const readiness = object(manifest.readiness), validatedReady = object(validation.readiness), deliveredReady = object(delivery.readiness);
  const reportedValidation = validation.status === "pass" && validation.validator === "v4.11_reference_pack_4.1"
    && Array.isArray(validation.errors) && validation.errors.length === 0
    && validation.pack_id === manifest.pack_id && validation.pack_version === manifest.pack_version
    && validatedReady.positioning_ready === true && validatedReady.p0_ready === p0;
  // 不把原CLI交付证明伪装成另一次validator pass；逐一验证其可复核的来源绑定。
  const nativeDelivery = validation.source === "frozen_native_cli_delivery"
    && /^[a-f0-9]{64}$/u.test(validation.workflowSha256)
    && validation.workflowSha256 === context.contentWorkflow?.sha256
    && validation.stateArtifactSha256 === stateArtifact.contentSha256
    && validation.zipSha256 === packArtifact.contentSha256 && delivery.status === "created"
    && Array.isArray(validation.members)
    && [...NATIVE_PACK_REQUIRED_MEMBERS, ...(p0 ? NATIVE_PACK_P0_MEMBERS : [])].every(member => validation.members.includes(member));
  if (input.pack.validatedZipSha256 !== packArtifact.contentSha256
    || delivery.portable_zip_sha256 !== `sha256:${packArtifact.contentSha256}`
    || typeof delivery.portable_zip_path !== "string" || !delivery.portable_zip_path
    || (!reportedValidation && !nativeDelivery)
    || manifest.schema_version !== "4.1" || manifest.profile !== "frontmind-content-reference-pack"
    || !/^rp_[a-f0-9]{16}$/u.test(manifest.pack_id) || !integer(manifest.pack_version) || manifest.pack_version < 1
    || manifest.pack_id !== delivery.pack_id || manifest.pack_version !== delivery.pack_version
    || text(manifest.brand_name) !== folder.name.trim() || text(delivery.brand_name) !== folder.name.trim()
    || ![readiness, deliveredReady].every(value => value.positioning_ready === true && value.p0_ready === p0)) {
    return reject("CONTENT_NATIVE_PACK_DELIVERY_MISMATCH");
  }
  const confirmation = object(input.pack.positioningConfirmation);
  if (confirmation.artifact_type !== "frontmind_core_positioning_confirmation" || confirmation.confirmed !== true
    || confirmation.pack_id !== manifest.pack_id || !integer(confirmation.source_pack_version)
    || confirmation.source_pack_version < 1 || confirmation.source_pack_version > manifest.pack_version
    || !integer(confirmation.positioning_revision) || !date(confirmation.confirmed_at)) {
    return reject("CONTENT_NATIVE_PACK_POSITIONING_UNCONFIRMED");
  }
  const decisions = object(state.decisions);
  if (positioning) {
    const nativeConfirmation = object(decisions.core_positioning_confirmation);
    if (nativeConfirmation.confirmed !== true || canonical(nativeConfirmation) !== canonical(confirmation)) {
      return reject("CONTENT_NATIVE_PACK_POSITIONING_UNCONFIRMED");
    }
  }
  if (p0) {
    const record = object(input.pack.p0Record), paths = object(record.paths);
    if (record.artifact_type !== "frontmind_p0_record" || record.pack_id !== manifest.pack_id
      || record.pack_version !== manifest.pack_version || !integer(record.source_pack_version)
      || record.source_pack_version < 1 || record.source_pack_version >= record.pack_version
      || !["create", "import"].includes(record.route) || record.route !== state.p0_route
      || !integer(record.p0_revision) || record.p0_revision > state.revision || !date(record.created_at)
      || paths.markdown !== "p0/p0_brand_article.md" || paths.html !== "p0/p0.html"
      || paths.docx !== "p0/p0.docx" || paths.title_map !== "p0/p0_title_map.json") {
      return reject("CONTENT_NATIVE_PACK_P0_UNCONFIRMED");
    }
    if (record.route === "create") {
      const blueprint = object(decisions.p0_blueprint_confirmation);
      if (!integer(blueprint.revision) || blueprint.revision >= state.revision || !date(blueprint.confirmed_at)) {
        return reject("CONTENT_NATIVE_PACK_P0_UNCONFIRMED");
      }
    }
  }
  const id = `native-pack-${sha(Buffer.from([scope.ownerUserId, scope.projectId, folder.id, manifest.pack_id, manifest.pack_version, packArtifact.contentSha256].join("|")))}`;
  if (folder.versions.some(version => version.id === id)) return input.workspace;
  return publishSubjectPack(input.workspace, {
    folderId: folder.id, sourceConversationId: conversation.id, sourceTaskId: task.id,
    file: { fileUrl: `/api/frontmind/v2/artifacts/${packArtifact.id}/content`, fileName: packArtifact.filename, mimeType: "application/zip" },
    includesP0: p0, confirmed: true,
    id,
    createdAt: state.updated_at,
  });
}

/** 证据缺失或不匹配时保持原状态，不制造版本，也不影响客户继续查看聊天。 */
export function projectConfirmedNativePack(input: ConfirmedNativePackInput): ContentSubjectWorkspace {
  try { return verifyConfirmedNativePack(input); }
  catch (error) {
    if (error instanceof ConfirmedNativePackError) return input.workspace;
    throw error;
  }
}
