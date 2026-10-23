# 内容制作工作流 v4.13.2 Final v16.8

完整业务源码位于 `source/`，可在本子仓直接修改阶段、Prompt、模型调用、工具与文档生成，再通过 delivery Skill 发布到内容子域名。实际新任务使用的版本由镜像 manifest 决定，任务会冻结包哈希、执行方式与功能策略。开发位置和旧任务处理方式见 [DEVELOPMENT.md](DEVELOPMENT.md)。

正式网站走 `module/server/runtime.ts` → 私有执行器 → 包内 OpenAI Agents SDK 的真实链路，默认 XTY 的 `gpt-5.6-sol/high`、备用 `glm-5.3/max`。`standalone/local-workflow.ts` 是本地可选适配器，其改动不会替换网站后端。

Runtime/state `4.11` 与 Reference Pack `4.1` 是状态格式版本，不是当前发行版本。历史任务保持原包、原业务确认与原记录。额外模型摘要默认关闭。

## 本次接入

- 完整业务源码位于 `source/`。运行状态仍采用 `4.11`，Reference Pack 仍为 `4.1`；它们不是发布版本号。
- 新 P01 保留自然场景与合理价值表达；新 P02 明确选择两家竞品；标题为五个正式推荐加五个场景卖点，历史任务仍使用冻结策略。
- 本地问题文章可选行业盘点文体，并按顺序填写 3—12 个主体。工作流将名单传递到编辑准备、蓝图、正文和交付校验；事实校验失败后保留原稿快照，界面显示问题类别并允许显式返工及否决事实 ID。
- 新任务可在界面限定细分产品／功能、核心读者问题和不展开的主题；行业盘点需填写 2—8 个共同对比维度。上述选择随任务冻结并传入各写作阶段，行业盘点还检查问题映射、型号与证据的对应关系。组内 FDNv2 的通用写作要求已选择性接入，旧任务的提示词保持冻结。
- 支持从资料包的问题目录中选择问题、导入监控问答表、原生确认、编辑、标题复核和成果交付。
- 业务页面保留原生确认机制，在对话中逐条展示后端生成的思考与工具摘要，成功后折叠整段过程，再展示最终答复和交付文件。摘要只依据实际模型输出和工具回执，不展示或臆造隐藏推理。制作档案保留阶段进度和事实校验反馈。

## 本地 Chat API 与执行 Harness

本地开发服务使用 `standalone/local-workflow.ts` 的同源 HTTP 接口：先 `POST /api/frontmind/v2/assets` 上传材料，再 `POST /api/frontmind/v2/tasks` 创建任务；页面通过 `GET /api/content/conversations` 读取消息及执行过程。写入请求校验本机 Host 与 Origin、任务 ID、修订号和确认动作。Harness 将命令交给 `run_managed.py → frontmind_workflow.py`，每次尝试的模型输出、工具请求和回执落在 Job 内；`workflow_snapshot.py` 与 `export-managed-timeline.py` 只投影允许公开的阶段状态和摘要，`ConversationExecutionProcess.tsx` 以大脑／扳手图标按时间显示，任务完成后折叠。工具摘要必须有实际回执；Managed 的 `agent.thinking` 只表示正在运行，不作为可公开的隐藏思考正文。

真实执行启动后，独立的 `process_summary.py` 可用 GLM-5.2 对已结束的实际步骤生成一句话公开摘要，需额外模型调用；纯 GET、历史读取、离线单测不会启动它。测试命令：在 `source/` 运行 `python -m unittest scripts.tests_v411.test_process_summary scripts.tests_v411.test_managed_timeline`，在可视化包 `module/` 运行 `vitest run --config vitest.config.mjs`。这些验证只检查链路、顺序、脱敏和失败回执，不证明真实模型生成时的文章质量。

## 包装与版本保留

主仓 `tools/modules/build-content-workflow.py` 从此目录生成确定性的 ZIP、哈希和 manifest；Dashboard 与内容子域名使用同一构建路径。
每个新任务冻结该 manifest，并把原包写入私有资产库。后续镜像更新不改变旧任务的 ZIP、状态、确认或标题规则；缺失旧包时明确报错，不能用新包代替。

原分发包中的客户资料、真实运行记录、标题样本和 `.codex` 配置不公开。三个供应商配置中的 `api_key` 已清空。上游的历史说明保留作版本记录，不代表宿主环境已部署或真实生成已验收。
上游 `source/scripts/build_release.py` 是原作者的离线发行工具，不是应用镜像的构建入口；不要用它重新打包客户资料或凭据。

## 运行环境

工作流由包内执行器运行，不能让外层智能体手写 `provider-output`。通过 `FRONTMIND_CONTENT_HOST_PROVIDER` 显式选择宿主；未设置时保持已有 XTY 路由，设为 `zhipu` 时使用智谱 Managed Agents：

