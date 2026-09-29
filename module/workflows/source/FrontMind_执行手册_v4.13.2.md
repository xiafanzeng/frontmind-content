# Final_v14 当前执行说明

新建任务默认使用 `editorial-mission-v2`，以本版 `README.md`、`START_HERE.md` 和 `FIX_v4.13.2_Final_v14.md` 为准。正文采用 **DeepSeek 成稿 → DeepSeek E8 → XTY 文字意见 → 必要时 DeepSeek 返工一次 → 标题与导出**；P0 在 E8 后保留原第三遍文风编辑。XTY 只给文字意见，不回查来源或改写正文，返工后不再次审正文。

当前委托决定体裁、介绍层次、对象、篇幅与排版。素材和模型拟定构思作为参考数据，当前委托独立置于输入末尾；其中 `article_brief` 决定正文主次。编辑先读完整基稿，再读素材与例文。每阶段保留同一篇幅目标，不另设初稿预算，也不把明确上限变成补足任务。

DeepSeek 使用 `deepseek-v4-pro`、thinking enabled、`reasoning_effort=max` 和既有65536输出额度。其他模型、网关及备用恢复配置保持原配置。最终正文记录真实DeepSeek来源，标题、Word及后续改稿读取这一稿。

在新解压目录安装依赖并运行 `./scripts/frontmind preflight`，随后使用该目录的 `./scripts/frontmind`。新任务自动采用v14；历史任务和已冻结请求继续按原版本恢复，不自动重写或切换提示。验证新版案例使用新的Job目录，命令见 `README.md`。

下文保留基础接口与历史操作说明，其中“当前”“默认”等表述仅指对应历史版本；旧升级器不能代替本版完整程序，也不覆盖本节规则。

---

# FrontMind v4.13.2 执行手册

## 基线与适用范围

当前宿主是本地OpenAI Agents SDK（openai-agents 0.22.3 / openai 3.16.2），经config/xty.json调用XTY Chat Completions；默认模型及Key按原配置保留。作者仍为DeepSeek；智谱辅助搜索/Reader/OCR与旧Managed动作显式恢复保留。迁移执行框架不等于更换写作模型或重新生成既有文章。

本版为v4.13.1的运行修复。已解决F1/F2/F3、三项本地只读工具的断点重做，并保留4.13.1标题和题库逻辑。用户本地是否还有其他补丁，须由升级器比较，不能假设全部相同。

## 安装与升级

### 全新目录

