import type {GeneralExecutionDto} from "@frontmind/module-contracts/execution";

/** 仅投影公开摘要；不翻译原始来源、用户消息、代码或隐藏推理。 */
export function chineseContentSummary(value: string): string {
  if (/[\u3400-\u9fff]/u.test(value) && !/[a-z]+(?:\s+[a-z]+){3,}/iu.test(value)) return value;
  const known: Array<[RegExp, string]> = [
    [/^(?:I(?:'m| am) |Currently )?(?:reading|reviewing)(?: the)? (?:uploaded |provided )?(?:files|materials|documents)[.!…]*$/iu, "正在读取本轮提供的资料。"],
    [/^(?:I(?:'m| am) |Currently )?(?:analyzing|analysing)(?: the)? (?:materials|documents|requirements)[.!…]*$/iu, "正在分析当前资料与要求。"],
    [/^(?:I(?:'m| am) )?searching (?:the web|public sources)[.!…]*$/iu, "正在检索公开来源。"],
    [/^(?:I(?:'m| am) )?(?:preparing|drafting)(?: the)? (?:writing plan|article outline|blueprint)[.!…]*$/iu, "正在整理文章写作方案。"],
    [/^waiting for (?:your |user )?(?:confirmation|input)[.!…]*$/iu, "正在等待确认或补充资料。"],
    [/^(?:tool call|tool execution) completed[.!…]*$/iu, "本次工具调用已返回。"],
  ];
  const text = value.trim();
  for (const [expression, translated] of known) if (expression.test(text)) return translated;
  return "本条过程记录暂无中文摘要。";
}

export function projectContentExecutionLanguage(execution?: GeneralExecutionDto): GeneralExecutionDto | undefined {
  if (!execution) return execution;
  return {...execution, timeline:execution.timeline.map(entry => entry.kind === "status" && entry.publicSummary
    ? {...entry, publicSummary:chineseContentSummary(entry.publicSummary)} : entry)};
}
