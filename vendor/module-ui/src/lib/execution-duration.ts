import {orderExecutionTimeline,type GeneralExecutionEntry} from "@frontmind/module-contracts/execution";
export type ExecutionTiming = {
  startedAt: number;
  completedAt?: number;
  active: boolean;
};
const validTime = (value: number | undefined): value is number =>
  value !== undefined &&
  Number.isFinite(value) &&
  value >= 0 &&
  value <= 8.64e15;

/** Uses persisted event times; mounting a view never starts a new clock. */
export function executionTimelineTiming(
  entries: readonly GeneralExecutionEntry[],
  active?: boolean,
): ExecutionTiming | undefined {
  const ordered = orderExecutionTimeline(entries).filter((entry) =>
    validTime(entry.timestamp),
  );
  if (!ordered.length) return undefined;
  const last = ordered.at(-1)!;
  const live =
    active ??
    (last.kind !== "message" &&
      last.isCurrent === true &&
      ![
        "ended",
        "cancelled",
        "error",
        "completed",
        "failed",
        "unconfirmed",
        "returned",
      ].includes(last.status) &&
      (last.status !== "waiting" || Boolean(last.phase)));
  return {
    startedAt: Math.min(...ordered.map((entry) => entry.timestamp)),
    completedAt: live
      ? undefined
      : Math.max(
          ...ordered.map((entry) =>
            validTime(entry.finishedAt)
              ? Math.max(entry.timestamp, entry.finishedAt)
              : entry.timestamp,
          ),
        ),
    active: live,
  };
}
