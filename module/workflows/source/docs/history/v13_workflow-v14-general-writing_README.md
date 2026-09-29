# FrontMind Content Workflow v4.13.2 Final_v13

P0 是品牌深度特写，固定港隽和星源智例文及原第三遍。P01 围绕正式问题完成单主体推荐；P02 保留本篇已确认的分档含义、推荐重点、主体角色与顺序。体裁由当前要求决定，删除排序辩解不能删掉推荐任务。其他 Pattern 保持各自任务。

新增写作要求合同 `frontmind-writing-requirements/4.13.2-final13`，正文执行合同继续使用 v12 的 XTY 意见分离与一次 DeepSeek 返工。v12 提示原样保留，新建任务启用 v13；旧完成稿通过新的蓝图/正文修改和 `--upgrade-writing-editor` 升级并保存完整快照。

持续要求与实际基稿分别传入每次编辑。用户更改题目、篇幅、对象、排版或推荐关系时，入口助手把明确变化整理为 `--writing-requirements requirements.json`，随新 `--blueprint-edits` 或 `--manuscript-edits` 一起提交；字段沿用 article_brief、estimated_length、candidate_order、brand_positioning_use，可补充 recommendation_relationships、formatting、reference_roles。只更新明确变化的字段，不需要新增确认页面。普通措辞意见不更新要求字段，外层助手不能把自己的编辑建议包装成用户撤销要求。新蓝图包含当前持续要求；局部改稿、标题修改和恢复不会丢掉它们。

文风例文只影响选材、展开和行文。AI 回答只作内容背景，不计篇幅，不作文风。只有明确标为 length/length_only/style_and_length 的完整文本参与样本统计；用户指定某一篇则只给该篇篇幅用途。显式字数目标优先，短例文不能下调目标。程序统计正文可见字符，包含小标题、标点、数字和英文，排除主标题、候选标题、空白与 Markdown 标记。删除重复和错误内容同时补足主题相关的深度，不能自行把目标改成上限。

P01 默认例文组合在 resources/p01_recommendation：金蝶主参考、ThinkPad 辅助。任务保存来源原始 HTML、完整正文与用途；分发包保留已确认来源和用途配置，首次在原例文节点取得并冻结全文，可换成 1—2 篇全文；只换例文不重做仍匹配的已确认题目定位。P0 不受这组例文影响。

正文链不变：DeepSeek 初稿 → E8 →（仅 P0 第三遍）→ XTY 编辑意见 → 必要时 DeepSeek 返工一次 → 标题和导出。返工后不再调用 XTY 审正文；不增加评分、质量门控或审核页面。标题继承推荐任务。Markdown、HTML、Word 保持作者给出的独立档名加粗及机构名段首行内加粗，不在导出时重组文章。

本次台心任务：P01 3000 正文字符，P02 约 4330 正文字符。P01 仅写台心并回答腰腹吸脂推荐问题；核心项目开展与医生信息未确认时应补充材料，不能用泛皮肤美容扩写遮盖缺口。P02 保留当前 11 家、3 档及各档推荐重点；这不是全行业固定机构名单或安全效果等级。

2026-09-28 经用户授权，后续 DeepSeek 调用的 reasoning_effort 由 `high` 改为 `max`；模型、网关、最大额度和备用配置保持原设置。历史请求保留当时配置。包内旧规则仅服务相应历史任务，不能与本版规则共同注入当前写作。


## 当前启动入口

当前版本是 Final_v13。解压后在程序目录运行：

```bash
./scripts/frontmind preflight
./scripts/frontmind
```

日常使用先读 [START_HERE.md](START_HERE.md) 和 [RUNBOOK.md](RUNBOOK.md)；本次修订见 [FIX_v4.13.2_Final_v13.md](FIX_v4.13.2_Final_v13.md)。新任务使用上方 v13 规则，已有任务按其保存的合同恢复；历史段落中的版本升级命令只用于对应旧版。

