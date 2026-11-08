# FrontMind 第二阶段 v16.25.1

输入定位.md、核心差异化优势.md、知识库.zip，输出用户选择的一个问题的一篇正文、10个标题和20个独立信源建议。第一阶段P0不作为输入。沿用第一阶段定位、用户确认优势及同类池。

配置与分工：

| 任务 | 接口/模型 | 强度 |
|---|---|---|
| 任务分析、选材、约稿、文风检查、标题核对、媒体推荐 | Kimi Hosted Agents，kimi-k3.1-pro | high |
| 正文初稿、必要文风轻润色、10标题 | XTY Chat Completions HTTP，gemini-4-argon | high |
| 输入/统计/抓取/合同校验/导出 | 本地确定性程序 | 无模型 |

无需OpenAI SDK或OpenAI Agents SDK。config/kimi.json保存已有Key和可复用Agent/Environment；config/xty.json保留XTY配置。每篇文章的分析步骤复用同一Session；正文与标题文风检查另用独立文风Session，不带入分析阶段的知识库历史。等待或状态读取失败时原请求不重发，不用新Session掩盖错误。run-agent的实际任务Prompt、公共操作事件及JSON产物按hosted_runs记录，原始私有思维链不对外输出。

```sh
python3 scripts/workflow.py import-pack --project /path/project --pack /path/Reference_Pack.zip
python3 scripts/workflow.py screen --project /path/project
python3 scripts/workflow.py choose-question --project /path/project --question-id q000001 --period-id p000001
# 也可 add-question --text '新问题原文'；随后attach-answers或skip-answers明确暂无
python3 scripts/workflow.py attach-sources --project /path/project --file 本题信源.xlsx
python3 scripts/workflow.py select --project /path/project --article article1
python3 scripts/workflow.py show-sources --project /path/project --article article1
python3 scripts/workflow.py choose-writing --project /path/project --article article1 --category 行业排名 --pattern P01 --by user --note '用户具体选择'
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 5
# Kimi返回waiting时重复同一命令只续查，不重复提交；完成后展示任务并记录用户确认
python3 scripts/workflow.py confirm --project /path/project --article article1 --step 5 --by user --note '用户确认本篇任务'
python3 scripts/workflow.py acquire --project /path/project --article article1
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 6
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 7
python3 scripts/workflow.py confirm --project /path/project --article article1 --step 7 --by user --note '用户确认约稿'
python3 scripts/workflow.py run-writer --project /path/project --article article1 --step 8
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 8
# 无问题则初稿直接定稿；有具体问题时只执行一次以下编辑，再复核修改处
python3 scripts/workflow.py run-writer --project /path/project --article article1 --step 8 --edit-notes /path/project/articles/article1/steps/08/edit_notes.md
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 8
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 9 --phase refs
python3 scripts/workflow.py run-writer --project /path/project --article article1 --step 9
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 9 --phase edit
# 只有用户实际点名来源时保存以下偏好；例如用户已明确说抖音也要纳入
python3 scripts/workflow.py require-media --project /path/project --article article1 --source 抖音 --note '用户原话：抖音也要有'
python3 scripts/workflow.py run-agent --project /path/project --article article1 --step 10
python3 scripts/workflow.py export --project /path/project --article article1
# 渲染并逐页检查新Word，再以visual-qa记录实际结果
```

上面有条件命令不是固定轮次：初稿通过时跳过编辑两行；标题无问题不增加Gemini调用。标题核对有具体问题会保存title_edit_notes.md，由Gemini修改一次再核对。初稿或编辑API失败不自动重试；只有用户明确授权才使用--retry，保留原始失败与相同请求。一次文风轻润色后仍有实质问题时展示原句及问题，待用户新版本要求，不自动反复润色。

三类问题：行业排名、美誉舆情、产品场景。五种模式：P01单品牌推荐、P02多品牌分别介绍、P03场景说明、P04真实事件新闻、P06评价回应；只有P05点名对比被删除。P02在choose-writing增加--subject c001等，使用用户已确认同类池的本篇子集；主品牌自动在前，不固定主体数量。select不代替类型选择，泛泛确认不代替具体模式选择。任务和约稿确认保留；已有同范围明确授权可据实记录prior_authorization。

第二包实际打印媒体归并统计、全部Top20文章和自动选中的两篇完整参考及理由。题名不能伪装全文。正文参考与标题核心参考分别选择。完整例文只作为文风/构思参考，其他品牌事实不移植。

默认文字处理只用反防御性skill：一次文风检查，删除无对象辩解和重复免责，保留真实状态、数字、条件与必要范围。不加载Sepia，不做评分或固定多轮全文诊断。编辑Prompt只给当前全文、具体文字问题和简短写作意图，不重复附上完整例文、全部知识库和长篇诊断Skill。

媒体按[媒体skill](skills/frontmind-classify-media/SKILL.md)完整评估候选，按实际载体去重选20；合格不足20给实数。主表仅媒体名字、类型、比例、具体文章依据四列；企业官网等剔除，其他未入选候选保留完整TXT/CSV。已明确要求、在本题有依据且合格的抖音等渠道须纳入；不能因图文转视频自动落选。不执行发稿、不声明可购性或收录保证。

导出包括Word/TXT、10标题、媒体四列表、全部候选、剔除清单、原始信源及文章目录、Gemini逐字Prompt/返回、Kimi真实任务Prompt/JSON返回与公开操作记录。正文和媒体表Word必须使用bundled runtime渲染并逐页看过，才能称视觉验收完成。CLI的prepare只预览Prompt；submit/review手工文件仅用于明确历史导入或离线测试，不是实际云端执行记录。

离线检查：python3 -m unittest discover -s validation -v。真实Kimi协议验证与离线模拟必须分别记录，不将小型接口验证冒充整篇新写作或两阶段业务全流程验证。


Word先由本地bundled runtime实际渲染所有页PNG，生成渲染清单documents（每项含file_name、当前docx_sha256及全部rendered_pages绝对路径），再运行run-agent --step 11 --pages-manifest 清单.json，由Kimi Hosted high逐页视觉检查后记录验收。未渲染、图片不全或有实际排版问题时不标通过；本地渲染不调用文本模型。
