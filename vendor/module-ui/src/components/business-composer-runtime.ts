import type { ComponentType } from "react";

export interface ComposerSendOptions<ContentInput = unknown, ResponseContext = unknown> {
  agentProfile?: string;
  purpose?: "enterprise_qa" | "content_production";
  contentProduction?: ContentInput;
  responseLogicContext?: ResponseContext;
  syncKnowledgeBaseSnapshot?: boolean;
  knowledgeBaseExpectedGeneration?: number;
  knowledgeBaseExpectedResetRevision?: number;
  knowledgeBaseExpectedStateEpoch?: number;
  knowledgeBaseExpectedContentVersion?: number;
  knowledgeBaseExpectedRevision?: number;
  knowledgeBaseExpectedLeafId?: string;
  knowledgeBaseExpectedPresentationKey?: string;
  submissionKind?: "message" | "logo";
}
export interface ComposerUploadProgress {
  phase?: "uploading" | "verifying";
  totalBytes?: number; uploadedBytes?: number; confirmedFiles?: number;
  currentFileIndex: number; totalFiles: number; currentFileName: string;
  currentFilePercent: number; overallPercent: number; conversationId?: string;
}
export interface ComposerAttachmentAttempt {
  conversationId: string; clientRequestId: string; turnId?: string;
  generation: number; resetRevision: number;
  phase: "hashing" | "reserving" | "uploading" | "staging" | "dispatching" | "reconciling_dispatch" | "failed_retryable" | "accepted";
  lastError?: string;
}
export interface ComposerSender<ContentInput = unknown, ResponseContext = unknown> {
  sendMessage(text: string, files: File[], options?: ComposerSendOptions<ContentInput, ResponseContext>): Promise<boolean>;
  uploadProgress: ComposerUploadProgress | null;
  knowledgeBaseAttachmentAttempt: ComposerAttachmentAttempt | null;
  stopKnowledgeBaseAttachmentAttempt(): unknown;
  continueKnowledgeBaseAttachmentAttempt(): unknown;
  discardKnowledgeBaseAttachmentAttempt(): void;
}

export interface ComposerSnapshot {
  generation: number; stateEpoch: number; contentVersion?: number; revision: number;
  leafId: string; presentationKey: string; presentationTurnId?: string;
}
export interface ComposerConversation {
  id: string; status: string; previousResponseId?: string; taskId?: string;
  knowledgeBase?: {
    generation: number; initialized?: boolean; canReply?: boolean;
    activeClientRequestId?: string | null; activeTurnId?: string | null;
    activeTurnResetRevision?: number; activeTurnOperationType?: string | null;
    activeTurnAwaitingClientAttachments?: boolean; notice?: {code?: string} | null;
  };
}
export interface ComposerKnowledgeProgress {
  workbench?: {phase: string};
  build: { currentLeafId: string | null; status: string; hasPublishedSnapshot?: boolean;
    executionMode?: string; logoRequired?: boolean; logoAvailable?: boolean; };
  branches: Array<{leaves: Array<{id: string; title: string; branchTitle: string}>}>;
  summary: {handled: number}; contentAvailability?: string;
  packageAllowed: boolean; packageState?: string;
}
export interface ComposerRecoveryProps<Observation> {
  conversationId: string; turnId: string; clientRequestId: string;
  expectedResetRevision: number; operationType?: "start" | "revise";
  onObservation(observation: Observation): void; onRecovered?(): void; onCancelled?(): void;
}
/** Host adapters inject business dispatch; presentation, draft/IME/drop interactions remain shared. */
export interface BusinessComposerRuntime<ContentInput = unknown, ResponseContext = unknown, Conversation extends ComposerConversation = ComposerConversation, Observation = unknown> {
  useConversation(): {
    activeConversation: Conversation | null; workbenchScopeKey?: string;
    commitKnowledgeBaseObservation(conversationId: string, observation: Observation): void;
    wakeKnowledgeBaseConversation(conversationId: string): void;
    rollbackPendingKnowledgeBaseTurn(conversationId: string, clientRequestId: string): void;
  };
  currentKnowledgeBaseReplySnapshot(conversation: Conversation | null | undefined): ComposerSnapshot | null;
  useSendMessage(resetRevision?: number): ComposerSender<ContentInput, ResponseContext>;
  useChatSubmission(scope: string | undefined, conversationId: string | null | undefined): {phase: string} | null | undefined;
  useWorkspaceDraftGuard(input: {dirty: boolean; label: string}): void;
  captureWorkspaceRestOperation(): {assertActive(): void; fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response>};
  consumePendingFrontMindBuildDraft(): string;
  GeneralAgentRuntimeBadge: ComponentType<{localTaskId?: string | null; purpose?: "enterprise_qa" | "content_production"; locked?: boolean; onProfile(profile: string): void}>;
  KnowledgeBaseManagedUploadRecovery: ComponentType<ComposerRecoveryProps<Observation>>;
  generalSuggestions: readonly {label: string; prompt: string}[];
  formatKnowledgeBaseUploadBytes(bytes: number): string;
  chatAttachmentSizeError(file: File): string | null;
  knowledgeLogoNoticeCode: string;
}
