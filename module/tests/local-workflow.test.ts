import { EventEmitter } from "node:events";
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Readable, Writable } from "node:stream";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

const testPython = process.env.FRONTMIND_PYTHON ?? "python3";

const childProcess = vi.hoisted(() => ({ snapshots: [] as unknown[], read: vi.fn(), spawn: vi.fn() }));
vi.mock("node:child_process", async importOriginal => {
  const original = await importOriginal<typeof import("node:child_process")>();
  const { promisify } = await import("node:util");
  const execFile = vi.fn();
  Object.defineProperty(execFile, promisify.custom, { value: childProcess.read });
  return { ...original, execFile, spawn: childProcess.spawn };
});
import { localWorkflowPlugin, localActionArgs } from "../../standalone/local-workflow";

function runnerState(revision = 7) {
  return {
    schema_version: "4.11", artifact_type: "frontmind_content_job_state", workflow_version: "4.11",
    job_id: "job_1", job_kind: "article", revision, created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:01Z",
    stage: "E8", status: "awaiting_blueprint_confirmation", pending_action: null,
    current_pause: { pause_type: "awaiting_blueprint_confirmation", title: "确认写作方案", available_choices: [], revision, requires_user_input: true, user_pause: true, must_stop: true },
    flags: {}, decisions: {}, p0_route: null,
  };
}
function fixture() {
  const root = mkdtempSync(join(tmpdir(), "frontmind-local-backend-test-"));
  const job = join(root, "job_1"); mkdirSync(job);
  const snapshot = { directory: "job_1", brand: "合成测试品牌", busy: false, state: runnerState(), reviews: [], files: [] as string[], processes: [] as unknown[] };
  childProcess.snapshots = [snapshot];
  let handler: any;
  function restart() {
    const plugin = localWorkflowPlugin({ root, configDir: join(root, "private-config-unused"), python: "isolated-python-unused" });
    (plugin.configureServer as Function)({ middlewares: { use: (value: unknown) => { handler = value; } } });
  }
  restart();
  async function request(method: string, path: string, value?: unknown, headers: Record<string, string> = {}) {
    const req = Object.assign(Readable.from(value === undefined ? [] : [Buffer.from(typeof value === "string" ? value : JSON.stringify(value))]), {
      method, url: path, headers: { host: "127.0.0.1:5173", origin: "http://127.0.0.1:5173", ...headers },
    });
    let status = 200, text = "", contentType = "";
    const res = Object.assign(new Writable({ write(chunk, _encoding, callback) { text += chunk.toString(); callback(); } }), {
      writeHead(code: number, values: Record<string, string>) { status = code; contentType = values["Content-Type"] ?? ""; },
    });
    const finished = new Promise<void>((resolve, reject) => { res.once("finish", resolve); res.once("error", reject); });
    await handler(req, res, () => { throw new Error("Unexpected fall-through"); });
    await finished;
    return { status, body: text && contentType.startsWith("application/json") ? JSON.parse(text) : null, text };
  }
  return { root, job, snapshot, request, restart };
}
const confirmation = (requestId: string, extra: Record<string, unknown> = {}) => ({
  clientRequestId: requestId, conversationId: "job_1", prompt: "确认写作方案", localAssetIds: [],
  contentProductionAction: { kind: "confirm_blueprint", revision: 7 }, ...extra,
});

beforeEach(() => {
  childProcess.read.mockReset().mockImplementation(async () => ({ stdout: JSON.stringify(childProcess.snapshots), stderr: "" }));
  childProcess.spawn.mockReset().mockImplementation(() => Object.assign(new EventEmitter(), { kill: vi.fn() }));
});
afterEach(() => { vi.restoreAllMocks(); });

