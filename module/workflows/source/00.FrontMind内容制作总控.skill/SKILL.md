---
name: frontmind-content-workflow-v4-11
description: FrontMind Content Workflow 入口；以 Reference Pack 4.1 执行差异化定位、P0 与单问题内容生产，当前新建 P01/P02 使用 v16 正文流程与 v16.2 十个同主题近义标题。
---

# Final v16.2 编辑准备、自然写作与品类推荐标题

新建 P01/P02 默认使用 `frontmind-natural-prose/16`。P0 和其他 Pattern 保持原流程；历史正文任务按冻结版本恢复，不因标题修改升级正文合同；标题规则的显式升级见下文。技能名称保留既有入口标识。

## 当前标题规则

新 P01／P02 每篇10个，全部默认不带品牌名，围绕当前确认的同一地区、品类／项目和推荐意图自然近义改写。P01标题可写品类推荐，正文只介绍一家，不承诺多家榜单或横向对比；P02标题覆盖全文主体范围。允许“机构推荐、品牌推荐、选择参考、选择指南”等表达，不按章节拆成不同选题。用户明确要求标题带品牌时覆盖默认；正文出现品牌不等于此要求。

作者与标题编辑共用规则和去掉旧H1的最终正文；angle为表达侧重点，可以重复。仍然只有拟题与一次标题编辑两步。P0及其他Pattern保持20个。旧任务重试沿用冻结规则；已完成P01／P02显式使用 `--title-edits` 时，在验证旧稿、快照后仅升级标题规则，正文流程不升级、不重写。人工参考样例见 `title_examples/v16_2/README.md`，不代替生产模型结果。

## 当前正文流程

编辑准备 → 正式蓝图 → DeepSeek 初稿 → E8 全文编辑 → XTY 最后文字编辑 → 独立标题 → Word 与 Markdown 导出。

编辑准备由独立的 XTY 动作 `article_editorial_preparation` 完成：结合当前企业和文章任务，实际搜索、获取并完整阅读两篇同类已发布案例，再阅读原始材料并完成编辑取舍。P01 的案例应匹配单主体介绍，P02 匹配多机构推荐；既有参考材料继续按用户约定的文风、篇幅或背景用途使用。

本轮交付自然事实段落和基于案例、编辑经验的蓝图建议，冻结在 `editorial/article_preparation.json`。案例出处与企业事实来源分别保存。取材与写法判断留在编辑内部，不输出事实缺口、评分或审计报告；本轮不定正式蓝图。

蓝图轮只接收当前委托、干净事实段落、编辑建议及适用的参考内容，不能重新读取原始知识库。程序继承准备轮的素材与来源，蓝图负责正式内容安排，并给作者保留表达空间。

事实段落是内容基础和方向提示，不是逐句保留或逐项覆盖的底稿。蓝图和作者可以取舍、组织、合并，充分润色、美化；在保持事实含义的基础上，优先完成漂亮、自然、重点清楚的文章。E8 通读全文，改善主次、表达、节奏与衔接，不因成稿措辞不同于材料而改回原句。`count_article` 只统计实际正文长度，按当前委托范围安排篇幅。

XTY 最后只读当前完整稿与写作要求，提交少量 `original/replacement` 句级修改。局部修改准确对应当前稿，不重排段落、改标题或改变加粗主体。确需重组内容时，由 DeepSeek 返工一次，再经独立 `article_polish` 动作让 XTY 阅读返工全文；仍需大修则保留待修改，不自动循环或宣告合格。

最终来源记录 DeepSeek 基稿和 XTY 局部修改，并如实标记 v16 合同。标题、Word、Markdown 和续改读取同一实际终稿。程序校验来源与流程，成文质量仍须阅读全文判断。

## 运行与恢复

沿用 `./scripts/frontmind` 及已有新建、继续、正文精修、标题修改入口；先用 `./scripts/frontmind preflight` 检查环境。新 DeepSeek 请求默认使用 `high`，模型与网关读取现有配置。相同历史冻结请求保留原配置恢复，不把旧 `max` 记录改写为 `high`。

仅调整蓝图组织时复用已完成的编辑准备；新增原始材料或改变实际委托时，经准备轮重新处理。普通正文和标题修改不重新搜索。v16 不通过 `--writing-materials` 直接向作者注入新材料，新增材料使用现有蓝图补料入口。

案例命令保留已设置的 `FRONTMIND_PYTHON`，未设置时使用 `python3`；预检与案例使用同一解释器。使用其他已有运行时时，先设置该变量。

本次案例输入保存在 `customer_inputs/taixin/v16/`，原始附件可通过案例配置引用已保留的原件。P01 约3000字，P02 约4330字，三类11家及顺序属于案例配置，不写死到通用 Prompt。

```bash
export FRONTMIND_PYTHON="${FRONTMIND_PYTHON:-python3}"
./scripts/frontmind preflight
"$FRONTMIND_PYTHON" scripts/run_taixin_v16_case.py --pattern P01 --job-dir jobs/taixin-p01-v16 --stage all
"$FRONTMIND_PYTHON" scripts/run_taixin_v16_case.py --pattern P02 --job-dir jobs/taixin-p02-v16 --stage all
```

`prepare` 只在新目录准备输入；`blueprint` 也会新建任务，再完成编辑准备和正式蓝图；`all` 从新任务完整执行。已执行 `prepare` 的同一目录应使用 `resume` 推进到蓝图确认，再用 `write` 接受已生成的案例蓝图并执行正文链。`resume` 恢复已保存阶段，不重新建任务。API 失败使用原有显式重试入口。本案例复用已确认委托，入口助手不手写正文、不代填或修改模型结果。

`generated/` 保存实际运行的交付结果、准备材料和 Prompt，不作为后续写作输入。交付前阅读全文，再渲染 Word 逐页查看；发布包经解压启动检查，包内正文与独立交付保持一致。

## 版本说明

当前入口与操作说明见 [v16说明](../FIX_v4.13.2_Final_v16.md) 和 [总控手册](../Master_Control/FrontMind_Content_Workflow_Master.md)。v15 的“选材与蓝图合并”及旧自然写作规则仅对应冻结的 `frontmind-natural-prose/15` 任务，保留在 [v15说明](../FIX_v4.13.2_Final_v15.md)。历史说明不加入新版模型上下文，也不覆盖 v16 的当前分工。
