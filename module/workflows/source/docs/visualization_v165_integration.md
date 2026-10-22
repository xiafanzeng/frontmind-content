# v16.5 过程展示适配

主Workflow已在Job内生成reviews/article_process.html，展示当前真实步骤、初稿、全文编辑稿、修订稿、通过的正文及各轮验读意见。它是本地结果页面，生成过程只读取已有工件，没有额外模型摘要。

## 外部可视化应用

若将本版接入完整的内容制作可视化应用，先同步完整运行源码与本版资源，并更新release.json、发行manifest及新任务版本。保留应用原有私有凭据、回环代理与来源读取保护，不能用主Workflow的model_runtime整体覆盖应用适配版本。历史任务继续使用各自冻结的包。

界面沿用原始确认和继续动作。新自然文风返工由Workflow内部推进，不使用article_fact_repair、repair_article_facts或--repair-facts。后台只投影实际阶段状态、开始结束时间、公开稿件链接与已有编辑意见；不把后台来源内容、私有路径、凭据或模型内部推理呈现给用户。

关闭run_managed.py中process_summary.py的worker启动与SummaryClient支线，停止向业务启动路径注入用于自动摘要的FRONTMIND_PROCESS_SUMMARY_CACHE。不请求GLM-5.2或其他摘要模型，也不从reasoning_text构造“思考摘要”。GET及历史读取只读取已保存记录。

需要展示执行进度时，用真实执行记录的动作名称、状态和时间；有实际工具回执才展示其完成或失败状态。写作步骤完成后显示稿件与本轮已有editorial_notes、needs_revision/comments。这里描述的是已发生的结果，无需另一个模型改写。

## 验证边界

确认创建、继续、GET和历史恢复不会启动摘要worker或摘要HTTP请求；缺少可展示记录时留空，不能编造过程。保留工具身份与时间顺序，完成状态来自Workflow实际交付结果。

用户提供的v16.3文件只是一份29文件改动包，缺少现代可视化项目的若干执行器、投影与前端依赖。本文是完整应用的接入说明，不代表已经实现、构建或部署那个外部应用。此次完整交付为Workflow ZIP及其本地过程页面。
