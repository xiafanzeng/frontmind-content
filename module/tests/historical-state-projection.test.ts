import { createHash } from "node:crypto";
import { expect, it, vi } from "vitest";
import { restoreContentObservationFields } from "../worker/observations";
import { parseContentRunnerState } from "../server/state";

function fixture() {
  const raw = { schema_version: "4.11", artifact_type: "frontmind_content_job_state", workflow_version: "4.11",
    job_id: "original-job", job_kind: "reference_pack", updated_at: "2026-10-21T10:00:00+00:00",
    stage: "positioning_research", status: "running_positioning_market_research", revision: 1,
    current_pause: null, pending_action: { action: "positioning_market_research", error: { code: "tool_call_source_mismatch", message: "private detail" } },
    flags: {}, decisions: {}, p0_route: null };
  const bytes = Buffer.from(JSON.stringify(raw));
  const state = parseContentRunnerState(bytes)!;
  const runtime = { context: { frozen: true }, contentProductionProgress: { revision: 2,
    progressPosition: 3, completedConfirmations: [], lastObservation: { state: { ...state, pending_action: { action: raw.pending_action.action } },
      providerRank: 1, artifactId: "original-state", eventId: "old-event", sha256: createHash("sha256").update(bytes).digest("hex") } } };
  return { bytes, runtime };
}

it("restores dropped failure fields from the exact historical bytes without changing the task", async () => {
  const { bytes, runtime } = fixture();
  const result = await restoreContentObservationFields(runtime, async () => bytes);
  expect(result).toMatchObject({ context: { frozen: true }, contentProductionProgress: { progressPosition: 3,
    lastObservation: { state: { job_id: "original-job", revision: 1, pending_action: { error: { code: "tool_call_source_mismatch" } } } } } });
  expect(runtime.contentProductionProgress.lastObservation.state.pending_action).not.toHaveProperty("error");
  expect(JSON.stringify(result)).not.toContain("private detail");
});

it("rejects substituted original state and tolerates unavailable historical storage", async () => {
  const { runtime } = fixture();
  expect(await restoreContentObservationFields(runtime, async () => Buffer.from("changed"))).toBe(runtime);
  expect(await restoreContentObservationFields(runtime, async () => { throw new Error("unavailable"); })).toBe(runtime);
  const read = vi.fn();
  expect(await restoreContentObservationFields({}, read)).toEqual({});
  expect(read).not.toHaveBeenCalled();
});
