import { useId, useState } from "react";
import { ChevronRight } from "lucide-react";
import {
  generalExecutionActivity,
  businessExecutionLabels,
  orderExecutionTimeline,
  generalExecutionStatusText,
  generalToolStatusText,
} from "@frontmind/module-contracts/execution";
import type { GeneralExecutionEntry } from "@frontmind/module-contracts/execution";
import MarkdownRenderer from "./MarkdownRenderer";
type ExecutionDisplayEntry = Exclude<GeneralExecutionEntry, {kind:"message"}> & {animate?:boolean;isCurrent?:boolean};
import "./GeneralExecutionActivity.css";

type ActivityItem = ExecutionDisplayEntry;

function isLive(item: ActivityItem) {
  if (item.animate === false || item.isCurrent === false) return false;
  if (item.kind === "status" && item.publicSummaryOrigin === "provider_native" && item.thinkingComplete) return false;
  if (item.kind === "tool")
    return item.status === "running" && item.finishedAt === undefined;
  return ["thinking", "running", "rescheduling", "retrying"].includes(
    item.status,
  );
}

function safeToolLabel(item: ActivityItem) {
  if (item.kind !== "tool") return "调用工具";
  // Keep the public label allowlist at the display boundary too. Historical
  // records must never turn a raw command/argument into a customer summary.
  const safe = generalExecutionActivity({
    kind: "tool_use",
    label: item.label,
    toolKind: item.toolKind,
  });
  return item.resultOnly
    ? "工具结果"
    : safe?.kind === "tool_use"
      ? safe.label
      : "调用工具";
}

function activityTitle(item: ActivityItem) {
  if (item.phase && item.kind === "status")
    return {
      thinking: "分析中",
      running: "进行中",
      rescheduling: "重新安排中",
      waiting: "等待中",
      retrying: "重试中",
      error: "失败",
      ended: "已完成",
      cancelled: "已停止",
    }[item.status];
  if (item.kind === "tool")
    return `${safeToolLabel(item)} · ${generalToolStatusText[item.status]}`;
  return generalExecutionStatusText[item.status];
}

