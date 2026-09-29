<!-- 当前标题规则以 v16.2 为准，历史版本说明保留。 -->

# Final_v14 当前说明

新建任务默认使用 `editorial-mission-v2`，当前写作分工、篇幅与输入规则见本版 `README.md`、`START_HERE.md` 和 `FIX_v4.13.2_Final_v14.md`。正文采用DeepSeek成稿、E8、XTY文字意见及必要时一次DeepSeek返工；P0保留原第三遍。DeepSeek为 `deepseek-v4-pro / max`，其余运行配置保持原配置。

以下保留基础接口与历史版本说明；其中“当前”“默认”等表述仅指对应历史版本，不覆盖上述v14入口规则。历史Job及冻结请求继续使用原版本。

---

当前配置补充（2026-09-29）：经用户授权，DeepSeek 新请求使用 `high`。模型、网关、最大输出额度及备用恢复配置不变；历史冻结请求保留当时配置。新建 P01/P02 使用 v16 案例研究与编辑准备流程，入口见 START_HERE.md。下述历史版本说明仅适用于对应版本。

## v4.13.1：P0品牌标题与Pack选题（当前优先规则）

P0的20个候选是同一篇品牌长文的替代主标题，不是20篇问题文章或按章节派生的项目问答。标题作者与标题编辑共用 `resources/p0_titles/SKILL.md`；编辑可在原有一次动作中重拟整组。限制、面诊、风险告知和内部编辑要求不得因为出现频繁就成为品牌卖点。正文、E8与第三遍4.12.8合同不变；不追加评分或轮次。

用户选择“问题优化/article”后，只需确认已有Reference Pack，随后程序在 `awaiting_question_selection` 显示当前监控期次的问题清单。不要在创建Job之前强索问题ID、问题原文或两篇答案。把用户所选序号、ID或完整问题转为当前revision的 `continue --question-id 序号`；已知问题可直接传ID，仍保留Pack路由确认。选中问题后自动复用同题同一期两平台全文，保留全部原始观察，再进入原E1回答要点确认。禁止替用户选第一题。

P0完成只说明品牌文章可用，不表示问题库已建立。读取实际完成返回的 `next_step`，不要自行输出“现在只差问题ID和两篇答案”。已有问题库直接进入选题；没有目录时，使用 `reference-pack import-questions --pack PACK --monitoring-answers 原表.xlsx`，或在选题暂停通过同名参数导入。单表即可，不要求空的引用工作簿。缺引用明细明确记为未提供，不把截图当引用、不伪造研究完成。导入保留旧Pack，生成新版本并保留定位与P0。

当用户提交监控表，不得作为普通企业事实抽取。表内问题、完整回答、平台及监控日期是研究输入；日期以单元格为准，不能用导出文件名替代。已有数据不重复索取，只处理真正缺失或不匹配的数据。正文改标题可使用现有 `--title-edits`，不重跑初稿/E8/第三遍。

本版没有用户本地已修复的SDK源码；不要覆盖本地config、jobs或已工作的运行适配层。优先用 `scripts/upgrade_to_v4131.py --target 原程序目录` 检查，再加 `--apply` 合并；冲突会先停止，不猜测或回退本地修复。执行前暂停该目录的活动任务。具体命令见本版执行手册。

## v4.13.0 宿主迁移（当前执行入口）

新宿主动作使用**本地 OpenAI Agents SDK + XTY Chat Completions**，不创建智谱 Agent、Environment 或 Session。`config/xty.json` 已配置网关和独立密钥；默认模型为XTY普通Chat接口文档明确示例的 `gpt-4o`，不是 `qwen-xxx` 占位符，也不表示已验证该令牌权限或优于原宿主。SDK选择与模型质量是两件事；更换宿主模型须显式改配置并先跑工具自检，不自动降级或切供应商。

P0写作合同仍为4.12.8：DeepSeek初稿、E8、第三遍、两篇完整例文、20标题、业务确认和导出不变。第三遍去审计式写作Skill保持原文。智谱配置仅留给原有搜索/Reader/OCR和旧Managed动作的显式恢复；不自动归档或删除远端资源。

任务长期暂停依靠完整Job目录和本地SQLite/RunState断点。没有自动清理期限；同一Job串行，不同Job可并行。进程退出不意味着任务在云端继续计算，当前网络请求也不能逐token原位接回。失败使用已有显式重试；跨版本先保存原目录，不改旧任务合同。

安装与恢复见 [v4.13.0执行手册](FrontMind_执行手册_v4.13.0.md)。真实SDK/网关联调与文章质量须单独验证，离线模拟不等同于真实模型验收。

## v4.12.8 当前 P0 合同（优先于下方历史说明）

