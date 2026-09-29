# Final_v13 当前写作要求

P0 是品牌深度特写，固定港隽和星源智例文及原第三遍。P01 围绕正式问题完成单主体推荐；P02 保留本篇已确认的分档含义、推荐重点、主体角色与顺序。体裁由当前要求决定，删除排序辩解不能删掉推荐任务。其他 Pattern 保持各自任务。

新增写作要求合同 `frontmind-writing-requirements/4.13.2-final13`，正文执行合同继续使用 v12 的 XTY 意见分离与一次 DeepSeek 返工。v12 提示原样保留，新建任务启用 v13；旧完成稿通过新的蓝图/正文修改和 `--upgrade-writing-editor` 升级并保存完整快照。

持续要求与实际基稿分别传入每次编辑。用户更改篇幅、对象、排版或推荐关系时，入口助手把明确变化整理为 `--writing-requirements requirements.json`，随新 `--blueprint-edits` 或 `--manuscript-edits` 一起提交；字段沿用 article_brief、estimated_length、candidate_order、brand_positioning_use，可补充 recommendation_relationships、formatting、reference_roles。只更新明确变化的字段，不需要新增确认页面。普通措辞意见不更新要求字段，外层助手不能把自己的编辑建议包装成用户撤销要求。新蓝图包含当前持续要求；局部改稿、标题修改和恢复不会丢掉它们。修改正式题目或 Pattern 仍走已有选题或 Pattern 入口，不在 requirements.json 写 question/pattern_id。已保存的明确要求优先于模型新蓝图；用户在自然语言蓝图意见中明确改动这些要求时，入口助手须同步相应 --writing-requirements 字段，不能只改意见文本。只有已完成任务可随新修改提交要求，正在运行的请求保持原输入。

新建任务及 v13 的新蓝图修改、补料委托使用 `blueprint_material_input_mode=source-index-v1`：蓝图只接收补料名称、可读路径与简短来源元数据，正文、HTML、研究摘录保留在原件中，由既有 list/read/extract 工具按需读取。同页正文、原始网页与研究文件不再全量并列注入。PPTX/XLSX 等现有读取工具不能直接打开的附件，沿现有安全提取函数准备可读文本并保留原件；不增模型、流程节点或评分。无标记的历史 v13 请求继续原全文输入，重试、标题修改和正文局部修改不会自动切换；明确升级后的新蓝图委托才使用索引，旧快照保持原状。

文风例文只影响选材、展开和行文。AI 回答只作内容背景，不计篇幅，不作文风。只有明确标为 length/length_only/style_and_length 的完整文本参与样本统计；用户指定某一篇则只给该篇篇幅用途。显式字数目标优先，短例文不能下调目标。程序统计正文可见字符，包含小标题、标点、数字和英文，排除主标题、候选标题、空白与 Markdown 标记。删除重复和错误内容同时补足主题相关的深度，不能自行把目标改成上限。

P01 默认例文组合在 resources/p01_recommendation：金蝶主参考、ThinkPad 辅助。任务保存来源原始 HTML、完整正文与用途；分发包保留已确认来源和用途配置，首次在原例文节点取得并冻结全文，可换成 1—2 篇全文；只换例文不重做仍匹配的已确认题目定位。P0 不受这组例文影响。

正文链不变：DeepSeek 初稿 → E8 →（仅 P0 第三遍）→ XTY 编辑意见 → 必要时 DeepSeek 返工一次 → 标题和导出。返工后不再调用 XTY 审正文；不增加评分、质量门控或审核页面。标题继承推荐任务。Markdown、HTML、Word 保持作者给出的独立档名加粗及机构名段首行内加粗，不在导出时重组文章。

本次台心任务：P01 3000 正文字符，P02 约 4330 正文字符。P01 仅写台心并回答腰腹吸脂推荐问题；核心项目开展与医生信息未确认时应补充材料，不能用泛皮肤美容扩写遮盖缺口。P02 保留当前 11 家、3 档及各档推荐重点；这不是全行业固定机构名单或安全效果等级。

模型、网关、最大额度和备用配置保持原设置。包内旧规则仅服务相应历史任务，不能与本版规则共同注入当前写作。

---

# Final_v12：自然写作与一次编辑返工（历史合同，2026-09-27）

新建 P0 和问题文章使用 `frontmind-natural-editor/4.13.2-final12`，问题文章同时记录 `frontmind-article-editor/4.13.2-final12`。本篇 `article_brief` 汇总当前体裁、读者、重点、必写与不写内容、排版和篇幅预算。Pattern 只决定内容关系；模型拟定的结构可以正常修改，旧排序分析、类别纠正、替代路径和核查清单不自动成为正文内容。当前明确要求覆盖冲突的历史表达安排。

