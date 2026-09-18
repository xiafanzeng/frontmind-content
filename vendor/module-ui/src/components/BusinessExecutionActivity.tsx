import type { GeneralExecutionDto } from "@frontmind/module-contracts/execution";
import { GeneralExecutionActivity } from "./GeneralExecutionActivity";
import { ExecutionDuration } from "./ExecutionDuration";
import { executionTimelineTiming } from "../lib/execution-duration";
/** Reuses the conversation execution renderer and its accessible disclosure. */
export function BusinessExecutionActivity({
  execution,
  thinkingDisplay,
}: {
  execution: GeneralExecutionDto;
  thinkingDisplay?: "disclosure" | "inline";
}) {
  const items = execution.timeline
    .filter((item) => item.kind !== "message")
    .map((item) =>
      item.kind === "status" ? { ...item, thinkingText: undefined } : item,
    );
  const currentTurn = items.at(-1)?.turnId;
  const timing = executionTimelineTiming(
    items.filter((item) => item.turnId === currentTurn),
  );
  if (!items.length) return null;
  return (
    <details className="business-execution-disclosure" open={timing?.active ?? false}>
      <summary aria-label="查看过程">
        查看过程{timing && <> · <ExecutionDuration {...timing} /></>}
      </summary>
      <GeneralExecutionActivity
        thinkingDisplay={thinkingDisplay ?? "inline"}
        items={items.map((item) => ({
          ...item,
          animate: item.isCurrent === true,
        }))}
      />
    </details>
  );
}