## 历史版本说明：仅供对应旧版恢复

以下保留 Final_v12 及更早版本说明全文。文中的“本版”“当前优先规则”“当前执行入口”“新任务自动采用”等称谓，只指该段标明的历史版本；旧流程、旧默认模型、旧验收状态不作为 Final_v13 的当前操作说明。当前入口与正文分工以上方 v13 说明为准。

<details>
<summary>展开 Final_v12 及更早版本的原始说明</summary>

# FrontMind Content Workflow v4.13.2 Final_v12

本版将写作要求集中在每篇的 `article_brief`，用实际事实组织自然文章。Pattern 决定内容关系，本篇要求决定体裁、重点、排版与篇幅。事实来源、内容背景、篇幅样本和文风例文各司其用；原 AI 回答不再自动成为新闻品宣的文风范本。

正文流程：**DeepSeek 初稿 → E8 编辑 → XTY 提意见 → 必要时 DeepSeek 自动返工一次 → 标题与 Word 导出**。P0 保留 E8 后的第三遍文风编辑。XTY 只给意见，不直接写稿；一次返工后直接交付，不再审正文。候选标题独立交付，编辑意见留在任务目录。

从包目录运行 `./scripts/frontmind` 启动。新任务自动采用 v12。继续旧任务时保留旧规则；如要对已完成稿启用本版，可使用：

```bash
./scripts/frontmind continue --job-dir JOB --revision CURRENT --blueprint-edits REQUEST.md --upgrade-writing-editor
```

上述命令保存旧任务快照，再根据本次要求重整选材与构思。仅修改现有正文时，将 `--blueprint-edits` 换为 `--manuscript-edits`；仅改标题继续使用 `--title-edits`，无需重写正文。`CURRENT` 使用任务实际 revision，`REQUEST.md` 写本次具体要求。

程序保存 XTY 意见、DeepSeek 返工和最终正文的真实来源，标题与导出读取实际最终稿。模型、网关、最大额度及备用恢复配置沿用包内现有设置；本版不增设评分、审核层或新的确认步骤。

Word 默认沿用包内字体设置；需要使用本机已有字体时，可设置 `FRONTMIND_DOCX_FONT`（例如 `Hiragino Sans GB`）。字体须实际安装，导出后应检查页面显示。

历史合同与说明继续保留，旧任务不被自动迁移。下方为历史版本记录，其中“当前”“默认”等表述仅指对应历史版本。

---

## 历史版本记录

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

# FrontMind Content Workflow v4.13.0

基于v4.12.8完整包迁移宿主运行时；写作Skill不变。业务Runtime保持4.11，Reference Pack保持4.1。本版SDK和网关实际联网验证尚未完成，详见VALIDATION_v4.13.0.md。

## v4.12.8 当前 P0 合同（优先于下方历史说明）

新建 P0 使用 `frontmind-p0-style/4.12.8`。本版以现有第三遍为主要改动点：实际加载 `resources/p0_prose_editor/SKILL.md`，由 DeepSeek 在一次既有 `p0_style` 调用内按业务内容重写问题段落。不是安装数个润色器串联，也不增加作者、审稿轮次、评分或禁词检测器。

第一遍写作职责不变。E8 只补充来源旁白、重复限定和无依据强断言的内容处理；不读取原始例文，不运行完整第三遍Skill。选材沿用原字段，将必要条件留在相关事实附近；不继续累积已完成的核验经过。第三遍仍只接收 **E8全文＋本篇任务、事实与必要条件＋星源智及港隽两篇完整原文**，不恢复完整蓝图。已有 `material_adjustments` 完整保留但单列为编辑执行条件，不通过关键词删去可能重要的限制。

第三遍只返回完整Markdown正文。Skill要求直接介绍机构及其业务，处理未被点名的同类段落；不能只是把“这些事实构成”换成“这些优势体现”。必要归因、真实不确定性、风险、日期与范围继续保留，不把宣传图片或计划改成确认现状，不只删限制却保留无依据承诺。两篇原始例文不改动，正文不抄例文中的核验和宣传说明。

