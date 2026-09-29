# P0编辑Skill的取舍与接入

本地版本1.0.0，工作流合同4.12.8。由用户前轮提供的研究候选SKILL.md及调研包发展而来；本轮执行的是集成任务，没有重新拉取上游或声称这些仓库的状态最新。它不是上游任一技能的官方版本或完整翻译。

## 采用的方法

- Kiterlin/anti-defensive-writing：按句子用途区分必要限制、真实反对意见与多余辩解，再围绕主旨重建段落。P0把叙述对象改为机构及其业务，不沿用论文、证据和本节等主语。
- blader/humanizer：识别无对象辩解、重复收尾、夸大意义和叠加限定；以段落修改而非逐词替换完成编辑。
- op7418/Humanizer-zh：借鉴中文空泛总结及模板语言的例子，不引入虚构个人经历、题外话或强行第一人称。
- hardikpandya/stop-slop与softaworks/agent-toolkit的writing-clearly-and-concisely：参考具体直接、减少无信息文字、把行动者讲清；不强制删副词、禁否定、禁被动或标点评分。
- coreyhaines31/marketingskills的copy-editing：参考受众与信息清晰度；不引入七轮调用、专家评分、固定意义桥接或营销承诺放大。

Adkid-Zephyr/anti-defensive-writing-Skill未整体采用。‘少防御’不意味着掩去重要的不利信息，不能把强硬表述或优势优先当准确性的替代。

## 原始研究中的来源

https://github.com/Kiterlin/anti-defensive-writing/blob/main/SKILL.md
https://github.com/blader/humanizer/blob/main/SKILL.md
https://github.com/op7418/Humanizer-zh/blob/main/SKILL.md
https://github.com/hardikpandya/stop-slop/blob/main/SKILL.md
https://github.com/softaworks/agent-toolkit/blob/main/skills/writing-clearly-and-concisely/SKILL.md
https://github.com/coreyhaines31/marketingskills/blob/main/skills/copy-editing/SKILL.md
https://github.com/Adkid-Zephyr/anti-defensive-writing-Skill/blob/main/skills/anti-defensive-writing/SKILL.md

这些来源由前轮提供的RESEARCH_AND_INTEGRATION.md登记。本文件说明取舍，不是仓库效果排行榜；没有安装上游插件或运行其中代码。SKILL.md是本项目新写的适配文本，非上游正文逐字转载。

## 实际执行

资源只在4.12.8的p0_style系统提示中加载正文。元数据、此研究说明、测试案例和上游仓库文档不进入模型请求。原始例文全文作为第三组输入保持不变。本地版本/文件哈希检查只确认资源完整，不检查文章词语，也不评定成稿质量。

material_adjustments的旧内容不通过代码筛选或删除：它可能含必要范围。新选材从源头不持续累积完成日志；传给作者时以独立的编辑执行条件呈现，不能当品牌事实抄入正文。

## 验证边界

系统提示已经在实际运行分支接入，并提供请求、缓存、历史兼容和输出合同测试。人工反例/正例不是模型输出；测试通过不说明新稿已经自然。没有付费API调用或质量保证。
