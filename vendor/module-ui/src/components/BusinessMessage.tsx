import React, { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { AlertCircle, BookOpen, CheckCircle2, Copy, Download, FileText, Loader2, User, X } from "lucide-react";
import { cn, copyToClipboard } from "../lib/utils";
import MarkdownRenderer from "./MarkdownRenderer";
import FilePreview from "./FilePreview";
import ImagePreview from "./ImagePreview";
const PdfDocumentViewer = React.lazy(() => import("./PdfDocumentViewer"));
import { Dialog, DialogContent, DialogTitle } from "./ui/dialog";
import { Button } from "./ui/button";
import { toast } from "sonner";
import EnterpriseQaReferences from "./EnterpriseQaReferences";
import IntermediateSteps from "./IntermediateSteps";
import { sanitizeBrandText, usesModuleFileTransport } from "./file-preview-runtime";
import { moduleFileContentUrl } from "../lib/module-file-source";

export interface BusinessAttachment {
  id: string; type: "file" | "image"; name: string; fileId?: string; base64?: string; blobUrl?: string; file?: File; expiresAt?: number; expired?: boolean;
}
export interface BusinessMessageStep { id: string; type: string; label: string; description?: string; details?: string }
export interface BusinessMessageStepGroup { id: string; title: string; steps: BusinessMessageStep[]; description?: string }
export interface BusinessMessageOutputFile { fileUrl: string; fileName: string; mimeType: string }
export interface BusinessMessageData {
  id: string; role: "user" | "assistant"; content: string; timestamp?: number; attachments?: BusinessAttachment[]; outputFiles?: BusinessMessageOutputFile[]; inlineImages?: {src:string;alt?:string}[]; intermediateSteps?: BusinessMessageStep[]; stepGroups?: BusinessMessageStepGroup[]; elapsedTime?: number; isStepsPlaceholder?: boolean; enterpriseQaAnswer?: any;
}
export interface BusinessMessageRuntime {
  MessageActions?: React.ComponentType<any>; FilePreview?: React.ComponentType<any>; ImagePreview?: React.ComponentType<any>; EnterpriseQaReferences?: React.ComponentType<any>; IntermediateSteps?: React.ComponentType<any>;
  sanitizeText?: (text:string)=>string; deliveryHeaders?: ()=>Record<string,string>; fetchWithAuth?: (url:string,name:string)=>Promise<string>; buildProxyDownloadUrl?: (url:string,name?:string,download?:boolean)=>string|null; nativeDownload?: (url:string,name:string)=>void;
  filterWaitingText?: (text:string)=>string;
}
const defaultFetchWithAuth = async (url:string, _name:string) => {
  const sourceUrl = usesModuleFileTransport()
    ? moduleFileContentUrl({ kind: "external", url })
    : url;
  const response = await fetch(sourceUrl, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`文件读取失败（HTTP ${response.status}）`);
  return URL.createObjectURL(await response.blob());
};
const defaultBuildProxyDownloadUrl = (url: string) => {
  if (!usesModuleFileTransport()) return null;
  return moduleFileContentUrl({ kind: "external", url });
};
const defaultRuntime: Required<Pick<BusinessMessageRuntime,"sanitizeText"|"deliveryHeaders"|"fetchWithAuth"|"buildProxyDownloadUrl"|"nativeDownload">> = {
  sanitizeText: sanitizeBrandText, deliveryHeaders: () => ({}), fetchWithAuth: defaultFetchWithAuth, buildProxyDownloadUrl: defaultBuildProxyDownloadUrl, nativeDownload: (url,name) => { const a=document.createElement("a"); a.href=url; a.download=name; a.rel="noopener"; document.body.appendChild(a); a.click(); a.remove(); },
};
const filterWaitingText = (content: string) => content.replace(/^等待用户输入[。.…]*$/gm, "").replace(/等待用户输入[。.…]*/g, "").trim();
const fileTypeLabel = (filename: string, mimeType?: string) => {
  const ext = filename.split(".").at(-1)?.toLowerCase() ?? "";
  const labels: Record<string, string> = { xlsx: "Excel 工作表", xls: "Excel 工作表", csv: "CSV 数据表", docx: "Word 文档", doc: "Word 文档", pptx: "PowerPoint 演示文稿", ppt: "PowerPoint 演示文稿", pdf: "PDF 文档", zip: "ZIP 压缩包", txt: "文本文档", md: "Markdown 文档", json: "JSON 文件", png: "PNG 图片", jpg: "JPEG 图片", jpeg: "JPEG 图片", webp: "WebP 图片", gif: "GIF 图片", svg: "SVG 图片" };
  if (labels[ext]) return labels[ext];
  const mime = mimeType?.split(";")[0].trim().toLowerCase() ?? "";
  if (mime.startsWith("image/")) return "图片";
  if (mime.startsWith("audio/")) return "音频";
  if (mime.startsWith("video/")) return "视频";
  if (mime.startsWith("text/")) return "文本文档";
  return "文件";
};
function MarkdownFileReader({ runtime,
  fileUrl,
  fileName,
  isOpen,
  onClose,
}: {
  fileUrl: string;
  fileName: string;
  isOpen: boolean;
  onClose: () => void;
  runtime: BusinessMessageRuntime;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDownloading, setIsDownloading] = useState(false);
  const [size, setSize] = useState({ width: 720, height: 560 });
  const displayFileName = runtime.sanitizeText!(fileName);
  const resizingRef = useRef(false);
  const startRef = useRef({ x: 0, y: 0, w: 0, h: 0 });

  useEffect(() => {
    if (isOpen && fileUrl) {
      setLoading(true);
      setError(null);
      setContent(null);

      // Fetch through the same-origin proxy when the source is an external signed URL.
      const displayName = runtime.sanitizeText!(fileName);
      const normalizedUrl =
        runtime.buildProxyDownloadUrl!(fileUrl, displayName, false) || fileUrl;

      fetch(normalizedUrl, {
        credentials: "include",
        headers: runtime.deliveryHeaders!(),
      })
        .then(async (res) => {
          if (!res.ok) {
            throw new Error(`HTTP ${res.status}`);
          }
          const ct = res.headers.get("content-type") || "";
          if (
            ct.includes("application/json") &&
            fileUrl.includes("/v1/files/")
          ) {
            await res.body?.cancel().catch(() => undefined);
            throw new Error("服务返回了文件信息，但未返回文件内容");
          }
          return res.text();
        })
        .then((text) => {
          // FIX #4: Sanitize FrontMind references in file content before display
          setContent(runtime.sanitizeText!(text));
          setLoading(false);
        })
        .catch((err) => {
          setError(err.message || "加载失败");
          setLoading(false);
        });
    }
  }, [isOpen, fileUrl, fileName]);

  const handleDownload = useCallback(async () => {
    setIsDownloading(true);
    try {
      if (content) {
        const downloadName = runtime.sanitizeText!(fileName);
        const blob = new Blob([content], {
          type: "text/markdown;charset=utf-8",
        });
        const url = URL.createObjectURL(blob);
        runtime.nativeDownload!(url, downloadName);
        URL.revokeObjectURL(url);
      } else {
        const downloadName = runtime.sanitizeText!(fileName);
        const proxiedUrl = runtime.buildProxyDownloadUrl!(fileUrl, downloadName, true);
        if (proxiedUrl) {
          const blobUrl = await runtime.fetchWithAuth!(proxiedUrl, downloadName);
          runtime.nativeDownload!(blobUrl, downloadName);
          URL.revokeObjectURL(blobUrl);
          return;
        }
        const blobUrl = await runtime.fetchWithAuth!(fileUrl, downloadName);
        runtime.nativeDownload!(blobUrl, downloadName);
        URL.revokeObjectURL(blobUrl);
      }
    } catch (err) {
      console.error("Download failed:", err);
    } finally {
      setIsDownloading(false);
    }
  }, [content, fileUrl, fileName]);

  const onResizeMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      resizingRef.current = true;
      startRef.current = {
        x: e.clientX,
        y: e.clientY,
        w: size.width,
        h: size.height,
      };

      const onMouseMove = (ev: MouseEvent) => {
        if (!resizingRef.current) return;
        const dw = ev.clientX - startRef.current.x;
        const dh = ev.clientY - startRef.current.y;
        setSize({
          width: Math.max(
            400,
            Math.min(window.innerWidth * 0.95, startRef.current.w + dw),
          ),
          height: Math.max(
            300,
            Math.min(window.innerHeight * 0.95, startRef.current.h + dh),
          ),
        });
      };

      const onMouseUp = () => {
        resizingRef.current = false;
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [size],
  );

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        showCloseButton={false}
        className="p-0 flex flex-col overflow-hidden"
        style={{
          width: size.width,
          height: size.height,
          maxWidth: "95vw",
          maxHeight: "95vh",
        }}
      >
        <DialogTitle className="sr-only">{displayFileName}</DialogTitle>

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-border/30 flex-shrink-0">
          <div className="flex items-center gap-2">
            <BookOpen className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-foreground/80 truncate max-w-[400px]">
              {displayFileName}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              disabled={isDownloading}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              {isDownloading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              下载
            </button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="w-8 h-8"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar px-8 py-6">
          {loading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-primary" />
              <span className="ml-2 text-sm text-muted-foreground">
                加载中...
              </span>
            </div>
          )}
          {error && (
            <div className="flex items-center justify-center py-12 text-destructive">
              <AlertCircle className="w-5 h-5 mr-2" />
              <span className="text-sm">加载失败: {error}</span>
            </div>
          )}
          {content !== null && !loading && (
            <div className="max-w-3xl mx-auto">
              <MarkdownRenderer
                content={content}
                className="prose prose-sm max-w-none prose-p:my-2 prose-headings:my-3 prose-pre:my-3 prose-ul:my-2 prose-ol:my-2"
              />
            </div>
          )}
        </div>

        {/* Resize handle */}
        <div
          onMouseDown={onResizeMouseDown}
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
          style={{ touchAction: "none" }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            className="text-muted-foreground/40"
          >
            <path d="M14 14L8 14L14 8Z" fill="currentColor" />
            <path d="M14 14L11 14L14 11Z" fill="currentColor" opacity="0.5" />
          </svg>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PdfViewer({ runtime,
  fileUrl,
  fileName,
  isPdf,
  isOpen,
  onClose,
}: {
  fileUrl: string;
  fileName: string;
  isPdf: boolean;
  isOpen: boolean;
  onClose: () => void;
  runtime: BusinessMessageRuntime;
}) {
  if (isPdf) {
    return (
      <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
        <DialogContent
          showCloseButton={false}
          className="p-0 flex flex-col overflow-hidden"
          style={{
            width: 1100,
            height: 760,
            maxWidth: "96vw",
            maxHeight: "96vh",
          }}
        >
          <DialogTitle className="sr-only">
            {runtime.sanitizeText!(fileName)}
          </DialogTitle>
          <React.Suspense
            fallback={
              <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-5 w-5 animate-spin" />
                正在启动 PDF 阅读器…
              </div>
            }
          >
            <PdfDocumentViewer
              fileName={fileName}
              source={{ kind: "external", url: fileUrl }}
              onClose={onClose}
            />
          </React.Suspense>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <HtmlFileViewer
      fileUrl={fileUrl}
      fileName={fileName}
      isOpen={isOpen}
      onClose={onClose}
      runtime={runtime}
    />
  );
}

/**
 * HTML remains isolated in a maximally restricted iframe. PDF files use the
 * PDF.js canvas viewer above and never enter an iframe.
 */
function HtmlFileViewer({ runtime,
  fileUrl,
  fileName,
  isOpen,
  onClose,
}: {
  fileUrl: string;
  fileName: string;
  isOpen: boolean;
  onClose: () => void;
  runtime: BusinessMessageRuntime;
}) {
  const [isDownloading, setIsDownloading] = useState(false);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [size, setSize] = useState({ width: 800, height: 640 });
  const displayFileName = runtime.sanitizeText!(fileName);
  const resizingRef = useRef(false);
  const startRef = useRef({ x: 0, y: 0, w: 0, h: 0 });

  // Load blob URL when dialog opens
  useEffect(() => {
    if (isOpen && fileUrl) {
      setLoading(true);
      setError(null);
      setBlobUrl(null);

      // If it's already a blob URL, use directly
      if (fileUrl.startsWith("blob:")) {
        setBlobUrl(fileUrl);
        setLoading(false);
        return;
      }

      // Convert an HTML data URL to a blob URL for sandboxed iframe rendering.
      if (fileUrl.startsWith("data:")) {
        try {
          const parts = fileUrl.split(",");
          const mimeMatch = parts[0]?.match(/:(.*?);/);
          const mime = mimeMatch ? mimeMatch[1] : "application/octet-stream";
          const binaryStr = atob(parts[1]);
          const bytes = new Uint8Array(binaryStr.length);
          for (let k = 0; k < binaryStr.length; k++) {
            bytes[k] = binaryStr.charCodeAt(k);
          }
          const blob = new Blob([bytes], { type: mime });
          setBlobUrl(URL.createObjectURL(blob));
        } catch (e) {
          console.error("Failed to convert data URL to blob:", e);
          setError("文件格式转换失败");
        }
        setLoading(false);
        return;
      }

      // Fetch with auth headers and create a sanitized blob URL through the proxy.
      const displayName = runtime.sanitizeText!(fileName);
      runtime.fetchWithAuth!(fileUrl, displayName)
        .then((url) => {
          setBlobUrl(url);
          setLoading(false);
        })
        .catch((err) => {
          console.error("Failed to load file for preview:", err);
          setError(err.message);
          setLoading(false);
        });
    }

    return () => {
      if (
        blobUrl &&
        blobUrl.startsWith("blob:") &&
        !fileUrl.startsWith("blob:")
      ) {
        URL.revokeObjectURL(blobUrl);
      }
    };
  }, [isOpen, fileUrl]);

  const handleDownload = useCallback(async () => {
    setIsDownloading(true);
    try {
      // If we already have a blobUrl from preview, use it directly. Blob/data
      // URLs use the download attribute; external fallback URLs use native HTTPS.
      if (blobUrl) {
        runtime.nativeDownload!(blobUrl, runtime.sanitizeText!(fileName));
      } else if (fileUrl.startsWith("blob:") || fileUrl.startsWith("data:")) {
        runtime.nativeDownload!(fileUrl, runtime.sanitizeText!(fileName));
      } else {
        const downloadName = runtime.sanitizeText!(fileName);
        const proxiedUrl = runtime.buildProxyDownloadUrl!(fileUrl, downloadName, true);
        if (proxiedUrl) {
          runtime.nativeDownload!(proxiedUrl, downloadName);
          return;
        }
        const downloadBlobUrl = await runtime.fetchWithAuth!(fileUrl, downloadName);
        runtime.nativeDownload!(downloadBlobUrl, downloadName);
        URL.revokeObjectURL(downloadBlobUrl);
      }
    } catch (err) {
      console.error("Download failed:", err);
    } finally {
      setIsDownloading(false);
    }
  }, [fileUrl, fileName, blobUrl]);

  const onResizeMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      resizingRef.current = true;
      startRef.current = {
        x: e.clientX,
        y: e.clientY,
        w: size.width,
        h: size.height,
      };

      const onMouseMove = (ev: MouseEvent) => {
        if (!resizingRef.current) return;
        const dw = ev.clientX - startRef.current.x;
        const dh = ev.clientY - startRef.current.y;
        setSize({
          width: Math.max(
            400,
            Math.min(window.innerWidth * 0.95, startRef.current.w + dw),
          ),
          height: Math.max(
            300,
            Math.min(window.innerHeight * 0.95, startRef.current.h + dh),
          ),
        });
      };

      const onMouseUp = () => {
        resizingRef.current = false;
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    },
    [size],
  );

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        showCloseButton={false}
        className="p-0 flex flex-col overflow-hidden"
        style={{
          width: size.width,
          height: size.height,
          maxWidth: "95vw",
          maxHeight: "95vh",
        }}
      >
        <DialogTitle className="sr-only">{displayFileName}</DialogTitle>

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-border/30 flex-shrink-0">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-primary" />
            <span className="text-sm font-medium text-foreground/80 truncate max-w-[400px]">
              {displayFileName}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownload}
              disabled={isDownloading}
              className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground disabled:opacity-50"
            >
              {isDownloading ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              下载
            </button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="w-8 h-8"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* File viewer */}
        <div className="flex-1 overflow-hidden bg-muted/20">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-8 h-8 animate-spin text-primary/50" />
              <span className="ml-2 text-sm text-muted-foreground">
                加载文件中...
              </span>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full gap-3">
              <FileText className="w-12 h-12 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">文件加载失败</p>
              <p className="text-xs text-muted-foreground/60">{error}</p>
              <Button onClick={handleDownload} variant="outline" size="sm">
                <Download className="w-4 h-4 mr-1" />
                直接下载
              </Button>
            </div>
          ) : blobUrl ? (
            <iframe
              src={blobUrl}
              title={displayFileName}
              className="w-full h-full border-0"
              style={{ minHeight: "100%" }}
              sandbox=""
            />
          ) : null}
        </div>

        {/* Resize handle */}
        <div
          onMouseDown={onResizeMouseDown}
          className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
          style={{ touchAction: "none" }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            className="text-muted-foreground/40"
          >
            <path d="M14 14L8 14L14 8Z" fill="currentColor" />
            <path d="M14 14L11 14L14 11Z" fill="currentColor" opacity="0.5" />
          </svg>
        </div>
      </DialogContent>
    </Dialog>
  );
}


