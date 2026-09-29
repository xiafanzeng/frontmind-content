# 内容制作工作流 v4.13.2 Final v16.2

当前新任务版本为 `4.13.2-v16.2`，来自用户提供的
`FrontMind_Content_Workflow_v4.13.2_Final_v16_2_Category_Titles.zip`。
原包 SHA256：`3e3fdf9c1b0d58dc9c62011904018769b8a35f080eb46b4729b64edad1a3f608`。

## 本次接入

- 完整业务源码位于 `source/`。运行状态仍采用 `4.11`，Reference Pack 仍为 `4.1`；它们不是发布版本号。
- P01/P02 新任务使用分类表达和 10 个同主题备选标题。其他类型和历史任务保留各自冻结的标题规则。
- 支持从资料包的问题目录中选择问题、导入监控问答表、原生确认、编辑、标题复核和成果交付。
- 网页只增加新版所需的选择入口，沿用原有内容工作台样式与确认机制。

## 包装与版本保留

主仓 `tools/modules/build-content-workflow.py` 从此目录生成确定性的 ZIP、哈希和 manifest；Dashboard 与内容子域名使用同一构建路径。
每个新任务冻结该 manifest，并把原包写入私有资产库。后续镜像更新不改变旧任务的 ZIP、状态、确认或标题规则；缺失旧包时明确报错，不能用新包代替。

原分发包中的客户资料、真实运行记录、标题样本和 `.codex` 配置不公开。三个供应商配置中的 `api_key` 已清空。上游的历史说明保留作版本记录，不代表宿主环境已部署或真实生成已验收。
上游 `source/scripts/build_release.py` 是原作者的离线发行工具，不是应用镜像的构建入口；不要用它重新打包客户资料或凭据。

## 运行环境

新版由包内 OpenAI Agents SDK 执行，不能再让外层智能体手写 `provider-output`：

- Python 3.10+，`openai-agents==0.22.3`、`openai==3.16.2`，其他依赖见 `source/requirements.txt`。
- XTY 宿主默认 `gpt-5.6-sol/high`，备用 `glm-5.3/max`；DeepSeek 执行写作阶段，智谱提供检索、阅读与 OCR 工具。
- FrontMind 私有 runner 使用 `CONTENT_WORKFLOW_XTY_API_KEY`（可回退已有 `XTY_API_KEY`）、`CONTENT_WORKFLOW_DEEPSEEK_API_KEY`、`CONTENT_WORKFLOW_ZHIPU_API_KEY`。
- 沙箱只得到任务专用的回环代理地址，真实 Key 不进入沙箱、提示词、Job 快照或公开仓。代理仅对新版内容业务任务开放。
- 本地独立运行可通过私有环境变量 `FRONTMIND_CONTENT_XTY_API_KEY`、`FRONTMIND_CONTENT_DEEPSEEK_API_KEY`、`FRONTMIND_CONTENT_ZHIPU_API_KEY` 配置；不得提交配置后的文件。
- `scripts/frontmind preflight` 缺少凭据时明确失败。离线测试通过不代表线上供应商调用已通过。

接入新版还需要发布对应 runner/sandbox 镜像并配置私有凭据；仅发布前端或替换 ZIP 不足以启用真实执行。
