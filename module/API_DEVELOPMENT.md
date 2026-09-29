# 内容制作 API 开发入口

## 1. 现在可以改什么

`server/task-handlers.ts`（创建/确认规则）、`server/runtime.ts`（系统上下文、执行参数和文件策略）、`server/state.ts`、`server/task-persistence.ts`、`worker/`、`workflows/`。

可以修改本模块上游 API 请求、输入校验、响应解析、错误处理和业务状态机，也可以新增 API。不要把这些修改提交到主仓旧路径；旧路径主要是兼容装配，真实实现以本模块为准。

## 2. 新增 API

在 `module/server/http-api.ts` 的 `createModuleHttpApi(core)` 中注册 Express 路由，例如 `router.get("/your-feature", ...)`。发布后地址为 `/api/modules/content/your-feature`。`GET /api/modules/content/capabilities` 是可直接验证装配的只读接口，不代表供应商成功。

此文件与普通模块业务源码一样参与 delivery 构建与 sync 合回；主仓已有固定装载入口，不需要每加一个路径再修改主仓。现有 tRPC/REST API 可以继续在原模块路由文件中维护；新增公开扩展优先使用上述命名空间。

`core.context(req)` 给出服务器验证的账户、操作者、企业项目和 businessOwnerId/businessActorId。监控/发布的 businessOwnerId 是内部监控 UUID，其他模块是账户 ID 的字符串；不要混用。`core.database()` 复用现有数据库连接，不另开数据库或复制身份表。读写数据须显式限制所属工作区/owner，并复用已有同事务费用与幂等逻辑。

`core.environment` 是服务器环境配置，只用于服务端。已有供应商客户端使用它或现有授权执行句柄；禁止 `res.json(core.environment)`、回传 Key、记录完整认证请求头。新供应商需要一个新 Key 时，管理员只需配置服务器，业务调用仍由子仓实现。

异步 Express 4 路由须用 try/catch 处理错误；对外只返回稳定错误码/安全信息，不返回原始供应商错误中可能含有的凭据。

## 3. AI 流程边界

业务工作流、提示、输入输出契约和确认/恢复规则在模块代码。通用 OpenAI Agents 执行进程、持久化会话、沙箱、认证与统一账务由宿主复用；没有为五仓复制五套通用引擎。修改本模块业务不需要修改该引擎；修改通用执行器自身需要主仓发布。

## 4. 发布和验收

1. delivery 导出准确线上源码。
2. Pro 修改模块真实代码并返回协议 ZIP。
3. delivery 运行检查、提交子仓并发布本域名；依赖变化同步更新锁文件。
4. 核对 `/api/version`，登录开发门禁，再测试新增 API、原 API 和页面保存/刷新。
5. 真实付费操作按任务指定目标执行，并记录产生的任务/订单编号；HTTP 200 或目录查询不等于业务完成。
6. 验收后 sync 合回 `modules/content/`；生产 Dashboard 单独发布。

同一测试域名共用工作区，不能删除其他组员记录。GitHub public 只代表可阅读，推送和发布仍需 GitHub/私有构建权限。