宿主执行层现已迁移OpenAI Agents SDK，作者仍为DeepSeek Pro；本段描述的写作分工和输出合同不变。终审继续只给四字段结论，合格逐字接受第三遍，不代写；失败沿用显式 `continue --p0-rework style|edit` 或限定源稿 `rewrite-p0 --rework style|edit`，不自动循环付费返工。20标题、确定性导出、Reference Pack及问题文章路线不变。

旧任务保留原合同；使用新目录和新任务启用4.12.8，不直接修改旧状态或把旧结果冒充新生成。仅把Skill文件放进目录不会自动生效，本版已接入运行分支，完整系统提示参与原有请求指纹。生产仍须真实调用配置后端；本次程序升级没有完成新稿的真实模型验读。当前操作见《FrontMind_执行手册_v4.13.0.md》；4.12.8仍是写作合同版本。

## 启动

```bash
./scripts/frontmind preflight
./scripts/frontmind
```

请解压到新目录。无参数仍显示四项业务选择，不会直接创建任务或调用模型。已有Reference Pack可以正常选择使用，不需要仅为升级写作技能重新研究资料。旧Job继续履行旧合同；要启用本版，创建新的P0 Job。

## 实际执行链

按篇选材与蓝图 → DeepSeek初稿 → DeepSeek E8 → DeepSeek第三遍正文编辑 → Agents SDK宿主验读 → DeepSeek 20标题 → 标题编辑 → 确定性导出。

第三遍系统提示从 `shared/p0_prose_editor.py` 读取本地Skill正文，检查版本和资源一致性，再通过 `prose_only.role` → `model_runtime._initial_messages` 进入实际请求。Skill缺失不会静默回退旧提示。Markdown文件的研究说明与元信息不混入写作请求。

## 已有源稿的限定重写

```bash
./scripts/frontmind rewrite-p0 --live   --source /absolute/path/source.md   --brand "完整品牌名"   --requirements-file /absolute/path/requirements.md   --run-dir runs/brand_v4.12.8
```

`--live`会调用真实后端并产生费用。源稿入口只在用户提供的资料与委托范围内重写，不代替完整品牌研究，也不直接更新Reference Pack；不要把旧生成稿当成事实原件。未指定参数时仍使用包内一航样例，请为其他品牌显式指定以上参数。

终审失败后的同一任务可显式选择 `--rework style` 或 `--rework edit`，与 `--retry-current-action` 互斥。正常P0使用 `continue --job-dir ... --revision N --p0-rework style`（或edit），N为当前任务revision。这些路径保留原失败稿及真实模型记录。

## 资源与验证

`resources/p0_prose_editor/ADAPTATION.md`说明采用的方法和不采用的机械规则。`acceptance_fixtures/p0_prose_editor_v4128/`提供真实问题类型及合成反例/正例，供真实生成后的全文检查；不是声称这些文章已经由Workflow改好。

完整回归和发布检查由 `scripts/build_release.py` 执行。程序测试验证请求、传递、状态和返工，不证明实际新稿已经消除AI味。本次未调用付费API生成台心新稿，没有把人工示范或模拟回复当成真实模型效果。

包内保留原配置并增加XTY配置，包含私有凭据，请勿公开分发。更新内容见 [CHANGELOG_v4.13.0.md](CHANGELOG_v4.13.0.md)，操作见 [当前执行手册](FrontMind_执行手册_v4.13.0.md)。历史手册供相应旧合同参考。

原 AI 回答全文只在选材阶段使用；作者与编辑接收本篇要求、整理后的事实及相关文风参考。旧定位分析不再作为蓝图的默认全文输入，保留原文件供必要时读取。参考的显式 role/reference_role 会保留，length_only 只供篇幅统计；不适合本篇体裁的例文可保留原文而调整用途。

</details>
