# FrontMind 16.25.1 第一阶段：定位、差异化优势与P0

输入企业名称和完整Markdown知识库ZIP。定位、优势整理及成稿文风核对使用Kimi Hosted Agents的kimi-k3.1-pro/high；P0初稿与必要的一次文风轻润色使用XTY gemini-4-argon/high。均通过HTTP，不依赖OpenAI SDK。共享Agent/Environment定义；每个项目复用分析Session，成稿文风检查另用独立文风Session，避免带入定位和知识库历史。各类Session内续查同一请求。

唯一入口是scripts/workflow.py。流程为：导入知识库 → Kimi定位建议与问题目录 → A用户选择定位 → Kimi整理优势 → C用户排序增删确认 → 三项Reference Pack → Gemini初稿 → 一次Kimi文风核对 → 无问题直接定稿／有文字问题一次Gemini轻润色 → 仅核对改动 → 本地Word渲染与Kimi逐页视觉验收。

A与C必须保存用户具体选择；已有同范围明确授权可如实记explicit_prior_choice，不反复确认。Kimi不能代用户确认。系统先总结，不让用户从空白整理。没有固定B竞品暂停。已有明确确认同类池可用confirmed-peers加文件和用户原话继承；不从知识库随意提及厂商推断确认，不自动竞研或重排。无池允许为空，第二阶段P02再按实际授权选择。

Reference Pack固定只有定位.md、核心差异化优势.md、知识库.zip。定位.md保留问题目录和已确认同类池，知识库原ZIP字节保留；不生成资料整合说明.md，不另设材料审批。第一阶段不写问题文章、不发稿；第二阶段从三项Pack承接，P0不是第二阶段的事实输入或前置门槛。

P0先简要介绍品牌，再在差异化优势章内按已确认数量和顺序逐项设独立三级标题；不是固定九项。每项讲清特点与实际用途，背景项可短，不编成果。完整例文只参考文风，不能接管结构、事实或内容主次。作者收到自然语言事实和简要委托；知识库主题及原资料实际展开，不只传路径。

只用随包frontmind-anti-defensive-writing作必要轻润色，初稿也内置六行短原则。保留事实、必要用途/版本/职责条件和已确认优势强度；删无信息自辩、假对比和重复收尾。没有问题就保留初稿。正常流程成功编辑最多一次，编辑请求只含当前稿、具体文字意见和简短反防御性原则，不重发完整知识库、所有例文或诊断Skill。编辑后仅确认原文风问题和相关上下文，不另开文风轮。

run-agent返回waiting时重新执行同一命令只续查原请求，不自动重发或创建替代Session。Kimi与Gemini失败都保留记录，不自动付费重试、换模型或伪造成功；Gemini明确获准重试才用--retry。宿主只编排本地命令与业务交互，不能把未调用Kimi的本地分析伪报为Hosted结果。

导出P0 TXT/Word/HTML及实际Gemini System/User Prompt与返回，也导出Kimi task/system/user、请求、JSON产物与公开操作事件。记录可用于复核，不导出私有思维链。Word先用本地确定性工具实际渲染PNG，再run-agent --action p0_visual_check --pages-manifest上传本次页图给Kimi high逐页判断，不能把导出当视觉通过；没有真实页图不放行。默认交互为中文和Markdown表格，JSON仅内部或显式--format json。详细命令见docs/命令顺序.md。

成稿后仅处理文风：不对照知识库、不联网查证、不核验事实口径或数字/资质/功能，不重审已确认优势。Kimi只收到当前稿、简短反防御性规则和文字意见；不附知识库或定位/优势来源材料。无文字问题直接采用Gemini初稿，有问题才一次Gemini轻润色。事实、名称、数字、条件与既有标题原样保留是编辑边界，不是新核验任务。
