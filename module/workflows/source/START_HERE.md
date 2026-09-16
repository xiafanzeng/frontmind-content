# FrontMind 工作流启动规范

在解压后的工作流根目录运行：

```bash
./scripts/frontmind
```

无参数启动与 `./scripts/frontmind start` 完全相同：只显示标准启动页，不创建 Job、不接入材料，也不开始研究。

## 第一个决定：本次要完成什么

启动页固定显示四项：

1. **建立新的 Reference Pack**：首次接入企业材料，研究后确认比较对象，再生成并确认核心定位；
2. **刷新已有 Reference Pack**：企业材料、市场或定位需要更新；
3. **创建或导入 P0 品牌文章**：使用 `positioning_ready` Reference Pack；
4. **撰写单问题文章**：使用 `p0_ready` Reference Pack 回答一道正式问题。

用户没有选择前，不询问一组零散输入。品牌名称、附件、工作目录中的 ZIP、历史任务或技术预检结果都不能代替这个决定。用户只提供品牌名称时，继续显示启动页，不能默认选择“建立新的 Reference Pack”。

工作流发行 ZIP 是程序包，不能作为企业材料或 Reference Pack 使用。

## 选择后的最小输入

### 1. 建立新的 Reference Pack

先确认用户选择“建立新的 Reference Pack”，再接收品牌名称。普通企业材料可以同时提交，也可以在随后出现的 Reference Pack 输入页补交；定位 Brief 可留空。

```bash
./scripts/frontmind start \
  --task reference-pack \
  --brand "完整品牌名" \
  --input /absolute/path/brand-materials \
  --job-dir /absolute/path/jobs/reference-pack
```

这个选择等同于明确调用 `reference-pack create`，因此不会再次询问是否创建。

材料齐备后，研究首先生成候选对比列表。完整展示 `awaiting_competitor_selection` 页面，让用户选择实际比较对象、同类举例或不纳入；用户可以增删、补充名称和类别。用户确认范围后才生成定位，并在最终定位页再次确认。两次暂停分别决定“和谁区分”与“定位是否采用”，不得合并或由运行者代选。

### 2. 刷新已有 Reference Pack

选择后提供现有 Pack 4.0 或 4.1。市场刷新重做候选列表，已有选择作为可编辑预选，经过竞品确认和最终定位确认后导出新版本。旧 Pack 缺少比较范围仍可读取，不能自动推定用户已经选择过对象；不创建证据审核门控。

```bash
./scripts/frontmind start \
  --task reference-pack-refresh \
  --reference-pack /absolute/path/Reference_Pack.zip \
  --job-dir /absolute/path/jobs/reference-pack-refresh
```

### 3. 创建或导入 P0

选择 P0 后创建 P0 Job。该 Job 的第一个业务暂停仍是 Reference Pack 路由，用户需要明确选择使用已有 Pack 或创建新的 Pack。

```bash
./scripts/frontmind start \
  --task p0 \
  --reference-pack /absolute/path/Reference_Pack_v1.zip \
  --job-dir /absolute/path/jobs/p0
```

命令携带 Pack 路径只是在路由页提供候选输入，不代表系统已经替用户确认使用。

### 4. 撰写单问题文章

选择文章后先接收问题 ID 和正式问题，再创建 article Job。它同样首先进入 Reference Pack 路由。

```bash
./scripts/frontmind start \
  --task article \
  --question-id q000123 \
  --question "完整正式问题" \
  --reference-pack /absolute/path/Reference_Pack_v2.zip \
  --job-dir /absolute/path/jobs/q000123
```

## 对 Codex 或其他运行者的会话要求

当用户只说“启动工作流”“开始 FrontMind”或附上发行 ZIP 要求启动时：

1. 找到或安全解压工作流；
2. 可以完成只读预检，但不能把预检报告当作启动结果；
3. 运行 `./scripts/frontmind`；
4. 完整展示四项启动选择；
5. 只等待用户选择本次任务，不提前索取品牌材料；
6. 用户选择后，再按对应路径收集最小输入并创建 Job；
7. 一旦 Job 返回用户暂停，完整展示确认页并停止。

如果用户在首次消息中已经明确任务，例如“用这个 Pack 创建 P0”，可以直接启动相应任务。P0 与 article 的 Reference Pack 路由仍按运行时合同显示。

技术预检命令：

```bash
./scripts/frontmind preflight
```

完整的状态恢复和确认参数见 [RUNBOOK.md](RUNBOOK.md) 与 [FrontMind_执行手册_v4.11.0.md](FrontMind_执行手册_v4.11.0.md)。
