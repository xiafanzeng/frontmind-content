# 智谱 Managed Agents 与本地 OpenAI Agents SDK：本Workflow的选择

研究与实现日期：2026-09-21。外部能力来自以下官方资料；实际集成结果以VALIDATION_v4.13.0.md为准。

## 结论

本Workflow选择本地SDK作为新宿主。既有程序已经负责原文读取、工具执行、业务状态、用户确认、DeepSeek作者和文件导出；云端Agent/Environment并没有替代这些本地职责。当前Managed适配器每个动作创建专用Agent、Environment、Session，造成远端对象管理负担。这是当前实现的策略，不是说所有Managed应用都必须这样创建；复用云Agent/Environment也是另一种重构选择。

选择SDK的理由是将任务保存和资源生命周期统一到已有本地Job，不是断言SDK模型能力更强、无限并发、更便宜或只需十几行代码。云端托管环境、关机后继续执行和完整云基础设施是不同需求；本版没有用SDK伪装提供这些能力。

| 方面 | 原Managed实现 | 本版SDK |
|---|---|---|
| 资源 | 每动作创建远端Agent/Environment/Session，需考虑资源配额与归档 | Agent为本地对象，推理走Chat API；不创建上述对象 |
| 挂起 | 保留可继续的Session与平台状态；官方说明归档Session不能再继续 | 完整Job、文件SQLite和RunState自己保存，不设置自动TTL |
| 断线 | 事件日志可补取；环境/服务与会话状态仍需可用 | 已保存工具边界可恢复；正在请求的生成不能逐token接回 |
| 并发 | 服务商限流、运行及资源配额 | 不受Managed对象数量上限限制，仍受网关限流、本地资源和费用限制 |
| 托管计算 | 提供托管会话及环境能力；应用仍有本地职责 | 当前Agent/Runner在自己的进程运行，关机停止，不自带云worker |
| 自主工具调用 | 服务方运行Agent循环 | 官方Runner运行Agent循环，应用提供受限工具 |
| 可靠性 | 依赖云会话和本地工具正确衔接 | 应用承担备份、锁、断点、幂等与异常核对；本版增加这些职责 |
| 数据 | 内容到智谱，部分状态在远端 | 内容到XTY及上游，本地保存历史；不是本地推理或不留存承诺 |

智谱资料说明Session归档后仍保留历史，但不能创建新事件/资源；不要把Agent归档、Environment归档、Session归档混为一谈。未找到一个能无条件保证本账号任意Session闲置15天后恢复的官方承诺；不能据此断言智谱不能做到15天后继续。

SDK会话也不是默认永久保存。`SQLiteSession(id)`为内存；本版显式传文件路径，并将RunState与业务状态、原文、工具回执同时保存。15天后恢复依赖文件完整、版本兼容、凭据/模型可用与输入一致。SDK序列化暂停不等于任意崩溃的exactly-once，模型请求超时重试可能重复计费。

## 用户代码需要补什么

`from agents import Agent, Runner`来自openai-agents，不只是openai客户端包。仅设置AsyncOpenAI和base_url不会添加持久化Session、工具、断点或失败恢复；SDK默认模型接口也未必适配普通Chat网关。本版使用显式OpenAIChatCompletionsModel，每Agent自己的client，文件SQLite、RunState、白名单工具、submit_result停止、关闭tracing与自动重试。

不把一个长对话当全部业务状态。Job是主记录，按动作分Session，长时间用户暂停保留已完成产物。正常确认与中途失败的继续分别处理，保持原有业务页。

## 端点与模型

配置：https://api.xty.app/v1；接口：Chat Completions。XTY文档给出的普通Chat示例模型为gpt-4o，本版据此选择为明确默认值；没有证明提供的key可调用，也没有质量对比实验。qwen-xxx是占位符。Codex专用地址与模型示例不能直接证明普通Chat端点支持同一个模型。模型可显式配置，但不自动降级。DeepSeek作者保持原模型与参数。

## 官方参考

- SDK Sessions（SQLite内存/文件区别、会话历史、不同持久化后端）：https://openai.github.io/openai-agents-python/sessions/
- SDK模型与第三方Chat Completions适配：https://openai.github.io/openai-agents-python/models/
- SDK RunState序列化与中断恢复：https://openai.github.io/openai-agents-python/human_in_the_loop/
- SDK FunctionTool接口：https://openai.github.io/openai-agents-python/ref/tool/
- 智谱官方文档索引（Session归档、事件与资源生命周期）：https://docs.bigmodel.cn/llms.txt
- XTY入口：https://doc.xty.app/docs
- XTY OpenAI接口：https://doc.xty.app/docs/openai-api
- XTY Python示例：https://doc.xty.app/docs/16-python
- SDK固定版本：https://github.com/openai/openai-agents-python/releases/tag/v0.22.3 （2026-09-17发布）
- OpenAI客户端固定版本：https://github.com/openai/openai-python/releases/tag/v3.16.2 （2026-09-18发布）

以上不代表外部服务的账户授权、SLA或当前网络可达性已验证。没有触碰现有智谱或Website远端资源。
