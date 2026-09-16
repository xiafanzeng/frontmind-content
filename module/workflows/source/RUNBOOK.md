# FrontMind Content Workflow v4.11.0 RUNBOOK

## 1. 进入目录与预检

```bash
cd /absolute/path/FrontMind_Content_Workflow_v4.11.0
./scripts/frontmind --version
./scripts/frontmind preflight
./scripts/frontmind
```

预期为发行 `4.11.0`、Runtime `4.11`、Reference Pack `4.1`。如果系统 Python 缺文档依赖，指向已有运行时：

```bash
export FRONTMIND_PYTHON=/absolute/path/python3
```

生产 Job 不自动安装依赖。

最后一条命令显示标准启动页，不创建 Job。它固定提供四项：新建 Reference Pack、刷新 Reference Pack、P0、单问题文章。用户只说“启动工作流”时必须先显示此页；不能因品牌名、附件或预检成功而默认选择任务。详细会话协议见 `START_HERE.md`。

## 2. 识别暂停与内部动作

用户暂停包含 `review_markdown_path`、`available_choices`、`revision` 和 `requires_user_input=true`。完整展示页面并等待用户。

内部 Provider action 包含 `prompt_path` 和 `expected_output`。Provider 写入合法 JSON 后再次运行空 `continue`；配置 `FRONTMIND_CONTROLLER_PROVIDER` 时自动完成。

```bash
cat /absolute/job/job_state.json
./scripts/frontmind continue --job-dir /absolute/job
```

第二条命令在用户暂停时只重显页面，不推进。

## 3. 创建 Reference Pack

用户明确要求创建时：

```bash
./scripts/frontmind reference-pack create \
  --brand "完整品牌名" \
  --input /absolute/brand-materials \
  --positioning-brief /absolute/brief.md \
  --job-dir /absolute/jobs/reference-pack
```

该命令直接接入材料。

定位正常使用两个内部 Provider 动作，中间必须等待用户确认比较范围：`positioning_market_research` 研究市场并提供候选列表 → `awaiting_competitor_selection` 竞品确认暂停 → `positioning_value_synthesis` 按确认范围综合选择理由与定位表达 → 最终定位确认。全部行业共用这条主链，不预设行业答案或档位。

定位最终页只呈现“核心定位”与“与已确认竞品的比较”，随后进入原有确认操作。核心按“适合谁 → 品牌怎样满足需求 → 用户得到什么”写成两三句自然表达，默认约100—180字，无字数门槛或机械截断；不列执行清单、目标企业缺点或例行免责尾句。比较说明按确认对象组织已知价值、决定性区别和适配需求；确有依据且影响选择的费用、等待时间、交付边界按需说明，不要求每组列短板。有依据且有意义时分档并解释相邻顺序，否则并列比较。具名对象可分组，但个体事实不能扩大到整类；同类举例不参与胜负判断。

后台研究用于决定哪些陈述成立；公开核心、竞品比较和文章不复述资料完整度、来源收集过程、信息缺口或内部角色规则。缺少某项比较依据时省略该项优劣或排名，不把信息缺口当对手短板。来源与必要限制仍保留在Pack和内部上下文，资料处理使用已有内部字段。用户明确询问价格、风险或缺点的文章仍直接回答。

综合动作按“已注册的完整文本原料与选定研究 → 最终写作任务”的顺序组织输入，不截断或改写事实。正文中的任意文件链接不会自动成为新的读取来源；非文本资料继续通过已有材料入口读取。P01/P02 明列现有 JSON 字段名，后台备注写入 material_adjustments。

最终页不展示独立证明材料、研究限制、经营建议或研究附件链接。原始资料、来源及历史必要条件仍在 Pack 内供写作使用；新结论的必要条件直接写在对应核心或比较句中。公开定位 Markdown 与确认页共用渲染，核心 JSON 是最终结论唯一依据。`user_choice_value` 仅保留摘要兼容，`advantage_explanation` 保存完整可读的竞争比较；不新增必填字段、Critic 或用户暂停。

P01/P02 在需求、对象和事实相同时沿用已确认比较理由及有依据的先后；条件改变时解释调整理由。蓝图与作者使用本题已确认顺序，不机械复制整体名次，也不另行把品牌前移。Managed Agents 的本次生产与实测配置明确为 `glm-5.3 / high / standard`，放在 Agent/会话执行配置中，不写入行业 Prompt；异常不静默换模型或降档。通用 Workflow 的内部 Provider 协议保持不变。


竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 与作者接收确认范围和相关材料；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实 glm-5.3 观察分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](shared/README.md)。

### 竞品页操作

研究完成后先停在 `awaiting_competitor_selection`。完整展示按类型分组的候选、研究说明、当前角色和范围预览。用户可以用对话指定哪些是比较对象、哪些仅作同类举例、哪些不纳入，也可以补充名称或类别。

运行者把用户选择整理为选择 JSON，或保存为 JSON 文件后提交；不要求用户自行填写 JSON：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/reference-pack \
  --revision CURRENT --competitor-selection /absolute/competitor-selection.json
```

`--competitor-selection` 也接受直接传入的 JSON 文本。提交选择只更新预览，不等于最终定位确认。展示更新后的页面，按其当前修订明确确认范围：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/reference-pack \
  --revision CURRENT --confirm-competitors
```

然后才运行 `positioning_value_synthesis`，进入 `awaiting_core_positioning_confirmation`。最终页顺序为短结论、优势说明、完整段落、比较依据与适用条件。最终确认使用 `continue --job-dir /absolute/job --revision CURRENT --confirm-core-positioning`。终态为 `positioning_ready`，交付在 `deliverables/`，P0 单独启动。

## 4. 修改、补充和探索定位

补充事实，保留已确认范围，补研后再综合；范围尚未确认时仍回到竞品页：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/reference-pack \
  --revision CURRENT --positioning-supplement /absolute/new-material
```

最终页修改表述，保留比较范围，仅重新综合：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/reference-pack \
  --revision CURRENT --core-positioning-edits "修改要求"
```

更换比较对象，返回竞品页并使旧定位确认失效：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/reference-pack \
  --revision CURRENT --return-to-competitors
```

随后使用 `--competitor-selection` 编辑并通过 `--confirm-competitors` 重新确认，不通过表述修改入口暗中扩大范围。

重新探索市场选择，旧选择作为可编辑预选，研究后回到竞品页：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/reference-pack \
  --revision CURRENT --explore-positioning-alternatives
```

重新运行定位研究，刷新候选并回竞品页再次确认：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/reference-pack \
  --revision CURRENT --rerun-positioning-research
```

旧未完成定位动作通过上述研究刷新入口进入新流程。旧方向文件只作为历史或兼容投影，不能替代当前范围确认。新增对象资料不足时复用研究动作补查；对象重名或无法识别时，在当前竞品页指明对象，不新增审批。

任何修改、补充或重新研究都不会自动确认。每次命令使用最新页面的 `revision`，不要继续沿用上一次提交的修订。

## 5. Pack 4.0 升级与市场刷新

Pack 4.0 不能直接用于 v4.11 P0 或文章。使用：

```bash
./scripts/frontmind reference-pack refresh-market \
  --pack /absolute/Reference_Pack_4.0 \
  --job-dir /absolute/jobs/refresh-market \
  --positioning-brief /absolute/brief.md
```

升级保留 `pack_id`、版本序列、材料、Registry 和逐题研究；清除旧定位与 P0，重新运行行业中立的研究，经过竞品确认和最终定位确认后生成下一版 Pack。旧 Pack 缺少 `comparison_scope` 不影响兼容读取，也不能自动推定比较范围。P0 需要单独审阅。Pack 3.8 使用原始材料重建。

## 6. 新建或导入 P0

```bash
./scripts/frontmind p0 \
  --reference-pack /absolute/Reference_Pack_v1.zip \
  --job-dir /absolute/jobs/p0
```

即使已传 Pack，也先停在 Reference Pack 路由：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/p0 \
  --revision CURRENT --reference-pack-route use
```

选择新建：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/p0 \
  --revision CURRENT --p0-route create
```

选择导入：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/p0 \
  --revision CURRENT --p0-route import --p0-input /absolute/existing-p0.docx
```

有两篇可用例文时确认文风方案：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/p0 \
  --revision CURRENT --accept-p0-example-route top20
```

确认 P0 蓝图：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/p0 \
  --revision CURRENT --accept-p0-blueprint
```

