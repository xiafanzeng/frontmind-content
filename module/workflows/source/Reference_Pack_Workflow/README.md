# Reference Pack Workflow 4.1

## v4.12.3 当前运行与写作合同

本版以上传的 v4.12.2 为代码基线。宿主固定为智谱 **Managed Agents / glm-5.3 / max**；初稿、E8、P0 第三遍修饰和标题固定为 **DeepSeek Pro / deepseek-v4-pro / max**。入口 AI 只启动命令、转交真实输入与确认，不代填内部结果。没有 Claude 写作路由，也不回退 XTY/Astra。

新 P0 使用 `frontmind-p0-style/4.12.3`，保留蓝图→初稿→E8→第三遍修饰→最终验读→20标题→标题编辑→交付。先按篇选材，再写文章；不传整库原文或竞品研究。第三遍负责实际成文，终审保留已自然、准确的表达，不把每个事实改成定义、释义与抽象总结。不增加新的模型阶段、质量分数、字数配额或用户确认页。

固定两篇例文的身份和全文要求保留。生产任务读取并冻结真实文本；断网或源文变化不能用模拟样本替代。合成样本仅供显式离线测试。旧 4.12.1/4.12.2 成稿和例文合同保留，不补造新的模型记录；旧稿内容合同不自动升级，但重新执行的宿主动作只能使用当前托管后端。

本次已完成代码与离线模拟验证，真实 API 验证因当前环境 DNS 失败而未完成。运行成功、内容合同通过和最终文章质量是不同结论，不能相互替代。详细接口、恢复与联网核验见 [MODEL_RUNTIME.md](../MODEL_RUNTIME.md)。


Reference Pack 4.1 是 FrontMind v4.11 唯一的持久内容包。它用同一个 `pack_id` 系列保存企业材料、来源追踪、行业中立的竞争选择研究、用户确认的比较范围与完整核心定位、P0 和逐题研究。

## 生命周期

```text
材料接入
→ 真实选择与竞争研究
→ 用户确认比较对象与同类举例
→ 综合选择理由与定位表达
→ 用户最终确认
→ positioning_ready v1
→ P0 写回 v2
→ 逐题研究写回 v3、v4……
```

每次更新建立新目录和新 ZIP，不覆盖旧版本。运行中的文章固定绑定启动时的 `pack_version`。

## Readiness

| 字段 | 含义 |
|---|---|
| `materials_ready` | 材料已安全接入、规范化并建立 Registry |
| `brand_market_research_ready` | 市场研究及候选资料完成，不代替用户确认比较范围 |
| `positioning_ready` | 当前完整核心定位修订已经用户确认 |
| `p0_ready` | P0 已完成并写入 Pack |
| `question_ready[question_id]` | 对应问题已有两篇完整 AI 答案与可用输入 |

这些字段表示阶段是否完成，不代表资料得分或证据数量。

## 品牌市场研究成员

```text
research/brand_market/
├── positioning_research_review.md
├── competitive_choice_map.json
├── competitive_choice_map.md
├── brand_reality.md
├── audience_choice_logic.md
├── competitor_landscape.md
├── market_opportunities.md
├── ai_semantic_context.md
└── source_index.json
```

定位正常使用两个内部 Provider 动作，中间必须等待用户确认比较范围：`positioning_market_research` 研究市场并提供候选列表 → `awaiting_competitor_selection` 竞品确认暂停 → `positioning_value_synthesis` 按确认范围综合选择理由与定位表达 → 最终定位确认。全部行业共用这条主链，不预设行业答案或档位。

竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 依据当前用户的文章任务与 宿主 选出的自身业务事实组织，蓝图与宿主工具不接收旧 `own_brand_context`、核心定位投影、竞争比较或研究附件。问题路线继续使用已确认定位；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实模型运行分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](../shared/README.md)。

## 更新规则

新增问题答案或引用资料时保留定位、比较范围和 P0。新增品牌事实保留已确认范围，补研后重新综合；尚无范围时先确认竞品。刷新市场研究重做候选，旧选择作为可编辑预选，经竞品确认后再生成定位。修改表述只重新综合，更换比较对象返回竞品页并使旧定位确认失效。定位发生实质变化后，P0 在既有蓝图页重新审阅。纯格式和元数据修复不改变 readiness。

用户补充企业文件时，Builder 自动冻结、提取并记录来源；用户不需要编写 manifest、事实编号或来源分类。战略意图写入定位 Brief，客观材料写入 materials 与 Registry。

## CLI

```bash
./scripts/frontmind reference-pack create ...
./scripts/frontmind reference-pack validate PACK
./scripts/frontmind reference-pack add-materials ...
./scripts/frontmind reference-pack refresh-market ...
./scripts/frontmind reference-pack update-research ...
./scripts/frontmind questions --input PACK
```

Job 内的名单操作使用 `continue --job-dir JOB --revision CURRENT`，加 `--competitor-selection`（JSON 或文件路径）编辑，`--confirm-competitors` 确认，或 `--return-to-competitors` 返回。运行者根据用户自然语言提交参数，用户无需写 JSON。完整例子见 [运行手册](../RUNBOOK.md)。

已确认的 `comparison_scope` 随核心 JSON 保存实际比较对象、同类举例及范围说明。旧 Pack 无此字段仍可读，不自动推定，也不增加旧 Pack 必需文件。

Pack 4.0 可通过 `refresh-market` 保留材料、Registry 和逐题研究后升级，旧定位与 P0 需重新生成和审阅。Pack 3.8 使用原始材料重建。

## 安全

ZIP 不设外壳、单成员或解压总字节上限。仍限制最多 5,000 个成员，并拒绝重复规范化路径、路径逃逸、绝对路径、加密成员、嵌套 ZIP、符号链接、特殊文件和单成员压缩比超过 200。解压和版本发布使用流式 I/O、临时目录与原子提交。

Fixture 测试只验证结构、兼容性和流程行为，不证明真实 Provider 的语义质量或定位质量；这需要检查真实输出与来源。
