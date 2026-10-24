import type { ContentProductionInput, ContentProductionKnowledgeSource } from "./content-production";

/** Immutable task input. The host resolves and authorizes optional imported knowledge. */
export type FrozenContentTaskContext = {
  revision: 1;
  accountUserId: number;
  enterpriseProjectId?: string | null;
  purpose: "enterprise_qa" | "content_production";
  knowledgeBase: ContentProductionKnowledgeSource | null;
  knowledgeText: string | null;
  contentProduction?: ContentProductionInput;
  inputFiles?: { localAssetId: string; filename: string }[];
  contentWorkflow?: ContentWorkflowBinding;
  subjectContext?: FrozenContentSubjectContext;
};

/** 只由宿主根据权威主体账本和已校验的本地产物冻结，浏览器不得指定文件地址。 */
export type FrozenContentSubjectContext = {
  revision: 1;
  conversationId: string;
  folderId: string;
  generation: number;
  packVersionId: string | null;
  sourceTaskId?: string;
  artifactId?: string;
  localAssetId?: string;
  contentSha256?: string;
};

export type ContentWorkflowBinding = {
  version: string;
  filename: string;
  sha256: string;
  rootDirectory: string;
  /** Frozen when the task starts, so future releases cannot change its execution route. */
  runtime?: "native_content_v1";
  capabilities?: ("structured_article" | "editorial_v16_8" | "session_phases")[];
};

export type SystemAttachment = {
  filename: string;
  mime_type: string;
  file_data: string;
};