it("polls snapshots without starting a model process or exposing local storage paths", async () => {
  const view = fixture();
  for (let i = 0; i < 3; i++) {
    const response = await view.request("GET", "/api/content/conversations");
    expect(response.status).toBe(200);
    expect(response.body[0]).toMatchObject({ id: "job_1", status: "awaiting_input" });
    expect(response.text).not.toContain(view.root);
    expect(response.text).not.toContain("private-config");
    const task = await view.request("GET", "/api/frontmind/v2/tasks/job_1");
    expect(task.body.contentProduction).toMatchObject({ runnerRevision: 7, confirmation: "awaiting_blueprint_confirmation" });
  }
  expect(childProcess.read).toHaveBeenCalledTimes(1);
  expect(childProcess.read.mock.calls[0][1][1]).toMatch(/workflow_snapshot\.py$/);
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("dispatches exact revision arguments once and consumes the confirmation while running", async () => {
  const view = fixture();
  const input = confirmation("request_1");
  expect((await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", input)).status).toBe(202);
  expect(childProcess.spawn).toHaveBeenCalledTimes(1);
  const args = childProcess.spawn.mock.calls[0][1];
  expect(args.slice(args.indexOf("--") + 1)).toEqual(["continue", "--job-dir", view.job, "--revision", "7", "--accept-blueprint"]);
  const repeat = await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", input);
  expect(repeat.body).toMatchObject({ status: "running", contentProduction: { confirmation: null, availableActions: [] } });
  expect(childProcess.spawn).toHaveBeenCalledTimes(1);
  expect((await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", { ...input, prompt: "另一个请求内容" })).status).toBe(409);
  view.snapshot.state = runnerState(8);
  childProcess.spawn.mock.results[0].value.emit("close", 0);
  expect((await view.request("GET", "/api/frontmind/v2/tasks/job_1")).body).toMatchObject({ status: "awaiting_input", contentProduction: { runnerRevision: 8, confirmation: "awaiting_blueprint_confirmation" } });
});

it("refreshes an imported job's placeholder brand after a reference pack is bound", async () => {
  const clock = vi.spyOn(Date, "now"); clock.mockReturnValue(1000);
  const view = fixture(); view.snapshot.brand = "内容任务";
  expect((await view.request("GET", "/api/content/conversations")).body[0].title).toBe("内容任务 · 问题文章");
  view.snapshot.brand = "合成测试品牌"; clock.mockReturnValue(3000);
  expect((await view.request("GET", "/api/content/conversations")).body[0].title).toBe("合成测试品牌 · 问题文章");
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it.each([
  { contentProductionAction: { kind: "confirm_blueprint", revision: 6 } },
  { contentProductionAction: { kind: "confirm_competitors", revision: 7 } },
  { conversationId: "other_conversation" },
])("rejects a stale or mismatched confirmation before launch: %j", async extra => {
  const view = fixture();
  expect((await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("request_invalid", extra))).status).toBe(409);
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("launches only one process for concurrent confirmations of the same task revision", async () => {
  const view = fixture();
  const results = await Promise.all([
    view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("request_a")),
    view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("request_b")),
  ]);
  expect(results.map(result => result.status).sort()).toEqual([202, 409]);
  expect(childProcess.spawn).toHaveBeenCalledTimes(1);
});

it("creates at most one native job per conversation even with concurrent request IDs", async () => {
  const view = fixture();
  const upload = await view.request("POST", "/api/frontmind/v2/assets", "合成企业材料", { "x-frontmind-filename": "materials.md" });
  expect(upload.status).toBe(200);
  const input = { conversationId: "new_conversation", prompt: "创建品牌资料包", localAssetIds: [upload.body.localAssetId], contentProduction: { mode: "new_reference_pack", enterpriseName: "合成测试品牌", knowledgeSource: "files" } };
  const results = await Promise.all([
    view.request("POST", "/api/frontmind/v2/tasks", { ...input, clientRequestId: "create_a" }),
    view.request("POST", "/api/frontmind/v2/tasks", { ...input, clientRequestId: "create_b" }),
  ]);
  expect(results.map(result => result.status).sort()).toEqual([202, 409]);
  expect(childProcess.spawn).toHaveBeenCalledTimes(1);
  const args = childProcess.spawn.mock.calls[0][1];
  expect(args.slice(args.indexOf("--") + 1, args.indexOf("--") + 3)).toEqual(["reference-pack", "create"]);
});

it("passes the frozen v16.3 article genre and ordered subjects as separate arguments", async () => {
  const view = fixture();
  const upload = await view.request("POST", "/api/frontmind/v2/assets", "合成资料", {"x-frontmind-filename":"materials.md"});
  const result = await view.request("POST", "/api/frontmind/v2/tasks", {
    clientRequestId:"roundup_create",conversationId:"roundup_conversation",prompt:"写行业盘点",localAssetIds:[upload.body.localAssetId],
    contentProduction:{mode:"single_article",enterpriseName:"合成测试品牌",knowledgeSource:"files",genre:"industry_roundup",subjectScope:["合成测试品牌","竞品甲","竞品乙"],comparisonDimensions:["噪音","价格"],articleFocus:"吹风机的便携选择",readerQuestions:["噪音怎样比较？"],excludedTopics:["电动牙刷"],question:"高速吹风机怎么选"},
  });
  expect(result.status).toBe(202);
  const args = childProcess.spawn.mock.calls[0][1] as string[];
  expect(args.slice(args.indexOf("--focus"))).toEqual(["--focus","吹风机的便携选择","--reader-question","噪音怎样比较？","--exclude-topic","电动牙刷","--genre","industry_roundup","--subject","合成测试品牌","--subject","竞品甲","--subject","竞品乙","--dimension","噪音","--dimension","价格"]);
});

it("exposes deterministic fact-gate categories and launches explicit repair without replacing the job", async () => {
  const view = fixture();
  (view.snapshot as any).state = {...runnerState(),status:"running_article_production",current_pause:null,
    pending_action:{action:"article_fact_repair",error:{code:"fact_gate_failed"}},flags:{article_production_step:"deliver"}};
  (view.snapshot as any).factGate = {issueCount:2,categories:["缺少横向对比表","数字缺少同句依据"],publishReady:false};
  const task = await view.request("GET", "/api/frontmind/v2/tasks/job_1");
  expect(task.body.contentProduction).toMatchObject({factGate:{issueCount:2,publishReady:false},availableActions:["repair_article_facts"]});
  const result = await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", {
    clientRequestId:"repair_1",conversationId:"job_1",prompt:"事实返工",localAssetIds:[],
    contentProductionAction:{kind:"repair_article_facts",revision:7,rejectedClaimIds:["F01"]},
  });
  expect(result.status).toBe(202);
  const args = childProcess.spawn.mock.calls[0][1] as string[];
  expect(args.slice(args.indexOf("--")+1)).toEqual(["continue","--job-dir",view.job,"--revision","7","--repair-facts","--reject-fact-claim","F01"]);
});

it("retains the original confirmation after a CLI failure and keeps its diagnostic private", async () => {
  const view = fixture();
  await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("will_fail"));
  childProcess.spawn.mock.results[0].value.emit("error", new Error("PRIVATE_FIXTURE_SENTINEL"));
  const result = await view.request("GET", "/api/frontmind/v2/tasks/job_1");
  expect(result.body).toMatchObject({ status: "error", contentProduction: { runnerRevision: 7, confirmation: "awaiting_blueprint_confirmation" } });
  expect(result.text).not.toContain("PRIVATE_FIXTURE_SENTINEL");
  const retry = await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("corrected_retry"));
  expect(retry.status).toBe(202);
  expect(childProcess.spawn).toHaveBeenCalledTimes(2);
});

it("blocks foreign hosts and origins without reading or launching a workflow", async () => {
  const view = fixture();
  expect((await view.request("GET", "/api/content/conversations", undefined, { host: "example.org" })).status).toBe(403);
  expect((await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("foreign"), { origin: "https://example.org" })).status).toBe(403);
  expect(childProcess.read).not.toHaveBeenCalled();
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("rejects an artifact that resolves outside its job", async () => {
  const view = fixture();
  const outside = join(view.root, "outside.md"); writeFileSync(outside, "PRIVATE_FIXTURE_SENTINEL");
  symlinkSync(outside, join(view.job, "escaped.md")); view.snapshot.files = ["escaped.md"];
  const response = await view.request("GET", "/api/content/conversations");
  expect(response.status).toBe(403);
  expect(response.text).not.toContain("PRIVATE_FIXTURE_SENTINEL");
  expect(response.text).not.toContain(view.root);
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("keeps user edits as a single CLI argument and never interpolates a shell command", () => {
  const edits = "保留引号 ' 和 $(echo secret)，只调整事实表达";
  expect(localActionArgs({ kind: "confirm_blueprint", revision: 7, blueprintEdits: edits }, "awaiting_blueprint_confirmation")).toEqual(["--revision", "7", "--blueprint-edits", edits]);
});

it.each([
  ["article", "awaiting_blueprint_confirmation", "--blueprint-edits", "--blueprint-supplement"],
  ["p0", "awaiting_p0_blueprint_confirmation", "--p0-blueprint-edits", "--p0-blueprint-supplement"],
])("passes one %s blueprint supplement to its native flag alongside the edits", async (kind, status, editsFlag, supplementFlag) => {
  const view = fixture();
  Object.assign(view.snapshot.state, { job_kind: kind, status });
  view.snapshot.state.current_pause.pause_type = status;
  const upload = await view.request("POST", "/api/frontmind/v2/assets", "合成补充事实", { "x-frontmind-filename": "supplement.md" });
  const response = await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("supplement", {
    localAssetIds: [upload.body.localAssetId],
    contentProductionAction: { kind: "revise_current_step", revision: 7, instructions: "使用补充事实更新方案" },
  }));
  expect(response.status).toBe(202);
  const args = childProcess.spawn.mock.calls[0][1];
  expect(args.slice(args.indexOf("--") + 1)).toEqual(["continue", "--job-dir", view.job, "--revision", "7", editsFlag, "使用补充事实更新方案", supplementFlag, join(view.root, ".local-ui", "uploads", upload.body.localAssetId, "supplement.md")]);
  expect(args).not.toContain("--input");
});

it("passes an imported P0 article to the native single-file input", async () => {
  const view = fixture();
  Object.assign(view.snapshot.state, { job_kind: "p0", status: "awaiting_p0_route" });
  view.snapshot.state.current_pause.pause_type = "awaiting_p0_route";
  const upload = await view.request("POST", "/api/frontmind/v2/assets", "合成旧文章", { "x-frontmind-filename": "original.md" });
  const response = await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("import_p0", {
    localAssetIds: [upload.body.localAssetId], contentProductionAction: { kind: "choose_p0_route", revision: 7, route: "import" },
  }));
  expect(response.status).toBe(202);
  const args = childProcess.spawn.mock.calls[0][1];
  expect(args.slice(args.indexOf("--") + 1)).toEqual(["continue", "--job-dir", view.job, "--revision", "7", "--p0-route", "import", "--p0-input", join(view.root, ".local-ui", "uploads", upload.body.localAssetId, "original.md")]);
});

it.each([
  ["article", "awaiting_blueprint_confirmation", { kind: "revise_current_step", revision: 7, instructions: "更新事实" }, ["first.md", "second.md"]],
  ["p0", "awaiting_p0_route", { kind: "choose_p0_route", revision: 7, route: "import" }, ["first.md", "second.md"]],
  ["article", "awaiting_question_research_inputs", { kind: "provide_question_research_inputs", revision: 7 }, ["answers.xlsx", "answer.md"]],
  ["article", "awaiting_question_research_inputs", { kind: "provide_question_research_inputs", revision: 7 }, ["first.xlsx", "second.xlsx"]],
  ["reference_pack", "awaiting_core_positioning_confirmation", { kind: "revise_current_step", revision: 7, instructions: "更新定位" }, ["facts.md"]],
  ["article", "awaiting_question_positioning_confirmation", { kind: "revise_current_step", revision: 7, instructions: "更新定位" }, ["facts.md"]],
])("rejects attachments that native %s / %s cannot consume completely without launching", async (kind, status, action, filenames) => {
  const view = fixture();
  Object.assign(view.snapshot.state, { job_kind: kind, status });
  view.snapshot.state.current_pause.pause_type = status;
  const localAssetIds = [];
  for (const filename of filenames) {
    const upload = await view.request("POST", "/api/frontmind/v2/assets", "合成材料", { "x-frontmind-filename": filename });
    localAssetIds.push(upload.body.localAssetId);
  }
  const response = await view.request("POST", "/api/frontmind/v2/tasks/job_1/messages", confirmation("unsupported_files", { localAssetIds, contentProductionAction: action }));
  expect(response.status).toBe(400);
  expect(response.body.error.message).toMatch(/附件|文件|问答表/);
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("runs the snapshot reader offline and excludes raw provider traces and escaped files", () => {
  const view = fixture();
  const raw = { ...runnerState(), reference_pack: { brand: "合成测试品牌" }, provider_api_key: "PRIVATE_FIXTURE_SENTINEL" };
  writeFileSync(join(view.job, "job_state.json"), JSON.stringify(raw));
  mkdirSync(join(view.job, "reviews")); writeFileSync(join(view.job, "reviews", "review_r7.md"), "# 待确认方案\n这是隔离测试。");
  mkdirSync(join(view.job, "deliverables")); writeFileSync(join(view.job, "deliverables", "article.md"), "合成测试文章");
  writeFileSync(join(view.root, "private.json"), "PRIVATE_FIXTURE_SENTINEL");
  symlinkSync(join(view.root, "private.json"), join(view.job, "deliverables", "escape.md"));
  const script = fileURLToPath(new URL("../../standalone/workflow_snapshot.py", import.meta.url));
  const result = spawnSync(testPython, ["-B", script, view.root], { encoding: "utf8", env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: "1" } });
  expect(result.status, result.stderr).toBe(0);
  const snapshots = JSON.parse(result.stdout);
  expect(snapshots[0]).toMatchObject({ directory: "job_1", brand: "合成测试品牌", busy: false, processes: [], files: ["deliverables/article.md"] });
  expect(snapshots[0].reviews).toHaveLength(1);
  expect(result.stdout).not.toContain("PRIVATE_FIXTURE_SENTINEL");
  expect(result.stdout).not.toContain(view.root);
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("turns native review links into safe artifact URLs while preserving external citations", async () => {
  const view = fixture();
  writeFileSync(join(view.job, "job_state.json"), JSON.stringify(runnerState()));
  mkdirSync(join(view.job, "reviews")); mkdirSync(join(view.job, "research"));
  const material = join(view.job, "research", "source.md"); writeFileSync(material, "合成业务材料");
  const review = `# 确认例文\n[打开完整 Markdown](<${material}>)\n[原网页](https://example.org/evidence)`;
  writeFileSync(join(view.job, "reviews", "review_r7.md"), review);
  const script = fileURLToPath(new URL("../../standalone/workflow_snapshot.py", import.meta.url));
  const snapshot = spawnSync(testPython, ["-B", script, view.root], { encoding: "utf8", env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: "1" } });
  expect(snapshot.status, snapshot.stderr).toBe(0);
  childProcess.snapshots = JSON.parse(snapshot.stdout);
  const response = await view.request("GET", "/api/content/conversations");
  expect(response.status).toBe(200);
  expect(response.text).not.toContain(view.root);
  expect(response.body[0].messages[0].content).toContain("/api/frontmind/v2/artifacts/");
  expect(response.body[0].messages[0].content).toContain("https://example.org/evidence");
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("re-registers persisted review attachments after a server restart without duplicating messages", async () => {
  const view = fixture();
  writeFileSync(join(view.job, "job_state.json"), JSON.stringify(runnerState()));
  mkdirSync(join(view.job, "reviews")); mkdirSync(join(view.job, "research"));
  const material = join(view.job, "research", "source.md"); writeFileSync(material, "合成业务材料");
  const review = `# 待确认\n[原文](<${material}>)`;
  writeFileSync(join(view.job, "reviews", "review_r7.md"), review);
  const script = fileURLToPath(new URL("../../standalone/workflow_snapshot.py", import.meta.url));
  const snapshot = spawnSync(testPython, ["-B", script, view.root], { encoding: "utf8", env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: "1" } });
  expect(snapshot.status, snapshot.stderr).toBe(0);
  childProcess.snapshots = JSON.parse(snapshot.stdout);
  const conversation = (await view.request("GET", "/api/content/conversations")).body[0];
  const outputs = conversation.messages[0].outputFiles;
  expect(outputs).toHaveLength(2);
  await view.request("PUT", "/api/content/conversations/job_1", conversation);
  view.restart();
  // Directly open an old URL: the download request itself must restore registration.
  expect((await view.request("GET", outputs[0].fileUrl)).text).toBe(review);
  expect((await view.request("GET", outputs[1].fileUrl))).toMatchObject({ status: 200, text: "合成业务材料" });
  const refreshed = (await view.request("GET", "/api/content/conversations")).body[0];
  expect(refreshed.messages).toHaveLength(1);
  expect(refreshed.messages[0].id).toBe(conversation.messages[0].id);
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("lists packaged deliveries and native writing reruns without exposing unpacked materials as deliveries", () => {
  const view = fixture();
  writeFileSync(join(view.job, "job_state.json"), JSON.stringify({ ...runnerState(), metadata: { writing_reruns: [{ rerun_id: "rerun_1" }, { rerun_id: "../../outside" }] } }));
  mkdirSync(join(view.job, "deliverables", "Reference_Pack_v1", "materials"), { recursive: true });
  mkdirSync(join(view.job, "deliverables", "rerun_1"));
  writeFileSync(join(view.job, "deliverables", "Reference_Pack_v1.zip"), "synthetic zip");
  writeFileSync(join(view.job, "deliverables", "Reference_Pack_v1", "materials", "source.md"), "synthetic source");
  writeFileSync(join(view.job, "deliverables", "rerun_1", "article.md"), "synthetic revision");
  const script = fileURLToPath(new URL("../../standalone/workflow_snapshot.py", import.meta.url));
  const result = spawnSync(testPython, ["-B", script, view.root], { encoding: "utf8", env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: "1" } });
  expect(result.status, result.stderr).toBe(0);
  expect(JSON.parse(result.stdout)[0].files).toEqual(["deliverables/Reference_Pack_v1.zip", "deliverables/rerun_1/article.md"]);
});

it("does not register provider or out-of-job files from native review links", async () => {
  const view = fixture();
  writeFileSync(join(view.job, "job_state.json"), JSON.stringify(runnerState()));
  mkdirSync(join(view.job, "reviews")); mkdirSync(join(view.job, "provider"));
  const provider = join(view.job, "provider", "secret.md"), outside = join(view.root, "outside.md");
  writeFileSync(provider, "PRIVATE_PROVIDER_SENTINEL"); writeFileSync(outside, "PRIVATE_OUTSIDE_SENTINEL");
  writeFileSync(join(view.job, "reviews", "review_r7.md"), `# 待确认\n[运行材料](<${provider}>)\n[外部本地文件](<${outside}>)\n[证据原网页](https://example.org/evidence)`);
  const script = fileURLToPath(new URL("../../standalone/workflow_snapshot.py", import.meta.url));
  const snapshot = spawnSync(testPython, ["-B", script, view.root], { encoding: "utf8", env: { PATH: process.env.PATH, PYTHONDONTWRITEBYTECODE: "1" } });
  expect(snapshot.status, snapshot.stderr).toBe(0);
  childProcess.snapshots = JSON.parse(snapshot.stdout);
  const response = await view.request("GET", "/api/content/conversations");
  expect(response.status).toBe(200);
  expect(response.text).not.toContain(view.root);
  expect(response.text).not.toContain("PRIVATE_");
  expect(response.body[0].messages[0].content).toContain("本地附件不可公开读取");
  expect(response.body[0].messages[0].content).toContain("https://example.org/evidence");
  expect(response.body[0].messages[0].outputFiles.map((file: { fileName: string }) => file.fileName)).toEqual(["阶段确认_版本7.md"]);
  expect(childProcess.spawn).not.toHaveBeenCalled();
});

it("returns only summary processes and anchors imported history without exposing diagnostics", async () => {
 const view=fixture();view.snapshot.processes=[{id:"attempt-1",startedAt:100,status:"completed",thinking:[{id:"context-1",timestamp:100,text:"正在处理：问题文章方案。",status:"recorded",rawThinking:"PRIVATE_REASONING"}],tools:[{id:"tool-1",timestamp:200,text:"未能完成核对网页来源。",status:"failed",reason:"来源地址未通过公网校验。",nextStep:"检查网络解析或补充可核验材料；保留地址安全校验。",functionName:"web_read",arguments:{url:"PRIVATE"},result:"PRIVATE"}],stack:"PRIVATE"}];
 const response=await view.request("GET","/api/content/conversations");expect(response.body[0].processes[0]).toMatchObject({id:"attempt-1",userMessageId:"history-attempt-1"});expect(response.body[0].messages.some((m:any)=>m.id==="history-attempt-1")).toBe(true);expect(response.body[0].execution).toBeUndefined();expect(response.text).not.toMatch(/PRIVATE|rawThinking|functionName|web_read|arguments|stack/);
});

it("keeps cancellation distinct and permits explicit recovery with a new round",async()=>{
 const view=fixture();await view.request("POST","/api/frontmind/v2/tasks/job_1/messages",confirmation("request_cancel"));await view.request("POST","/api/frontmind/v2/tasks/job_1/stop",{});childProcess.spawn.mock.results[0].value.emit("close",null);
 const cancelled=await view.request("GET","/api/content/conversations");expect(cancelled.body[0].status).toBe("cancelled");expect(cancelled.body[0].processes.at(-1)).toMatchObject({id:"turn-request_cancel",status:"cancelled",reason:"本次执行已取消。"});
 const retry=await view.request("POST","/api/frontmind/v2/tasks/job_1/messages",{clientRequestId:"retry_cancel",conversationId:"job_1",prompt:"重试当前执行",localAssetIds:[]});expect(retry.status).toBe(202);expect(childProcess.spawn.mock.calls.at(-1)?.[1]).toContain("--retry-current-action");const running=await view.request("GET","/api/content/conversations");expect(running.body[0].processes.find((p:any)=>p.id==="turn-request_cancel").status).toBe("cancelled");expect(running.body[0].processes.at(-1).status).toBe("running");
});

it("closes the acknowledged prior process when a confirmation starts the next turn",async()=>{
 const view=fixture();
 view.snapshot.processes=[{id:"attempt-prior",startedAt:100,status:"awaiting_input",thinking:[],tools:[{id:"prior-read",timestamp:110,status:"completed",text:"已完成读取登记材料。"}]}];
 expect((await view.request("POST","/api/frontmind/v2/tasks/job_1/messages",confirmation("next-confirmation"))).status).toBe(202);
 const conversation=(await view.request("GET","/api/content/conversations")).body[0];
 expect(conversation.processes.find((p:any)=>p.id==="attempt-prior").status).toBe("completed");
 expect(conversation.processes.find((p:any)=>p.id==="turn-next-confirmation").status).toBe("running");
});