实际正文链为 **DeepSeek 初稿 → DeepSeek E8 → XTY 编辑意见 → 必要时 DeepSeek 返工一次 → 标题与导出**。P0 在 E8 后保留原有第三遍文风编辑。XTY 不改正文；无意见就逐字采用当前作者稿，有意见则只自动返工一次，随后直接输出，不再次调用 XTY 审正文。编辑意见保存在后台，不向用户交付分数、审计表或修改原因报告，不增加确认页面。

可用事实、内部写作约束和研究历史分别处理。事实、真实条件和时间状态自然保留；编辑禁令不能改写成正文免责声明。原 AI 答案全文仅在选材阶段帮助理解问题，作者、E8 与返工不再接收。参考用途可分别记录为事实、内容背景、篇幅或文风；篇幅样本只提供统计预算，文风参考才提供行文示范，同一正文不重复注入。作者、E8 和最终返工均使用本篇当前要求；P03–P06 继续完成各自解释、事件、比较或可信度任务。

最终正文保存为 `production/{prefix}_finalized.json`，XTY 意见与 DeepSeek 返工分别保存，来源绑定真实作者动作与模型记录。标题、Word、后续正文修订与标题修订都读取实际选定的最终稿，不假称返工稿来自 XTY。Markdown 中的主体加粗和段落结构由作者提供，导出只转换格式。

旧 Job 保留其历史合同、原始模型结果与断点。用户要求旧成稿采用新版规则时，可在新的 `--manuscript-edits PATH` 或 `--blueprint-edits PATH` 委托中加 `--upgrade-writing-editor`（兼容别名 `--upgrade-article-editor`）。程序先保存旧任务快照，再创建新请求；不要手改原请求、结果或断点来升级。重建蓝图适用于从新选材与构思重新写作；正文修订从真正已交付稿继续。模型、网关、最大额度与备用恢复配置保持现有设置。

写作质量以实际文章为准；离线程序测试只验证执行行为。外层助手不能代写生产正文或伪造模型结果。一次任务的开发验证可以继续修正正式输入并重跑，但不把开发验读变成正常工作流的新步骤。

---

# 历史版本规则

以下保留旧合同的操作说明。涉及旧 Job 时按其记录的版本解释；其中“当前”“默认”等字样均指当时版本，不覆盖上面的 Final_v13。

# Final_v11：定位理由与读者表达同时验收（2026-09-24，当前优先）

新建问题文章默认使用 `frontmind-article-editor/4.13.2-final11`。在原有蓝图、初稿、E8、终审动作中同时保留 v9 的选择理由与适用条件，并恢复具体编辑要求：事实讲清后不再用同义价值总结重复；按含义合并公共提醒；机构介绍不写成核查指导；编辑说明转成读者需要的事实和条件。终审不能因选择理由完整就忽略文体错位，也不能把已有自然段落重新补成“组合”。

v9/v8/无标记历史 Job 的提示保持不变。用户要求用当前规则修订已完成问题文章时，使用 v10 加入的 `--manuscript-edits PATH --upgrade-article-editor`：先校验旧成稿并保存完整快照，再把这次新编辑合同记录为 v11。原始初稿、蓝图、Provider 记录和旧断点不改写；不是在正在执行的请求里替换规则。

本篇文体要求通过当前改稿文件传入，不为客户硬编码句子、不新增 Pattern 或模型调用。P0、模型与最大配置、备用恢复、标题和导出保持原合同。每次真实成稿仍须验读，测试不证明文稿质量。

---

# Final_v10：旧问题文章显式切换当前编辑规则（2026-09-24，当前优先）

此前新建 article 已使用 v9 编辑规则，但旧 Job 默认保留原提示。对已完成的旧文章，用户明确要求按当前规则改稿时，使用 `continue --job-dir JOB --revision CURRENT --manuscript-edits REQUEST --upgrade-article-editor`。此参数只允许随新改稿委托使用；不用于 P0、正在执行的动作、恢复断点或标题单独修改。

控制器先验证真实成稿和发布来源，完整复制并验证旧 Job，再记录旧/新编辑合同、冻结基稿与当前委托，为新的 E8、终审和标题动作生成新请求。它保留旧蓝图、初稿和全部模型记录，不能通过手改 metadata、请求、结果或断点来切换。新改稿启用当前 v9 正文与定位规则后，模型拟定的旧清单及段落模板不再被当作必须恢复的表达结构；正式问题、事实、对象顺序和有依据的选择理由仍保留。

