> 历史版本手册。v4.13.0宿主以[当前手册](FrontMind_执行手册_v4.13.0.md)为准；写作合同和旧任务恢复仍保留其原版本。

# FrontMind 执行手册 v4.12.7

## 1. 本次修改范围

以用户提供的 v4.12.6 为唯一程序基线，保留宿主、作者、业务路线、三遍正常写作、两篇完整原始例文、标题及导出。原包模型凭据不修改、不在文档展示；请勿公开分发此私有包。

本版改的是实际生效的提示和拒稿返工，不只是旧提示文档。`shared/reader_editing.py` 定义新规则；`brand_stage.py`、`prose_only.py` 和 `model_runtime.py` 分发到对应模型请求。`shared/p0_rework.py` 复用现有 E8/第三遍处理明确失败，不增加写作或审核阶段。

## 2. 新任务与旧任务

`./scripts/frontmind preflight` 检查运行环境，无参数 `./scripts/frontmind` 展示原有四个业务选择。P0 正常任务仍经 Reference Pack 路由与原业务确认；详见 `START_HERE.md`。

新 P0 默认 `frontmind-p0-style/4.12.7`。旧 v4.12.5、v4.12.6 任务保留既有请求、结果合同及原调用记录，不直接修改其 metadata 来升级。使用新写法应在新目录创建新任务；旧 v4.12.6 可以使用本版四字段拒稿恢复修复，但未返工的历史请求不变。

## 3. 写作分工

| 阶段 | 实际职责 |
|---|---|
| 选材与蓝图 | 按本篇目标选事实，写清一两句文章主次；区分事实、必要条件与内部写作要求，不把材料变成全文目录。 |
| 初稿 | 直接写完整文章；取舍、详略、段落衔接和自然表达从第一遍承担。 |
| E8 | 核对事实与事实之间的关系，同时处理主次失衡、重复、清单式铺陈，必要时重组整段整节。 |
| 第三遍 | 在现有事实和任务下完成全文。正常输入为 E8 全文、本篇任务与事实条件、两篇完整原始例文；返回纯 Markdown。 |
| 成稿验读 | 完整阅读唯一第三遍候选，判断是否能直接交付。不代写、不打分、不要求长篇审稿报告。 |

第三遍事实组只新增已确认的 `article_brief`，不传完整蓝图、章节脚本、整库原料或例文分析指南。两篇例文保留原字节，参考业务展开与详略，不模仿其中的对外表述、口径说明或核验旁白。

正文直接介绍业务。内部宣传话术不是要被保留的品牌事实，删后也不以空泛“理念”“原则”补位；但必要的范围、状态、统计定义、医疗评估等条件必须保留。不得通过编造客户故事、引用、结果、资源保障关系来让文章生动。标准不是“越短越好”或“禁用某些词”。

终审仍是 `outcome / article_markdown / editorial_notes / reason` 四字段：accepted 逐字接受候选、notes 为空、reason 为空；incomplete 或需业务重确认时正文为空，reason 简短指出位置、原句与问题。不得输出 revised 或旧 brand_review 评分。

## 4. 拒稿后的显式返工

仅当前 P0 `running_p0_production`、pending `p0_finalize`、错误 `host_incomplete` 可以走以下入口。先查看任务状态与 revision，再选择一个路径。

### 表达、段落组织、重复、内部话术

```bash
./scripts/frontmind continue --job-dir /absolute/path/jobs/p0 --revision N --p0-rework style
```

冻结被拒绝的第三遍全文和简短问题说明，作为第三遍修订基稿；事实仍以已确认材料为准。只重做第三遍及其后的终审、标题和导出，不重复初稿和 E8。显式返工的基稿会如实标记为“E8 之后的返工基稿”，不冒称新 E8，也不把拒稿内容当新事实。

### 现有材料内的事实错误、遗漏或内容关系问题

```bash
./scripts/frontmind continue --job-dir /absolute/path/jobs/p0 --revision N --p0-rework edit
```

从现有 E8 编辑动作修订冻结候选，再用新的 E8 做第三遍。蓝图、材料、初稿不变。没有依据的部分不能由返工补造；发现需要新证据或改变业务决定时应停止并转上游。

### 确实需要补料或改变已确认决定

沿用既有 `continue --blueprint-edits ...` 或 `continue --blueprint-supplement ...` 路由及当前 revision，保留业务确认。v4.12.6/4.12.7 的合法四字段 incomplete 不再被旧 `brand_review` 要求阻断；更旧合同仍按其原审核字段校验。

### 状态、缓存与存档

返工保留 `production/quality_rejections/` 下的原审结、原候选和冻结输入，校验文件指纹与上游绑定。每次明确返工给相关动作分配新的 epoch，避免命中旧 incomplete 缓存；与返工无关的上游结果不重做。E8 与第三遍各自保存输入指针，后续第三遍返工不会改写前次 E8 的输入历史。上游业务改变会清理活动返工指针，历史记录不删除。

普通 continue 不隐式启动返工；网络重试使用原 `--retry-current-action`，不等同于修正文稿。返工不与重试、补料、蓝图修改或其他继续命令混用。新问题仍不能通过时停止，不自动付费循环。

## 5. 限定源稿入口

新的源稿修订：

```bash
./scripts/frontmind rewrite-p0 --live   --source /absolute/path/source.md   --brand "本篇品牌"   --requirements-file /absolute/path/requirements.md   --run-dir /absolute/path/runs/new_p0_v4.12.7
```

拒稿修订：重复同一命令的同一来源、品牌、要求和 run-dir，加 `--rework style` 或 `--rework edit`。此路线不使用普通 `continue --p0-rework`，因为它不承诺普通 Reference Pack 生产状态。保留原 source/request 指纹；更换原件或要求请建新目录。所有阶段仍经原模型调用或已验证的真实调用缓存，不读取产物就冒称已调用。

成功导出正文与独立标题；正文只确定性去掉首个 H1，终审不能重写正文。视觉验收与正式资料包更新不因源稿导出而自动完成。

## 6. 验证与发布

```bash
python -B -m unittest discover -s scripts/tests_v411 -t . -v
python -B scripts/validate_workflow.py --release-projection
python -B scripts/build_release.py --output-dir /absolute/path/new_release
```

发布目录需不存在。构建器会执行完整单元测试、源目录检查、白名单投影、ZIP 完整性、解压后检查与逐文件指纹对照，并生成程序验证报告及校验和。构建器不宣称内容质量验收。

新增 `test_reader_editing_v4127.py`、`test_p0_rework_v4127.py` 等测试和 `acceptance_fixtures/p0_reader_editing_v4127/` 中的真实反例/合理正例。反例用于人工和真实输出对照，不是自动 AI 检测器。本轮没有调用付费模型生成客户新稿；程序检查通过不能等同于所有输出自然度得到保证。
