# FrontMind v4.13.1 执行手册

本版修复品牌标题任务与Reference Pack选题衔接。写作及宿主模型配置不变，不自动发起付费修订。用户本地已修复SDK的代码未附在本轮输入，优先用下述增量方式，不用整目录覆盖工作环境。

## 1. 先更新程序，不覆盖本地修复

暂停原程序正在执行的任务。解压新包后，在新包目录执行：

```bash
python3 scripts/upgrade_to_v4131.py --target /原来的/FrontMind程序目录
python3 scripts/upgrade_to_v4131.py --target /原来的/FrontMind程序目录 --apply
```

第一条只检查并显示文件计划。第二条仅更新本版差异，不碰config、jobs、已运行的SDK专用适配文件。其他触及文件若有本地修改，会尝试基于精确上下文合并；无法唯一匹配则整个升级先停止，不覆盖、不猜测。修改前备份，写入失败回滚。合并后的源码保留本地代码不意味着本地改动已被本次测试过；更新后运行原有本地自检。增量器只支持4.13.0到4.13.1/幂等重复更新。

全新环境可以直接使用完整包，按原requirements安装。发行包内SDK专用适配文件与4.13.0相同，本轮没有用户本地补丁的副本，也不声称已合并这些未知改动。

## 2. 已完成P0，只重拟标题

正文无须重写。在原Job上读取status，使用当前revision：

```bash
./scripts/frontmind status --job-dir /原来的/jobs/taixin_p0
./scripts/frontmind continue --job-dir /原来的/jobs/taixin_p0 \
  --revision 当前revision \
  --title-edits /新包路径/customer_inputs/taixin/只重拟P0标题.md
```

这会真实付费调用标题作者与宿主标题编辑，并确定性重新导出；初稿、E8、第三遍及宿主正文验读不重跑。正常结束会产生新版本Pack，不能假定仍叫v2；以返回路径为准。20项仍独立交付，不自动把推荐标题写入正文。

若本地Job含未结束/结果不明的SDK动作，先用原恢复流程处理，不能靠改标题绕过未完成写入。

## 3. 将现有监控表加入已完成P0的Pack

先查已有目录。不要因为P0完成页没显示问题就认定Pack无数据。

```bash
./scripts/frontmind questions --input /实际/Reference_Pack_v2.zip
```

有目标期次完整数据，直接下一节。目录为空或需要补充本次表时：

```bash
./scripts/frontmind reference-pack import-questions \
  --pack /实际/最新Reference_Pack.zip \
  --monitoring-answers /新包路径/customer_inputs/taixin/东莞台心医院-正式初始-问答明细-20260830-180117.xlsx \
  --output /实际/Reference_Pack_with_questions
```

品牌列与Pack名称不一致时停止。确认为医院与科室的同一项目资料后，显式加 `--brand-alias "东莞台心医院"`，不自动跨品牌导入。

导入不调用模型，不重新定位或重写P0；保持原Pack不变，在同系列新版本内保存问题库及原有定位/P0。相同文件哈希再次导入返回已有Pack，不重复建期次。JSON/CSV原始表也支持。旧 `update-research` 可仅传答案表；仍支持答案JSON+引用表的原配对入口。

本次附表有33个正式问题、332条回答（元宝167、通义千问165）。表内监控日期全为2026-06-22，文件名20260830不是采样日期。内部q000001等按原始首次出现顺序编号；若Pack已有ID，则沿用既有ID。预览不是现成的P0-ready Pack。

初始建Pack时，监控表会被自动路由到问题库，不抽取成机构事实。如果一个旧Pack曾将同哈希表格纳入普通材料，导入后会在后续业务材料投射中排除该源，但不静默改写历史定位/P0；应另外检查旧文章是否引用了AI回答作为事实。

## 4. 从Pack选择问题，直接复用答案

```bash
./scripts/frontmind article \
  --reference-pack /上一步返回的/Reference_Pack_with_questions.zip \
  --job-dir /实际/jobs/taixin_article
```

先按页面确认使用该Pack：

```bash
./scripts/frontmind continue --job-dir /实际/jobs/taixin_article \
  --revision 当前revision --reference-pack-route use
```

程序显示当前期次完整问题清单、日期、平台和回答数。用户选序号或完整问题；运行者转成：

```bash
./scripts/frontmind continue --job-dir /实际/jobs/taixin_article \
  --revision 当前revision --question-id 所选序号
```

直接带入正式问题与同一期次两个具名平台的完整回答。默认每平台按源行顺序取第一条非空回答供现有E1/E2读取，不挑对品牌有利的样本；全部观察保留在 `inputs/question_observations.json` 和Pack问题切片，不把前两条当成全量监测统计。随后停在原E1，等用户确认回答要点与品牌认知，再进行分析。

切换历史期次：`questions --input PACK --all-periods` 查看历史问题；`questions --input PACK --period-id p000001` 查看具体期次；选题页用 `continue --question-period p000001 --revision 当前revision` 刷新列表。不跨期拼接平台，不自动采用旧一期凑足两平台。停用问题不可手填ID绕过。

没有目录时，选题页可直接 `continue --monitoring-answers 文件.xlsx --revision 当前revision` 导入，保留当前Job。只有选定问题确实缺平台、缺完整回答或身份不匹配，才进入已有的研究输入页。缺引用明细不阻止两平台答案进入，但不表示网页核验已完成。

## 5. 验证范围

回归与数据导入测试仅验证程序行为。未对用户实际Job或Reference Pack内容作诊断，也未用真实模型生成新标题。文风及题目是否真正符合品牌传播要求，需要重拟后逐项阅读；测试不会给标题打“质量已通过”的分数。
