import type { EnterpriseQaAnswerMeta } from "../contracts/enterprise-qa-answer";

/** The original collapsed reference block shared by all business messages. */
export function EnterpriseQaReferences({ answer }: { answer?: EnterpriseQaAnswerMeta }) {
  if (!answer?.sources.length) return null;
  return (
    <details className="mt-4 rounded-lg border border-[#eaecf0] bg-white text-sm text-[#667085]">
      <summary className="cursor-pointer px-4 py-2.5 font-medium text-[#344054] focus-visible:outline-offset-2">
        参考资料（{answer.sources.length}）
      </summary>
      <ul className="divide-y divide-[#eaecf0] border-t border-[#eaecf0] px-4">
        {answer.sources.map((source) => (
          <li key={`${source.kind}:${source.id}`} className="flex items-start justify-between gap-3 py-2.5">
            <span className="min-w-0 break-words">{source.title}</span>
            <span className="shrink-0 text-xs leading-5">{source.kind === "published_knowledge" ? "企业资料" : "上传附件"}</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

export default EnterpriseQaReferences;
