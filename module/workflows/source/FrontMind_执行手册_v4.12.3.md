> 历史版本手册。v4.13.0宿主以[当前手册](FrontMind_执行手册_v4.13.0.md)为准；写作合同和旧任务恢复仍保留其原版本。

# FrontMind 执行手册 v4.12.3

## v4.12.3 当前运行与写作合同

本版以上传的 v4.12.2 为代码基线。宿主固定为智谱 **Managed Agents / glm-5.3 / max**；初稿、E8、P0 第三遍修饰和标题固定为 **DeepSeek Pro / deepseek-v4-pro / max**。入口 AI 只启动命令、转交真实输入与确认，不代填内部结果。没有 Claude 写作路由，也不回退 XTY/Astra。

新 P0 使用 `frontmind-p0-style/4.12.3`，保留蓝图→初稿→E8→第三遍修饰→最终验读→20标题→标题编辑→交付。先按篇选材，再写文章；不传整库原文或竞品研究。第三遍负责实际成文，终审保留已自然、准确的表达，不把每个事实改成定义、释义与抽象总结。不增加新的模型阶段、质量分数、字数配额或用户确认页。

固定两篇例文的身份和全文要求保留。生产任务读取并冻结真实文本；断网或源文变化不能用模拟样本替代。合成样本仅供显式离线测试。旧 4.12.1/4.12.2 成稿和例文合同保留，不补造新的模型记录；旧稿内容合同不自动升级，但重新执行的宿主动作只能使用当前托管后端。

本次已完成代码与离线模拟验证，真实 API 验证因当前环境 DNS 失败而未完成。运行成功、内容合同通过和最终文章质量是不同结论，不能相互替代。详细接口、恢复与联网核验见 [MODEL_RUNTIME.md](MODEL_RUNTIME.md)。




## 1. 版本与目标

- 发行版本：`4.12.1`
- Runtime：`4.11`
- Reference Pack Schema：`4.1`
- 唯一入口：`./scripts/frontmind`

v4.11 用一个 Reference Pack 保存企业材料、品牌市场研究、用户确认的比较范围与核心定位、P0 与逐题研究。定位要回答：相对于用户确认的选择，企业为什么值得目标用户选择。

```text
Reference Pack 路由
→ 材料接入
→ 动态理解行业与用户决策
→ 真实选择与竞争研究
→ 用户确认比较对象与同类举例
→ 综合选择理由与定位表达
→ 用户最终确认
→ positioning_ready Pack
→ 独立 P0
→ p0_ready Pack
→ 单问题优化
```

## 2. 首次运行

标准启动只需运行：

```bash
./scripts/frontmind
```

无参数启动等同于 `./scripts/frontmind start`，只显示以下四项，不创建 Job：

1. 建立新的 Reference Pack；
2. 刷新已有 Reference Pack；
3. 创建或导入 P0；
4. 撰写单问题文章。

用户先决定本次要完成什么，再接收该路线的最小输入。品牌名、普通附件、历史任务和技术预检不能替代启动选择。只收到品牌名时不得默认建立 Pack。

可选的只读预检命令：

```bash
./scripts/frontmind preflight
```

预检检查 Python 及文档依赖、启动器权限、活动 Schema 和控制器。它不安装软件、不代替用户选择；配置检查只报告凭据是否可用，不输出密钥。完成预检后仍须显示标准启动页。

文档运行时可设置 `FRONTMIND_PYTHON=/absolute/path/python3`。宿主和作者的认证分别保存在 `config/zhipu.json`、`config/deepseek.json`；智谱辅助工具共用智谱配置。两份文件权限为 `0600`，配置自动读取。

内部宿主固定 `glm-5.3 / max`，作者固定 `deepseek-v4-pro / max`，两者启用思考。外层会话负责展示业务确认页、提交用户决定、启动和查看状态；不代写生产 Provider 结果。未配置旧回调不再产生手填结果的操作。配置、错误恢复和验证边界见 `MODEL_RUNTIME.md`。

完整会话启动协议和四条命令见 `START_HERE.md`。

## 3. 用户暂停合同

统一暂停输出包含：

```text
pause_type
title
review_markdown_path
available_choices
full_text_links
source_links
revision
requires_user_input=true
```

