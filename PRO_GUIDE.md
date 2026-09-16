# Pro development guide

Start from the exact live commit supplied with your source ZIP, not an assumed repository HEAD. Preserve the module's current behavior and implement the requested code changes.

- module/client contains the real module UI; standalone/main.tsx mounts it in local preview and the live build.
- Put business dependencies in module/package.json. Root package.json contains only shell/build dependencies. Include the updated pnpm-lock.yaml when dependencies change.
- Do not implement product login, tenants, account management or the general agent. Private runtime supplies the fixed development workspace; main later injects real user/workspace context.
- Optional cross-module connections are injected by the main workspace. Independent inputs always remain available.
- Do not modify vendor/, credentials, deployment mapping, Core implementations or test runtime data.
- Run pnpm typecheck, pnpm test and pnpm build. State which checks actually ran. Local preview is not proof of provider execution.

Return handoff.json, HANDOFF.md and files/ containing complete changed files at repository-relative paths. handoff.json contains formatVersion:1, module:"content", the full baseCommit, mode:"changes", and an explicit delete list. Missing files are never treated as deletions. HANDOFF.md describes behavior, dependency changes, validations and limitations.

## Request template for Pro / Chat

Read [CAPABILITIES.md](CAPABILITIES.md) before selecting the scope. If the chat cannot read the fixed repository revision, attach the source ZIP exported from that same live revision.

```text
Read https://github.com/xiafanzeng/frontmind-content/tree/<full-40-character-SHA>
and its README.md, PRO_GUIDE.md and CAPABILITIES.md.

Module: content
Base commit: <the same full SHA>
Implement: <specific page, interaction and expected result>.

Modify the existing business components and their established CSS scope.
Preserve unrelated behavior. Return a downloadable ZIP containing actual
changed source files, handoff.json and HANDOFF.md. Report only checks you ran.
```

Example handoff.json:

```json
{
  "formatVersion": 1,
  "module": "content",
  "baseCommit": "<full-40-character-SHA>",
  "mode": "changes",
  "delete": []
}
```

Place complete changed files beneath `files/module/` or `files/standalone/` using their repository paths. Include allowed root build files and lockfile changes when needed. List removals explicitly in `delete`; represent a rename as an added file plus an explicit deletion. Exclude `.git`, environment files, credentials, dependencies, build artifacts and runtime data.

The delivery skill applies the ZIP in a separate worktree, checks the code and publishes only the requested development domain. `standalone/` changes participate in that build; only `module/` business source and dependencies synchronize into main. After publication, check the actual version, changed page, refresh and persistence. A local preview or successful build is not provider acceptance. Gateway and deployment configuration comes from trusted local settings and cannot be changed by the ZIP.

## Shared Dashboard presentation

The standalone app uses the original Dashboard sidebar, tabs, layout, and controls from vendor/module-ui. It only filters navigation to this business module. Keep business page and style changes in module/client so source synchronization brings them back to Dashboard. standalone/ only supplies runtime adapters and independent inputs; it is not merged into production. Shared shell changes are maintained in main and sent to vendor.
