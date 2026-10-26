# 内容制作工作流 v4.13.2 Final v16.8.6

完整业务源码位于 `source/`，可在本子仓直接修改阶段、Prompt、模型调用、工具与文档生成，再通过 delivery Skill 发布到内容子域名。实际新任务使用的版本由镜像 manifest 决定，任务会冻结包哈希、执行方式与功能策略。开发位置和旧任务处理方式见 [DEVELOPMENT.md](DEVELOPMENT.md)。

正式网站走 `module/server/runtime.ts` → 私有执行器 → 包内 OpenAI Agents SDK 的真实链路，默认 XTY 的 `gpt-5.6-sol/high`、备用 `glm-5.3/max`。`standalone/local-workflow.ts` 是本地可选适配器，其改动不会替换网站后端。

Runtime/state `4.11` 与 Reference Pack `4.1` 是状态格式版本，不是当前发行版本。历史任务保持原包、原业务确认与原记录。网站执行命令在配置 FRONTMIND_PROCESS_SUMMARY_CACHE 后生成中文公开摘要；历史查询只读取已保存摘要。

过程展示只根据 Managed、OpenAI Agents SDK 与 DeepSeek 已返回的正文、结构化结果、工具请求和回执生成中文摘要，并渲染 Markdown。私有推理字段和思考事件不进入摘要输入；仅含推理的步骤没有公开摘要。旧摘要必须与当前可公开输入的哈希一致才能展示。凭据由外部配置注入。

## 本次接入

v16.8.6 保留网页获取错误的原始分类。SDK 与 Managed 使用同一错误分类函数，将来源不可用、非公网地址和工具参数错误分别写入回执。公开页面按回执显示对应原因；已完成回执在恢复时原样复用，结果不明的外部调用仍保留断点。

v16.8.5 将同一份已选事实传入新 P0 的正文、编辑、文风、全文编辑和返工阶段。全文编辑核对稿件与材料的一致性，扩写意见须来自已选材料。原有阶段顺序和一次返工限制保持不变。该版本还包含平台宽表监控导入修复；旧任务继续读取原冻结包。

- 完整业务源码位于 `source/`。运行状态仍采用 `4.11`，Reference Pack 仍为 `4.1`；它们不是发布版本号。
- 新 P01 保留自然场景与合理价值表达；新 P02 明确选择两家竞品；标题为五个正式推荐加五个场景卖点，历史任务仍使用冻结策略。
- 本地问题文章可选行业盘点文体，并按顺序填写 3—12 个主体。工作流将名单传递到编辑准备、蓝图、正文和交付校验；事实校验失败后保留原稿快照，界面显示问题类别并允许显式返工及否决事实 ID。
- 新任务可在界面限定细分产品／功能、核心读者问题和不展开的主题；行业盘点需填写 2—8 个共同对比维度。上述选择随任务冻结并传入各写作阶段，行业盘点还检查问题映射、型号与证据的对应关系。组内 FDNv2 的通用写作要求已选择性接入，旧任务的提示词保持冻结。
- 支持从资料包的问题目录中选择问题、导入监控问答表、原生确认、编辑、标题复核和成果交付。
- 业务页面保留原生确认机制，在对话中逐条展示后端生成的思考与工具摘要，摘要直接显示并渲染 Markdown，完成后仍保留在对话中，同时展示最终答复和交付文件。摘要只依据实际模型输出和工具回执，不展示或臆造隐藏推理。制作档案保留阶段进度和事实校验反馈。

## 本地 Chat API 与执行 Harness

本地开发服务使用 `standalone/local-workflow.ts` 的同源 HTTP 接口：先 `POST /api/frontmind/v2/assets` 上传材料，再 `POST /api/frontmind/v2/tasks` 创建任务；页面通过 `GET /api/content/conversations` 读取消息及执行过程。写入请求校验本机 Host 与 Origin、任务 ID、修订号和确认动作。Harness 将命令交给 `run_managed.py → frontmind_workflow.py`，每次尝试的模型输出、工具请求和回执落在 Job 内；`workflow_snapshot.py` 与 `export-managed-timeline.py` 只投影允许公开的阶段状态和摘要，`ConversationExecutionProcess.tsx` 以大脑／扳手图标按时间直接显示公开摘要，完成和刷新后保留。工具摘要必须有实际回执；Managed 的 `agent.thinking` 只表示正在运行，不作为可公开的隐藏思考正文。

真实执行启动后，独立的 `process_summary.py` 默认用 GLM-5.2 对已结束的实际步骤生成一句话公开摘要，需额外模型调用；纯 GET、历史读取、离线单测不会启动它。摘要器也读取 OpenAI Agents SDK 的已完成模型输出与工具回执，不读取其隐藏推理。测试命令：在 `source/` 运行 `python -m unittest scripts.tests_v411.test_process_summary scripts.tests_v411.test_managed_timeline`，在可视化包 `module/` 运行 `vitest run tests/conversation-process.test.tsx`。这些验证只检查链路、顺序、脱敏和失败回执，不证明真实模型生成时的文章质量。

