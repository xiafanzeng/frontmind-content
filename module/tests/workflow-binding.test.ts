import { afterEach, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import release from "../workflows/release.json";
import { freezeContentWorkflow, originalContentWorkflowArchive, workflowForTask } from "../server/workflow-catalog";
import { contentProductionSystemContext, contentWorkflowRuntimeFor } from "../server/runtime";
import type { FrozenContentTaskContext } from "../contracts/task-context";

const roots: string[] = [];
const temporary = () => { const root = mkdtempSync(join(tmpdir(), "content-binding-")); roots.push(root); return root; };
afterEach(() => { vi.unstubAllEnvs(); roots.forEach(root => rmSync(root, { recursive: true, force: true })); roots.length = 0; });

it("freezes module-owned execution capabilities with the exact archive and retains historical bytes", () => {
  const root = temporary(), next = temporary(), store = temporary();
  vi.stubEnv("FRONTMIND_CONTENT_WORKFLOW_DIR", root);
  vi.stubEnv("FRONTMIND_CONTENT_WORKFLOW_STORE", store);
  const bytes = Buffer.from("synthetic workflow package");
  const binding = { version: release.version, rootDirectory: release.rootDirectory,
    filename: "workflow.zip", sha256: createHash("sha256").update(bytes).digest("hex") };
  writeFileSync(join(root, binding.filename), bytes);
  writeFileSync(join(root, "manifest.json"), JSON.stringify({ formatVersion: 1, current: binding }));
  const frozen = freezeContentWorkflow();
  expect(frozen).toEqual({ ...binding, runtime: "native_content_v1", capabilities: release.capabilities });
  vi.stubEnv("FRONTMIND_CONTENT_WORKFLOW_DIR", next);
  rmSync(root, { recursive: true });
  expect(originalContentWorkflowArchive(frozen)).toEqual(bytes);
});

it("restores a future frozen native release without falling back to legacy handoffs", () => {
  const context = { purpose: "content_production", contentProduction: { mode: "single_article" },
    contentWorkflow: { version: "4.20.0", filename: "workflow.zip", rootDirectory: "workflow", sha256: "a".repeat(64),
      runtime: "native_content_v1", capabilities: ["structured_article", "editorial_v16_8"] },
  } as FrozenContentTaskContext;
  expect(contentWorkflowRuntimeFor(context)).toBe("native_content_v1");
  expect(contentProductionSystemContext(context)).toContain("--pool-selection");
  expect(contentProductionSystemContext(context)).not.toContain("No external provider SDK");
  expect(() => workflowForTask({ ...context, contentWorkflow: { ...context.contentWorkflow!, runtime: "unknown" } } as unknown as FrozenContentTaskContext))
    .toThrow("CONTENT_WORKFLOW_BINDING_INVALID");
});

it("preserves legacy releases and does not grant newer editorial rules to them", () => {
  const context = { purpose: "content_production", contentProduction: { mode: "single_article" } } as FrozenContentTaskContext;
  expect(contentWorkflowRuntimeFor(context)).toBeUndefined();
  expect(contentProductionSystemContext(context)).toContain("No external provider SDK");
  expect(contentProductionSystemContext(context)).not.toContain("--pool-selection");
});


it("keeps a frozen v16.8.1 archive and native capabilities after the current release changes", () => {
  const store = temporary();
  vi.stubEnv("FRONTMIND_CONTENT_WORKFLOW_DIR", temporary());
  vi.stubEnv("FRONTMIND_CONTENT_WORKFLOW_STORE", store);
  const bytes = Buffer.from("synthetic immutable v16.8.1 workflow");
  const binding = { version: "4.13.2-v16.8.1", rootDirectory: release.rootDirectory,
    filename: "historical-v16.8.1.zip", sha256: createHash("sha256").update(bytes).digest("hex"),
    runtime: "native_content_v1" as const, capabilities: ["structured_article", "editorial_v16_8"] as const };
  writeFileSync(join(store, `${binding.sha256}.zip`), bytes);
  const context = { purpose: "content_production", contentProduction: { mode: "single_article" },
    contentWorkflow: { ...binding, capabilities: [...binding.capabilities] } } as FrozenContentTaskContext;
  expect(release.version).not.toBe(binding.version);
  expect(workflowForTask(context)).toEqual(context.contentWorkflow);
  expect(contentWorkflowRuntimeFor(context)).toBe("native_content_v1");
  expect(originalContentWorkflowArchive(workflowForTask(context))).toEqual(bytes);
  expect(contentProductionSystemContext(context)).toContain("--pool-selection");
});
