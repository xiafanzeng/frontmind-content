# Workflow v16 案例研究与自然成文
本包为 v16.2 标题规则修订：新 P01／P02 每篇提供10个同一推荐主题的近义标题，默认不带品牌名；P01正文介绍一家、P02正文介绍多家。明确要求标题带品牌时覆盖默认。保留 v16.1 的类别称谓、正文流程和全部历史生成记录。已完成 P01／P02 可通过 `--title-edits` 采用新标题规则；普通恢复和失败重试保持原冻结规则。详见 `FIX_v4.13.2_Final_v16_2.md`。

已保留 v16.1 类别称谓修订：新任务的定位、蓝图、正文及候选标题使用“第一类、第二类、第三类”和“这一类”等分类表述，保持推荐重点、主体顺序与其他写作安排。P02 仅替换称谓的当前样稿见 `customer_inputs/taixin/v16/current_delivery/P02/`；`generated/` 保留 v16 实际模型请求和输出供历史查看，不作为新任务输入。


新建 P01/P02 默认使用 v16：XTY 案例研究与编辑准备 → XTY 正式蓝图 → DeepSeek 初稿 → E8 全文编辑 → XTY 最后文字编辑 → 独立标题 → Word 与 Markdown 导出。

每篇前置编辑实际搜索并阅读全文，分析两个适合当前企业场景和文章类型的具体案例。研究过程留在后台，对蓝图只提供自然事实段落和蓝图建议。正式蓝图由下一轮决定。原始知识库不再直接进入蓝图、作者及 E8，不输出事实缺口、评分或审计报告，不增加确认节点。

事实段落提供内容基础和方向，作者可以自主取舍、组织、润色和美化。以漂亮、自然、流畅且有吸引力的文章为目标，不逐项转述材料，不要求每段解释意义。DeepSeek 新请求统一使用 high；历史冻结请求沿用原配置，XTY 配置保持现状。P0 和其他 Pattern 的专门流程保持原安排。

E8 编辑整篇文章的语言、节奏、主次和衔接。XTY 直接处理少量句子问题；结构问题只交给 DeepSeek 返工一次，再读取返工后的完整稿。仍需大修时保留待修改，不能自动宣告完成。局部替换必须唯一命中、不重叠、不跨段或改变主体及分类结构。最终标题、Word、Markdown 与续改读取同一份实际终稿。

## 运行

解压后在本目录执行：

```bash
export FRONTMIND_PYTHON="${FRONTMIND_PYTHON:-python3}"
./scripts/frontmind preflight
"$FRONTMIND_PYTHON" scripts/run_taixin_v16_case.py --pattern P01 --job-dir jobs/taixin-p01-v16 --stage all
"$FRONTMIND_PYTHON" scripts/run_taixin_v16_case.py --pattern P02 --job-dir jobs/taixin-p02-v16 --stage all
```

Python 须具备 requirements.txt 中的运行依赖。以上命令保留已设置的 FRONTMIND_PYTHON；未设置时使用 python3，预检与案例运行使用同一解释器。使用 Codex 捆绑运行时时，先将 FRONTMIND_PYTHON 设为该解释器路径。不自动安装依赖；模型及网关使用 config 中的现有配置。

`prepare` 只在新目录准备输入；`blueprint` 也会新建任务，再完成编辑准备和正式蓝图；`all` 从新任务完整执行。已执行 `prepare` 的同一目录应使用 `resume` 推进到蓝图确认，再用 `write` 接受已生成的案例蓝图并执行正文链。`resume` 恢复已保存阶段，不重新建任务。API 技术失败沿用显式重试入口。本案例已获完整执行授权，复用已确认的题目、主体、分类、篇幅和排版，不导入旧文章或旧蓝图。

## 案例与交付

原始资料、案例配置和原有参考例文在 customer_inputs/taixin/v16。P01 为台心单主体稿，正文 2850—3150 字；P02 为三类 11 家，保持原顺序和台心重点，正文 4110—4550 字。字符统计含小标题、标点、数字与英文，排除主标题、空白和 Markdown 标记。行业内容要求保留在案例配置中。

`customer_inputs/taixin/v16/generated/` 保存实际使用的编辑准备、研究案例、正式蓝图、Prompt 和模型结果，仅供查看，不作为新稿输入。运行日志、废弃试稿不进入发布 ZIP。

交付前完整阅读文章，检查字数、主体、分类和排版，渲染 Word 并逐页检查；解压验证入口与配置，确认包内正文和独立交付一致。
