

export type ManusV2Attachment =
  | {
      file_id: string;
      filename: string;
      file_data?: never;
      mime_type?: never;
    }
  | {
      /** Official Manus v2 inline-file data URL (decoded payload <= 20 MiB). */
      file_data: string;
      filename: string;
      mime_type: string;
      file_id?: never;
    };


export type ManusV2CreatedFile = {
  fileId: string;
  filename: string;
  uploadUrl: string;
  uploadExpiresAt: number;
  requestId: string | null;
};


export type ManusV2ProviderFileDetail = {
  fileId: string;
  filename: string;
  status: "pending" | "uploaded" | "deleted" | "error";
  bytes: number | null;
  expiresAt: number;
  contentType: string | null;
  /**
   * Provider MIME is optional diagnostic evidence. Keeping its parse status
   * separate lets frozen-source consumers distinguish a missing value from a
   * malformed value without rejecting the otherwise valid file envelope.
   */
  contentTypeParseStatus: "valid" | "missing" | "invalid";
  requestId: string | null;
};


export type ManusV2FileConfirmationPolicy =
  | "strict"
  | "kb_frozen_source_advisory";


export type ProviderMimeDisposition =
  | "exact"
  | "generic"
  | "missing"
  | "invalid"
  | "different";
export function canonicalMediaType(value: unknown) {
  if (typeof value !== "string") return null;
  const mediaType = value.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  return /^[a-z0-9!#$&^_.+-]+\/[a-z0-9!#$&^_.+-]+$/u.test(mediaType)
    ? mediaType
    : null;
}
export function isOoxmlContainer(filename: string, expectedContentType: string) {
  const normalizedFilename = filename.trim().toLowerCase();
  return (
    (normalizedFilename.endsWith(".pptx") &&
      expectedContentType ===
        "application/vnd.openxmlformats-officedocument.presentationml.presentation") ||
    (normalizedFilename.endsWith(".docx") &&
      expectedContentType ===
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document") ||
    (normalizedFilename.endsWith(".xlsx") &&
      expectedContentType ===
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
  );
}


export function classifyManusV2ProviderFileMime(input: {
  filename: string;
  expectedContentType: string;
  providerContentType: string | null;
  providerContentTypeParseStatus?: "valid" | "missing" | "invalid";
}): ProviderMimeDisposition {
  const expected = canonicalMediaType(input.expectedContentType);
  if (!expected) return "invalid";
  const providerParseStatus =
    input.providerContentTypeParseStatus ??
    (input.providerContentType === null ? "missing" : "valid");
  if (providerParseStatus === "invalid") return "invalid";
  const provider = canonicalMediaType(input.providerContentType);
  if (providerParseStatus === "missing" || !input.providerContentType) {
    return "missing";
  }
  if (!provider) return "invalid";
  if (provider === expected) return "exact";
  if (
    provider === "application/octet-stream" ||
    provider === "binary/octet-stream" ||
    (provider === "application/zip" &&
      isOoxmlContainer(input.filename, expected))
  ) {
    return "generic";
  }
  return "different";
}


/**
 * Strict is the default for generic Manus consumers. Knowledge-base uploads
 * may opt into the advisory policy only after Dashboard has revalidated its
 * frozen local bytes, hash, size, filename and canonical MIME.
 */
export function isManusV2ProviderFileMimeUsable(input: {
  filename: string;
  expectedContentType: string;
  providerContentType: string | null;
  providerContentTypeParseStatus?: "valid" | "missing" | "invalid";
  confirmationPolicy?: ManusV2FileConfirmationPolicy;
}) {
  const expected = canonicalMediaType(input.expectedContentType);
  if (!expected) return false;
  const disposition = classifyManusV2ProviderFileMime(input);
  if (input.confirmationPolicy === "kb_frozen_source_advisory") return true;
  if (disposition === "exact") return true;
  if (disposition !== "generic") return false;
  const provider = canonicalMediaType(input.providerContentType);
  const filename = String(input.filename || "")
    .trim()
    .toLowerCase();
  if (provider === "application/zip" && isOoxmlContainer(filename, expected)) {
    return true;
  }
  if (provider !== "application/octet-stream") return false;
  return (
    (filename.endsWith(".zip") &&
      (expected === "application/zip" ||
        expected === "application/x-zip-compressed")) ||
    (filename.endsWith(".txt") && expected === "text/plain")
  );
}
