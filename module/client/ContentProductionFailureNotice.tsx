import type { ContentProductionExecutionFailure } from "../contracts/content-production";

export default function ContentProductionFailureNotice({ failure }: {
  failure?: ContentProductionExecutionFailure | null;
}) {
  if (!failure) return null;
  return <div className="cp-notice" role="alert">
    <strong>{failure.action === "positioning_market_research" ? "市场研究执行失败" : "本轮执行失败"}</strong>
    <p>当前任务和已有产出已保留，可在修复后继续原任务。</p>
    <small>错误代码：{failure.code}</small>
  </div>;
}