## 网页读取与原任务恢复

HTTP 直连在本机解析域名并检查连接地址；智谱 Reader 在远端抓取，调用前检查 HTTP(S) 地址及显式内网地址；私有 runner 通过任务代理校验目标，本地直连 Reader 不使用本机 DNS 的 Fake-IP 判断远端目标。`auto` 沿用已有的 HTTP → Reader 顺序，因此本机使用 Fake-IP 代理时无需修改代理配置。

点击恢复当前执行后，没有完整回执的资料读取、网页读取和公开搜索可在原 SDK 尝试中重新执行，重试时间与来源保存在工具回执中；已完成的请求复用原回执。普通继续不会重做这些请求。网页地址或读取错误作为工具反馈返回模型，模型可继续查找其他来源。验证入口为 `source/scripts/tests_v411/test_runtime_hotfix_v4132.py` 和 `source/scripts/tests_v411/test_web_read_network_boundary.py`。

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

## 本地真实执行

从仓库根目录执行下面的命令。`--config-dir` 指向既有工作流的私有 `config` 目录；启动器按 `FRONTMIND_CONTENT_HOST_PROVIDER` 选择宿主，默认沿用 XTY，并读取相应宿主、智谱和 DeepSeek 配置中的 `api_key`，只在子进程环境中传递。已有的 `FRONTMIND_CONTENT_*_API_KEY` 环境变量优先。

```bash
python3 -B module/workflows/scripts/run_managed.py \
  --config-dir ../../FrontMind_Content_Workflow_v4.13.2/config -- preflight
python3 -B module/workflows/scripts/run_managed.py \
  --config-dir ../../FrontMind_Content_Workflow_v4.13.2/config -- start --help
```

`python3` 必须已有预检所需文档依赖，也可替换为本机已安装的完整 Python 路径。启动器使用同一个解释器执行预检和任务。`preflight` 与 `start --help` 不创建远端资源；真正执行任务会调用配置的模型服务。

资料包创建会把逐文件接收结果保存到 `inputs/material_intake_report.json`。如有附件被拒收，任务报告文件名与原因，并停止进入研究阶段。接收成功后，Agent 仍须提取并读取原件；图片中的文字另行识别。

新资料包启动时，将浏览器确认的完整任务要求传入原生 `--positioning-brief`；企业名、附件和任务要求分别保存。只传企业名与附件会丢失用户指定的材料检查和研究范围。修改本地适配器后须重启 Vite，修改业务组件后须先运行 `pnpm build:business`，再验收浏览器实际加载的版本。

新任务的宿主动作沿用现有 `HostTools → OpenAI Agents SDK 或 Managed Agents → 工具回执 → submit_result` 回路，正文、编辑、标题规则保持原业务流程。每次尝试保存 provider、模型、API 版本、工具定义和请求指纹。同一动作、同一提示已冻结另一宿主时，显式切换会报 `frozen_host_provider_mismatch`；使用原宿主恢复，或为新宿主新建任务，不能自动更换已付费尝试。

每次恢复任务也要使用 `run_managed.py` 启动器。宿主只在相同动作与提示的尝试中冻结，并非在整个 Job 上永久冻结；直接改用默认入口会让后续新动作重新选择默认宿主。

Managed 事件以持久化事件 ID 去重；排队中的用户消息可以暂缺 `processed_at`，后续回读只补充缺失字段，不覆盖已有内容。`agent.thinking` 只用于运行提示，不从进度标记生成模板思考摘要。独立普通 GLM-5.2 API 在模型步骤结束或工具回执返回后，总结真实输出与回执。工具调用与回执保持同一行身份。会话空闲、阶段成功和文章交付分别判断，不能仅凭 `session.status_idle.stop_reason` 标记交付完成。接口依据：[事件与流式输出](https://docs.bigmodel.cn/cn/managed-agents/events)、[自定义工具](https://docs.bigmodel.cn/cn/managed-agents/tools)。

材料工具要求使用登记目录中的准确 ID 或登记路径。新的拒绝回执保存脱敏的具体诊断。同一确定性错误再次出现时，在第二次实际工具执行前停止；修正后可显式恢复，旧失败保持原样。后端公开投影只包含摘要、状态、时间和关联身份，不返回内部思考、工具函数、参数、返回正文、堆栈或私有路径。

界面修改和浏览器验收使用启动终端报告的真实工作流首页；端口由 Vite 启动参数决定。会话关联、验证方法和生产接入限制见 [开发说明](../../DEVELOPMENT.md) 与 [对话内执行设计](../../docs/execution-v2.md)。本模块变更没有部署私有 Core，也没有重新运行历史客户任务。
