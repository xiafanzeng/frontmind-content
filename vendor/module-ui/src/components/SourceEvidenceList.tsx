import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { useState, type ReactNode } from "react";
import "./source-evidence-list.css";

export type SourceEvidenceRow = {
  id: string;
  number?: number | string;
  title: string;
  site?: string | null;
  type?: "cited" | "reference" | null;
  publishedAt?: string | null;
  url?: string | null;
  excerpt?: string | null;
};

export function sourceEvidenceUrl(value?: string | null) {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

function sourceSite(row: SourceEvidenceRow) {
  if (row.site?.trim()) return row.site;
  const url = sourceEvidenceUrl(row.url);
  return url ? new URL(url).hostname : "—";
}

function sourceDate(value?: string | null) {
  if (!value?.trim()) return "—";
  // Preserve provider dates without inventing a publication time.
  const isoDate = /^(\d{4}-\d{2}-\d{2})(?:T|\s|$)/.exec(value);
  return isoDate?.[1] || value;
}

export default function SourceEvidenceList(props: {
  rows: SourceEvidenceRow[];
  resetKey: string;
  emptyText?: string;
  showType?: boolean;
  renderAction?: (row: SourceEvidenceRow) => ReactNode;
}) {
  // A new answer/filter/report must never inherit another source's expansion or page.
  return <SourceEvidenceListPage key={props.resetKey} {...props} />;
}

function SourceEvidenceListPage({
  rows,
  emptyText = "暂无来源",
  showType = true,
  renderAction,
}: {
  rows: SourceEvidenceRow[];
  emptyText?: string;
  showType?: boolean;
  renderAction?: (row: SourceEvidenceRow) => ReactNode;
}) {
  const [page, setPage] = useState(1);
  const [expandedTitles, setExpandedTitles] = useState<Set<string>>(new Set());
  const totalPages = Math.max(1, Math.ceil(rows.length / 20));
  const currentPage = Math.min(page, totalPages);
  const visibleRows = rows.slice((currentPage - 1) * 20, currentPage * 20);
  const toggle = (id: string, setter: typeof setExpandedTitles) =>
    setter((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <div className="fm-source-evidence" data-source-evidence>
      {rows.length ? (
        <>
          <table aria-label="来源证据列表">
            <thead>
              <tr>
                <th scope="col" className="fm-evidence-number">
                  序号
                </th>
                <th scope="col">来源标题</th>
                <th scope="col" className="fm-evidence-site">
                  网站／来源
                </th>
                {showType && (
                  <th scope="col" className="fm-evidence-type">
                    类型
                  </th>
                )}
                <th scope="col" className="fm-evidence-date">
                  时间
                </th>
                <th scope="col" className="fm-evidence-actions">
                  操作
                </th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, index) => {
                const url = sourceEvidenceUrl(row.url);
                const typeLabel =
                  row.type === "cited"
                    ? "文内引用"
                    : row.type === "reference"
                      ? "答案参考"
                      : "—";
                const titleExpanded = expandedTitles.has(row.id);
                return (
                  <tr key={row.id}>
                    <td className="fm-evidence-number">
                      {row.number ?? (currentPage - 1) * 20 + index + 1}
                    </td>
                    <td className="fm-evidence-content">
                      <button
                        type="button"
                        className={`fm-evidence-title ${titleExpanded ? "is-expanded" : ""}`}
                        title={row.title || "未命名来源"}
                        aria-expanded={titleExpanded}
                        onClick={() => toggle(row.id, setExpandedTitles)}
                      >
                        {row.title || "未命名来源"}
                      </button>
                      <div className="fm-evidence-mobile-meta">
                        <span>{sourceSite(row)}</span>
                        {showType && row.type && (
                          <span className={`fm-evidence-badge is-${row.type}`}>
                            {typeLabel}
                          </span>
                        )}
                        <span>{sourceDate(row.publishedAt)}</span>
                      </div>
                    </td>
                    <td className="fm-evidence-site">{sourceSite(row)}</td>
                    {showType && (
                      <td className="fm-evidence-type">
                        <span
                          className={`fm-evidence-badge is-${row.type || "unspecified"}`}
                        >
                          {typeLabel}
                        </span>
                      </td>
                    )}
                    <td
                      className="fm-evidence-date"
                      title={row.publishedAt || undefined}
                    >
                      {sourceDate(row.publishedAt)}
                    </td>
                    <td className="fm-evidence-actions">
                      <div>
                        {renderAction ? (
                          renderAction(row)
                        ) : url ? (
                          <a
                            href={url}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            查看来源 <ExternalLink size={12} />
                          </a>
                        ) : (
                          <span className="fm-evidence-no-link">—</span>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {totalPages > 1 && (
            <nav className="fm-evidence-pagination" aria-label="来源分页">
              <span>共 {rows.length} 条来源</span>
              <div>
                <button
                  type="button"
                  aria-label="上一页来源"
                  disabled={currentPage <= 1}
                  onClick={() => setPage(currentPage - 1)}
                >
                  <ChevronLeft size={15} />
                </button>
                <span>
                  {currentPage} / {totalPages}
                </span>
                <button
                  type="button"
                  aria-label="下一页来源"
                  disabled={currentPage >= totalPages}
                  onClick={() => setPage(currentPage + 1)}
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </nav>
          )}
        </>
      ) : (
        <p className="fm-evidence-empty">{emptyText}</p>
      )}
    </div>
  );
}