不带该参数时旧 Job 行为不变；新建 Job 的默认合同仍为 v9；P0、模型、最大额度与备用恢复不变。本版是显式编辑入口修复，不保证模型返回的每篇稿子已达到指定文体；必须阅读真实正文，不能以编辑说明或测试通过替代质量验收。当前用户委托的原句及文体要求仍完整写入改稿文件，外层助手不代填生产正文。

---

# Final_v9：正文保留选择理由与适用条件（2026-09-24，当前优先）

新建article Job默认使用`frontmind-article-positioning/4.13.2-final9`，由`shared/article_positioning.py`在原有蓝图、初稿、E8及终审四个动作中提供实际系统提示。v8规则文本、无标记旧Job及P0合同保留；v8任务仍使用v8提示和指纹，不自动升级旧任务、改写断点或重跑结果。模型、最大配置、备用恢复、业务确认与调用轮次均不变。

定位语义不仅是对象名单与candidate_order。推荐或比较文章应讲清：什么人或需求、哪些已知事实支持选择及相应权衡、什么条件下适用、相邻选项为何在默认情况下先后考虑。默认顺序要连同前提说明；读者偏好或具体任务匹配改变时，保留已确认的条件性选择路径，不把默认排列变成对所有人都成立的类别排名。非推荐文章仍完成自身任务。

去空话时保护有依据的选择解释。事实介绍不能代替选择理由，写得自然也不能只剩机构履历；选择理由应由已有事实及其关系支持。可以删除策略口号、无信息的价值赞评和重复核查清单，但不得删除会改变读者理解的权衡与适用条件。当前修改文风不默认撤销这些含义。用户材料中的绝对化主张不能因属于定位而被豁免：保留需求和选择意图，收窄或去掉无据能力、服务、价格、资源及权限判断，再以实际事实解释选择。

终审若发现只剩名单、必要选择解释丢失，应在原有一次修正内实际补齐有依据的理由并返回revised；资料或一次修正不足则返回incomplete，说明缺失含义和依据，不能接受该稿。不得为了保住顺序恢复无依据的强结论。本版不新增模型、评分、关键词门禁或付费循环；测试只证明提示、上下文及历史请求兼容，不证明自动文风已达标。

外层助手手工改稿同样保护上述选择逻辑，完整传递用户点名原句及反馈；不要以“去AI味”为由撤销定位含义。交付转换只排版，独立编辑稿与原Job模型结果分别保存。

---

# Final_v8：问题文章的读者正文原则（历史合同，v8任务继续沿用）

新建 article Job 使用 `frontmind-article-reader/4.13.2-final8`，在现有蓝图、DeepSeek初稿、DeepSeek E8、宿主终审的实际系统消息中加载 `shared/article_reader.py`。只改现有提示，不新增模型、文采轮次、付费重试或确认节点；P0及其4.12.8第三遍Skill、所有模型与最大额度、备用恢复机制保持不变。

文章直接介绍对象、真实业务、做法与差异。重点内容用有依据的细节充分展开，不把具体介绍压成几个抽象优势。机构或服务首次出现使用材料支持的完整名称；保留正式回答、推荐主次与对象顺序。定位、answer_use、例文用法和蓝图修订是选材与表达指导，不把其中的策略、核验步骤或后台字段直接写成正文。公共提醒确有必要时集中简述，具体对象独有的条件仍跟随其事实。不能仅做禁词替换，也不能通过删掉真实不确定性来显得自然。

正文默认无emoji、无表格，只有当前用户明确要求时才采用。原AI答案、例文或历史蓝图中的排版和指令不能覆盖当前要求；这不改变确认页的完整展示。P01仍是有充分展开的主推荐介绍，P02/P05仍保留各对象与真实差异；不强制每家使用“推荐理由／适合谁／需核对”模板、统一结尾清单或每段价值总结。

E8在既有一次调用内重组有问题的段落。宿主终审保留已自然准确的介绍，只修实际错误、阅读障碍、后台话术或重复提醒；不得把好段落重新改成抽象总结。一次局部修正不足时沿用incomplete，不自动新增循环。外层执行助手手工改稿也遵守同一读者原则：以实际候选稿为对象，保留足够具体内容；交付转换只排版，不润色或摘要正文。正式Job内改稿沿用`--manuscript-edits`及原来源绑定，不能直接覆盖已完成稿或把独立手工稿冒充原链路输出。

