# 本地界面与收件验收

本目录提供三种用途不同的入口，复用 `module/client` 中的实际业务组件。

| 入口 | 数据与操作范围 |
| --- | --- |
| `/` | 既有默认开发预览。直接运行开发服务即可使用，不依赖 5174 收件桥。 |
| `/standalone/folder-review.html` | 主体文件夹、版本引用和泳道交互的离线演示。数据均为合成示例，保存在当前浏览器；没有真实研究、正文生成或业务任务。 |
| `/standalone/folder-live.html` | 经本机受限桥上传附件、保存并读回真实服务器收件记录。主体目录和未确认草稿保存在本机文件中；收件不创建 Runner Job，也不开始生成。 |

2026-10-24 已补正式 `/api/modules/content` 主体、聊天和收件接口及 Core 宿主；配套 Core 需要本轮数据库迁移和适配，不能只发布本公开前端。正式本地验收使用 Core 的 `http://127.0.0.1:5180/content-production` 和独立 MySQL，不使用上表的 Python 文件保存桥。默认 Edge 已验证新建聊天、底部选文件、确认收件、刷新读回；没有启动生成。上表两个可选入口仍分别是离线演示和旧收件桥，不能据此宣称正式研究或文章生成已完成。只有实际 Runner 状态和交付产物才能代表研究、写作或交付完成。

发布后的只收件验收使用正式页面 `/?verify=intake`。该入口先验证后端具有正式收件能力，再使用主体、聊天与收件接口；派发、任务查询和停止端口均拒绝调用，也不会轮询已有任务。能力检测失败只显示错误，不转入生成。它不会修改服务器全局开关，普通网址保持正常生成行为。正式收件回执及附件必须在刷新后仍可读回，不能把确认卡片出现视为收件成功。

## 依赖与离线页面

需要 Node.js 22、项目固定的 `pnpm@10.4.1`；收件桥和 Python 离线测试另需 Python 3.11 及以上，全部使用标准库，无需安装 Python 包。

在仓库根目录安装项目依赖，再启动开发服务：

```text
pnpm install --frozen-lockfile
pnpm build:business
pnpm dev --port 5173 --strictPort
```

用默认浏览器打开 <http://127.0.0.1:5173/standalone/folder-review.html>。Windows PowerShell 可执行：

```powershell
Start-Process 'http://127.0.0.1:5173/standalone/folder-review.html'
```

macOS 可用 `open`，Linux 可用 `xdg-open` 打开同一地址。离线演示会保存当前浏览器中的进度；它不会上传企业资料或执行模型。示例附件限制为单个 2 MB，仅用于界面验收。

## 真实后端仅收件

这个入口会在用户确认后把附件和输入保存到官方内容网站，需要已经获得授权的网关账号。当前代码只允许远端 `https://content.frontmind.cn`，没有可配置的其他目标域名；入站和出站均拒绝任务、Provider 和 Runner 路由。不要将此桥部署为对外服务。

网关凭据从本机文件读取，默认位置是 `~/.codex/frontmind-private/content-gateway.json`；可用 `FRONTMIND_REAL_BACKEND_CREDENTIAL_FILE` 指定另一个本机文件。格式为包含 `username`、`password` 的 JSON 对象。凭据不随源码交付，也不会出现在页面或日志中。

默认运行目录为 `standalone/devtools/.local-state/`，已由同目录 `.gitignore` 排除，其中的主体目录、草稿、收据及审计记录均为本机数据。可用 `FRONTMIND_REAL_BACKEND_DATA_DIR` 指向仓库外的绝对路径。不要提交或分享这个运行目录。

Windows PowerShell：在两个终端中分别启动桥和前端，均从仓库根目录执行。

```powershell
# 终端 1：使用默认凭据路径；只有凭据另有位置时才设置下面的变量。
# $env:FRONTMIND_REAL_BACKEND_CREDENTIAL_FILE = 'D:\private\content-gateway.json'
python -B .\standalone\devtools\real_backend_bridge.py
```

```powershell
# 终端 2：仅此显式开关会启用到本机 5174 的 /api 代理。
$env:FRONTMIND_REAL_BACKEND_BRIDGE = '1'
pnpm dev --port 5173 --strictPort
```

macOS / Linux：

```bash
# 终端 1；可提前 export FRONTMIND_REAL_BACKEND_CREDENTIAL_FILE=/private/path/content-gateway.json
python3 -B standalone/devtools/real_backend_bridge.py
```

```bash
# 终端 2
FRONTMIND_REAL_BACKEND_BRIDGE=1 pnpm dev --port 5173 --strictPort
```

打开 <http://127.0.0.1:5173/standalone/folder-live.html>。也可通过 `?conversation=<会话ID>` 选中本桥已经管理的会话。

新建聊天先保存本机草稿；确认提交时才上传附件，并将收件写入真实服务器。桥核对服务器读回的原文字、附件标识和收件信封后，才返回 `executionStarted: false` 的收据。为适配现有后端的内容用途投影，服务器消息保留待执行信封；这不代表任务已经派发，验收客户端不会提供执行或重试生成入口。界面应显示“服务器已收件，生成尚未启动”。

桥只操作自己建立的新收件草稿，不接管已有执行任务；附件上限为单个 512 MB，实际仍须通过远端校验。写入结果未知时保持当前收据状态供核对，不自动重发，也不创建替代任务。

`FRONTMIND_REAL_BACKEND_BRIDGE=1` 不可与已有的 `FRONTMIND_LOCAL_WORKFLOW_ROOT` / `FRONTMIND_LOCAL_CONFIG_DIR` 生成模式同时启用。退出收件验收后，Windows 可用 `Remove-Item Env:FRONTMIND_REAL_BACKEND_BRIDGE` 清除当前终端开关；重新启动默认开发服务即可回到离线预览。

## 不调用模型的检查

```text
pnpm exec vitest run standalone/folder-demo-client.test.ts --maxWorkers=1 --minWorkers=1
python -B -m unittest discover -s standalone/devtools -p test_real_backend_bridge_offline.py -v
```

其他平台将最后一行的 `python` 换为 `python3`。桥的 8 项单元测试使用内存远端和临时目录，并在 socket 层阻止真实联网；不会读取网关凭据或上传文件。运行后仍需在需要的入口手动核对布局、输入、返回修改和刷新等交互。
