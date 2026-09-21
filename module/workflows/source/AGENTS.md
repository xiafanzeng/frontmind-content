# FrontMind Content Workflow v4.11 Runtime Contract

This package is release `4.11.0`, runtime `4.11`, using Reference Pack schema `4.1`. Run production tasks only through `./scripts/frontmind` at the package root.

## Natural-language startup

When the user says only “启动工作流”, “开始 FrontMind”, or attaches the release ZIP and asks to start, run `./scripts/frontmind` and display its complete four-choice startup page. No arguments is intentionally equivalent to `./scripts/frontmind start`.

The four startup choices are: create a new Reference Pack, refresh an existing Reference Pack, create or import P0, and write one question article. Do not replace this menu with an open-ended request for brand, materials and target. Do not create a Job or begin research until the user chooses. A brand name by itself is a hint, not a choice to create a Pack. A preflight may run first, but its result does not replace the startup page.

After the choice, collect only that path's minimum input. Creating a new Pack then needs a brand and ordinary company material; material may also be supplied at the existing input pause. Refresh needs an existing Pack. P0 and article create their Jobs and still stop at the Reference Pack route described below.

## Startup routing

Every new `p0` or `article` Job starts at `awaiting_reference_pack_route`. A supplied brand, ordinary file, Pack path, earlier task or group of questions does not approve a route. Display the whole route page and wait for the user's explicit choice.

`reference-pack create` is itself an explicit choice to create a Pack, so it starts intake directly. A batch parent may record one explicit Pack decision and bind it to all children; a launcher must never infer that decision.

The release ZIP is executable workflow code. Never use it as company material or as a Reference Pack.

## User pauses

A payload using `frontmind-user-pause/v3`, `requires_user_input=true`, `user_pause=true` or `must_stop=true` is a real turn boundary. Display the complete Markdown page, tables, local files and source links, then stop. Never submit a recommendation for the user.

Every mutation or confirmation uses the current `revision`. A stale revision fails. An empty `continue` leaves state and page unchanged.

The active business pauses are Reference Pack route and input, competitor selection (`awaiting_competitor_selection`), final positioning, P0 route, conditional P0 examples, P0 blueprint, missing question research input, E1 response brief, Pattern, conditional question examples, P01/P02 question positioning and article blueprint. Legacy direction artifacts do not create a new direction-selection step.

Material gaps use the nearest existing business page. Show the proposed narrower, rewritten or omitted wording there. The user may confirm, edit, add ordinary material or return.

## Positioning provider

`frontmind-provider-action/v3` is an internal action. Read `prompt_path`, write valid JSON to `expected_output`, then resume. A configured `FRONTMIND_CONTROLLER_PROVIDER` callback performs this automatically. Internal actions cannot confirm or cross a user pause.

定位正常使用两个内部 Provider 动作，中间必须等待用户确认比较范围：`positioning_market_research` 研究市场并提供候选列表 → `awaiting_competitor_selection` 竞品确认暂停 → `positioning_value_synthesis` 按确认范围综合选择理由与定位表达 → 最终定位确认。全部行业共用这条主链，不预设行业答案或档位。

定位最终页只呈现“核心定位”与“与已确认竞品的比较”，随后进入原有确认操作。核心按“适合谁 → 品牌怎样满足需求 → 用户得到什么”写成两三句自然表达，默认约100—180字，无字数门槛或机械截断；不列执行清单、目标企业缺点或例行免责尾句。比较说明按确认对象组织已知价值、决定性区别和适配需求；确有依据且影响选择的费用、等待时间、交付边界按需说明，不要求每组列短板。有依据且有意义时分档并解释相邻顺序，否则并列比较。具名对象可分组，但个体事实不能扩大到整类；同类举例不参与胜负判断。

后台研究用于决定哪些陈述成立；公开核心、竞品比较和文章不复述资料完整度、来源收集过程、信息缺口或内部角色规则。缺少某项比较依据时省略该项优劣或排名，不把信息缺口当对手短板。来源与必要限制仍保留在Pack和内部上下文，资料处理使用已有内部字段。用户明确询问价格、风险或缺点的文章仍直接回答。

最终页不展示独立证明材料、研究限制、经营建议或研究附件链接。原始资料、来源及历史必要条件仍在 Pack 内供写作使用；新结论的必要条件直接写在对应核心或比较句中。公开定位 Markdown 与确认页共用渲染，核心 JSON 是最终结论唯一依据。`user_choice_value` 仅保留摘要兼容，`advantage_explanation` 保存完整可读的竞争比较；不新增必填字段、Critic 或用户暂停。