function UserAttachmentImage({ attachment, runtime }: { attachment: BusinessAttachment; runtime: BusinessMessageRuntime }) {
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  useEffect(() => { if (attachment.base64 || attachment.blobUrl || !attachment.file) { setLocalUrl(null); return; } const nextUrl=URL.createObjectURL(attachment.file); setLocalUrl(nextUrl); return () => URL.revokeObjectURL(nextUrl); }, [attachment.base64, attachment.blobUrl, attachment.file]);
  const source=attachment.base64 || attachment.blobUrl || localUrl || ""; if(!source && !attachment.fileId) return null; const PreviewImage = runtime.ImagePreview ?? ImagePreview;
  return <PreviewImage {...(source ? {src:source} : {fileId:attachment.fileId!})} alt={runtime.sanitizeText!(attachment.name)} className="max-w-[200px] max-h-[200px]" expiresAt={attachment.expiresAt} expired={attachment.expired} />;
}

export default function BusinessMessage({
  message,
  isFinalReply,
  inlineContent,
  isRunning,
  generalChatLinks,
  fixedElapsedTime,
  suppressKnowledgeArtifacts,
  onDelete,
  runtime: suppliedRuntime,
}: {
  message: BusinessMessageData;
  isFinalReply?: boolean;
  inlineContent?: React.ReactNode;
  isRunning?: boolean;
  generalChatLinks?: boolean;
  fixedElapsedTime?: number;
  suppressKnowledgeArtifacts?: boolean;
  onDelete?: () => void;
  runtime?: BusinessMessageRuntime;
}) {
  const host = { ...defaultRuntime, ...(suppliedRuntime ?? {}) };
  const Actions = host.MessageActions ?? ((props:any) => <>{props.children}</>);
  const Preview = host.FilePreview ?? FilePreview;
  const PreviewImage = host.ImagePreview ?? ImagePreview;
  const References = host.EnterpriseQaReferences ?? EnterpriseQaReferences;
  const Steps = host.IntermediateSteps ?? IntermediateSteps;
  const isUser = message.role === "user";
  const [mdReaderOpen, setMdReaderOpen] = useState(false);
  const [mdReaderFile, setMdReaderFile] = useState<{
    url: string;
    name: string;
  } | null>(null);
  const [pdfViewerOpen, setPdfViewerOpen] = useState(false);
  const [pdfViewerFile, setPdfViewerFile] = useState<{
    url: string;
    name: string;
    isPdf: boolean;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const visibleOutputFiles = suppressKnowledgeArtifacts
    ? message.outputFiles?.filter((file) => {
        const filename = file.fileName.toLowerCase();
        const mimeType = file.mimeType.toLowerCase();
        return (
          !filename.endsWith(".zip") &&
          !filename.endsWith(".html") &&
          !filename.endsWith(".htm") &&
          !mimeType.includes("zip") &&
          !mimeType.includes("html")
        );
      })
    : message.outputFiles;

  const openMdReader = useCallback((url: string, name: string) => {
    setMdReaderFile({ url, name });
    setMdReaderOpen(true);
  }, []);

  const openPdfViewer = useCallback(
    (url: string, name: string, isPdf: boolean) => {
      setPdfViewerFile({ url, name, isPdf });
      setPdfViewerOpen(true);
    },
    [],
  );

  // Check file types
  const isMdFile = (fileName: string) => {
    const ext = fileName.split(".").pop()?.toLowerCase();
    return ext === "md" || ext === "markdown";
  };

  const isPdfFile = (fileName: string, mimeType?: string) => {
    if (mimeType?.includes("pdf")) return true;
    const ext = fileName.split(".").pop()?.toLowerCase();
    return ext === "pdf";
  };

  const isHtmlFile = (fileName: string, mimeType?: string) => {
    if (mimeType?.includes("html")) return true;
    const ext = fileName.split(".").pop()?.toLowerCase();
    return ext === "html" || ext === "htm";
  };

  // Filter "等待用户输入" from content (req 8)
  const displayContent = isUser
    ? message.content
    : (suppliedRuntime?.filterWaitingText ?? filterWaitingText)(message.content);

  // Apply FrontMind brand sanitization for assistant messages
  const sanitizedContent =
    !isUser && displayContent
      ? host.sanitizeText!(displayContent)
      : displayContent;

  // Sanitize step groups labels and descriptions
  const sanitizedStepGroups =
    !isUser && message.stepGroups
      ? message.stepGroups.map((group) => ({
          ...group,
          title: host.sanitizeText!(group.title),
          description: group.description
            ? host.sanitizeText!(group.description)
            : undefined,
          steps: group.steps.map((step) => ({
            ...step,
            label: host.sanitizeText!(step.label),
            description: step.description
              ? host.sanitizeText!(step.description)
              : undefined,
          })),
        }))
      : message.stepGroups;
  const canCopyReply =
    isFinalReply ?? (!isRunning && !message.isStepsPlaceholder);

  // Copy handler - uses sanitizedContent for assistant messages
  const handleCopyMessage = () => {
    const contentToCopy = isUser ? displayContent : sanitizedContent;
    if (!contentToCopy) return;
    void copyToClipboard(contentToCopy).then((ok) => {
      if (ok) {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } else {
        toast.error("复制失败");
      }
    });
  };

  const handleArtifactDownload = useCallback(
    async (href: string) => {
      const matchingImage = message.inlineImages?.find(
        (image) => image.src === href,
      );
      const matchingFile = visibleOutputFiles?.find(
        (file) => file.fileUrl === href,
      );
      const downloadName = host.sanitizeText!(
        matchingFile?.fileName ||
          matchingImage?.alt ||
          href.split("/").filter(Boolean).at(-2) ||
          "frontmind-artifact",
      );
      try {
        const blobUrl = await host.fetchWithAuth!(href, downloadName);
        host.nativeDownload!(blobUrl, downloadName);
        URL.revokeObjectURL(blobUrl);
      } catch (error) {
        console.error("Artifact download failed:", error);
        toast.error("文件下载失败", {
          description: error instanceof Error ? error.message : "请稍后重试",
        });
      }
    },
    [message.inlineImages, visibleOutputFiles],
  );

  return (
    <>
      <Actions
        message={message}
        allowCopy={isUser || canCopyReply}
        onDelete={onDelete}
      >
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          data-message-role={message.role}
          className={cn("brand-conversation-message flex items-start gap-3", `brand-conversation-message--${message.role}`, isUser && "flex-row-reverse")}
        >
          {/* User identity stays visible; assistant messages are intentionally
              text-first and do not carry a robot avatar. */}
          {isUser && (
            <div className="brand-conversation-message__avatar flex flex-shrink-0 flex-col items-center gap-0.5" aria-label="用户">
              <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-full bg-accent/15 text-accent">
                <User className="h-4 w-4" />
              </div>
            </div>
          )}

          {/* Message content */}
          <div
            className={cn(
              "brand-conversation-message__content chat-message-content space-y-2",
              isUser
                ? "max-w-[92%] items-end sm:max-w-[80%]"
                : "w-full max-w-none items-start",
              inlineContent ? "w-full !max-w-full" : undefined,
            )}
          >
            {/* Intermediate steps (assistant only) */}
            {!isUser &&
              sanitizedStepGroups &&
              sanitizedStepGroups.length > 0 && (
                <Steps
                  stepGroups={sanitizedStepGroups}
                  isRunning={isRunning && !message.elapsedTime}
                />
              )}

            {/* Attachments (user) - with PDF/HTML inline viewer support */}
            {message.attachments && message.attachments.length > 0 && (
                <div
                  aria-label="消息附件"
                  className={cn("brand-conversation-message__attachments flex flex-wrap gap-2 mb-1", isUser && "justify-end")}
              >
                {message.attachments.map((att) => (
                  <div key={att.id}>
                    {att.type === "image" && !(att.expired === true || (att.expiresAt !== undefined && att.expiresAt <= Date.now())) ? (
                      <UserAttachmentImage attachment={att} runtime={host} />
                    ) : (
                      // PDF, HTML and every other user file share one source
                      // resolver. In particular, local PDFs reach
                      // PdfDocumentViewer through sourceFile instead of being
                      // forced through the remote preparation endpoint.
                      <Preview file={att} />
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Text content */}
            {displayContent && displayContent.trim() !== "" && (
              <div
                className={cn(
                  "brand-conversation-message__answer text-[16px] leading-relaxed",
                  isUser
                    ? "rounded-2xl rounded-tr-md border border-[#e4e4e7] bg-[#f4f4f5] px-4 py-3 text-foreground"
                    : "chat-message-body px-0 pt-1 text-foreground",
                )}
              >
                {isUser ? (
                  <p className="brand-conversation-message__user-text whitespace-pre-wrap break-words">
                    {displayContent}
                  </p>
                ) : (
                  <MarkdownRenderer
                    content={sanitizedContent}
                    allowCopy={canCopyReply}
                    generalChatLinks={generalChatLinks}
                    onArtifactDownload={handleArtifactDownload}
                    className="prose prose-sm max-w-none prose-p:my-1.5 prose-headings:my-2 prose-pre:my-2 prose-ul:my-1 prose-ol:my-1"
                  />
                )}
              </div>
            )}

            {!isUser && <References key={message.id} answer={message.enterpriseQaAnswer} />}

            {/* Inline images (from API output) */}
            {message.inlineImages && message.inlineImages.length > 0 && (
              <div className="flex flex-wrap gap-2 mt-1">
                {message.inlineImages.map((img, i) => (
                  <PreviewImage
                    key={i}
                    src={img.src}
                    alt={host.sanitizeText!(img.alt || "image")}
                    className="max-w-[300px]"
                  />
                ))}
              </div>
            )}

            {inlineContent}

            {/* Output files (assistant) - with PDF/HTML inline viewer and MD reader */}
            {visibleOutputFiles && visibleOutputFiles.length > 0 && (
              <div className="space-y-1.5 mt-1">
                {visibleOutputFiles.map((file, i) => {
                  const displayOutputFileName = host.sanitizeText!(
                    file.fileName,
                  );
                  const isMarkdown = isMdFile(displayOutputFileName);
                  const isPdf = isPdfFile(displayOutputFileName, file.mimeType);
                  const isHtml = isHtmlFile(
                    displayOutputFileName,
                    file.mimeType,
                  );
                  return (
                    <div
                      key={i}
                      data-workbench-output-key={`${message.id}:${i}`}
                      onClick={(e) => {
                        if (isMarkdown) {
                          e.preventDefault();
                          openMdReader(file.fileUrl, displayOutputFileName);
                        } else if (isPdf || isHtml) {
                          e.preventDefault();
                          openPdfViewer(
                            file.fileUrl,
                            displayOutputFileName,
                            isPdf,
                          );
                        }
                      }}
                      className="cursor-pointer"
                    >
                      {isMarkdown ? (
                        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-2xl bg-card/80 hover:bg-secondary/70 transition-all group border border-border/70 shadow-sm">
                          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                            <BookOpen className="w-4 h-4 text-primary/60" />
                          </div>
                          <div className="flex-1 overflow-hidden">
                            <p className="text-xs font-medium text-foreground/70 truncate">
                              {displayOutputFileName}
                            </p>
                            <p className="text-xs text-muted-foreground/50">
                              点击在页面内阅读
                            </p>
                          </div>
                          <BookOpen className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      ) : isPdf || isHtml ? (
                        <div className="flex items-center gap-2.5 px-3 py-2.5 rounded-2xl bg-card/80 hover:bg-secondary/70 transition-all group border border-border/70 shadow-sm">
                          <div className="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center flex-shrink-0">
                            <FileText className="w-4 h-4 text-red-500/60" />
                          </div>
                          <div className="flex-1 overflow-hidden">
                            <p className="text-xs font-medium text-foreground/70 truncate">
                              {displayOutputFileName}
                            </p>
                            <p className="text-xs text-muted-foreground/50">
                              {isPdf ? "点击查看 PDF" : "点击查看 HTML"}
                            </p>
                          </div>
                          <BookOpen className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      ) : (
                        <div
                          data-output-download
                          onClick={async (e) => {
                            e.stopPropagation();
                            try {
                              const downloadName = displayOutputFileName;
                              const proxiedUrl = host.buildProxyDownloadUrl!(
                                file.fileUrl,
                                downloadName,
                                true,
                              );
                              if (proxiedUrl) {
                                host.nativeDownload!(proxiedUrl, downloadName);
                                return;
                              }
                              const blobUrl = await host.fetchWithAuth!(
                                file.fileUrl,
                                downloadName,
                              );
                              host.nativeDownload!(blobUrl, downloadName);
                              URL.revokeObjectURL(blobUrl);
                            } catch (err) {
                              console.error("Download failed:", err);
                            }
                          }}
                          className="flex items-center gap-2.5 px-3 py-2.5 rounded-2xl bg-card/80 hover:bg-secondary/70 transition-all group border border-border/70 cursor-pointer shadow-sm"
                        >
                          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0">
                            <FileText className="w-4 h-4 text-primary/60" />
                          </div>
                          <div className="flex-1 overflow-hidden">
                            <p className="text-xs font-medium text-foreground/70 truncate">
                              {displayOutputFileName}
                            </p>
                            <p className="text-xs text-muted-foreground/50">
                              {fileTypeLabel(displayOutputFileName, file.mimeType)}
                            </p>
                          </div>
                          <Download className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Keep the reply action beside the content, without time metadata. */}
            {!isUser && displayContent?.trim() && canCopyReply && (
              <div
                className={cn(
                  "chat-message-actions flex items-center justify-start",
                )}
              >
                {/* Copy button for assistant messages */}
                {!isUser && displayContent && displayContent.trim() !== "" && (
                  <button
                    type="button"
                    onClick={handleCopyMessage}
                    className={cn(
                      "inline-flex min-h-7 items-center gap-1 rounded-md bg-transparent px-0 py-1 text-[11px] font-medium transition-all duration-200 hover:bg-transparent active:scale-95",
                      copied
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-muted-foreground hover:text-primary",
                    )}
                    title="复制内容"
                  >
                    {copied ? (
                      <>
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        已复制
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        复制
                      </>
                    )}
                  </button>
                )}
              </div>
            )}
          </div>
        </motion.div>
      </Actions>

      {/* Markdown file reader dialog */}
      {mdReaderFile && (
        <MarkdownFileReader
          runtime={host}
          fileUrl={mdReaderFile.url}
          fileName={mdReaderFile.name}
          isOpen={mdReaderOpen}
          onClose={() => {
            setMdReaderOpen(false);
            setMdReaderFile(null);
          }}
        />
      )}

      {/* PDF/HTML viewer dialog */}
      {pdfViewerFile && (
        <PdfViewer
          runtime={host}
          fileUrl={pdfViewerFile.url}
          fileName={pdfViewerFile.name}
          isPdf={pdfViewerFile.isPdf}
          isOpen={pdfViewerOpen}
          onClose={() => {
            setPdfViewerOpen(false);
            setPdfViewerFile(null);
          }}
        />
      )}
    </>
  );
}


export { BusinessMessage };
