import { sanitizeFrontMindPublicText } from "@frontmind/module-contracts/public-text";
export interface BusinessFileRuntime {
  deliveryProjectHeaders(headers?: Record<string, string>): Record<string, string>;
  sanitizeBrandText(text: string): string;
}
let runtime: BusinessFileRuntime = {
  deliveryProjectHeaders: headers => ({...headers}),
  sanitizeBrandText: sanitizeFrontMindPublicText,
};
/** The host supplies workspace authentication; fixed development hosts need no identity headers. */
export function configureBusinessFileRuntime(value: BusinessFileRuntime) { runtime = value; }
export function deliveryProjectHeaders(headers?: Record<string,string>) { return runtime.deliveryProjectHeaders(headers); }
export function sanitizeBrandText(text: string) { return runtime.sanitizeBrandText(text); }
let moduleFileTransport = false;
/** Standalone hosts fetch only their existing purpose-scoped V2 asset/artifact endpoints. */
export function enableModuleFileTransport() { moduleFileTransport = true; }
export function usesModuleFileTransport() { return moduleFileTransport; }