新建 P0 使用 `frontmind-p0-style/4.12.8`。本版以现有第三遍为主要改动点：实际加载 `resources/p0_prose_editor/SKILL.md`，由 DeepSeek 在一次既有 `p0_style` 调用内按业务内容重写问题段落。不是安装数个润色器串联，也不增加作者、审稿轮次、评分或禁词检测器。

第一遍写作职责不变。E8 只补充来源旁白、重复限定和无依据强断言的内容处理；不读取原始例文，不运行完整第三遍Skill。选材沿用原字段，将必要条件留在相关事实附近；不继续累积已完成的核验经过。第三遍仍只接收 **E8全文＋本篇任务、事实与必要条件＋星源智及港隽两篇完整原文**，不恢复完整蓝图。已有 `material_adjustments` 完整保留但单列为编辑执行条件，不通过关键词删去可能重要的限制。

第三遍只返回完整Markdown正文。Skill要求直接介绍机构及其业务，处理未被点名的同类段落；不能只是把“这些事实构成”换成“这些优势体现”。必要归因、真实不确定性、风险、日期与范围继续保留，不把宣传图片或计划改成确认现状，不只删限制却保留无依据承诺。两篇原始例文不改动，正文不抄例文中的核验和宣传说明。

宿主执行层现已迁移OpenAI Agents SDK，作者仍为DeepSeek Pro；本段描述的写作分工和输出合同不变。终审继续只给四字段结论，合格逐字接受第三遍，不代写；失败沿用显式 `continue --p0-rework style|edit` 或限定源稿 `rewrite-p0 --rework style|edit`，不自动循环付费返工。20标题、确定性导出、Reference Pack及问题文章路线不变。

旧任务保留原合同；使用新目录和新任务启用4.12.8，不直接修改旧状态或把旧结果冒充新生成。仅把Skill文件放进目录不会自动生效，本版已接入运行分支，完整系统提示参与原有请求指纹。生产仍须真实调用配置后端；本次程序升级没有完成新稿的真实模型验读。当前操作见《FrontMind_执行手册_v4.13.0.md》；4.12.8仍是写作合同版本。


# FrontMind Content Workflow v4.12.1 RUNBOOK

## 1. 进入目录与预检

```bash
cd /absolute/path/FrontMind_Content_Workflow_v4.12.1
./scripts/frontmind --version
./scripts/frontmind preflight
./scripts/frontmind
```

预期为发行 `4.12.1`、Runtime `4.11`、Reference Pack `4.1`。如果系统 Python 缺文档依赖，指向已有运行时：

```bash
export FRONTMIND_PYTHON=/absolute/path/python3
```

生产 Job 不自动安装依赖。

最后一条命令显示标准启动页，不创建 Job。它固定提供四项：新建 Reference Pack、刷新 Reference Pack、P0、单问题文章。用户只说“启动工作流”时必须先显示此页；不能因品牌名、附件或预检成功而默认选择任务。详细会话协议见 `START_HERE.md`。

## 2. 识别暂停与内部动作

用户暂停包含 `review_markdown_path`、`available_choices`、`revision` 和 `requires_user_input=true`。完整展示页面并等待用户。

内部 action 由包内固定运行时自动执行。外层对话模型不能填写 Provider 结果、冒充 Agents SDK / XTY宿主或 DeepSeek 作者；旧回调不作为生产替代。状态和重试见 MODEL_RUNTIME.md。

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

P01/P02 在需求、对象和事实相同时沿用已确认比较理由及有依据的先后；条件改变时解释调整理由。蓝图与作者使用本题已确认顺序，不机械复制整体名次，也不另行把品牌前移。内部宿主使用config/xty.json明确指定的兼容模型和本地Agents SDK，正文、E8和标题作者仍为 `deepseek-v4-pro / max`，作者保持原思考设置。配置属于两个独立运行时；不设置速度或服务档位，不由外层对话模型代填生产动作，不静默换模型或降档。


竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 依据当前用户的文章任务与 宿主 选出的自身业务事实组织，蓝图与宿主工具不接收旧 `own_brand_context`、核心定位投影、竞争比较或研究附件。问题路线继续使用已确认定位；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实模型运行分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](shared/README.md)。

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

终态为 `p0_ready`，并生成同一 `pack_id` 的下一版 Pack。P0 使用当前用户文章任务、宿主 整理的本篇自身业务事实和完整例文；蓝图与宿主工具不读取旧 `own_brand_context`、核心定位投影、竞争比较或研究附件，不重复定位研究。

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
  --job-dir /absolute/jobs/q000123
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

完成后交付无文章主标题的 Markdown、HTML、DOCX 正文及独立的候选标题（新P01／P02为10个，其他及旧冻结任务为20个）。候选标题必须完整打印到对话，另存标题清单；用户在发布时自行选用。

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

