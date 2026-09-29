# v16 当前配置

DeepSeek 新请求采用 high；历史已冻结请求按原参数恢复。P01/P02 增加 XTY 案例研究与编辑准备，实际搜索并阅读两篇案例，再进入正式蓝图。

# Final_v14 当前执行说明

新建任务默认使用 `editorial-mission-v2`，以本版 `README.md`、`START_HERE.md` 和 `FIX_v4.13.2_Final_v14.md` 为准。正文采用 **DeepSeek 成稿 → DeepSeek E8 → XTY 文字意见 → 必要时 DeepSeek 返工一次 → 标题与导出**；P0 在 E8 后保留原第三遍文风编辑。XTY 只给文字意见，不回查来源或改写正文，返工后不再次审正文。

当前委托决定体裁、介绍层次、对象、篇幅与排版。素材和模型拟定构思作为参考数据，当前委托独立置于输入末尾；其中 `article_brief` 决定正文主次。编辑先读完整基稿，再读素材与例文。每阶段保留同一篇幅目标，不另设初稿预算，也不把明确上限变成补足任务。

DeepSeek 使用 `deepseek-v4-pro`、thinking enabled、`reasoning_effort=high` 和既有65536输出额度。其他模型、网关及备用恢复配置保持原配置。最终正文记录真实DeepSeek来源，标题、Word及后续改稿读取这一稿。

在新解压目录安装依赖并运行 `./scripts/frontmind preflight`，随后使用该目录的 `./scripts/frontmind`。新任务自动采用v14；历史任务和已冻结请求继续按原版本恢复，不自动重写或切换提示。验证新版案例使用新的Job目录，命令见 `README.md`。

下文保留基础接口与历史操作说明，其中“当前”“默认”等表述仅指对应历史版本；旧升级器不能代替本版完整程序，也不覆盖本节规则。

---

# v4.13.0 模型运行时

## 路由

默认宿主为本地OpenAI Agents SDK + XTY Chat Completions；实际入口为`shared.model_runtime.run_action` → `shared.agents_runtime.run_agents_action` → official `Agent`/`Runner.run`。不是把原手写循环改名。使用每Agent独立`AsyncOpenAI`和显式`OpenAIChatCompletionsModel`，没有全局`set_default_openai_client`的跨任务副作用。

宿主模型取config/xty.json，默认gpt-4o（网关文档示例，当前key实际权限未验证）。SDK 0.22.3和客户端3.16.2固定。HTTP retries=0、RunConfig tracing_disabled=True、parallel_tool_calls=False。保留完整事实/例文输入，不采用自动截断与静默摘要。更换模型/配置改变请求指纹，不自动重绑旧断点。

DeepSeek七类作者动作、system/user请求、Pro/max参数、P0 4.12.8 Skill与业务合同不变。旧Managed适配器保留，只在原动作请求身份匹配时显式恢复，不作为SDK失败后的备用供应商。智谱搜索/Reader/OCR仍按原适配器执行。

## 存储与恢复

持久化粒度是`Job/action/attempt`。SDK SQLiteSession保存历史，RunState在工具执行前保存，与工具状态及会话快照配对。内部approval仅用于断点，不新增业务确认。已有工具范围、完整读取要求、submit_result数据结构、来源校验和确定性导出继续有效。

工具执行前写started，执行后写completed回执。重启复用完成回执；started缺回执停止并要求核对。模型输出先保存再执行工具。submit_result成功即停止SDK，不再请求模型写一段“完成说明”。已成功动作重复进入只校验并返回原结果；生产禁止替代响应、测试SDK和外层模型伪造Provider结果。

持久化哈希用于检测不一致，不是对文件系统管理员的安全认证。只反序列化本机受控任务目录的RunState，不能接受浏览器提交的RunState JSON。SQLite和RunState依赖固定代码/SDK；备份、迁移、异常重试及并发边界见执行手册。

## 测试边界

`test_agents_runtime_v4130.py`及controller/session tests使用显式假的SDK和模型输出，SQLite为真实本地数据库。这些测试不验证官方SDK的内部实现。`test_agents_real_sdk_v4130.py`使用官方SDK、只模拟模型层；未安装依赖时显式skip。`probe_agents_gateway.py --live-tool`才是实际SDK+网关的计费工具调用测试。

本轮网络DNS不可用，官方SDK未安装，真实网关联调未完成。不得将全部离线测试通过写成真实模型、真实SDK或新稿质量验收。详细比较及来源见HOST_RUNTIME_COMPARISON.md，实际记录见VALIDATION_v4.13.0.md。
