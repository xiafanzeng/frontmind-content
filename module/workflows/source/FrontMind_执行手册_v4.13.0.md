# FrontMind v4.13.0 执行手册

## 运行方案

新宿主动作由本地 OpenAI Agents SDK 执行，通过 XTY 的 Chat Completions 调用模型。初稿、E8、第三遍润色及20个标题继续使用原 DeepSeek Pro/max。P0写作合同仍是 `frontmind-p0-style/4.12.8`，两篇完整例文和去审计式表达Skill不变。研究、定位、选材、验读、标题编辑等原宿主动作全部走新适配器；不新增业务审批或审稿轮次。

本包是完整代码与配置交付。此次环境无法解析网关和依赖源域名，未安装官方SDK，也未验证实际工具调用；请先完成下列安装和自检。离线模拟通过不代表模型权限、官方SDK联调或文章质量通过。

## 安装

使用 macOS、Linux 或 WSL。既有文件锁有不同系统的实现分支；本轮仅在Linux验证，没有完成原生Windows验证。Python 3.10及以上。解压到新目录，不覆盖旧程序与Job。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
./scripts/frontmind --version
./scripts/frontmind preflight
```

固定 `openai-agents==0.22.3`、`openai==3.16.2`。旧断点保留原程序和依赖；不要运行中直接升级SDK。`preflight`只检查本地依赖与配置，不证明网关可用。

`config/xty.json` 已写入本次提供的key，base_url为 `https://api.xty.app/v1`。默认宿主模型为 `gpt-4o`，依据XTY普通Chat接口文档的明确示例选择，并非已确认该key可用。`qwen-xxx`不是有效部署名；Codex专用域名的示例也不作为普通Chat接口可用性的证明。需要更换时显式修改此文件的model，先用同一个端点与key完成工具自检；不自动探测候选、切备线路或降级。宿主模型选择与SDK选择分开，不承诺gpt-4o的规划或验读质量等同原glm宿主。

原 `config/deepseek.json` 与 `config/zhipu.json` 保留。智谱用于既有搜索、网页Reader、OCR及原Managed动作恢复，不再为新动作创建Agent、Environment、Session。配置文件权限为0600。

## 网关自检

```bash
# 只打印本地公开配置，不联网、不显示key
python scripts/probe_agents_gateway.py
# 只读模型列表；不生成文章
python scripts/probe_agents_gateway.py --models --output /tmp/frontmind-models.json
# 明确授权一次小额真实模型请求：验证工具调用及RunState保存恢复
python scripts/probe_agents_gateway.py --live-tool --output /tmp/frontmind-tool.json
```

模型列表成功不等于tools成功；未列出某模型也不自动断言不能调用。`--live-tool`会计费，不自动重试。它只检查短工具调用、序列化及新数据库连接恢复，不验证长材料、所有业务动作、文章文风或真实等待15天后的供应商稳定性。

完整原业务入口：

```bash
./scripts/frontmind
```

无参数保留四项任务选择。用户选择后才创建Job；业务确认页照常显示。具体Reference Pack、P0、问题文章、精修参数见START_HERE.md和RUNBOOK.md。仅安装SDK不授权程序自动跑全部历史任务。

## 挂起半个月后继续

Job目录是任务主记录，不能只保存Session ID。每个宿主动作的尝试使用独立本地SQLite文件和稳定Session ID，动作之间通过既有Job状态衔接，不把所有阶段塞进一个无限长会话。

```text
Job/
  job_state.json
  ... 原有材料、确认、稿件、产物 ...
  provider/<action>/runtime/
    latest.json
    attempts/<attempt_id>/
      execution.json
      request_plan.json
      session.sqlite3
      checkpoint.json
      model_..._request.json / model_..._response.json / model_..._wire.json
      tool_<hash>.json
      submission.json
```

`SQLiteSession(id, file_path)`明确落盘，未设置自动到期清理。checkpoint保存SDK RunState、配套会话条目和本地工具状态。模型实际响应和完成工具回执均保留。文件内容属于私有业务材料；它们不是匿名日志。

