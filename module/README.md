# FrontMind 内容制作

公开仓库：https://github.com/xiafanzeng/frontmind-content
开发域名：https://content.frontmind.cn/

`module/` 对应主仓 `modules/content/`；公开仓 `standalone/` 是独立启动壳，不合回 Dashboard。

## 业务代码

材料输入、任务创建、逐步确认、原任务恢复、快照和成果下载。页面在 `client/`，业务服务在 `server/`，表定义在 `schema/`，后台处理在 `worker/`，有效工作流在 `workflows/`（各目录按实际业务存在）。

重点入口：`server/task-handlers.ts`（创建/确认规则）、`server/runtime.ts`（系统上下文、执行参数和文件策略）、`server/state.ts`、`server/task-persistence.ts`、`worker/`、`workflows/`。

新增后端 API 从 **`server/http-api.ts`** 开始，挂在 `/api/modules/content/`。此注册函数由真实开发环境和主仓共同装载；在本模块命名空间新增路径不需要修改主仓的逐接口允许清单。现有 API 地址保留。

## 开发方式

公开仓根目录执行 `pnpm install --frozen-lockfile`、`pnpm dev`；检查使用 `pnpm typecheck`、`pnpm test`、`pnpm build`。本地预览使用合成数据；真实保存、任务、上传下载和供应商调用在开发子域名检查。

先用 delivery skill 导出准确线上 SHA，交给 Pro 修改并返回 ZIP，再用 delivery skill 提交/部署子域名，验收后用 sync skill 合回主仓。见 [API 开发说明](API_DEVELOPMENT.md) 和 [Pro 交接规则](PRO_GUIDE.md)。

## 运行基础设施

主仓装配真实登录/租户或开发固定工作区、数据库连接、统一资金、文件存储和通用 AI 执行器。业务请求参数、状态机及结果解释由本模块维护。已有测试凭据在服务器配置，组员修改服务端调用代码后沿用它们，无需在本地拿 Key；新增供应商/新凭据仍需管理员配置服务器。服务端可读取注入环境，任何密钥都不得返回浏览器或写入公开 Git/ZIP。

开发入口可用、配置存在或本地测试通过，均不等于所有付费业务链路已验收；HANDOFF 必须记录实际检查范围。
