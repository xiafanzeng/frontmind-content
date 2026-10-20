import type { BusinessExecutionPhase, GeneralExecutionDto, GeneralExecutionEntry } from "@frontmind/module-contracts/execution";

/** Module-owned public evidence. No provider prose, arguments or result bodies. */
export const contentExecutionActionLabels = {
  positioning_market_research: "公开资料研究", positioning_value_synthesis: "品牌定位整理",
  answer_analysis: "现有回答分析", article_blueprint: "问题文章方案", p0_blueprint: "品牌文章方案",
  article_editorial_preparation: "案例研究与编辑准备",
  article_draft: "问题文章初稿", p0_draft: "品牌文章初稿",
  article_edit: "问题文章编辑", p0_edit: "品牌文章编辑", article_style: "问题文章润色", p0_style: "品牌文章润色",
  article_finalize: "问题文章复核", p0_finalize: "品牌文章复核",
  article_repair: "问题文章修订", p0_repair: "品牌文章修订",
  article_polish: "问题文章终稿润色",
  article_titles: "问题文章标题", p0_titles: "品牌文章标题",
  article_title_review: "问题文章标题复核", p0_title_review: "品牌文章标题复核",
  unknown: "工作流动作",
} as const;
export const contentToolOperationLabels = {
  list_materials: "查看材料目录", read_material: "读取材料", search_materials: "检索材料",
  extract_document: "提取文档", web_search: "搜索网页", web_read: "读取网页",
  ocr: "识别图片文字", submit_result: "提交阶段结果", count_article: "检查文章字数",
} as const;
export const contentExecutionDiagnostics = {
  material_reference_missing: { title:"材料标识未登记", action:"从材料目录复制准确标识后再读取。" },
  material_boundary_rejected: { title:"材料范围或内容已变更", action:"重新登记并确认材料后继续。" },
  invalid_tool_arguments: { title:"读取要求不符合约定", action:"修正读取要求后继续。" },
  deterministic_tool_repeat: { title:"相同读取错误重复出现", action:"修正来源或材料标识后显式恢复。" },
  network_error: { title: "连接中断", action: "检查连接后，使用原任务的重试入口恢复。" },
  http_error: { title: "服务请求失败", action: "检查服务可用性与账户配置，再决定是否重试。" },
  invalid_result: { title: "阶段结果未通过校验", action: "检查来源引用与结果格式；修正后显式重试。" },
  tool_request_rejected: { title: "工具请求被拒绝", action: "检查材料标识、工具参数和允许读取的范围。" },
  source_unavailable: { title: "来源读取失败", action: "检查来源是否可访问，或在当前阶段补充可核验材料。" },
  non_public_address: { title: "来源地址未通过公网校验", action: "检查网络解析或补充材料；不要绕过地址安全校验。" },
  retries_exhausted: { title: "服务重试已耗尽", action: "检查服务状态，再从原任务显式恢复。" },
  execution_error: { title: "执行未完成", action: "检查本地运行记录，确认原因后再重试当前动作。" },
} as const;
export type ContentExecutionDiagnosticCode = keyof typeof contentExecutionDiagnostics;
export type ContentToolOperation = keyof typeof contentToolOperationLabels;
export type ContentExecutionEntry = GeneralExecutionEntry & {
  attemptId?: string;
  operation?: ContentToolOperation;
  diagnosticCode?: ContentExecutionDiagnosticCode;
};
export type ContentExecutionAttempt = {
  id: string;
  turnId: string;
  action: keyof typeof contentExecutionActionLabels;
  phase?: BusinessExecutionPhase;
  provider: "zhipu" | "deepseek";
  status: "running" | "succeeded" | "failed" | "unknown";
  startedAt: number;
  finishedAt?: number;
  recovery?: "same_session" | "new_attempt";
  diagnosticCode?: ContentExecutionDiagnosticCode;
  recoveryDiagnosticCode?: ContentExecutionDiagnosticCode;
  /** Writer receipts have no per-tool timestamp. Do not invent timeline rows. */
  toolCounts?: { calls: number; returned: number; failed: number; unconfirmed: number };
};
export type ContentExecutionDto = Omit<GeneralExecutionDto, "timeline"> & {
  timeline: ContentExecutionEntry[];
  attempts?: ContentExecutionAttempt[];
  sources?: ("zhipu_managed" | "deepseek_writer")[];
};