历史 glm-5.3 三轮开发迭代的主运行、独立复测与跨行业观察另行保存和报告，生产流程不增加三稿生成。观察是否只比较确认对象、同类举例是否保持角色、改变范围与事实后是否改变论证。未完成真实验证时如实注明，不把离线通过、示意段落或人工润色写成质量达标。

```bash
python scripts/run_acceptance_v411.py --output /absolute/acceptance-v4.11
python scripts/build_release.py \
  --source /absolute/FrontMind_Content_Workflow_v4.12.1 \
  --acceptance-source /absolute/acceptance-v4.11 \
  --output-dir /absolute/release-v4.12.1
```

发行器先验证源码，再构建精确白名单 ZIP，从全新目录解压并再次运行测试。最终检查：

```bash
cd /absolute/release-v4.12.1
shasum -a 256 -c FrontMind_Content_Workflow_v4.12.1_Final.zip.sha256
unzip -Z -v FrontMind_Content_Workflow_v4.12.1_Final.zip
```

`scripts/frontmind` 的 ZIP Unix 权限必须是 `0755`。

## v4.12.1 内部动作与恢复

确认蓝图后，包内 宿主/Pro 双运行时自动完成写作链；外层不得代填结果。普通 `continue` 不重复失败的付费调用。明确重试使用 `continue --job-dir /absolute/job --revision CURRENT --retry-current-action`，历史尝试保留。

已完成任务需要重新写作时，明确提交当前 revision 和原接受蓝图参数；需要先改选材或蓝图时，使用原 `--blueprint-edits /absolute/path/edits.md` 参数，修改完成后仍停在原蓝图确认页。两种操作都会先保存完整旧任务副本，新交付写入独立目录；不要同时提交接受和修改参数。状态查询和空 `continue` 不改写完成任务。

蓝图修改意见可与 `--blueprint-supplement /absolute/path/materials` 一起提交；P0 使用对应 `--p0-blueprint-edits` 和 `--p0-blueprint-supplement`。本次补料先登记，再进入同一个蓝图动作，不需要单独调用补料函数。

E8 正文格式失败可以交一次 宿主 收尾，接口鉴权、网络或未完成响应仍停止并报告。标题必须读取通过宿主验读的实际全文；不能根据旧初稿或本地路径猜写。具体合同见 [MODEL_RUNTIME.md](MODEL_RUNTIME.md)。

文章只输出文字，不包含自动选图、插图或图片占位。


已完成文章只修标题时，使用 `./scripts/frontmind continue --job-dir 任务目录 --revision 当前版本 --title-edits 修改要求.md`。程序验证并冻结既有真实终稿，只重新调用DeepSeek拟题与一次Agents SDK / XTY标题编辑，并交付新的独立标题清单，正文仍不含文章主标题，保留旧稿、旧标题与资料包。正文需要变化时使用原成稿精修入口。

## 标题交付方式

新P01／P02各生成10个同主题近义标题，默认不带品牌；用户明确要求带品牌时覆盖默认。P01单机构正文使用品类推荐标题，不承诺多家榜单。P0、其他Pattern与旧冻结任务仍为20个。新结果使用统一的candidates列表，不预分搜索或媒体两组；历史families结果仍可读取。品宣的20项均围绕本篇品牌内容，先确定全文的读者关切和品牌价值，再形成不同阅读入口，不能逐节轮换业务、流程或数字凑数。每项附简短角度，模型推荐不等于发布采用。

新候选生成后，由Agents SDK / XTY宿主结合完整正文编辑一次，再按本轮冻结策略交付10项或20项。编辑须实际修正过度承诺、局部章节式命题和重复表达，不能仅因JSON数量正确就判为可发布；合适的标题保持原样。原始DeepSeek候选与Agents SDK / XTY编辑结果、修改说明分别保存，交付同时绑定两者和正文。每篇增加一次标题编辑调用，不增加用户确认；失败保留现场并停止，不自动反复重拟。

任务完成时完整打印全部候选，并提供独立标题清单文件；正文Markdown、HTML、DOCX不含文章主标题，保留章节小标题，Word页眉不放题名。无需为了选题再确认一次，用户在发布时自行选择。仅重新拟题继续使用`--title-edits`，不会把推荐题写回正文。历史完成稿保留旧形式，新交付使用正文与标题分离形式。

正文精修需更新事实时，可随 `--manuscript-edits` 传 `--writing-materials facts.json`（或 Markdown、含唯一 writing_materials.json/md 入口的目录）。JSON 使用 writing_material_markdown、material_adjustments、writing_material_sources；它是完整当前选材，替代旧蓝图事实。后续精修自动继承，显式再传才替换；标题修改保留。原件按现有补料方式保存。
