# Pro handoff guide: Content

Use the exact public projection commit supplied by `frontmind-module-delivery`. Return a ZIP with `handoff.json`, `HANDOFF.md`, and complete changed files under `files/module/` or `files/standalone/`. Put explicit deletions in `handoff.json`; absent files are not deletions. Do not include `.git`, credentials, environment files, caches, customer data, private Core code, or deployment targets.

## Current boundary

- Projection path: `modules/content` in the private main repository.
- Production/application baseline: `332d5ef072104283601682a3aca165a127c14e2c`.
- Public repository and subdomain are not created by this source projection.
- Cross-module imports, authentication, provider credentials, persistence adapters, and deployment remain host-owned unless a file is explicitly present in this projection.

Describe dependencies and actual checks in `HANDOFF.md`. A ZIP is reviewed and merged in an isolated worktree; it does not automatically publish production or create external infrastructure.
