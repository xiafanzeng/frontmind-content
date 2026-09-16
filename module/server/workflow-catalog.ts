import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import release from "../workflows/release.json";
import type { ContentWorkflowBinding, FrozenContentTaskContext } from "../contracts/task-context";

// Compatibility for tasks created before version binding was introduced.
export const CONTENT_WORKFLOW_FILENAME = release.legacy.filename;
export const CONTENT_WORKFLOW_SHA256 = release.legacy.sha256;

function validateBinding(value: ContentWorkflowBinding): ContentWorkflowBinding {
  if (!value || !/^[a-f0-9]{64}$/u.test(value.sha256) ||
      !/^[A-Za-z0-9._-]+\.zip$/u.test(value.filename) ||
      !/^[A-Za-z0-9][A-Za-z0-9._-]*$/u.test(value.rootDirectory) ||
      !/^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/u.test(value.version)) {
    throw new Error("CONTENT_WORKFLOW_BINDING_INVALID");
  }
  return value;
}

function workflowRoots() {
  const configured = process.env.FRONTMIND_CONTENT_WORKFLOW_DIR;
  return [
    ...(configured ? [resolve(configured)] : []),
    resolve(process.cwd(), "dist/workflows/content"),
    resolve(process.cwd(), "apps/dashboard/dist/workflows/content"),
    resolve(process.cwd()),
    resolve(process.cwd(), "apps/dashboard"),
  ];
}

function retainedRoot() {
  const configured = process.env.FRONTMIND_CONTENT_WORKFLOW_STORE;
  if (configured) return resolve(configured);
  const assets = process.env.FRONTMIND_DASHBOARD_ASSET_DIR;
  return assets ? resolve(assets, "workflows/content") : null;
}

export function workflowForTask(context: FrozenContentTaskContext): ContentWorkflowBinding {
  return validateBinding(context.contentWorkflow ?? release.legacy);
}

export function originalContentWorkflowArchive(binding: ContentWorkflowBinding = release.legacy): Buffer {
  validateBinding(binding);
  const retained = retainedRoot();
  const paths = [
    ...workflowRoots().map(root => resolve(root, binding.filename)),
    ...(retained ? [resolve(retained, `${binding.sha256}.zip`)] : []),
  ];
  for (const path of paths) {
    if (!existsSync(path)) continue;
    const bytes = readFileSync(path);
    if (createHash("sha256").update(bytes).digest("hex") !== binding.sha256) {
      throw new Error("CONTENT_WORKFLOW_ARCHIVE_HASH_MISMATCH");
    }
    return bytes;
  }
  throw new Error(`CONTENT_WORKFLOW_ARCHIVE_UNAVAILABLE: ${binding.sha256}`);
}

/** Freeze before task creation. Immutable packages survive image replacement in the asset volume. */
export function freezeContentWorkflow(): ContentWorkflowBinding {
  const manifest = workflowRoots().map(root => resolve(root, "manifest.json")).find(existsSync);
  if (!manifest && process.env.NODE_ENV === "production") {
    throw new Error("CONTENT_WORKFLOW_MANIFEST_UNAVAILABLE");
  }
  const binding = validateBinding(manifest
    ? JSON.parse(readFileSync(manifest, "utf8")).current
    : release.legacy);
  const bytes = originalContentWorkflowArchive(binding);
  const retained = retainedRoot();
  if (process.env.NODE_ENV === "production" && !retained) {
    throw new Error("CONTENT_WORKFLOW_STORE_UNAVAILABLE");
  }
  if (retained) {
    const destination = resolve(retained, `${binding.sha256}.zip`);
    mkdirSync(dirname(destination), { recursive: true });
    try { writeFileSync(destination, bytes, { flag: "wx", mode: 0o600 }); }
    catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      if (createHash("sha256").update(readFileSync(destination)).digest("hex") !== binding.sha256) {
        throw new Error("CONTENT_WORKFLOW_STORED_ARCHIVE_HASH_MISMATCH");
      }
    }
  }
  return { ...binding };
}
