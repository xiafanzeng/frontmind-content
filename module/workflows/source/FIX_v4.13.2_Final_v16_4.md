# v16.4 写作上下文 fdnv6 接入

## 变更范围

- 新增 `shared/writing_context_fdnv6.py`、`shared/writing_context_v165.py` 与 `shared/natural_editorial_v165.py`。三个文件来自本轮写作组件材料，按附件源文件逐字节放入工作流。
- 写作上下文按开关三级选择：`natural_editorial_v165.enabled(state)` 为真时使用 `writing_context_v165`（fdnv6）；否则 `editorial_preparation.enabled(state)` 为真时使用 `writing_context_v16`；其他情况继续使用 `writing_context_v15`。
- 该选择应用于准备、蓝图、初稿、编辑、定稿、返工及全文编辑所调用的写作上下文入口。文章生产状态在 `natural_editorial_v165.enabled(state)` 为真时转交 `natural_editorial_v165.run_production`，使该版本的阶段链实际执行。fdnv6 的启用条件仍由任务状态中的 `natural_prose_contract`、文章任务类型和 Pattern 决定。
- `build_release.py` 发布白名单及 `validate_workflow.py` 必需文件清单已登记三个新增 shared 文件与本说明。
- 发布标识从 `4.13.2-v16.3` 更新为 `4.13.2-v16.4`，最终 ZIP 名称同步更新为 `FrontMind_Content_Workflow_v4.13.2_Final_v16_4.zip`。

## 兼容与边界

- 当 `natural_editorial_v165.enabled(state)` 为假时，保留原有 v16 / v15 选择规则；本轮不修改写作上下文依赖文件本身。
- 不修改资源、服务端/客户端、standalone、样式、部署配置或依赖声明。
- 新增文件只有在发布白名单投影包含且实际工作流开关启用时才生效；发布后仍需通过真实任务确认实际提示词链路。

## 验证状态

本轮仅进行源码阅读、差异自查和交接打包。未安装依赖，未运行类型检查、测试、构建或线上 API；因此不宣称运行验证已通过。

建议由智谱 ZCode 在最终合并工作树中：
1. 检查合并差异和发布投影，确认三个新增文件进入 release ZIP。
2. 运行工作流校验、类型/语法检查、相关测试及构建，记录真实退出码。
3. 部署后分别用开关开启和关闭的真实任务验证提示词选择：开启时应走 fdnv6，关闭时应保持当前 v16.3 兼容路径。
4. 检查准备、蓝图、初稿、编辑、定稿、返工、全文编辑及验读阶段，并核对每个正文自然段最后一句对该段已说明内容作总结的提示词要求。
