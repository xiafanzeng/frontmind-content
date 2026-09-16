

export type ZhipuThinkingCapture = {
  eventId: string;
  commandKey: string;
  afterEventId?: string;
  text: string;
  startedAt: string;
  complete: boolean;
  authoritativeText?: true;
};


export type DashboardProviderIdentity = {
  provider: "manus" | "zhipu";
  accountUserId: number;
  credentialId: string;
  credentialVersion: number;
  credentialOwnerUserId?: number;
  /** Captured when the client is created; asynchronous work never follows UI scope. */
  enterpriseProjectId?: string | null;
  enterpriseProjectLegacyDefault?: boolean;
};

export type DashboardManagedMutation = {
  requestHash: string;
  state: "sending" | "acknowledged" | "rejected" | "outcome_unknown";
  startedAt: string;
  resourceId?: string;
  status?: number | null;
  code?: string;
};

export type DashboardManagedFile = {
  id: string;
  filename: string;
  bytes: number;
  sha256: string;
  contentType: string;
  role: "input" | "output";
  commandKey?: string;
  deleted?: boolean;
  /** Immutable server-provided workflow/knowledge input; browser turns cannot replace its mount. */
  serverOwned?: boolean;
};

export type DashboardManagedCommand = {
  key: string;
  intentId: string;
  prompt: string;
  providerPromptHash: string;
  turnContext?: string | null;
  productIdentityContext?: string | null;
  qaInputFiles?: Array<{ localAssetId: string; filename: string }>;
  attachments: Array<{ fileId: string; filename: string; sha256: string }>;
  schema?: Record<string, unknown>;
  beforeEventIds: string[];
  beforeFileIds: string[];
  createdAt: string;
  eventId?: string;
};

export type DashboardManagedRuntime = {
  revision: 1;
  generalIdentitySystem?: string;
  model: string;
  effort: "low" | "high" | "max";
  intentId: string;
  agentId?: string;
  environmentId?: string;
  sessionId?: string;
  title?: string;
  deleted?: boolean;
  mutations: Record<string, DashboardManagedMutation>;
  commands: DashboardManagedCommand[];
  files: DashboardManagedFile[];
  usage?: Record<string, unknown>;
  /** Actual provider thinking transcripts, isolated to the owning command/session. */
  thinkingCaptures?: ZhipuThinkingCapture[];
  observedEventIds?: string[];
  eventCursor?: string;
  /** One internal formatting correction remains within its original billable user command. */
  enterpriseQaRepairs?: Record<string, {
    finalEventId: string;
    terminalEventId: string;
    prompt: string;
    createdAt: string;
    failed?: boolean;
  }>;
};

export type DashboardRuntimeRecord = {
  localTaskId: string;
  operationId: string;
  runtime: DashboardManagedRuntime;
};

export type DashboardRuntimeReservation = {
  generalIdentitySystem?: string;
  identity: DashboardProviderIdentity;
  intentId: string;
  model: string;
  effort: DashboardManagedRuntime["effort"];
  localTaskId?: string;
  operationId?: string;
};

export interface DashboardAgentRuntimeStore {
  reserve(input: DashboardRuntimeReservation): Promise<DashboardRuntimeRecord>;
  findByIntent(
    identity: DashboardProviderIdentity,
    intentId: string,
  ): Promise<DashboardRuntimeRecord | null>;
  findBySession(
    identity: DashboardProviderIdentity,
    sessionId: string,
  ): Promise<DashboardRuntimeRecord | null>;
  findByFile(
    identity: DashboardProviderIdentity,
    fileId: string,
    binding?: {
      localTaskId?: string;
      operationId?: string;
      role?: "input" | "output";
    },
  ): Promise<DashboardRuntimeRecord | null>;
  mutate(
    identity: DashboardProviderIdentity,
    localTaskId: string,
    change: (runtime: DashboardManagedRuntime) => DashboardManagedRuntime,
  ): Promise<DashboardRuntimeRecord>;
}

export type AiBillingPause = {
  reason: "balance" | "cost";
  stage: "before_send" | "after_send";
  commandKey: string;
  sessionId: string;
  pausedAt: string;
};