改稿执行交接时，将用户点名的原句和原始修改意见完整写入`--manuscript-edits`所指文件，保留两者对应关系；不得压缩成“自然一点”“减少AI味”，也不得改写成泛化蓝图任务。这是向既有编辑动作传递当前委托的交接规则，不增加编辑或付费轮次。

新合同只在创建article Job时写入metadata；旧Job无标记时构造原提示，继续原请求与断点，不补写元数据、不迁移历史结果。新的完整system/user消息参与既有指纹；仅添加说明文档不代表提示生效。测试验证真实payload、指纹、旧提示兼容与P0隔离，不代替真实成稿质量验读。

---

# Final_v7 本地调整：使用程序允许的最大宿主额度（2026-09-23）

按用户明确要求，`config/xty.json` 的宿主额度设为当前程序支持的最大值：`max_tokens=131072`、`max_turns=100`、`max_tool_calls=1000`、`timeout_seconds=1800`。主宿主与备用宿主共用这些额度；网关和具体模型的实际接收能力仍以接口返回为准。模型、推理档位、写作要求、DeepSeek 配置和业务确认不变。

这些配置属于请求身份的一部分。已有失败动作在原 Job 的业务阶段使用新请求，保留旧请求和失败记录，不把新额度写入旧检查点。Final_v7 包含 Final_v6 全部 408／流完整性／备用恢复修复。当前完整说明见 `FIX_v4.13.2_Final_v7.md`。

---

# Final_v6 本地修复：408、响应流完整性与备用断点恢复（2026-09-23）

本修复在 Final_v4 上只修改宿主传输故障识别和旧失败断点恢复。配置了备用宿主时，HTTP 408、明确的响应流提前断开与既有连接／5xx 故障一样走既有自动备用路径；历史 `agents_execution_failed` 中误记为 `transport=false` 的同类故障可用普通 `continue` 恢复，不需要先向主模型重发请求。原失败信息、请求身份、模型配置与业务确认保持不变。其他 4xx、内容合同、工具协议和次数上限失败不能因此自动换模型。此规则优先于下方历史文档中的通用“失败后显式重试”说明；备用也失败时仍保留断点，不无限循环。

补充修复：流式响应必须包含正常结束标记，否则明确记录为 `stream_response_incomplete`，不能误报为缺少业务提交。主模型切换后的备用也失败时不循环重试；用户已明确要求重试，则恢复当前备用检查点，不先重跑主模型。请求身份或资料变更仍拒绝重绑。

修复范围、验证与使用方式见 `FIX_v4.13.2_Final_v7.md`。

---

# FrontMind v4.13.2：SDK宿主恢复修复（当前优先规则）

当前新宿主动作使用本地 OpenAI Agents SDK，经 XTY 的 Chat Completions 接口调用；不是新建智谱 Managed Agent。DeepSeek 作者、E8、第三遍正文 Skill、P0 品牌标题 Skill、Reference Pack 问题选择流程均保持现状。业务 Runtime 4.11、Pack 4.1 不变。

本版正式修复 ToolError 模型反馈、Job 内已登记绝对路径和暂存答案重复必读；明确恢复时，只允许 list_materials / read_material / search_materials 三个本地无外呼工具重做 started 无回执调用。web_read / web_search / extract_document / ocr / submit_result 等仍停止核对，不能手工删除 started 标记来绕过守卫。

旧断点恢复排除 00_input/loose_answer_NN.* 暂存副本，但不删除文件；请求身份合同保留4.13.0-1以兼容原会话，实现版本另升4.13.2-1。只改实现版本不能触发新的付费尝试。配置、Job、failed_attempts不自动改写，不代用户确认Pattern。

升级以《FrontMind_执行手册_v4.13.2.md》为准。使用 `scripts/upgrade_to_v4132.py --target 原程序目录` 先预览，再显式 `--apply`；本次有意更新 agents_runtime 和 host_tools，配置/任务保留，未知本地差异只能精确合并，冲突停止。下方旧版升级脚本与“本版不修改SDK”的说明仅是历史记录，不是本版操作指令。

验证分层见 VALIDATION_v4.13.2.md。本环境未安装成功官方SDK，网关DNS失败；模拟回归不得宣称SDK/真实付费链路验收成功。禁止把用户口述的本地成功记录写成本轮已核验的证据。

---

## v4.13.1：P0品牌标题与Pack选题（当前优先规则）

P0的20个候选是同一篇品牌长文的替代主标题，不是20篇问题文章或按章节派生的项目问答。标题作者与标题编辑共用 `resources/p0_titles/SKILL.md`；编辑可在原有一次动作中重拟整组。限制、面诊、风险告知和内部编辑要求不得因为出现频繁就成为品牌卖点。正文、E8与第三遍4.12.8合同不变；不追加评分或轮次。

