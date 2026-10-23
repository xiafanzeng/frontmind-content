# 内容工作流开发

内容组可以直接修改本仓的完整 Workflow，并发布到 <https://content.frontmind.cn/>。

## 修改位置

- `module/workflows/source/scripts/frontmind_workflow.py`：任务阶段、人工确认和继续执行。
- `module/workflows/source/shared/`：模型调用、工具、研究、文章和标题实现。
- `module/workflows/source/config/`：公开的模型与参数配置；真实 Key 由服务器注入。
- `module/workflows/source/` 下各 Skill、Prompt、模板：实际执行规则。
- `module/server/runtime.ts`：网站如何把输入和确认交给原工作流。
- `module/server/state.ts`、`module/client/`：过程状态、失败提示及操作界面。
- `module/server/http-api.ts`：新增业务 API，自动挂载在 `/api/modules/content/`。

这些实现均随子仓代码构建到真实镜像，`standalone/local-workflow.ts` 仅为本地预览服务。业务修复应进入 `module/`。

## 版本与发布

1. 每轮从当前子域名导出完整交接 ZIP；由 Pro 修改，再用 delivery Skill 合并和发布。
2. 调整发行版本时更新 `release.json` 的 `version`。`runtime` 和 `capabilities` 在本模块声明，新任务会冻结执行方式与包哈希，不需要为每个新版本再修改私有主仓的版本允许列表。
3. 工作流打包器由实际 `source/` 生成 ZIP 和 SHA256，不提交生成包、运行记录或客户材料。
4. 已创建任务保留原版本和完整 Job 快照，不因发布自动升级。修复后的新任务使用新包；旧失败任务不能靠改版本号、删除回执或关闭一致性校验恢复。需要迁移时，应保留原包和原快照，先明确适用的修复范围。
5. 发布后在网站验证真实生成、人工确认、恢复和下载，再把已验收业务源码合回主仓。

## 本次故障的约束

模型原始响应和工具调用参数属于不可变执行证据。编号、补默认值等规范化只操作深拷贝。`tool_call_source_mismatch` 校验必须保留，不能通过重写原始响应掩盖错误。内部动作失败通过安全的错误码和阶段传给页面，不再显示持续执行。

`4.13.2-v16.8.1` 修复隔离执行环境的网页读取：本地执行仍检查 DNS；无外网网卡的沙箱通过固定可信代理的 CONNECT 校验公网目的地，实际 HTTP、重定向和 Reader 最终地址继续校验。该预检不调用模型或 Reader，不产生供应商费用。代理异常、私网或目标不可达会明确拒绝，不绕过网络边界。已知来源读取失败作为模型可见的工具错误回执；付费接口结果不明仍停止，不自动重做。原生失败后先回传原始状态和完整快照并结束本轮，禁止外层隐式重试。

新增供应商地址或服务器凭据仍需配置对应运行环境；已有工作流、模型参数、Prompt、业务 API 和页面不需要额外 GitHub 权限。当前内容组已拥有子仓和私有构建仓写权限。
