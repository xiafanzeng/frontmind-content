# FrontMind Content Workflow v4.11.0

v4.11 使用一个持续升级的 Reference Pack 4.1 保存企业材料、竞争选择研究、用户确认的比较范围与核心定位、P0 和逐题研究。定位先研究市场，等用户确定要和谁区分，再围绕该范围推导选择理由。

定位正常使用两个内部 Provider 动作，中间必须等待用户确认比较范围：`positioning_market_research` 研究市场并提供候选列表 → `awaiting_competitor_selection` 竞品确认暂停 → `positioning_value_synthesis` 按确认范围综合选择理由与定位表达 → 最终定位确认。全部行业共用这条主链，不预设行业答案或档位。

定位最终页只呈现“核心定位”与“与已确认竞品的比较”，随后进入原有确认操作。核心按“适合谁 → 品牌怎样满足需求 → 用户得到什么”写成两三句自然表达，默认约100—180字，无字数门槛或机械截断；不列执行清单、目标企业缺点或例行免责尾句。比较说明按确认对象组织已知价值、决定性区别和适配需求；确有依据且影响选择的费用、等待时间、交付边界按需说明，不要求每组列短板。有依据且有意义时分档并解释相邻顺序，否则并列比较。具名对象可分组，但个体事实不能扩大到整类；同类举例不参与胜负判断。

后台研究用于决定哪些陈述成立；公开核心、竞品比较和文章不复述资料完整度、来源收集过程、信息缺口或内部角色规则。缺少某项比较依据时省略该项优劣或排名，不把信息缺口当对手短板。来源与必要限制仍保留在Pack和内部上下文，资料处理使用已有内部字段。用户明确询问价格、风险或缺点的文章仍直接回答。

最终页不展示独立证明材料、研究限制、经营建议或研究附件链接。原始资料、来源及历史必要条件仍在 Pack 内供写作使用；新结论的必要条件直接写在对应核心或比较句中。公开定位 Markdown 与确认页共用渲染，核心 JSON 是最终结论唯一依据。`user_choice_value` 仅保留摘要兼容，`advantage_explanation` 保存完整可读的竞争比较；不新增必填字段、Critic 或用户暂停。

P01/P02 在需求、对象和事实相同时沿用已确认比较理由及有依据的先后；条件改变时解释调整理由。蓝图与作者使用本题已确认顺序，不机械复制整体名次，也不另行把品牌前移。Managed Agents 的本次生产与实测配置明确为 `glm-5.3 / high / standard`，放在 Agent/会话执行配置中，不写入行业 Prompt；异常不静默换模型或降档。通用 Workflow 的内部 Provider 协议保持不变。


竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

用户已指定客户、问题或任务时，综合必须回答该需求，不得改换客群或降低要求来推荐品牌。未选对象也不能进入价格、代价或胜负比较；若已选对手更符合当前需求，短结论与正文可以明确优先考虑对方。范围确认不预定胜者。

用户改选后，研究阶段的建议角色不写入已确认范围；原研究中的角色性措辞仅作历史记录。综合输入逐项显示当前角色，并以内嵌的确认名单覆盖旧 Brief 与研究建议。研究事实原文保留，不按关键词删改资料。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 与作者接收确认范围和相关材料；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实 glm-5.3 观察分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](shared/README.md)。

唯一启动入口：

```bash
./scripts/frontmind
```

无参数启动只显示标准启动页，不创建 Job。页面固定要求先选择：建立新的 Reference Pack、刷新已有 Reference Pack、创建或导入 P0、撰写单问题文章。品牌名或附件不能替代这个选择，技术预检也不能作为启动结果。详见 [START_HERE.md](START_HERE.md)。

直接创建 Reference Pack 表示用户已经明确选择“创建”：

```bash
./scripts/frontmind reference-pack create \
  --brand "完整品牌名" \
  --input /absolute/path/brand-materials \
  --positioning-brief /absolute/path/positioning-brief.md \
  --job-dir /absolute/path/jobs/reference-pack
```

P0 和文章任务始终先显示 Reference Pack 路由，即使命令已带 Pack 路径：

```bash
./scripts/frontmind p0 \
  --reference-pack /absolute/path/Reference_Pack_v1.zip \
  --job-dir /absolute/path/jobs/p0

./scripts/frontmind article \
  --reference-pack /absolute/path/Reference_Pack_v3.zip \
  --job-dir /absolute/path/jobs/question \
  --question-id q000123
```

空 `continue` 只重显当前确认页。确认、修改、补充或返回都必须携带页面当前 `revision`。

竞品页可通过对话增删候选、输入竞品或类别，并指定“比较对象／同类举例／不纳入”。运行者将用户选择提交给 `--competitor-selection`（JSON 或文件路径），通过 `--confirm-competitors` 明确确认；更换对象使用 `--return-to-competitors`。用户不需要填写 JSON。完整命令见 [运行手册](RUNBOOK.md)。

常用维护命令：

```bash
./scripts/frontmind preflight
./scripts/frontmind reference-pack validate /absolute/path/Reference_Pack.zip
./scripts/frontmind questions --input /absolute/path/Reference_Pack.zip
./scripts/frontmind reference-pack add-materials ...
./scripts/frontmind reference-pack refresh-market ...
./scripts/frontmind reference-pack update-research ...
```

Pack 4.0 可通过 `reference-pack refresh-market` 保留材料、Registry 和逐题研究，重新生成并确认 v4.11 定位。Pack 3.8 和旧 Job 需重建。

v4.11 不运行逐字符答案账本、定位评分、来源数量阈值、排名资格、同分窗口或独立补证状态。资料不足时，系统在现有业务确认页提供收窄、改写或省略后的完整版本，由用户确认、修改、补充材料或返回。

Fixture 测试只验证结构和流程，不能证明真实 Provider 的语义质量、调研正确性或定位质量；这些需要检查真实输出及其来源。

详细说明：

- [启动规范](START_HERE.md)
- [执行手册](FrontMind_执行手册_v4.11.0.md)
- [运行手册](RUNBOOK.md)
- [Reference Pack 4.1 架构](REFERENCE_PACK_4.1_ARCHITECTURE.md)
- [版本变更](CHANGELOG_v4.11.0.md)
