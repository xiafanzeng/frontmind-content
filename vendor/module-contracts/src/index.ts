export const MODULE_IDS = ["brand", "intent", "progress", "content", "publish"] as const;
export type ModuleId = (typeof MODULE_IDS)[number];

export interface ModuleVersion {
  module: ModuleId;
  moduleSha: string;
  coreSha: string;
}

/** Import provenance is immutable; edits to the source do not change the input snapshot. */
export interface SourceReference<T> {
  module: ModuleId;
  recordId: string;
  version: string;
  snapshot: Readonly<T>;
}

/** Provided by the main workbench only. Absence leaves standalone manual inputs intact. */
export interface ModuleConnections<Inputs, Outputs> {
  importInput?: () => Promise<SourceReference<Inputs> | null>;
  openSource?: (reference: SourceReference<unknown>) => void;
  useOutput?: (output: Outputs) => Promise<void>;
}

export interface CoreIdentity {
  userId: number;
  actorUserId: number;
  projectId: string;
}

/** The transaction is the host's existing in-process transaction, never an HTTP handle. */
export interface CoreServices<Transaction> {
  identity: {
    requireProject(module: ModuleId, projectId: string): Promise<CoreIdentity>;
    lockBusinessWrite(tx: Transaction, identity: CoreIdentity): Promise<void>;
  };
  database: {
    transaction<T>(run: (tx: Transaction) => Promise<T>): Promise<T>;
  };
  funds: {
    reserve(tx: Transaction, input: {
      identity: CoreIdentity; operationId: string; amountMinor: bigint; currency: string;
    }): Promise<{ reservationId: string }>;
    settle(tx: Transaction, reservationId: string, amountMinor: bigint): Promise<void>;
    release(tx: Transaction, reservationId: string): Promise<void>;
  };
  objects: {
    read(identity: CoreIdentity, key: string): Promise<Uint8Array>;
    write(identity: CoreIdentity, input: {
      key: string; bytes: Uint8Array; contentType: string;
    }): Promise<void>;
  };
}
