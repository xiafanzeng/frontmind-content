export interface Attachment {
  id: string; type: "file" | "image"; name: string;
  fileId?: string; base64?: string; blobUrl?: string; file?: File;
  expiresAt?: number; expired?: boolean;
}
