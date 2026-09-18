import type { FilePreviewSource } from "./file-preview-source";
export function moduleFileContentUrl(source: Exclude<FilePreviewSource, {kind: "local"}>): string {
  if (source.kind === "external" && /^(blob:|data:)/.test(source.url)) return source.url;
  const url = new URL(source.kind === "owned_file" ? `/api/frontmind/v2/assets/${encodeURIComponent(source.fileId)}/content` : source.url, window.location.origin);
  if (url.origin !== window.location.origin || !/^\/api\/frontmind\/v2\/(?:assets|artifacts)\/[^/]+\/content$/.test(url.pathname)) throw new Error("该文件未通过当前模块的文件权限入口，请重新选择本模块的文件。");
  return url.pathname + url.search;
}
/** Endpoints retain server-side owner, module and task validation. URL input
 * never enables the legacy generic proxy or an external URL fetch. */
export async function loadModulePdfSource(source: FilePreviewSource, name: string, signal?: AbortSignal): Promise<FilePreviewSource> {
  if (source.kind === "local") return source;
  const expiresAt = source.kind === "owned_file" ? source.expiresAt : undefined;
  if (expiresAt !== undefined && expiresAt <= Date.now()) throw new Error("文件已超过 30 天，请重新上传");
  const response = await fetch(moduleFileContentUrl(source), {signal,credentials:"same-origin"});
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.error?.message || `文件读取失败（${response.status}）`);
  }
  const blob = await response.blob();
  if (blob.type.includes("json")) throw new Error("文件服务未返回 PDF 内容");
  return {kind:"local",file:new File([blob], name, {type:"application/pdf"}),expiresAt};
}