执行规则：

1. 完整显示 `review_markdown_path`；
2. 保留所有自然段、表格、本地全文与网页来源链接；
3. 等待用户明确决定；
4. 后续命令传入页面当前 `revision`；
5. 修改、补充或返回按明确入口展示相应页面；表述修改返回最终定位页，更换比较对象或重新探索返回竞品页；
6. 旧修订不能确认新内容；
7. 空 `continue` 只重显页面。

## 4. Reference Pack 路由

每个新 P0 或 article Job 首先进入 `awaiting_reference_pack_route`。命令中提供 Pack、企业名、普通资料或多个问题，都不会静默选择路线。

P0 示例：

```bash
./scripts/frontmind p0 \
  --reference-pack /absolute/Reference_Pack_v1.zip \
  --job-dir /absolute/jobs/p0
```

然后由用户确认使用已有 Pack：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/p0 \
  --revision 1 \
  --reference-pack-route use
```

若路由页选择创建：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/p0 \
  --revision 1 \
  --reference-pack-route create \
  --brand "完整品牌名" \
  --input /absolute/material-one \
  --input /absolute/material-directory \
  --positioning-brief /absolute/brief.md
```

此时当前 Job 转为 Reference Pack 构建任务。核心定位确认后导出 Pack 并结束，不自动返回原 P0。

如果用户明确要求直接创建 Pack，可跳过路由页：

```bash
./scripts/frontmind reference-pack create \
  --brand "完整品牌名" \
  --input /absolute/materials \
  --positioning-brief /absolute/brief.md \
  --job-dir /absolute/jobs/reference-pack
```

## 5. Reference Pack 材料接入

可输入 Markdown、TXT、CSV、TSV、JSON、HTML、PDF、DOCX、PPTX、XLSX、XLS、图片、目录或 ZIP。系统自动：

- 冻结普通文件；
- 安全展开目录和 ZIP；
- 提取可读文本；
- 保存原材料；
- 建立 source、knowledge、claim 与 image Registry；
- 建立最小来源索引。

用户不填写 manifest、事实编号或来源分类。

基础安全规则：

- 最多 5,000 个 ZIP 成员；
- 拒绝重复规范化路径；
- 拒绝绝对路径和路径逃逸；
- 拒绝加密成员；
- 拒绝嵌套 ZIP；
- 拒绝符号链接和特殊文件；
- 拒绝单成员压缩比超过 200；
- 使用流式 I/O、临时目录和原子提交。

ZIP 不设外壳、单成员和解压总字节上限；磁盘与系统 I/O 问题按真实错误返回。

## 6. 定位 Brief

Brief 可以是文本或文件，可填写：

1. 重点传播的业务、产品或能力；
2. 最希望吸引的人群；
3. 希望用户如何记住品牌；
4. 希望避开的定位或业务；
5. 已有的完整定位设想；
6. 认为最有价值的竞品差异；
7. 近期业务重点。

Brief 可留空。留空时研究仍基于企业材料与公开信息运行。

## 7. 两个 Provider 动作与竞品确认

定位正常使用两个内部 Provider 动作，中间必须等待用户确认比较范围：`positioning_market_research` 研究市场并提供候选列表 → `awaiting_competitor_selection` 竞品确认暂停 → `positioning_value_synthesis` 按确认范围综合选择理由与定位表达 → 最终定位确认。全部行业共用这条主链，不预设行业答案或档位。

定位最终页只呈现“核心定位”与“与已确认竞品的比较”，随后进入原有确认操作。核心按“适合谁 → 品牌怎样满足需求 → 用户得到什么”写成两三句自然表达，默认约100—180字，无字数门槛或机械截断；不列执行清单、目标企业缺点或例行免责尾句。比较说明按确认对象组织已知价值、决定性区别和适配需求；确有依据且影响选择的费用、等待时间、交付边界按需说明，不要求每组列短板。有依据且有意义时分档并解释相邻顺序，否则并列比较。具名对象可分组，但个体事实不能扩大到整类；同类举例不参与胜负判断。