使用Python3.10或以上；优先沿用已通过实际联调的Python版本。不要在业务Job运行途中安装依赖。

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
export FRONTMIND_PYTHON="$PWD/.venv/bin/python"
./scripts/frontmind preflight
```

需要运行测试时，单独安装开发依赖 `python -m pip install pytest`；requirements.txt没有因此改动。不要把依赖安装失败的环境标记为可运行。

### 原4.13.0或4.13.1目录

暂停该目录活动任务，备份完整目录和Job。使用**新解压包**中的升级器，先检查再应用：

```bash
python3 scripts/upgrade_to_v4132.py --target /absolute/path/old-frontmind
python3 scripts/upgrade_to_v4132.py --target /absolute/path/old-frontmind --apply
```

config、jobs、workspace、.venv、requirements、未变更供应商适配文件受保护。本次会修改agents_runtime.py与host_tools.py，不再套用旧版“SDK文件全部不动”政策。未知本地差异只按唯一精确上下文合并；冲突在写入之前停止。更新前备份放在目标目录`.frontmind-upgrade-backups/`，包含实际升级回执。出现冲突时保留旧目录，不手动整目录覆盖。升级器不清理Job、不移动failed_attempts、不归档任何远端对象。

进入升级后的原目录，设置FRONTMIND_PYTHON为原来已安装并联调的venv绝对路径，再做下列自检。

## 三步自检与验收

```bash
./scripts/frontmind preflight
python scripts/probe_agents_gateway.py --models --output probe_models_4132.json
python scripts/probe_agents_gateway.py --live-tool --output probe_live_4132.json
```

models只进行模型列表GET，不生成内容；供应商是否对非生成请求收费仍按其规则。live-tool显式执行一次小额模型工具请求（最多128输出token，不代表总计费token上限），再使用相同本地SQLite和序列化RunState执行工具，无业务文章生成。失败无自动HTTP重试、无自动换模型。模型列表成功不等于工具调用成功。

```bash
python -m pytest scripts/tests_v411 -q
python -B scripts/validate_workflow.py --run-tests
python scripts/run_acceptance_v411.py --output /absolute/path/NEW-acceptance-output
python scripts/build_release.py --output-dir /absolute/path/NEW-release-output
```

官方SDK测试使用真实库，只将模型响应替换成离线响应，不能证明网关连接。发行检查要求这些测试实际运行且零skip；依赖缺失时保持失败，不把跳过算通过。匿名验收只使用包内合成夹具，不验证客户医疗事实、定位判断或语言质量；运行时需要已安装的LibreOffice/poppler及系统中文字体，包内不分发字体文件。

## 现有任务如何恢复

```bash
./scripts/frontmind status --job-dir /absolute/path/jobs/q000001
python scripts/agents_sessions.py --job-dir /absolute/path/jobs/q000001 inspect
python scripts/agents_sessions.py --job-dir /absolute/path/jobs/q000001 backup --output /absolute/path/backup-q000001.zip
```

状态为业务确认时，仅按实际revision提交用户已经作出的选择。q000001若停在Pattern确认页，必须等待实际Pattern选择，本版不会代确认或继续。只有失败动作需要重试时，按状态中的revision显式执行：

```bash
./scripts/frontmind continue --job-dir /absolute/path/jobs/q000001 --revision 当前revision整数 --retry-current-action
```

同一Job一次只能有一个执行者；不同Job可并行，仍受网关限流/费用/机器资源限制。关闭进程后不会在云端继续计算，重新运行是从持久化边界继续。

### 工具恢复规则

| 已有记录 | 行为 |
|---|---|
| completed且签名一致 | 复用已保存回执，不重复外呼或执行 |
| started且工具为list_materials/read_material/search_materials | 显式恢复时重新执行，保存完整新回执和重做记录 |
| started且为web_read/web_search/extract_document/ocr/submit_result等 | 停止并报告结果未知；先核对外部结果及账单，不自动执行 |
| 工具ID参数不一致、源文件/指纹或SDK不匹配 | 停止核对，不清空会话规避 |

不要手工删除started文件来“解锁”。普通ToolError现在写成模型可见失败回执，模型可以用新的调用ID纠正；这可能需要后续模型轮次，不承诺免费纠正。网络失败或其他异常仍不会被伪装成成功工具结果。

### 路径和答案

可以使用已注册文件的Job内绝对路径、相对路径或artifact_id。路径处于Job根内仍不足以授权：必须已登记、非内部符号链接且sha256一致。config/provider不因绝对路径支持而开放。

`00_input/loose_answer_NN.*`是生成器暂存命名空间，冻结答案为`inputs/answer_NN.md`。旧快照恢复会排除暂存登记，不删除文件，也不放宽冻结答案完整阅读。

## 未变更的业务流程

从Reference Pack中确认使用并选择优化问题，已有同题同一期两平台全文直接带入原E1；没有数据才导入监控表。P0标题仍为整篇品牌介绍的20个替代主标题，不改回疾病/项目问答。正文/E8/第三遍Skill和现有四字段验读全部保留。此修复无需新建客户任务或重新付费生成已完成P0。

## 未完成和已知限制

1. 本交付环境无法安装官方SDK并无法访问网关，本轮完整发布预检不能通过；使用者应在已成功运行的环境执行上述SDK与live-tool自检。外部验证文件如实区分可用结果与未验证项。
2. 模型未完成必读即submit_result仍按成文设计停止，不自动付费修稿。本版没有扩大该异常为可恢复ToolError。
3. 自备文件名含answer仍按旧规则登记为必读答案。普通品牌资料建议使用不含answer的文件名；不要给真实答案改名来逃避必读。
4. 半个月后恢复需要完整Job、相同输入、兼容SDK及模型可用。不保证在未知本地补丁改变了request_plan合同或模型配置后继续使用旧断点。此时先核对，不自动改指纹或新开付费尝试。
5. 用户自述的本地真实成功目录未上传，本轮没有重新验证其结果、内容质量或进行收费链路续跑。

## 外呼错误分类补充

原HostTools的部分网络异常也被包成ToolError。现在传输失败、未能解析的外部结果使用ToolOutcomeUnknown（仍兼容ToolError基类），SDK不会把它作为可继续的参数纠正反馈，而是保留started并停止核对。明确的参数/路径合同错误继续反馈给模型；收到明确API错误的行为不等于承诺无费用。此分类避免F1修复意外绕过未知付费结果守卫。