P01/P02 在需求、对象和事实相同时沿用已确认比较理由及有依据的先后；条件改变时解释调整理由。蓝图与作者使用本题已确认顺序，不机械复制整体名次，也不另行把品牌前移。本次生产与实测使用当前任务冻结的供应商、模型和推理档位，由宿主的 Agent/会话执行配置决定，不在工作流或行业 Prompt 中固定供应商或模型；异常不静默换模型或降档。旧 `glm-5.3 / high / standard` 的验收观察仅供历史对照，不能代表当前配置已经验收。通用 Workflow 的内部 Provider 协议保持不变。


竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

用户已指定客户、问题或任务时，综合必须回答该需求，不得改换客群或降低要求来推荐品牌。未选对象也不能进入价格、代价或胜负比较；若已选对手更符合当前需求，短结论与正文可以明确优先考虑对方。范围确认不预定胜者。

用户改选后，研究阶段的建议角色不写入已确认范围；原研究中的角色性措辞仅作历史记录。综合输入逐项显示当前角色，并以内嵌的确认名单覆盖旧 Brief 与研究建议。研究事实原文保留，不按关键词删改资料。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 与作者接收确认范围和相关材料；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实 glm-5.3 观察分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](shared/README.md)。

Translate the user's natural-language selections into `continue --competitor-selection` JSON or a JSON file path; do not ask the user to write JSON. Show the role and comparison-scope preview on the competitor page. Use `--confirm-competitors` only for the user's explicit scope confirmation; `--return-to-competitors` returns to that page and invalidates the old positioning confirmation. All three use the current `revision`. Provider actions cannot supply the user's selection or cross this pause.

## Reference Pack lifecycle

Reference Pack 4.1 is the only persistent package:

```text
materials
→ competitive choice map and market research
→ user-confirmed competitors and peer examples
→ value synthesis
→ confirmed positioning
→ P0
→ exact-question research
```

The Pack keeps a stable `pack_id` and increments `pack_version` for each immutable update. Positioning normally produces v1, P0 v2 and question research v3 onward. Never overwrite an earlier version or silently switch a running article.

`materials_ready`, `brand_market_research_ready`, `positioning_ready`, `p0_ready` and per-question `question_ready` describe completed stages, not scores or evidence thresholds. Question answers preserve positioning and P0. Brand material or market changes reopen the existing positioning path; a material positioning change requires P0 blueprint review.

Pack 4.0 can enter `reference-pack refresh-market`: preserve materials, registries and question research, regenerate positioning under 4.11, reconfirm it and review P0 later. Pack 3.8 and old Jobs require rebuilding.

## P0 and question workflow

The Reference Pack Job ends after positioning export. P0 starts separately, asks create or import, conditionally confirms examples, confirms the blueprint, produces Markdown, HTML, DOCX and 20 titles, then writes a new `p0_ready` Pack version. P0 reuses the confirmed positioning, comparison scope and relevant research instead of rerunning brand research or treating every researched brand as a selected competitor.

An article requires a `p0_ready` Pack and two complete AI answers for the exact question. Missing answers use the existing question-input page and create a new Pack version without rerunning positioning.

E1 always pauses. Pattern always displays P00–P06; P00 is unavailable for question tasks. P01/P02 alone create question-positioning pages. P03–P06 proceed from examples to blueprint. The optimized company may be introduced from its Pack even when AI answers omit it, but the article must not claim those answers mentioned or recommended it.

## Author and editor context

The author receives the question and brief, confirmed positioning with its advantage explanation, natural-language comparison scope and applicable supporting material, P0, applicable P01/P02 positioning, complete AI answers, relevant natural material, complete examples and the confirmed blueprint. Scope content tells the author which objects are targets or peer examples; internal confirmation records remain excluded. Neither P0 nor an article must copy the entire core paragraph or every strategic note.

Do not expose registries, internal IDs, hashes, source classes, scores or confirmation records. Do not create span ledgers, candidate scoring, coverage checks, source-count gates, rank gates, tie windows, evidence overlays or supplement contracts.

E8 may fix ordinary wording, repetition, report tone, unsupported comparisons and heading rhythm. If an edit changes positioning, the direct answer, confirmed order, an entire core section or the subject set, return to the same blueprint page.

## Pack and ZIP safety

Reference Pack ZIPs have no outer-file, single-member or expanded-byte ceiling. Keep the 5,000-member limit, normalized duplicate rejection, traversal and absolute-path rejection, encryption rejection, nested-ZIP rejection, symlink and special-file rejection, and per-member compression-ratio limit of 200. Use streaming I/O, temporary directories and atomic commits.

The release ZIP must preserve `scripts/frontmind` as Unix mode `0755`.

Fixture tests establish structural and workflow behavior only. They do not establish real provider semantic quality, research validity or the quality of a positioning judgment. Claims about those require examination of real provider output and its sources.
