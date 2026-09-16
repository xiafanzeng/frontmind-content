# Pro development guide

Start from the exact live commit supplied with your source ZIP, not an assumed repository HEAD. Preserve the module's current behavior and implement the requested code changes.

- module/client contains the real module UI; standalone/main.tsx mounts it in local preview and the live build.
- Put business dependencies in module/package.json. Root package.json contains only shell/build dependencies. Include the updated pnpm-lock.yaml when dependencies change.
- Do not implement product login, tenants, account management or the general agent. Private runtime supplies the fixed development workspace; main later injects real user/workspace context.
- Optional cross-module connections are injected by the main workspace. Independent inputs always remain available.
- Do not modify vendor/, credentials, deployment mapping, Core implementations or test runtime data.
- Run pnpm typecheck, pnpm test and pnpm build. State which checks actually ran. Local preview is not proof of provider execution.

Return handoff.json, HANDOFF.md and files/ containing complete changed files at repository-relative paths. handoff.json contains formatVersion:1, module:"content", the full baseCommit, mode:"changes", and an explicit delete list. Missing files are never treated as deletions. HANDOFF.md describes behavior, dependency changes, validations and limitations.
