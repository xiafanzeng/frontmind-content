# FrontMind 通用内容 Workflow v16.3

本包是一套跨行业流程。输入当前客户的品牌、原始资料、问题与写作要求；不会自动使用台心客户的范围、篇幅或历史授权。模型配置沿用原包，不自动安装依赖或调用模型。

新版 P01 为单品牌自然品宣；新版 P02 为主品牌与用户选定的两家竞品，主品牌先介绍。P01／P02 每篇独立交付 10 个标题：5 个正式推荐、5 个场景与卖点，默认不带品牌。P0 和其他 Pattern 保持原流程。

行业横向盘点可在**新建** article Job 时显式指定 `--genre industry_roundup`，并用重复的 `--subject` 固定 3—12 个主体。`pattern` 仍说明问题的主体关系，`genre` 决定文体，`subject_scope` 是本篇名单。新任务还须重复提供 2—8 个 `--dimension`，在蓝图中形成按具体型号区分的同维度矩阵、读者问题到章节的映射和选型规则。该文体不进入默认 P02 的三家选择页；旧 Job 不迁移。编辑准备登记逐条事实与本地原文片段；交付前保存 `production/industry_roundup_quality_gate.json`，未过机器检查则不交付。机器检查不能替代来源真实性和同条件可比性的人工复核。

新 article Job 可选 `--focus` 指定本篇细分产品／功能，重复 `--reader-question` 指定核心读者问题，重复 `--exclude-topic` 划出不展开的范围。三个字段写入任务快照，并进入编辑准备、蓝图、正文及复核提示词；行业盘点的指定问题另由蓝图校验逐项映射。写作提示词吸收组内 `writing_context_fdnv2.py` 的通用规则：围绕当前问题取材、优先有效信息、区分事实来源、不编造亲身体验、不强制凑 FAQ；没有照搬其中的医疗行业示例。没有这些新标记的历史 Job 继续使用旧提示词。

自 `fdnv2-focus-2` 起，新任务的蓝图与初稿增加行业盘点约束：用真实问题限定细分场景；材料支持时先解释技术路线／方案类别及适用边界，再按同口径比较品牌型号；主品牌与竞品采用同一证据标准；关键小节独立说明对象、条件与结论。初稿只接收一次已筛选材料和对比矩阵，不重复注入同一证据；只写与本篇相关的信息，不为凑结构补市场数字、趋势或 FAQ。旧 `fdnv2-focus-1` 任务及更早任务保持冻结提示词。以上为写作和蓝图约束，跨段中立程度与语义自包含仍需人工审稿；没有调用模型验证成文效果。

交付校验失败时，查看上述 JSON，使用 `continue --job-dir ... --revision 当前修订号 --repair-facts` 从全文编辑返工。若某条事实本身不可靠，可同时重复填写 `--reject-fact-claim F01`；该 ID 在后续编辑提示词中失效，正文继续使用会被拦下。返工前的产物保存在 `reviews/fact_repair_before_*`，原模型调用记录也保留。

## 通用运行入口

```bash
export FRONTMIND_PYTHON="${FRONTMIND_PYTHON:-python3}"
./scripts/frontmind preflight
./scripts/frontmind article --brand '当前品牌' --input '/绝对路径/当前客户资料' --question '当前正式问题' --job-dir '/绝对路径/新任务目录'

# 行业盘点示意；Windows 将 ./scripts/frontmind 换成 .\scripts\frontmind.cmd
./scripts/frontmind article --genre industry_roundup --brand '当前品牌' --subject '当前品牌' --subject '竞品甲' --subject '竞品乙' --dimension '价格' --dimension '噪音' --focus '某一类产品的选购' --reader-question '预算内怎样选择？' --exclude-topic '其他品类' --input '/绝对路径/当前客户资料' --question '当前正式问题' --job-dir '/绝对路径/新任务目录'
```

也可传 `--reference-pack '/绝对路径/现有资料包.zip'` 复用资料包。若包内已有监控问题目录，可不传问题，在现有选题页面选择；没有监控答案时按现有页面提供两个不同平台的完整回答。运行环境需要 requirements.txt 内的依赖；预检缺依赖时报告，不自动安装。实际执行会使用 config 中已配置的模型与网关。

新任务沿用：定位与对象确认 → 案例研究及编辑准备 → 正式蓝图 → 初稿 → 全文编辑 → 最后文字编辑 → 独立标题 → Word、Markdown 与标题表。

## P02 对象选择

在现有竞品选择页展示自身位置、候选客观实力及证据、AI提及的期次和各平台分母。优先建议两家在客观实力和可比声量上均更强的机构；未证明双强时保留未知或相近状态，仍允许用户选定两家。不会自动补位或扩大地区。

用户通过现有 `--competitor-selection` 提交两家具体名称／编号，再用 `--confirm-competitors` 确认。角色使用 `comparison_targets`，`peer_examples` 为空。不新增第四个推荐主体。确认后名单贯穿准备、蓝图、正文和编辑。同一问题、期次和委托可复用确认记录；明确范围改变回到现有选择页。定位页的措辞编辑保留确认名单；要换对象，在该页提交 --competitor-selection 与 --confirm-competitors，或 --rerun-positioning-research。已完成稿的 --writing-requirements 若明确变更 article_brief、candidate_order 或 recommendation_relationships，会先留存旧稿，再返回选择流程。

程序使用本题本期的全部有效监控回答，按每答每机构一次、平台等权计算提及；不把提及率称作引用率。缺少逐机构正向推荐和引用标注时记录未知。窄范围选择更新保存为资料包的 `strategy/p02_selection.json`，不删除或重做 P0，也不覆盖原核心定位。

## 写作与标题

P01 可以把具体特点放进合理场景，写出直接便利、体验和吸引力。编辑删除空泛或重复总结，保留自然价值表达，不把文章压成资料摘要。不固定场景数或段落公式；事实、实际服务与效果判断有依据，不编造经历。

标题前五项 style=formal，后五项 style=scenario。两组均是同一篇正文的替换标题；场景组不必逐个对应不同人群或卖点。P01 可以用“这家机构”，P02 覆盖全文名单。推荐项可来自任一组，不自动回填正文。

## 历史任务与显式修改

无策略标记的历史 20 标题、v16.2 的 10 个近义标题以及历史正文沿用冻结策略。`continue --title-edits '/绝对路径/修改要求.txt'` 对已完成 P01/P02 留存快照，只重跑新版 5＋5 标题和导出，正文及哈希不变。旧 P02 十一家文章仅修改标题时仍覆盖原正文全部主体，不暗中删成三家。

将旧多主体文章改为三家，请新建 P02 委托并重新确认名单、准备材料、蓝图和正文；只改标题不会完成正文范围迁移。

## 历史案例复现

`customer_inputs/taixin/v16/` 是保留的台心历史案例。其“腰腹为入口、医学美容科为主体”、P01 篇幅和 P02 十一家名单仅属于该案例。`generated/` 是历史模型结果，不是新客户输入。案例中的旧授权不适用于当前任务。

仅在明确复现该案例时使用：

```bash
"$FRONTMIND_PYTHON" scripts/run_taixin_v16_case.py --pattern P01 --job-dir '/绝对路径/历史案例新目录' --stage all
```

复现脚本固定历史正文及 v16.2 标题策略，不演示新版 P02 三家规则。新版样例在 `examples/v16_3/`，均明确标为人工／离线合成，不代表实际模型效果、真实竞品评估或 AI 引用效果。
