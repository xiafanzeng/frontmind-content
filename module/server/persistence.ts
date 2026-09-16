import type { FrozenContentTaskContext } from "../contracts/task-context";
import { compareContentRunnerObservations, reduceContentProductionProgress, type ContentProductionProgress, type ContentRunnerObservation } from "./state";
export type { ContentRunnerObservation } from "./state";

export type ContentTaskScope = { taskId: string; operationId: string; userId: number };
export interface ContentTaskPersistence {
  /** Host checks ownership and holds a database row lock until run/save completes. */
  withLockedTask(scope: ContentTaskScope, run: (task: {
    context: FrozenContentTaskContext | null;
    providerRuntime: Record<string, unknown> | null;
    saveRuntime(value: Record<string, unknown>): Promise<void>;
  }) => Promise<void>): Promise<void>;
}

export async function persistObservations(
  input: ContentTaskScope & { observations: ContentRunnerObservation[] },
  persistence: ContentTaskPersistence,
) {
  if (!input.observations.length) return;
  await persistence.withLockedTask(input, async (task) => {
    const context = task.context;
    if (context?.purpose !== "content_production" || !context.contentProduction) return;
    const previous = task.providerRuntime?.contentProductionProgress as ContentProductionProgress | undefined;
    let progress = previous ?? null;
    for (const observation of [...input.observations].sort((left, right) =>
      left.providerRank - right.providerRank || compareContentRunnerObservations(left, right))) {
      progress = reduceContentProductionProgress(progress, observation, context.contentProduction.mode);
    }
    if (progress === previous) return;
    await task.saveRuntime({ ...task.providerRuntime, contentProductionProgress: progress });
  });
}
