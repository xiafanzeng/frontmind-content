---
name: frontmind-content-workflow-v4-11
description: FrontMind Content Workflow v4.11 唯一入口；用一个 Reference Pack 4.1 完成行业中立的差异化定位咨询、P0 与单问题内容生产。
---

# FrontMind Content Workflow v4.11

只从包根运行 `./scripts/frontmind`。发行版本为 `4.11.0`，运行时合同为 `4.11`，Reference Pack Schema 为 `4.1`。

## 标准启动页

用户只说“启动工作流”“开始 FrontMind”或附上发行 ZIP 要求启动时，先运行：

```bash
./scripts/frontmind
```

无参数命令等同于 `./scripts/frontmind start`。完整展示它返回的四个选项：建立新的 Reference Pack、刷新已有 Reference Pack、创建或导入 P0、撰写单问题文章。用户选择前不创建 Job、不开始研究，也不改成一次索取“品牌＋材料＋目标”的开放式问题。只收到品牌名称仍不能默认建立 Pack；只读预检也不能代替启动页。

用户选择后才收集该路径的最小输入。发行 ZIP 是程序，不是企业材料或 Reference Pack。完整规则见 `START_HERE.md`。

## 首次路由

每个新 P0 或 article Job 都必须先停在 `awaiting_reference_pack_route`。即使命令带有 Pack 路径，也要完整展示“使用已有 Pack / 创建新 Pack”页面，等用户明确选择。

用户明确要求直接建立 Reference Pack 时，运行：

```bash
./scripts/frontmind reference-pack create \
  --brand "完整品牌名" \
  --input /absolute/materials \
  --job-dir /absolute/jobs/reference-pack
```

该命令已经代表“创建”的明确选择，不重复询问。

## 暂停处理

遇到用户暂停：

1. 完整展示 `review_markdown_path`；
2. 保留全部表格、全文链接和来源链接；
3. 等待用户决定；
4. 继续时传入当前 `revision`；
5. 不代选系统推荐。

空 `continue` 只能重显当前页。定位修改、补充和返回按下文的明确入口处理，并使用当前修订。内部 Provider action 不展示给用户，也不能确认或越过用户暂停。

## 行业中立的定位主链

定位正常使用两个内部 Provider 动作，中间必须等待用户确认比较范围：`positioning_market_research` 研究市场并提供候选列表 → `awaiting_competitor_selection` 竞品确认暂停 → `positioning_value_synthesis` 按确认范围综合选择理由与定位表达 → 最终定位确认。全部行业共用这条主链，不预设行业答案或档位。

竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 与作者接收确认范围和相关材料；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实 glm-5.3 观察分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](../shared/README.md)。

竞品页必须展示每个候选的名称、类型、所属类别、研究说明与角色，以及当前范围的自然语言预览。将用户的对话选择转成 `continue --competitor-selection` 接收的 JSON 或文件路径，不要求用户自行填写。只在用户明确确认比较范围后使用 `--confirm-competitors`；更换对象使用 `--return-to-competitors`，旧定位确认随之失效。三个入口都使用当前 `revision`，确认比较范围不等于确认最终定位。

## P0

核心定位确认后导出 `positioning_ready` Pack 并结束 Reference Pack Job。另起 P0 Job：

```bash
./scripts/frontmind p0 \
  --reference-pack /absolute/Reference_Pack_v1.zip \
  --job-dir /absolute/jobs/p0
```

用户确认 Pack 路由后，再选新建或导入 P0。P0 读取已确认的定位、比较范围和相关研究，不把整份市场候选表当作用户选定的竞品，也不重复品牌市场研究。完成后产生同一 `pack_id` 的新版本，包含 Markdown、HTML、DOCX 和 20 个标题。

## 单问题

article 必须使用 `p0_ready` Pack：

```bash
./scripts/frontmind article \
  --reference-pack /absolute/Reference_Pack_v2.zip \
  --job-dir /absolute/jobs/question \
  --question-id q000123
```

E1 真实暂停；Pattern 页完整展示 P00–P06；只有 P01/P02 生成问题定位。P02 按本题需求解释实际选择、差异及适用条件，是否分层或排序由问题决定，不强制权重公式。需要与品牌整体范围不同的对象时，在该问题定位页说明；同档品牌首先展示不等于竞争胜出。P03–P06 直接进入文章蓝图。

两篇 AI 答案未提优化企业时，可以使用 Pack 中确认的定位和 P0 说明企业角色，但不得写成 AI 提到或推荐了企业。

作者根据蓝图使用相关定位、优势解释、自然语言比较范围与支持材料，无需照搬核心段落或所有战略结论。范围说明应保留比较对象和同类举例的角色；内部确认记录、Registry、内部 ID、哈希、评分和来源等级不进入写作上下文。不得恢复逐字符答案账本、候选评分、覆盖率、来源数量阈值、排名资格、同分窗口或独立补证流程。

完整命令和恢复方式见 `FrontMind_执行手册_v4.11.0.md` 与 `RUNBOOK.md`。

Fixture 测试只验证结构与流程，不证明真实 Provider 的语义质量或定位判断；后者需要检查真实输出及其来源。
