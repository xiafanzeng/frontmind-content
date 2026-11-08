---
name: frontmind-positioning-p0
description: 第一阶段：用Kimi Hosted high读取完整知识库形成定位与用户确认优势，交付三项Reference Pack及XTY Gemini按优势组织的P0。
metadata:
  version: "16.25.1"
---

# 第一阶段

只使用scripts/workflow.py，命令见../../docs/命令顺序.md。输入企业名称和完整Markdown知识库ZIP，不生成资料整合说明或额外材料审批。

Kimi Hosted Agents（kimi-k3.1-pro/high）通过run-agent依次执行positioning、advantages、p0_check；共享Agent/Environment；分析与成稿文风分别复用独立Session。waiting续查同请求。P0初稿与必要定向编辑只用XTY Gemini high及HTTP，不用OpenAI SDK，不由本地宿主代写分析冒充Kimi。

完整读知识库后给定位选项与问题目录，A等待用户具体选类；优势先总结特点、客户价值和建议写法，C允许排序增删补充。已有同范围明确授权记录原话，不反复确认。用户确认优势不增证据等级或首家证明门槛。

已有明确确认同类池可用confirmed-peers和原文件/授权note继承；保留顺序，不从材料任意提及自动认定确认。无池可空，不设固定B。三项Pack为定位.md、核心差异化优势.md、知识库.zip，定位含问题目录及确认池，原知识ZIP保持。第二阶段承接Pack后独立选择问题与模式，P0不是输入。

P0按确认优势实际数量、顺序各设独立三级小标题；例文只学文风。默认初稿加一次反防御性文风核对；无问题直接定稿，有文字问题才一次Gemini轻润色。仅用frontmind-anti-defensive-writing，不固定多轮全文诊断。编辑后仅确认原文风问题和相关上下文，不启动新的风格轮。事实范围、必要条件与优势强度保持，背景项不编成果。

保存实际Prompt/返回、Hosted artifact与公开操作事件；不输出私有思维链。失败不自动重发、换模或假报成功。输出P0 TXT/Word及辅助格式；本地实际渲染PNG后用p0_visual_check和--pages-manifest交Kimi high逐页看图，再验收。本包不写问题文章、不发布。

成稿后仅处理文风：不对照知识库、不联网查证、不核验事实口径或数字/资质/功能，不重审已确认优势。Kimi只收到当前稿、简短反防御性规则和文字意见；不附知识库或定位/优势来源材料。无文字问题直接采用Gemini初稿，有问题才一次Gemini轻润色。事实、名称、数字、条件与既有标题原样保留是编辑边界，不是新核验任务。