后台研究用于决定哪些陈述成立；公开核心、竞品比较和文章不复述资料完整度、来源收集过程、信息缺口或内部角色规则。缺少某项比较依据时省略该项优劣或排名，不把信息缺口当对手短板。来源与必要限制仍保留在Pack和内部上下文，资料处理使用已有内部字段。用户明确询问价格、风险或缺点的文章仍直接回答。

最终页不展示独立证明材料、研究限制、经营建议或研究附件链接。原始资料、来源及历史必要条件仍在 Pack 内供写作使用；新结论的必要条件直接写在对应核心或比较句中。公开定位 Markdown 与确认页共用渲染，核心 JSON 是最终结论唯一依据。`user_choice_value` 仅保留摘要兼容，`advantage_explanation` 保存完整可读的竞争比较；不新增必填字段、Critic 或用户暂停。

P01/P02 在需求、对象和事实相同时沿用已确认比较理由及有依据的先后；条件改变时解释调整理由。蓝图与作者使用本题已确认顺序，不机械复制整体名次，也不另行把品牌前移。内部宿主固定为 `glm-5.3 / max`，正文、E8 和标题作者固定为 `deepseek-v4-pro / max`，两者均启用思考。配置属于两个独立运行时；不设置速度或服务档位，不由外层对话模型代填生产动作，不静默换模型或降档。


竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

用户已指定客户、问题或任务时，综合必须回答该需求，不得改换客群或降低要求来推荐品牌。未选对象也不能进入价格、代价或胜负比较；若已选对手更符合当前需求，短结论与正文可以明确优先考虑对方。范围确认不预定胜者。

用户改选后，研究阶段的建议角色不写入已确认范围；原研究中的角色性措辞仅作历史记录。综合输入逐项显示当前角色，并以内嵌的确认名单覆盖旧 Brief 与研究建议。研究事实原文保留，不按关键词删改资料。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 依据当前用户的文章任务与 宿主 选出的自身业务事实组织，蓝图与宿主工具不接收旧 `own_brand_context`、核心定位投影、竞争比较或研究附件。问题路线继续使用已确认定位；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实模型运行分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](shared/README.md)。

竞品页按类别展示候选名称、对象类型、所属类别、研究说明、来源及当前角色。用户可勾选、删除、补充名称或自定义类别，并指定“比较对象／同类举例／不纳入本次定位”。用户只需用自然语言表达，运行者负责转换技术参数。

同页预览本次语义：类型间比较说明所属类型的价值，同类型比较说明品牌间实际差异，混合比较分开解释。用户确认的是范围，不是赢家。第一档需要比较支持；档内目标品牌首先展示只是呈现顺序。

研究结束必须在 `awaiting_competitor_selection` 停下，不能因为 Brief 提到了竞品或 Provider 推荐了一组对象就代替用户确认。新增对象缺资料时复用研究补查；仅当重名或无法识别时在当前页请用户指明。

## 8. 用户确认与更新

以下参数都用于 `continue --job-dir /absolute/job --revision CURRENT`，每次提交以最新页面修订为准：

| 操作 | 参数 | 结果 |
|---|---|---|
| 编辑比较名单与角色 | `--competitor-selection /absolute/selection.json`，也接受 JSON 文本 | 更新候选和范围预览；用户对话不需要写 JSON。 |
| 确认比较范围 | `--confirm-competitors` | 进入综合；仍需后续最终定位确认。 |
| 更换比较对象 | `--return-to-competitors` | 回竞品页，旧定位确认失效；重新选择并确认后生成。 |
| 修改表述 | `--core-positioning-edits "修改要求"` | 保留范围，仅重新综合。 |
| 补充事实 | `--positioning-supplement /absolute/material` | 保留已确认范围，补研后再综合；未确认范围时回竞品页。 |
| 重新探索／刷新研究 | `--explore-positioning-alternatives` / `--rerun-positioning-research` | 重新研究候选，旧选择预选，回竞品页再次确认。 |
| 确认最终定位 | `--confirm-core-positioning` | 导出不可变的新 Pack 版本。 |

最终页按短结论、优势说明、完整段落、比较依据与适用条件展示。修改和研究不会自动确认；不能通过表述修改暗中新增比较对象。旧未完成动作由研究刷新入口进入新流程，不混用旧中间结果。完整命令例子见 `RUNBOOK.md`。

## 9. 轻量结构