- Python 3.10+，文档依赖见 `source/requirements.txt`。XTY 路由另需 `openai-agents==0.22.3`、`openai==3.16.2`；智谱 Managed 路由不依赖这两个包。
- XTY 宿主默认 `gpt-5.6-sol/high`，备用 `glm-5.3/max`。智谱 Managed 宿主固定为 `glm-5.3/max`，复用已有受限工具和业务校验。两条路由均由 DeepSeek 执行写作阶段，智谱提供检索、阅读与 OCR 工具。
- FrontMind 私有 runner 使用 `CONTENT_WORKFLOW_XTY_API_KEY`（可回退已有 `XTY_API_KEY`）、`CONTENT_WORKFLOW_DEEPSEEK_API_KEY`、`CONTENT_WORKFLOW_ZHIPU_API_KEY`。
- 沙箱只得到任务专用的回环代理地址，真实 Key 不进入沙箱、提示词、Job 快照或公开仓。代理仅对新版内容业务任务开放。
- 本地独立运行可通过私有环境变量 `FRONTMIND_CONTENT_XTY_API_KEY`、`FRONTMIND_CONTENT_DEEPSEEK_API_KEY`、`FRONTMIND_CONTENT_ZHIPU_API_KEY` 配置；不得提交配置后的文件。
- `scripts/frontmind preflight` 缺少凭据时明确失败。离线测试通过不代表线上供应商调用已通过。

可选的智谱 Managed 本地适配器与网站的 OpenAI Agents SDK 路径是两种执行方式。当前私有 runner 的回环代理不支持 Managed Agents 端点。选择智谱宿主时，预检与执行都会明确报 `managed_proxy_unsupported`，不会把代理占位令牌发往智谱公网。部署生产版仍需主仓扩展代理并发布 runner/sandbox 镜像；仅发布前端或替换 ZIP 不足以启用真实执行。

## 本地智谱运行

从仓库根目录执行下面的命令。`--config-dir` 指向既有工作流的私有 `config` 目录；启动器只读取 `zhipu.json` 和 `deepseek.json` 中的 `api_key`，在当前子进程环境中传递，不复制配置、不输出密钥。已配置的 `FRONTMIND_CONTENT_ZHIPU_API_KEY` 和 `FRONTMIND_CONTENT_DEEPSEEK_API_KEY` 优先。

```bash
python3 -B module/workflows/scripts/run_managed.py \
  --config-dir ../../FrontMind_Content_Workflow_v4.13.2/config -- preflight
python3 -B module/workflows/scripts/run_managed.py \
  --config-dir ../../FrontMind_Content_Workflow_v4.13.2/config -- start --help
```

`python3` 必须已有预检所需文档依赖，也可替换为本机已安装的完整 Python 路径。启动器使用同一个解释器执行预检和任务。`preflight` 与 `start --help` 不创建远端资源；真正执行任务会创建 Agent、Environment、Session 并产生模型调用费用。

新任务的宿主动作沿用现有 `HostTools → Managed Agents → 工具回执 → submit_result` 回路，正文、编辑、标题规则保持原业务流程。每次尝试保存 provider、模型、API 版本、工具定义和请求指纹。同一动作、同一提示已冻结另一宿主时，显式切换会报 `frozen_host_provider_mismatch`；使用原宿主恢复，或为新宿主新建任务，不能自动更换已付费尝试。

每次恢复任务也要使用 `run_managed.py` 启动器。宿主只在相同动作与提示的尝试中冻结，并非在整个 Job 上永久冻结；直接改用默认入口会让后续新动作重新选择默认宿主。

Managed 事件以持久化事件 ID 去重；排队中的用户消息可以暂缺 `processed_at`，后续回读只补充缺失字段，不覆盖已有内容。`agent.thinking` 只用于运行提示，不从进度标记生成模板思考摘要。独立普通 GLM-5.2 API 在模型步骤结束或工具回执返回后，总结真实输出与回执。工具调用与回执保持同一行身份。会话空闲、阶段成功和文章交付分别判断，不能仅凭 `session.status_idle.stop_reason` 标记交付完成。接口依据：[事件与流式输出](https://docs.bigmodel.cn/cn/managed-agents/events)、[自定义工具](https://docs.bigmodel.cn/cn/managed-agents/tools)。

材料工具要求使用登记目录中的准确 ID 或登记路径。新的拒绝回执保存脱敏的具体诊断。同一确定性错误再次出现时，在第二次实际工具执行前停止；修正后可显式恢复，旧失败保持原样。后端公开投影只包含摘要、状态、时间和关联身份，不返回内部思考、工具函数、参数、返回正文、堆栈或私有路径。

界面修改和浏览器验收只使用真实工作流首页 http://127.0.0.1:5174/。离线回放页面已删除，不再维护。会话关联、验证方法和生产接入限制见 [开发说明](../../DEVELOPMENT.md) 与 [对话内执行设计](../../docs/execution-v2.md)。本模块变更没有部署私有 Core，也没有重新运行历史客户任务。