function callSummary(calls: ActivityItem[], live: boolean) {
  const counts = new Map<string, number>();
  for (const call of calls) {
    const label = safeToolLabel(call);
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  if (counts.size === 1 && counts.has("执行命令"))
    return live ? `${calls.length} 个命令` : `执行了 ${calls.length} 个命令`;
  return [...counts]
    .map(([label, count]) =>
      label === "执行命令"
        ? `执行 ${count} 个命令`
        : `${label === "搜索网页" ? "搜索" : label === "调用工具" ? "工具操作" : label} ${count} 次`,
    )
    .join(" · ");
}

function thinkingText(item: ActivityItem) {
  return item.kind === "status" &&
    item.status === "thinking" &&
    item.publicSummary?.trim()
    ? item.publicSummary
    : null;
}

function ThinkingBlock({
  item,
  expandedOverride,
  onToggle,
  display = "disclosure",
}: {
  item: ActivityItem;
  expandedOverride?: boolean;
  onToggle?: () => void;
  display?: "disclosure" | "inline";
}) {
  const [localExpanded, setExpanded] = useState(true);
  const expanded = expandedOverride ?? localExpanded;
  const detailsId = useId();
  const text = thinkingText(item);
  if (!text || item.kind !== "status") return null;
  const live = isLive(item);
  const heading = (
    <>
      <span className="general-execution__summary">思考过程</span>
      <span
        className="general-execution__metadata"
        aria-live={live ? "polite" : undefined}
      >
        {item.thinkingComplete === true
          ? "已完成"
          : live
            ? "思考中"
            : "过程记录"}
      </span>
    </>
  );
  if (display === "inline" || item.publicSummaryOrigin === "provider_native") {
    return (
      <div className="general-execution__thinking" aria-label="公开过程摘要" aria-live={live ? "polite" : undefined}>
        {item.publicSummaryTitle && <strong className="general-execution__thinking-title">{item.publicSummaryTitle}</strong>}
        <MarkdownRenderer
          content={text}
          className="general-execution__thinking-text"
          allowCopy={false}
          generalChatLinks
        />
      </div>
    );
  }
  return (
    <section className="general-execution__thinking" aria-label="思考过程">
      <button
        type="button"
        className="general-execution__toggle"
        aria-label="思考过程"
        aria-expanded={expanded}
        aria-controls={detailsId}
        onClick={() => (onToggle ? onToggle() : setExpanded((value) => !value))}
      >
        <ChevronRight
          className="general-execution__chevron"
          aria-hidden="true"
        />
        {heading}
      </button>
      {expanded && (
        <div id={detailsId} className="general-execution__details">
          <MarkdownRenderer content={text} className="general-execution__thinking-text" allowCopy={false} generalChatLinks />
        </div>
      )}
    </section>
  );
}

function ActivityLine({
  children,
  live = false,
}: {
  children: React.ReactNode;
  live?: boolean;
}) {
  return (
    <div
      className="general-execution__line"
      data-live={live || undefined}
      aria-live={live ? "polite" : undefined}
    >
      <span className="general-execution__label">{children}</span>
    </div>
  );
}

function TurnActivity({
  items,
  expandedGroups,
  onToggleGroup,
  thinkingDisplay,
  hideSuccessfulResults,
  hideToolDetails,
}: {
  items: ActivityItem[];
  expandedGroups?: ReadonlySet<string>;
  onToggleGroup?: (id: string) => void;
  thinkingDisplay?: "disclosure" | "inline";
  hideSuccessfulResults?: boolean;
  hideToolDetails?: boolean;
}) {
  const calls = [
    ...new Map(
      items
        .filter((item) => item.kind === "tool" && !item.resultOnly)
        .map((item) => [item.id, item]),
    ).values(),
  ];
  const active = [...items].reverse().find(isLive);
  const start = items.find(
    (item) => item.kind === "status" && item.status === "running",
  );
  const lastLifecycle = items.findLast(
    (item) => item.kind === "status" && item.status !== "thinking",
  );
  const summaryId =
    calls[0]?.id ??
    start?.id ??
    (active && !thinkingText(active) ? active.id : undefined);
  const nativeMessages = items.filter(item => item.kind === "status" && item.publicSummaryOrigin === "provider_native" && thinkingText(item));
  const earlierNative = nativeMessages.slice(0, -3);
  const earlierIds = new Set(earlierNative.map(item => item.id));
  const nativeCalls = calls.filter(item => item.id.includes(":wma:"));
  const nativeEntries = items.filter(item => item.id.includes(":wma:") ||
    (item.kind === "status" && item.publicSummaryOrigin === "provider_native"));
  const latestNativeAt = Math.max(0, ...nativeEntries.map(item =>
    Math.max(item.timestamp, item.kind === "tool" ? item.finishedAt ?? 0 : 0)));
  const hasNativeProgress = nativeEntries.length > 0;
  // Animation is disabled on restored knowledge messages. It must not decide
  // whether the authoritative business phase is still running.
  const nativeRunning = hasNativeProgress && lastLifecycle?.isCurrent !== false &&
    ["running", "rescheduling", "retrying"].includes(lastLifecycle?.status ?? "");
  const timeLabel = (timestamp: number) => new Date(timestamp).toLocaleTimeString("zh-CN", { hour12: false });
  return (
    <>
      {hasNativeProgress && <div className="general-execution__native-heading">
        <strong>WMA 执行进展</strong>
        {latestNativeAt > 0 && <span>最近记录 {timeLabel(latestNativeAt)}</span>}
      </div>}
      {nativeRunning && nativeMessages.length === 0 && <ActivityLine>
        任务仍在执行，正在等待新的公开进展。
      </ActivityLine>}
      {items.map((item) => {
        if (earlierIds.has(item.id)) return item.id === earlierNative[0]?.id ? (
          <details key="earlier-native" className="general-execution__native-history">
            <summary>查看较早进展（{earlierNative.length} 条）</summary>
            {earlierNative.map(entry => <ThinkingBlock key={entry.id} item={entry} display="inline" />)}
          </details>
        ) : null;
        const summary =
          !item.phase &&
          !(item.kind === "status" && item.publicSummary) &&
          item.id === summaryId &&
          (active || calls.length > 0) ? (
            <ActivityLine key="commands" live={Boolean(active)}>
              {active
                ? `${active.kind === "status" && active.status === "retrying" ? "正在重试…" : active.kind === "status" && active.status === "rescheduling" ? "正在恢复执行…" : active.kind === "status" && active.status === "thinking" && !calls.length ? "正在分析任务…" : "正在执行…"}${calls.length ? ` · ${callSummary(calls, true)}` : ""}`
                : callSummary(calls, false)}
            </ActivityLine>
          ) : null;
        let detail: React.ReactNode = null;
        if (item.phase && Object.hasOwn(businessExecutionLabels, item.phase)) {
          detail = (
            <ActivityLine live={isLive(item)}>
              {businessExecutionLabels[item.phase]}
              {item.kind === "status" && item.publicSummary
                ? ` · ${item.publicSummary}`
                : ""}{" "}
              · {activityTitle(item)}
            </ActivityLine>
          );
        } else if (
          item.kind === "status" &&
          item.status !== "thinking" &&
          item.publicSummary?.trim()
        ) {
          detail = (
            <ActivityLine live={isLive(item)}>
              {item.publicSummary}
            </ActivityLine>
          );
        } else if (thinkingText(item)) {
          detail = (
            <ThinkingBlock
              item={item}
              display={thinkingDisplay}
              expandedOverride={
                expandedGroups ? expandedGroups.has(item.id) : undefined
              }
              onToggle={
                onToggleGroup ? () => onToggleGroup(item.id) : undefined
              }
            />
          );
        } else if (item.kind === "tool") {
          if (!hideToolDetails && (
            (item.resultOnly && !(hideSuccessfulResults && ["completed", "returned"].includes(item.status))) ||
            ["failed", "unconfirmed"].includes(item.status) ||
            (item.status === "waiting" && item.isCurrent !== false)
          ))
            detail = <ActivityLine>{activityTitle(item)}</ActivityLine>;
        } else if (
          item.status === "error" ||
          item.status === "cancelled" ||
          (item.status === "waiting" && item.isCurrent !== false)
        ) {
          detail = (
            <ActivityLine>
              {item.status === "error" && lastLifecycle?.id !== item.id
                ? "过程记录：执行曾遇到问题"
                : activityTitle(item)}
            </ActivityLine>
          );
        }
        // Completed tool-free turns have no activity summary. Empty analysis
        // labels and terminal completion markers add no detail.
        // Only real call records contribute to the count; a lone result cannot
        // manufacture an earlier invocation.
        return summary || detail ? (
          <div key={item.id}>
            {summary}
            {detail}
          </div>
        ) : null;
      })}
      {nativeCalls.length > 0 && <details className="general-execution__native-history">
        <summary>公开操作记录（{nativeCalls.length} 项）</summary>
        <ol className="general-execution__native-operations">
          {nativeCalls.map(item => <li key={item.id}><time dateTime={new Date(item.timestamp).toISOString()}>{timeLabel(item.timestamp)}</time><span>{safeToolLabel(item)}</span></li>)}
        </ol>
      </details>}
    </>
  );
}

export function GeneralExecutionActivity({
  items,
  expandedGroups,
  onToggleGroup,
  placement = "before",
  thinkingDisplay = "disclosure",
  hideSuccessfulResults = false,
  hideToolDetails = false,
}: {
  items?: ActivityItem[];
  expandedGroups?: ReadonlySet<string>;
  onToggleGroup?: (id: string) => void;
  placement?: "before" | "after";
  thinkingDisplay?: "disclosure" | "inline";
  hideSuccessfulResults?: boolean;
  hideToolDetails?: boolean;
}) {
  if (
    !items?.some(
      (item) =>
        item.phase ||
        (item.kind === "status" && item.publicSummary) ||
        thinkingText(item) ||
        isLive(item) ||
        item.kind === "tool" ||
        ["error", "cancelled"].includes(item.status) ||
        (item.status === "waiting" && item.isCurrent !== false),
    )
  )
    return null;
  const groups: ActivityItem[][] = [];
  for (const item of orderExecutionTimeline(items) as ActivityItem[]) {
    const last = groups.at(-1);
    if (last?.[0]?.turnId === item.turnId) last.push(item);
    else groups.push([item]);
  }
  return (
    <div
      className="general-execution"
      aria-label="执行过程"
      data-placement={placement}
    >
      {groups.map((group) => (
        <TurnActivity
          key={group[0]!.turnId}
          items={group}
          expandedGroups={expandedGroups}
          onToggleGroup={onToggleGroup}
          thinkingDisplay={thinkingDisplay}
          hideSuccessfulResults={hideSuccessfulResults}
          hideToolDetails={hideToolDetails}
        />
      ))}
    </div>
  );
}
