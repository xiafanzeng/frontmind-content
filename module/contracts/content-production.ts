export * from "@frontmind/module-contracts/content-production";
import type { ContentProductionDto as SharedContentProductionDto } from "@frontmind/module-contracts/content-production";

/** Safe business failure metadata; provider text and private paths stay private. */
export type ContentProductionExecutionFailure = {
  action: string;
  code: string;
  attemptId: string | null;
};

export type ContentProductionDto = SharedContentProductionDto & {
  /** Absent in older observations; the original workflow status stays intact. */
  executionFailure?: ContentProductionExecutionFailure | null;
};
