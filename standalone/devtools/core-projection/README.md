# 共享 UI 来源

清单中的四个 vendor 文件精确投影自 Core 主仓 `packages/module-ui/src/dashboard/` 和 `packages/module-contracts/src/content-production.ts`；补丁基线为 `e57e9e2ff06cc3c8bcf30fb9e466a58657c81b12`。

`shared-source.patch` 是针对该 Core 基线的补丁，保留导航链接和修饰键点击，提供侧栏子内容插槽、正式宿主可注入的目标 Provider，以及服务端验证的主体与资料包选择契约。`projection-manifest.json` 记录公开投影路径、提交来源与哈希。共享文件以 Core 为唯一源码，不独立维护 vendor。

补丁使用零上下文格式。仅在上述确切基线执行 `git apply --check --unidiff-zero shared-source.patch`，再使用 `git apply --unidiff-zero shared-source.patch` 应用；已经合并相同 Core 提交时无需再次应用。该补丁包含共享 UI 和契约；主体 API、数据库迁移、正式宿主和会话缓存适配也必须随本轮 Core 改动一并整合，不能只发布公开前端。
