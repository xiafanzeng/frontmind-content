# FrontMind content

Public business source and standalone UI for [content.frontmind.cn](https://content.frontmind.cn).

## Local preview

Use Node.js 22 and pnpm 10.4.1:

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm typecheck
pnpm test
pnpm build
```

Local preview uses synthetic fixtures and labels them as preview data. It does not connect to test databases or paid providers. The same module/client components are built into the real development domain. Live persistence, jobs, files and provider execution require its private Core runtime.

Business code and dependencies belong in module/. The independent entry, root Vite settings and root shell dependencies also participate in the development-domain build. Only module/ synchronizes into the private main repository. vendor/ is a reviewed version from main; request shared changes there.

Open the development domain through the configured browser gateway; no product login or tenant selection belongs in this standalone shell. Gateway credentials and deployment settings are supplied privately and never committed here.