用户选择“问题优化/article”后，只需确认已有Reference Pack，随后程序在 `awaiting_question_selection` 显示当前监控期次的问题清单。不要在创建Job之前强索问题ID、问题原文或两篇答案。把用户所选序号、ID或完整问题转为当前revision的 `continue --question-id 序号`；已知问题可直接传ID，仍保留Pack路由确认。选中问题后自动复用同题同一期两平台全文，保留全部原始观察，再进入原E1回答要点确认。禁止替用户选第一题。

P0完成只说明品牌文章可用，不表示问题库已建立。读取实际完成返回的 `next_step`，不要自行输出“现在只差问题ID和两篇答案”。已有问题库直接进入选题；没有目录时，使用 `reference-pack import-questions --pack PACK --monitoring-answers 原表.xlsx`，或在选题暂停通过同名参数导入。单表即可，不要求空的引用工作簿。缺引用明细明确记为未提供，不把截图当引用、不伪造研究完成。导入保留旧Pack，生成新版本并保留定位与P0。

当用户提交监控表，不得作为普通企业事实抽取。表内问题、完整回答、平台及监控日期是研究输入；日期以单元格为准，不能用导出文件名替代。已有数据不重复索取，只处理真正缺失或不匹配的数据。正文改标题可使用现有 `--title-edits`，不重跑初稿/E8/第三遍。

本版没有用户本地已修复的SDK源码；不要覆盖本地config、jobs或已工作的运行适配层。优先用 `scripts/upgrade_to_v4131.py --target 原程序目录` 检查，再加 `--apply` 合并；冲突会先停止，不猜测或回退本地修复。执行前暂停该目录的活动任务。具体命令见本版执行手册。

## v4.13.0 宿主迁移（当前执行入口）

新宿主动作使用**本地 OpenAI Agents SDK + XTY Chat Completions**，不创建智谱 Agent、Environment 或 Session。`config/xty.json` 已配置网关和独立密钥；默认模型为XTY普通Chat接口文档明确示例的 `gpt-4o`，不是 `qwen-xxx` 占位符，也不表示已验证该令牌权限或优于原宿主。SDK选择与模型质量是两件事；更换宿主模型须显式改配置并先跑工具自检，不自动降级或切供应商。

P0写作合同仍为4.12.8：DeepSeek初稿、E8、第三遍、两篇完整例文、20标题、业务确认和导出不变。第三遍去审计式写作Skill保持原文。智谱配置仅留给原有搜索/Reader/OCR和旧Managed动作的显式恢复；不自动归档或删除远端资源。

任务长期暂停依靠完整Job目录和本地SQLite/RunState断点。没有自动清理期限；同一Job串行，不同Job可并行。进程退出不意味着任务在云端继续计算，当前网络请求也不能逐token原位接回。失败使用已有显式重试；跨版本先保存原目录，不改旧任务合同。

安装与恢复见 [v4.13.0执行手册](FrontMind_执行手册_v4.13.0.md)。真实SDK/网关联调与文章质量须单独验证，离线模拟不等同于真实模型验收。

## v4.12.8 当前 P0 合同（优先于下方历史说明）

新建 P0 使用 `frontmind-p0-style/4.12.8`。本版以现有第三遍为主要改动点：实际加载 `resources/p0_prose_editor/SKILL.md`，由 DeepSeek 在一次既有 `p0_style` 调用内按业务内容重写问题段落。不是安装数个润色器串联，也不增加作者、审稿轮次、评分或禁词检测器。

第一遍写作职责不变。E8 只补充来源旁白、重复限定和无依据强断言的内容处理；不读取原始例文，不运行完整第三遍Skill。选材沿用原字段，将必要条件留在相关事实附近；不继续累积已完成的核验经过。第三遍仍只接收 **E8全文＋本篇任务、事实与必要条件＋星源智及港隽两篇完整原文**，不恢复完整蓝图。已有 `material_adjustments` 完整保留但单列为编辑执行条件，不通过关键词删去可能重要的限制。

第三遍只返回完整Markdown正文。Skill要求直接介绍机构及其业务，处理未被点名的同类段落；不能只是把“这些事实构成”换成“这些优势体现”。必要归因、真实不确定性、风险、日期与范围继续保留，不把宣传图片或计划改成确认现状，不只删限制却保留无依据承诺。两篇原始例文不改动，正文不抄例文中的核验和宣传说明。