详见 `shared/README.md`。研究增加轻量候选列表，综合仍返回三个正文字段及可选说明；`comparison_scope` 由控制器保存到核心 JSON。Schema 同时接受旧完整结构和新轻量结构，只检查结构。旧 Pack 缺少比较范围仍可读，不能自动补成已确认范围，不新增旧 Pack 必需文件。

## 10. 资料不足

研究对象无法识别时在竞品页说明；无法支持优势时在最终页说明目前能判断的内容和缺口，允许收窄或省略无依据的主张。没有排名、同档示例也很强，都不是自动判定定位失败的理由。用户选择范围也不是品牌获胜的事实依据。

## 11. Reference Pack 版本

`reference_pack.json` 使用稳定 `pack_id` 和递增整数 `pack_version`。

| 更新 | 典型版本 | 保留规则 |
|---|---:|---|
| 定位确认 | v1 | `positioning_ready=true` |
| P0 完成 | v2 | 定位保持有效，`p0_ready=true` |
| 新问题研究 | v3+ | 定位和 P0 保持有效 |
| 新品牌材料 | 下一版 | 保留已确认范围，补研后重新确认定位；无范围时先确认竞品 |
| 刷新市场研究 | 下一版 | 重做候选，旧选择预选，经竞品与最终定位确认 |

旧版本不覆盖。运行中的 article 固定绑定启动版本。

验证与查看问题：

```bash
./scripts/frontmind reference-pack validate /absolute/Reference_Pack.zip
./scripts/frontmind questions --input /absolute/Reference_Pack.zip
```

## 12. P0 独立任务

P0 需要 `positioning_ready` Pack：

```bash
./scripts/frontmind p0 \
  --reference-pack /absolute/Reference_Pack_v1.zip \
  --job-dir /absolute/jobs/p0
```

先确认 Pack 路由，再选择：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/p0 \
  --revision CURRENT \
  --p0-route create
```

导入已有 P0：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/p0 \
  --revision CURRENT \
  --p0-route import \
  --p0-input /absolute/existing-p0.docx
```

同 Pattern 合格例文达到两篇时显示条件式例文页。选择 Top20：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/p0 \
  --revision CURRENT \
  --accept-p0-example-route top20
```

也可传 `workflow` 使用工作流文风。

P0 蓝图展示开头、H2/H3、每节任务、按当前用户文章任务与自身业务事实整理的本篇方向、本篇事实段落、收窄处理、长度、结尾和文风。宿主在同一次蓝图动作中按篇读取原件并整理事实；来源关联留在后台，不新增事实审批页。

确认蓝图：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/p0 \
  --revision CURRENT \
  --accept-p0-blueprint
```

修改或补充：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/p0 --revision CURRENT \
  --p0-blueprint-edits "修改要求"

./scripts/frontmind continue --job-dir /absolute/jobs/p0 --revision CURRENT \
  --p0-blueprint-supplement /absolute/new-material
```

P0 完成后输出无文章主标题的 Markdown、HTML、DOCX 正文及独立的20个品宣候选标题，并写回同一 Pack 系列的新版本。候选标题完整打印到对话，不能只给文件链接或一个推荐题。

## 13. 逐题研究

直接更新已有 Pack：

```bash
./scripts/frontmind reference-pack update-research \
  --pack /absolute/Reference_Pack_v2.zip \
  --monitoring-answers /absolute/answers.xlsx \
  --source-workbook /absolute/sources.xlsx \
  --question "正式问题" \
  --output /absolute/Reference_Pack_v3 \
  --portable-zip /absolute/Reference_Pack_v3.zip
```

两篇完整 AI 答案即使没有引用明细，也可以建立空引用切片并达到该问题的输入 readiness。它不构成事实证明。

article 启动时也可临时提交两篇答案：

```bash
./scripts/frontmind article \
  --reference-pack /absolute/Reference_Pack_v2.zip \
  --job-dir /absolute/jobs/q000123 \
  --question-id q000123 \
  --question "正式问题" \
  --answer /absolute/answer-one.md \
  --answer /absolute/answer-two.md
