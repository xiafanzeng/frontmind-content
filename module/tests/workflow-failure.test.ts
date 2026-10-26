import { describe, expect, it } from "vitest";
import { contentProductionInputSchema } from "../contracts/content-production";
import type { FrozenContentTaskContext } from "../contracts/task-context";
import { contentProductionPublicDto, parseContentRunnerState, reduceContentProductionProgress } from "../server/state";

const context: FrozenContentTaskContext = {
  revision: 1, accountUserId: 1, purpose: "content_production", knowledgeBase: null, knowledgeText: null,
  contentProduction: contentProductionInputSchema.parse({ mode: "new_reference_pack", enterpriseName: "合成企业", knowledgeSource: "files" }),
};
function rawState(error?: unknown) {
  return {
    schema_version: "4.11", artifact_type: "frontmind_content_job_state", workflow_version: "4.11",
    job_id: "synthetic-job", job_kind: "reference_pack", updated_at: "2026-10-23T10:00:00+00:00",
    stage: "positioning_research", status: "running_positioning_market_research", revision: 7,
    current_pause: null, pending_action: { action: "positioning_market_research", ...(error === undefined ? {} : { error }) },
    flags: {}, decisions: {}, p0_route: null,
  };
}
function observation(raw = rawState()) {
  const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(raw)));
  expect(parsed).not.toBeNull();
  return { state: parsed!, providerRank: 1, eventId: "synthetic-event", artifactId: "synthetic-state", sha256: "a".repeat(64) };
}

describe("content workflow failures", () => {
  it("projects an internal action failure without exposing the provider message", () => {
    const observed = observation(rawState({
      code: "tool_call_source_mismatch", attempt_id: "synthetic-attempt", recoverable_edit: false,
      message: "Private provider detail /private/runtime/config with Bearer synthetic-secret",
    }));
    const progress = reduceContentProductionProgress(null, observed, "new_reference_pack");
    const dto = contentProductionPublicDto(context, { contentProductionProgress: progress });
    expect(dto).toMatchObject({ workflowVersion: "4.11.0", workflowStatus: "running_positioning_market_research", runnerRevision: 7,
      executionFailure: { action: "positioning_market_research", code: "tool_call_source_mismatch", attemptId: "synthetic-attempt" },
      progressPosition: 3, availableActions: ["resume_current_execution"], confirmation: null });
    expect(JSON.stringify(observed)).not.toContain("synthetic-secret");
    expect(JSON.stringify(dto)).not.toContain("Private provider");
  });

  it("keeps legacy observations readable and clears a failure only on a later observation", () => {
    const failed = reduceContentProductionProgress(null, observation(rawState({ code: "tool_call_source_mismatch" })), "new_reference_pack");
    const later = observation({ ...rawState(), updated_at: "2026-10-23T10:00:01+00:00" });
    const resumed = reduceContentProductionProgress(failed, later, "new_reference_pack");
    expect(contentProductionPublicDto(context, { contentProductionProgress: resumed })).toMatchObject({
      executionFailure: null, workflowStatus: "running_positioning_market_research", runnerRevision: 7, progressPosition: 3,
    });
    expect(reduceContentProductionProgress(resumed, observation(rawState({ code: "tool_call_source_mismatch" })), "new_reference_pack")).toBe(resumed);
    expect(contentProductionPublicDto(context)).toMatchObject({ executionFailure: null, source: "awaiting_runner" });
  });

  it("uses a stable safe failure when older error metadata is unstructured", () => {
    for (const error of ["Private provider detail", { code: "/private/config", attempt_id: "../private", message: "secret" }]) {
      const progress = reduceContentProductionProgress(null, observation(rawState(error)), "new_reference_pack");
      expect(contentProductionPublicDto(context, { contentProductionProgress: progress })?.executionFailure).toEqual({
        action: "positioning_market_research", code: "content_workflow_failed", attemptId: null,
      });
    }
  });
});