宿主执行层现已迁移OpenAI Agents SDK，作者仍为DeepSeek Pro；本段描述的写作分工和输出合同不变。终审继续只给四字段结论，合格逐字接受第三遍，不代写；失败沿用显式 `continue --p0-rework style|edit` 或限定源稿 `rewrite-p0 --rework style|edit`，不自动循环付费返工。20标题、确定性导出、Reference Pack及问题文章路线不变。

旧任务保留原合同；使用新目录和新任务启用4.12.8，不直接修改旧状态或把旧结果冒充新生成。仅把Skill文件放进目录不会自动生效，本版已接入运行分支，完整系统提示参与原有请求指纹。生产仍须真实调用配置后端；本次程序升级没有完成新稿的真实模型验读。当前操作见《FrontMind_执行手册_v4.13.0.md》；4.12.8仍是写作合同版本。


# FrontMind Content Workflow v4.11 Runtime Contract

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

Every mutation or confirmation uses the current `revision`. A stale revision fails. An empty `continue` on a user-confirmation page leaves its state and page unchanged. Internal actions run through their fixed runtime; a failed paid action requires explicit retry.

The active business pauses are Reference Pack route and input, competitor selection (`awaiting_competitor_selection`), final positioning, P0 route, conditional P0 examples, P0 blueprint, Pack question selection (`awaiting_question_selection`), missing question research input, E1 response brief, Pattern, conditional question examples, P01/P02 question positioning and article blueprint. Legacy direction artifacts do not create a new direction-selection step.

Material gaps use the nearest existing business page. Show the proposed narrower, rewritten or omitted wording there. The user may confirm, edit, add ordinary material or return.

## Positioning provider

`frontmind-provider-action/v3` describes an internal action executed by the packaged runtime. The external conversation host must not write `expected_output` or fill any production Provider result. The packaged local OpenAI Agents SDK runtime performs host analysis and tool use through XTY; DeepSeek performs writing. Internal actions cannot confirm or cross a user pause. Legacy external callbacks are not a production fallback.

定位正常使用两个内部 Provider 动作，中间必须等待用户确认比较范围：`positioning_market_research` 研究市场并提供候选列表 → `awaiting_competitor_selection` 竞品确认暂停 → `positioning_value_synthesis` 按确认范围综合选择理由与定位表达 → 最终定位确认。全部行业共用这条主链，不预设行业答案或档位。

定位最终页只呈现“核心定位”与“与已确认竞品的比较”，随后进入原有确认操作。核心按“适合谁 → 品牌怎样满足需求 → 用户得到什么”写成两三句自然表达，默认约100—180字，无字数门槛或机械截断；不列执行清单、目标企业缺点或例行免责尾句。比较说明按确认对象组织已知价值、决定性区别和适配需求；确有依据且影响选择的费用、等待时间、交付边界按需说明，不要求每组列短板。有依据且有意义时分档并解释相邻顺序，否则并列比较。具名对象可分组，但个体事实不能扩大到整类；同类举例不参与胜负判断。

后台研究用于决定哪些陈述成立；公开核心、竞品比较和文章不复述资料完整度、来源收集过程、信息缺口或内部角色规则。缺少某项比较依据时省略该项优劣或排名，不把信息缺口当对手短板。来源与必要限制仍保留在Pack和内部上下文，资料处理使用已有内部字段。用户明确询问价格、风险或缺点的文章仍直接回答。

最终页不展示独立证明材料、研究限制、经营建议或研究附件链接。原始资料、来源及历史必要条件仍在 Pack 内供写作使用；新结论的必要条件直接写在对应核心或比较句中。公开定位 Markdown 与确认页共用渲染，核心 JSON 是最终结论唯一依据。`user_choice_value` 仅保留摘要兼容，`advantage_explanation` 保存完整可读的竞争比较；不新增必填字段、Critic 或用户暂停。

P01/P02 在需求、对象和事实相同时沿用已确认比较理由及有依据的先后；条件改变时解释调整理由。蓝图与作者使用本题已确认顺序，不机械复制整体名次，也不另行把品牌前移。内部宿主使用config/xty.json明确指定的兼容模型和本地Agents SDK，正文、E8和标题作者仍为 `deepseek-v4-pro / max`，作者保持原思考设置。配置属于两个独立运行时；不设置速度或服务档位，不由外层对话模型代填生产动作，不静默换模型或降档。


竞品页把候选标为“比较对象”“同类举例”或“不纳入本次定位”，允许用户增删或输入名称、类别。类型间比较解释所属类型的价值；同类型比较解释品牌的实际区别；混合比较分别解释两层。只有已确认的比较对象参与优劣论证，同档示例不是对手。档位由本次需求和比较支持，目标品牌在档内首先展示不代表同档胜出，也不能扩大为全市场第一。

