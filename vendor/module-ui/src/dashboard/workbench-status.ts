export function workbenchStatus(status?: string) {
  return (
    (
      {
        running: "执行中",
        pending: "正在准备",
        awaiting_input: "等待确认",
        completed: "已完成",
        failed: "执行失败",
        error: "执行失败",
        idle: "就绪",
      } as Record<string, string>
    )[status ?? "idle"] ?? "就绪"
  );
}