```

确认 Pack 路由后，系统先生成含本题研究的新 Pack 版本，再进入 E1，不重做定位。

## 14. E1 应答简报

E1 显示：

- 正式问题与 Question ID；
- 优化品牌；
- Pack ID 和版本；
- 核心定位与 P0 修订；
- 完整核心定位段落；
- 两篇答案是否出现品牌；
- 额外应答要求；
- AI 品牌认知是否充分。

无额外要求：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/q000123 \
  --revision CURRENT \
  --no-extra-response-requirements \
  --ai-brand-recognition insufficient
```

有额外要求：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/q000123 \
  --revision CURRENT \
  --response-brief "希望重点回答的内容" \
  --ai-brand-recognition uncertain
```

两项都必须明确提交。

## 15. Pattern

Pattern 页显示 P00–P06。确认系统推荐：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/q000123 \
  --revision CURRENT \
  --accept-pattern
```

选择其他合法 Pattern：

```bash
./scripts/frontmind continue \
  --job-dir /absolute/jobs/q000123 \
  --revision CURRENT \
  --pattern P05
```

P00 仅用于 P0，不可用于问题任务。

## 16. 单问题例文

两篇 Top20 达标时，页面同时显示两篇完整 Top20 和两篇完整 AI 答案。

方案 A：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --example-route A
```

两篇 Top20 负责文风，两篇 AI 答案负责内容。

方案 B：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --example-route B
```

两篇 AI 答案同时参与内容与文风。Top20 不足两篇时不增加暂停。

## 17. P01/P02 问题定位

P01 自然说明本题选择、企业角色、整体定位关系、替代路径、适合人群、短板与其他选择条件。读取已确认比较范围；本题需要不同对象时在此页明确说明，不静默扩大品牌整体范围。

P02 解释本题选择逻辑、实际替代选择、差异和适用条件。按问题需要决定是否分层或排序，不强制档位或权重公式，不直接继承整体品牌排名。使用分档时说明顺序依据；档内品牌首先展示不等于同档胜出，同类举例不能自动升级成比较对象。

确认：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --confirm-question-positioning
```

修改、补充或返回：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --question-positioning-edits "修改要求"

./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --question-positioning-supplement /absolute/material

./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --return-to-pattern
```

P03–P06 不创建此页面。

## 18. 文章蓝图与生产

蓝图完整显示回答主线、开头结论、H2/H3、主体顺序、每节任务、定位/P0/AI/例文的使用、资料处理、长度和结尾。

确认：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --accept-blueprint
```

修改或补充：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --blueprint-edits "修改要求"

./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --blueprint-supplement /absolute/material
```

P01/P02 可返回问题定位：

```bash
./scripts/frontmind continue --job-dir /absolute/jobs/q000123 \
  --revision CURRENT --return-to-question-positioning
```

确认后运行写作、E8 编辑、机械检查、20个候选标题生成及一次智谱 Managed Agents标题编辑；Markdown/HTML/DOCX只交付正文，20个标题另存并完整打印。

## 19. 作者输入和编辑边界

作者只看到：

- 正式问题与用户 Brief；
- 已确认的核心定位、优势解释、自然语言比较范围、支持材料与相关战略结论；
- P0；
- P01/P02 问题定位；
- 两篇完整 AI 答案；
- 相关品牌与竞品材料；
- 完整例文；
- 已确认蓝图。

作者按问题与蓝图选择相关内容，不要求照搬整个核心段落或所有战略结论。比较范围说明保留实际对手与同类举例的角色，不把范围内结论扩大成全市场排名。作者不看到 Registry、内部 ID、哈希、来源等级、评分或内部确认记录。

E8 可修正普通不自然表达、重复、报告腔、悬空比较、一般过强措辞、标题层级和节奏。若修改会改变核心定位、直接回答、已确认顺序、整个核心章节或主体集合，则返回同一蓝图页。

## 20. Pack 维护

新增品牌材料：

```bash
./scripts/frontmind reference-pack add-materials \
  --pack /absolute/current-pack.zip \
  --input /absolute/new-material \
  --output /absolute/next-pack \
  --portable-zip /absolute/next-pack.zip
```

该操作保留逐题研究并重新打开定位流程。已有比较范围保留，补研后再综合并确认；缺少范围时先进入竞品确认。P0 是否需要更新由新的定位和 P0 蓝图判断。

刷新市场研究：

