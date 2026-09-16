# FrontMind 内容制作模块

公开仓库：<https://github.com/xiafanzeng/frontmind-content>
开发域名：<https://content.frontmind.cn>

`module/` 是与主仓 `modules/content/` 双向同步的完整业务源码。独立启动壳由子仓 `standalone/` 提供；主仓通过公开宿主接口装配同一业务页面。

## 业务源码

- `client/ContentProductionWorkspace.tsx`：原内容工作台、任务输入、文件选择、成果、继续使用资料包和任务历史。
- `client/ContentProductionConfirmation.tsx`：原工作流人工确认，不自动跳过确认或改写 revision。
- `client/runtime.tsx`：独立内容会话、上传、持久化提交信封、同请求重试、刷新恢复、停止与成果访问。没有通用智能体入口。
- `server/task-handlers.ts`：创建校验、冻结输入与工作流版本、确认冲突检查。
- `server/task-persistence.ts` / `persistence.ts` / `state.ts`：原执行账本行锁、用途校验、观察排序与状态归并。
- `worker/observations.ts`：读取内容工作流状态，过滤私有任务快照与内部文件。
- `workflows/source/`：有效工作流可编辑源码；构建生成版本和哈希，已开始任务沿用冻结版本。
- `schema/`：实际使用的共享执行账本及内容 JSON 字段契约。本次不创建替代业务表或迁移旧任务。

## 预览与真实运行

在公开仓执行 `pnpm install --frozen-lockfile`、`pnpm dev`。本地预览使用明确标注的合成数据，不发起真实研究或付费调用。`pnpm typecheck`、`pnpm test`、`pnpm build` 用于验证提交。

真实子域名通过服务器开发门禁后直接使用固定测试工作区。账户、租户、凭据与通用执行存储由私有宿主注入。模块不查询登录或成员表。主仓可以注入已发布知识作为可选连接，独立模式只使用手工材料。

不得把本地预览标记为供应商真实验收通过。需要供应商配置和指定的付费测试目标时，验收记录单独列出。