终态为 `p0_ready`，并生成同一 `pack_id` 的下一版 Pack。P0 使用已确认定位、比较范围和相关研究，不重复定位研究，不将所有研究候选解释为用户选定对手。

写作可按蓝图使用相关定位、比较与支持材料，无需全文照搬核心段落或战略结论。

## 7. 添加逐题研究

已有监控答案和来源工作簿：

```bash
./scripts/frontmind reference-pack update-research \
  --pack /absolute/Reference_Pack_v2.zip \
  --monitoring-answers /absolute/monitoring.json \
  --source-workbook /absolute/citations.xlsx \
  --question "完整问题" \
  --output /absolute/Reference_Pack_v3
```

两篇不同平台的完整答案可建立 `question_ready`；引用明细可以为空。不存在引用数量门槛。逐题更新保留定位和 P0。

## 8. 启动文章

```bash
./scripts/frontmind article \
  --reference-pack /absolute/Reference_Pack_v3.zip \
  --job-dir /absolute/jobs/q000123 \
  --question-id q000123 \
  --question "完整问题"
```

确认 Reference Pack 路由：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --reference-pack-route use
```

Pack 只有 `positioning_ready` 时不会进入 E1，页面会要求先完成 P0。问题缺两篇答案时，在既有问题研究输入页提交 `--answer`，生成新 Pack 版本后进入 E1。

## 9. E1、Pattern、例文和蓝图

没有额外要求也必须明确提交：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT \
  --no-extra-response-requirements \
  --ai-brand-recognition insufficient
```

有要求时使用 `--response-brief /absolute/brief.md`。AI 品牌认知只能由用户选择 `sufficient`、`insufficient` 或 `uncertain`。

Pattern 页显示 P00–P06。问题任务只能选择 P01–P06：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --pattern P02
```

有两篇例文时，页面必须链接两篇例文与两篇完整 AI 答案：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --example-route A
```

P01/P02 进入问题定位确认，相同条件沿用已确认比较依据，条件变化时解释调整；需要不同对象时在该页说明，不静默扩大品牌整体范围或复制整体排名。同类举例不能自动变成品牌优劣论证对象。确认：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --confirm-question-positioning
```

P03–P06 直接进入蓝图。确认文章蓝图并生产：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --accept-blueprint
```

完成后交付 Markdown、HTML、DOCX 和 20 个标题。

## 10. 版本、恢复与不可变性

- `pack_id` 在同一品牌系列内保持稳定；
- `pack_version` 每次写回递增；
- 旧目录与 ZIP 不覆盖；
- Job 固定绑定启动时的 Pack 版本；
- 确认只对当前 `revision` 有效；
- 终态不得残留 `pending_action`。

## 11. 安全边界

ZIP 不限制外壳、单成员或解压总字节。仍拒绝超过 5,000 个成员、重复规范化路径、路径逃逸、绝对路径、加密、嵌套 ZIP、符号链接、特殊文件和单成员压缩比超过 200。解压与发布使用流式 I/O、临时目录和原子提交。

## 12. 验收与发行

Fixture 验收只证明结构、兼容性和流程行为，包括两次正常 Provider 动作、竞品与最终定位两个暂停、范围传递及旧 Pack 读取。它不证明真实 Provider 的语义质量、调研正确性或定位判断。

真实 glm-5.3 三轮开发迭代的主运行、独立复测与跨行业观察另行保存和报告，生产流程不增加三稿生成。观察是否只比较确认对象、同类举例是否保持角色、改变范围与事实后是否改变论证。未完成真实验证时如实注明，不把离线通过、示意段落或人工润色写成质量达标。

```bash
python scripts/run_acceptance_v411.py --output /absolute/acceptance-v4.11
python scripts/build_release.py \
  --source /absolute/FrontMind_Content_Workflow_v4.11.0 \
  --acceptance-source /absolute/acceptance-v4.11 \
  --output-dir /absolute/release-v4.11.0
```

发行器先验证源码，再构建精确白名单 ZIP，从全新目录解压并再次运行测试。最终检查：

```bash
cd /absolute/release-v4.11.0
shasum -a 256 -c FrontMind_Content_Workflow_v4.11.0_Final.zip.sha256
unzip -Z -v FrontMind_Content_Workflow_v4.11.0_Final.zip
```

`scripts/frontmind` 的 ZIP Unix 权限必须是 `0755`。