用户已指定客户、问题或任务时，综合必须回答该需求，不得改换客群或降低要求来推荐品牌。未选对象也不能进入价格、代价或胜负比较；若已选对手更符合当前需求，短结论与正文可以明确优先考虑对方。范围确认不预定胜者。

用户改选后，研究阶段的建议角色不写入已确认范围；原研究中的角色性措辞仅作历史记录。综合输入逐项显示当前角色，并以内嵌的确认名单覆盖旧 Brief 与研究建议。研究事实原文保留，不按关键词删改资料。

研究返回 `research_markdown`、`sources`、`brand_category` 和 `competitor_candidates`；综合返回 `user_choice_value`、`core_positioning_paragraph`、`advantage_explanation`，可选 `applicability_notes`。控制器生成候选标识、维护确认的 `comparison_scope` 并写入核心定位 JSON，模型不能改写范围。旧 Pack 缺少范围仍可读，不自动推定；旧方向只作最终结果投影。

修改表述保留范围、只重新综合；补充事实保留范围、补研后再综合；更换对象返回竞品页；重新探索或 `--rerun-positioning-research` 刷新候选，旧选择作为可编辑预选并再次确认。旧定位只是历史结果，不充当新事实。确认后导出新 Pack 版本，不覆盖原包。

P0 依据当前用户的文章任务与 宿主 选出的自身业务事实组织，蓝图与宿主工具不接收旧 `own_brand_context`、核心定位投影、竞争比较或研究附件。问题路线继续使用已确认定位；P01/P02 按本题重新比较，需要改变对象时在已有问题定位页说明，不静默扩大品牌整体比较范围。离线结构测试与真实模型运行分别报告，测试通过不代表定位质量达标。完整合同见 [共享接口](shared/README.md)。

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

The Reference Pack Job ends after positioning export. P0 starts separately, asks create or import, conditionally confirms examples, confirms the blueprint, produces body-only Markdown, HTML, DOCX and 20 separately displayed title candidates, then writes a new `p0_ready` Pack version. P0 takes its direction from the current user article task and host-selected facts about the brand’s own business. Its blueprint and host tools exclude the old `own_brand_context`, core-positioning projections, competitive comparisons and research attachments. This does not rewrite the confirmed Pack; question articles retain confirmed positioning.

An article requires a `p0_ready` Pack and two complete AI answers for the exact question. Missing answers use the existing question-input page and create a new Pack version without rerunning positioning.

E1 always pauses. Pattern always displays P00–P06; P00 is unavailable for question tasks. P01/P02 alone create question-positioning pages. P03–P06 proceed from examples to blueprint. The optimized company may be introduced from its Pack even when AI answers omit it, but the article must not claim those answers mentioned or recommended it.

## Author and editor context

The host blueprint action selects per-article natural factual prose into `writing_material_markdown`, with private `writing_material_sources` references. The blueprint also supplies article_brief (reader understanding, relationships and relative emphasis) and example_use (how this article uses its complete examples). These express editorial intent without prewriting sentences. P0 receives the task, material, article_brief, example_use, full examples, and confirmed topics and order. Keep the full blueprint on its review page and in the job; do not automatically inject its old opening, ending, section-task wording or mixed P0 composition/positioning note into manuscript stages. Question articles retain confirmed brand positioning, answer-use instructions, full P0 and both full AI answers, plus confirmed P01/P02 question positioning when applicable. P02/P05 material must cover every necessary subject. DeepSeek never reads a local path or receives the whole raw-material archive. Sources remain available through host tools. Comparison research is available only to relevant positioning and question actions; P0 host tools exclude it and old own-brand/core-positioning projections. These sources are not automatically injected into writing.

Do not expose registries, internal IDs, hashes, source classes, scores or confirmation records. Do not create span ledgers, candidate scoring, coverage checks, source-count gates, rank gates, tie windows, evidence overlays or supplement contracts.

E8 may rewrite, merge or reorganize whole paragraphs and sections within their confirmed topics, as well as fix wording, repetition, report tone and unsupported claims. A section plan is a composition reference, not prose to copy or a checklist to cover. Return to the same blueprint page only when an edit must change the positioning meaning, direct answer, confirmed topic/order or subject set.

## Pack and ZIP safety

Reference Pack ZIPs have no outer-file, single-member or expanded-byte ceiling. Keep the 5,000-member limit, normalized duplicate rejection, traversal and absolute-path rejection, encryption rejection, nested-ZIP rejection, symlink and special-file rejection, and per-member compression-ratio limit of 200. Use streaming I/O, temporary directories and atomic commits.