正常业务暂停后，先读状态，再按页面提供的参数继续：

```bash
./scripts/frontmind status --job-dir /absolute/path/Job
python scripts/agents_sessions.py --job-dir /absolute/path/Job inspect
# N为当前revision；确认型暂停仍必须补齐原页面要求的用户选择
./scripts/frontmind continue --job-dir /absolute/path/Job --revision N
```

异常中断后，同样输入与依赖匹配时才可显式重试：

```bash
./scripts/frontmind continue --job-dir /absolute/path/Job --revision N --retry-current-action
```

普通continue不悄悄重发失败请求。材料、提示、模型配置改变时产生新的请求身份，不能拿旧断点冒充当前任务的执行结果。业务上的稿件问题仍用已有p0-rework等显式返工，不由网络重试代写第二稿。

## 恢复的范围

已完成的工具调用按call_id复用持久化回执；已验证提交但进程未返回，可以补齐本地完成状态，不再次请求模型。工具前利用SDK interruption写入执行断点，然后只放行原有工具，属于程序内部持久化边界，不增加用户审批或新增可执行权限。

网络请求发出但未收到完整响应时，不能从供应商内部逐token接回；显式重试可能产生新的请求及费用。工具已开始但没有完整回执时，程序停止，避免盲目重复副作用。先核对动作目录；确认可以重做的读取工具才可用以下入口：

```bash
python scripts/agents_sessions.py --job-dir /absolute/path/Job allow-tool-retry   --action p0_blueprint --call-id ACTUAL_CALL_ID   --reason "已核对原记录，允许重做该读取" --acknowledge-possible-duplicate-cost
```

此命令只保留核对记录并授权，不执行API；之后再显式continue重试。已完成提交和非读取工具不受此入口放行。不要删除回执绕过恢复逻辑。不是所有异常都能自动恢复，也不宣称任意崩溃下exactly-once。

没有自动清理期限不等于模型无限上下文或供应商永久可用。长暂停后仍需原SDK与代码、可用网关和模型、原材料、完整Job；事实可能过时需要用户决定刷新。不能把半个月前的确认自动改成今天的新业务选择。

## 备份和并发

```bash
python scripts/agents_sessions.py --job-dir /absolute/path/Job backup   --output /absolute/path/backups/Job-20260921.zip
```

命令锁定业务Job及SDK宿主，备份整个Job（包括SQLite相关文件），拒绝符号链接及覆盖已有文件。配置与程序在Job之外，需单独保留同一发行版本。数据丢失后只有Session ID无法恢复。

不同Job可在不同进程运行，使用不同目录及Session；同一Job的写操作互斥。单个Agent的工具串行，避免同任务状态竞态。本版没有全站队列、集群调度或全局速率限制器；并发量仍受网关限流、磁盘、上下文和成本影响。多机器部署不能把本地锁和SQLite当作分布式一致性方案。

CLI采用同步业务控制器包裹async Runner；异步Web服务应把该控制器放入工作进程/线程，不能在已有事件循环里直接调用同步adapter。进程退出会停止本地计算；本版没有提供关机后仍继续运行的云托管worker。

## 原Managed任务与资源

不自动归档、删除、扫描清理智谱资源，也不处理Website资源。原Managed动作存在且请求、依赖可匹配时仍用原适配器恢复；已完成产物继续可读。新动作默认SDK。不把Managed Session ID转换为本地RunState，也不导入远端内部推理状态。需要旧动作的精确恢复请保留完整旧Job和代码；不要随意改旧输入。

## 数据路径

新宿主消息和工具内容会发往用户配置的XTY网关及其上游模型；本地保存历史不等于推理在本地，也不证明第三方服务不保留数据。RunConfig关闭OpenAI tracing，HTTP自动重试设0，不跟随重定向，不使用全局default client以避免多任务串配置。不增加远端OpenAI Conversations或托管Agent资源。来源文件按已有读取范围提供，不开放任意shell。
