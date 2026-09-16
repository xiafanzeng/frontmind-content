/** Server-resolved references. A reference identifies material used, not claim-level proof. */
export type EnterpriseQaAnswerSource = {
  id: string;
  kind: "published_knowledge" | "user_attachment";
  title: string;
};

export type EnterpriseQaAnswerMeta = {
  schemaVersion: 1;
  sources: EnterpriseQaAnswerSource[];
};

export function parseEnterpriseQaAnswerMeta(value: unknown): EnterpriseQaAnswerMeta | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const record = value as Record<string, unknown>;
  if (record.schemaVersion !== 1 || !Array.isArray(record.sources) || record.sources.length > 64) return undefined;
  const sources: EnterpriseQaAnswerSource[] = [];
  for (const entry of record.sources) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return undefined;
    const source = entry as Record<string, unknown>;
    if (typeof source.id !== "string" || !source.id || typeof source.title !== "string" || !source.title || !["published_knowledge", "user_attachment"].includes(String(source.kind))) return undefined;
    sources.push({ id: source.id, title: source.title, kind: source.kind as EnterpriseQaAnswerSource["kind"] });
  }
  return { schemaVersion: 1, sources };
}

export type EnterpriseQaAnswerLength = {
  kind: "ordinary" | "multiple" | "detailed";
  maxCharacters: 300 | 450 | 800;
};

/** Count Unicode characters, not UTF-16 code units; never cut a model answer. */
export function enterpriseQaAnswerCharacterCount(text: string): number {
  return Array.from(text.normalize("NFC").replace(/\s/gu, "")).length;
}

export function enterpriseQaAnswerLength(prompt: string): EnterpriseQaAnswerLength {
  if (/(?:详细|详尽|深入|展开)(?:地|的|一下)?(?:说明|介绍|解释|讲|分析|回答|说说)|(?:请|希望|需要|要)(?:你)?(?:详细|详尽)|详细版|完整分析|in\s+detail|detailed\s+(?:answer|explanation)/iu.test(prompt)) {
    return { kind: "detailed", maxCharacters: 800 };
  }
  const questions = prompt.match(/[？?]/gu)?.length ?? 0;
  const numbered = prompt.match(/(?:^|[\n；;])\s*(?:\d+[.、)）]|[一二三四五六七八九十]+[、.）)])/gu)?.length ?? 0;
  if (questions >= 2 || numbered >= 2) {
    return { kind: "multiple", maxCharacters: 450 };
  }
  return { kind: "ordinary", maxCharacters: 300 };
}