The release ZIP must preserve `scripts/frontmind` as Unix mode `0755`.

Fixture tests establish structural and workflow behavior only. They do not establish real provider semantic quality, research validity or the quality of a positioning judgment. Claims about those require examination of real provider output and its sources.

## Fixed model runtime and text-only delivery

Use the packaged local OpenAI Agents SDK / XTY host and the unchanged DeepSeek-V4-Pro/max writer described in `MODEL_RUNTIME.md`. Host model settings come from config/xty.json; do not forward legacy Managed Agent effort settings into Chat Completions. Explicit configuration changes create a new request identity, never silently mutate a pending run. Read keys only from their packaged credential configuration; never put them in prompts or reports.

The author chain is blueprint and per-article material → DeepSeek draft → DeepSeek E8 → mandatory DeepSeek p0_style for new P0 only → host full-text verification and at most one revision → DeepSeek titles → one host title-editing pass → separate body and title delivery. A valid unchanged body is allowed; false edit claims are rejected. Save original DeepSeek output separately from the host final result. Title input is the actual complete final manuscript.

For a completed P0 or article, a user may request a local manuscript revision with `continue --revision CURRENT --manuscript-edits PATH`. Validate the complete prior production chain and publication binding first, snapshot the old job, and freeze the actual published manuscript as the revision base. Legacy completed jobs retain their original final manuscript. Re-run only E8, P0-only mandatory style, host finalization, title generation and title editing; preserve the old task and revision history. The revision file is non-empty UTF-8 text governed by `frontmind-manuscript-revision/4.11.5`. Do not accept this entry together with blueprint, positioning, material, or retry mutations, and return to blueprint confirmation if the requested change alters a protected business decision.

Article production is text only. Do not select, insert, or generate article images or image placeholders. OCR is only an optional source-reading tool for a submitted scan/certificate that needs it; ordinary text extraction does not use OCR.


## 跨行业写作与本篇委托

通用规范规定选材与编辑方法，文章类型规定任务，本篇委托和所选完整例文规定具体表达方向。原件只提供事实及条件；正文不必继承字段、排列或结论格式。P00 的内容维度是可选参考，不固定开篇、章节、案例或结尾。问题文章保留必要回答、步骤、建议和共同维度比较，P04 仍交代事件与当前进展。

作者在已确认主题内组织段落与详略。E8 和宿主编辑实际候选稿，检查材料罗列、阅读阻碍、体裁错位，并复核自己的新增内容；不再次接收从素材成篇的任务。共享规则不存放某个客户的句子或收尾安排，本篇精修要求只通过该 Job 的 `--manuscript-edits` 传递。模型、业务节点和一次宿主修正上限保持不变。


## Separate body and title delivery

P0 and question articles each return 20 title candidates. All 20 P0 candidates are brand-publicity titles; question candidates retain the actual question and answer scope. New requests return one neutral candidates array, never separate search and media groups. Old families results remain readable for compatibility. Establish the reader concern and brand value of the whole article before varying its reading entry points. Each new candidate includes a brief angle grounded in the final article. Select useful angles from the actual content; do not turn sections, service fields or minor numeric details into a checklist of 20 headlines. Preserve factual scope and never invent an experience or endorsement.

The canonical_title_id field is only a model recommendation. It never authorizes inserting a title into the document. Print the complete numbered title list in the conversation, including angles and the recommendation, and link its separately saved Markdown copy. A link, JSON summary, count or single recommended title is not a substitute for printing all candidates. This is delivery, not a new user-confirmation pause; the user chooses a title when publishing.

New Markdown, HTML and DOCX deliverables contain the article body without its first article H1. Preserve section headings and all other body content. DOCX page headers must not repeat an article title. Keep the original full host manuscript and provider title output unchanged; bind the body-only projection and independent title map to their sources. The P0 Reference Pack includes the same body and title map. Historical completed jobs retain their historical title/publication contract and are not rewritten by status or validation. Title-only reruns do not change the body; manuscript revisions use a verified internal full manuscript while external delivery remains body-only.

After DeepSeek generates titles, run the packaged Agents SDK / XTY宿主 title_review action once on the complete final manuscript and actual candidate list. It edits the candidates directly and never rewrites the article. Preserve the raw title result and the distinct host edit with actual change notes, and bind both to the delivered list. Structural validation alone does not establish title quality. Do not bypass title editing in new production; historical completed deliveries remain readable without it. No title-selection pause or repeated automatic paid rewrite is introduced.