```bash
./scripts/frontmind reference-pack refresh-market \
  --pack /absolute/current-pack.zip \
  --job-dir /absolute/jobs/market-refresh \
  --positioning-brief /absolute/new-brief.md
```

只修复格式或元数据时，readiness 保持有效。

## 21. 不兼容输入

Reference Pack 4.0 通过 `reference-pack refresh-market` 保留材料、Registry 和逐题研究，重新生成并确认定位，旧 P0 需要重新审阅。Reference Pack 3.8 返回明确重建提示；旧 Job 不迁移。

## 22. 发行验收

Fixture 测试只验证结构、兼容性和流程行为，包括两个正常 Provider 动作、竞品与最终定位两个暂停、范围传递和旧 Pack 读取，不能证明真实 Provider 的语义质量、调研正确性或定位质量。

三轮开发迭代固定 glm-5.3，分别保留主运行、独立复测与跨行业观察，不把三轮生成加进生产流程。报告需要区分离线结果、真实输出与未验证范围；三轮最佳不自动表示达标，不以人工改写或示意段落替代真实结果。

```bash
python scripts/validate_workflow.py --run-tests
python scripts/run_acceptance_v411.py --output /absolute/acceptance-v4.11
python scripts/build_release.py \
  --source /absolute/FrontMind_Content_Workflow_v4.12.1 \
  --acceptance-source /absolute/acceptance-v4.11 \
  --output-dir /absolute/release-v4.12.1
```

发行器校验源码与精确白名单，在全新解压目录执行预检和静态检查，并核验 ZIP 权限与 SHA-256。匿名夹具验收结果仅在显式提供时进行结构校验，不代表真实 API 执行或内容质量通过。最终包不包含客户资料、验收成稿、私有 Top20、Provider 输出、日志或缓存。已授权 API 凭据仅保存在包内 `config/deepseek.json` 和 `config/zhipu.json`，文件权限为 `0600`，不进入其他交付内容。

## 文章写作与验读

P0 和问题文章共用：宿主 蓝图与本篇事实素材 → Pro 初稿 → Pro E8 → 新 P0 专属 p0_style（问题稿与旧未完成 P0 跳过此新增项） → 宿主 全文验读并按需修正一次 → Pro 20 个候选标题 → 智谱 Managed Agents/max 对照全文编辑标题一次 → 无文章主标题的 Markdown / HTML / DOCX 与独立标题清单。例文全文进入蓝图、初稿、E8 和宿主验读。问题文章保留 P0 与两篇完整 AI 答案的原有用途，P01/P02 保留逐题定位；P03–P06 不套用逐题定位。

普通企业事实直接陈述，日期、范围和服务条件写在对应事实中；不例行使用“企业简介载明”“企业披露”“公开资料显示”等审阅语气。P0 不写具名或类别竞争论证，问题文章按本题所需正常比较。

正文制作不选择或插入图片，不添加图片占位；后续由用户自行配图。扫描原件可以按需 OCR 以读取事实，普通文档文本直接提取。

## 标题交付方式

品宣和问题文章各生成20个候选标题。新结果使用统一的candidates列表，不预分搜索或媒体两组；历史families结果仍可读取。品宣的20项均围绕本篇品牌内容，先确定全文的读者关切和品牌价值，再形成不同阅读入口，不能逐节轮换业务、流程或数字凑数。每项附简短角度，模型推荐不等于发布采用。

新候选生成后，由智谱 Managed Agents/max结合完整正文编辑一次，再交付20项。编辑须实际修正过度承诺、局部章节式命题和重复表达，不能仅因JSON数量正确就判为可发布；合适的标题保持原样。原始DeepSeek候选与智谱 Managed Agents编辑结果、修改说明分别保存，交付同时绑定两者和正文。每篇增加一次标题编辑调用，不增加用户确认；失败保留现场并停止，不自动反复重拟。

任务完成时完整打印全部候选，并提供独立标题清单文件；正文Markdown、HTML、DOCX不含文章主标题，保留章节小标题，Word页眉不放题名。无需为了选题再确认一次，用户在发布时自行选择。仅重新拟题继续使用`--title-edits`，不会把推荐题写回正文。历史完成稿保留旧形式，新交付使用正文与标题分离形式。
