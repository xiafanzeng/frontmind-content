import { describe, expect, it } from "vitest";
import { contentProductionActionSchema, contentProductionInputSchema } from "../contracts/content-production";
import { parseContentRunnerState, reduceContentProductionProgress, contentProductionPublicDto } from "../server/state";
import { contentProductionSystemContext, contentWorkflowRuntimeFor } from "../server/runtime";
import { assertContentConfirmation } from "../server/task-handlers";
import type { FrozenContentTaskContext } from "../contracts/task-context";

const context: FrozenContentTaskContext = {
  revision: 1, accountUserId: 1, purpose: "content_production", knowledgeBase: null, knowledgeText: null,
  contentProduction: contentProductionInputSchema.parse({ mode: "single_article", enterpriseName: "合成企业", knowledgeSource: "files" }),
  contentWorkflow: { version: "4.13.2-v16.2", rootDirectory: "FrontMind_Content_Workflow_v4.13.2", filename: "workflow.zip", sha256: "a".repeat(64) },
};
function state(status = "awaiting_question_selection", stage = "question_selection") {
  return {
    schema_version: "4.11", artifact_type: "frontmind_content_job_state", workflow_version: "4.11",
    job_id: "one-job", job_kind: "article", updated_at: "2026-09-29T10:00:00+00:00", stage, status, revision: 7,
    current_pause: status.startsWith("awaiting_") ? {
      pause_type: status, title: "选择问题", available_choices: ["1. 合成问题"], revision: 7,
      requires_user_input: true, user_pause: true, must_stop: true,
    } : null,
    pending_action: null, flags: {}, decisions: {}, p0_route: null,
  };
}

describe("native v16.2 host integration", () => {
  it("uses the frozen release to select native execution and leaves legacy execution intact", () => {
    expect(contentWorkflowRuntimeFor(context)).toBe("native_content_v1");
    expect(contentProductionSystemContext(context)).toContain("Never hand-write provider results");
    expect(contentProductionSystemContext(context)).toContain("timeout_seconds=7200");
    expect(contentProductionSystemContext(context)).toContain("exactly ten same-topic");
    expect(contentProductionSystemContext(context)).not.toContain("No external provider SDK");
    const legacy = { ...context, contentWorkflow: undefined };
    expect(contentWorkflowRuntimeFor(legacy)).toBeUndefined();
    expect(contentProductionSystemContext(legacy)).toContain("No external provider SDK");
    expect(contentProductionSystemContext(legacy)).not.toContain("This frozen release uses its own OpenAI Agents SDK");
  });

  it("projects question selection with its real revision and rejects stale or cross-stage submission", () => {
    const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(state())))!;
    expect(parsed).not.toBeNull();
    const progress = reduceContentProductionProgress(null, { providerRank: 1, eventId: "event", artifactId: "state", sha256: "a".repeat(64), state: parsed }, "single_article");
    const dto = contentProductionPublicDto(context, { contentProductionProgress: progress });
    expect(dto).toMatchObject({ workflowVersion: "4.13.2-v16.2", confirmation: "awaiting_question_selection", runnerRevision: 7, progressPosition: 13 });
    expect(dto.availableActions).toContain("choose_question");
    const action = contentProductionActionSchema.parse({ kind: "choose_question", selection: "1", revision: 7 });
    expect(() => assertContentConfirmation({ action, availableActions: dto.availableActions, runnerRevision: 7 })).not.toThrow();
    expect(() => assertContentConfirmation({ action, availableActions: dto.availableActions, runnerRevision: 8 })).toThrow();
    expect(() => assertContentConfirmation({ action, availableActions: ["confirm_blueprint"], runnerRevision: 7 })).toThrow();
    expect(contentProductionActionSchema.safeParse({ ...action, selection: " " }).success).toBe(false);
    const wrong = state(); wrong.current_pause!.revision = 6;
    expect(parseContentRunnerState(Buffer.from(JSON.stringify(wrong)))).toBeNull();
  });

  it.each(["style", "finalize", "repair", "polish", "title_review"])("accepts native substage %s without claiming completion", (step) => {
    const raw = { ...state("running_article_production", "article_production"), flags: step === "style" ? { p0_production_step: step } : { article_production_step: step } };
    const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(raw)))!;
    expect(parsed).not.toBeNull();
    const progress = reduceContentProductionProgress(null, { providerRank: 1, eventId: "event", artifactId: "state", sha256: "a".repeat(64), state: parsed }, "single_article");
    expect(progress.progressPosition).toBeLessThan(20);
    expect(parseContentRunnerState(Buffer.from(JSON.stringify({ ...raw, status: "completed" })))).toBeNull();
  });

  it("preserves a 100-question catalog and its two additional input actions", () => {
    const raw = state();
    raw.current_pause!.available_choices = [
      ...Array.from({ length: 100 }, (_, index) => `${index + 1}. 合成问题${index + 1}`),
      "导入监控问答表", "更换Reference Pack",
    ];
    const parsed = parseContentRunnerState(Buffer.from(JSON.stringify(raw)));
    expect(parsed?.current_pause?.available_choices).toEqual(raw.current_pause!.available_choices);
  });
});
