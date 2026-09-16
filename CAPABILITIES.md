# 内容制作：能力与验收记录

## 记录基线

- 模块：`content`。
- 审阅的业务源码：[`8e71210f02683f94f2d57848b8b9ca8dbb7b34a0`](https://github.com/xiafanzeng/frontmind-content/tree/8e71210f02683f94f2d57848b8b9ca8dbb7b34a0)。
- 整理日期：2026-09-16。本清单记录已执行检查与仍待补充的验收。
- 开发域名：[content.frontmind.cn](https://content.frontmind.cn)。实际运行版本以 `/api/version` 的 `moduleSha` 和 `coreSha` 为准。

“源码已包含”“本地检查通过”“真实业务验收通过”分别记录，不能互相替代。文档合并不会更新正在运行的镜像。

## 能力清单

| 能力 | 源码能力 | 主要源码 | 本地验证 | 真实业务验收 |
|---|---|---|---|---|
| 任务输入 | 已包含：内容工作台、问题与材料输入、回答/参考文件引用；业务输入和文件归属校验。 | `module/client/ContentProductionWorkspace.tsx`；`module/server/task-handlers.ts`；`module/contracts/` | 见下方本地检查；不据此推定真实业务通过。 | 真实业务快照 API 保存、页面读取与刷新持久化通过；材料上传及创建并执行任务仍未验收。 |
| Job 与持久化 | 已包含：内容业务会话、任务记录、冻结输入快照、状态和持久化接口。 | `module/server/conversations.ts`；`module/server/task-persistence.ts`；`module/server/persistence.ts`；`module/server/state.ts` | 见下方本地检查；不据此推定真实业务通过。 | 合成业务快照的保存、页面读取、刷新及删除通过；真实 Job 派发和继续执行未验收。 |
| 人工确认与恢复 | 已包含：按可用 action 和修订号检查确认动作，保留任务用途和冻结上下文，提供执行观察处理。 | `module/server/task-handlers.ts`；`module/server/runtime.ts`；`module/worker/observations.ts` | 见下方本地检查；不据此推定真实业务通过。 | 真实任务的人工确认、错误修订拒绝、暂停后恢复未验收。 |
| 工作流版本 | 已包含：内容制作 v4.11.0 源码、构建脚本、工作流目录和历史归档选择；任务绑定原工作流版本。 | `module/workflows/release.json`；`module/workflows/source/`；`module/server/workflow-catalog.ts` | 见下方本地检查；不据此推定真实业务通过。 | 新旧真实任务跨版本恢复未验收，单元校验不能替代供应商运行。 |
| 成果与下载 | 已包含：内容产物解释、呈现和文件下载接入；通用文件授权由私有 Core 提供。 | `module/server/artifact-presentation.ts`；`module/client/ContentProductionWorkspace.tsx` | 见下方本地检查；不据此推定真实业务通过。 | 真实生成成果、刷新后的下载和文件授权待验收；供应商执行未验收。 |

## 已完成的本地检查

名称修改基线完成 frozen install、typecheck、1 个 Vitest 文件 / 6 项测试和完整 build，覆盖输入、来源文件、冻结上下文和确认冲突。弹窗居中修复完成 frozen install、typecheck、完整 build；真实业务组件的本地预览在 1440×1000 和 1280×800 两个视口内完整居中。

本轮修改包均经过 delivery skill 的路径检查、准确基线候选和隔离三方合并，没有未解决冲突。以上测试使用本地或合成场景，不产生真实供应商任务。

## 开发域名实际验收记录

| 范围 | 已有证据与待完成项 |
|---|---|
| 目标版本页面 | 目标 moduleSha 的首页、内容页、深链、刷新和通用智能体路径回首页已通过；页面没有名称测试后缀、预览标记、会话接口 500 或浏览器异常。真实截图已确认新建弹窗居中且内容完整可见。 |
| 普通保存与刷新 | 真实测试域名通过合成业务会话快照的 API 保存、页面读取、刷新持久化和测试记录删除。没有派发供应商任务，不能将此记为完整任务创建或执行恢复通过。 |
| 供应商流程 | 完整内容制作、人工确认、跨版本恢复和成果下载未真实执行。 |

后续部署应重新记录实际两个 SHA，并对变更交互复验。停用的 worker 不记为任务执行通过；旧版本结果不直接作为新镜像验收。公开文档只记录检查结论，不包含账号凭据、私有路径、业务记录正文或运行数据。

## 仍保留的能力边界

页面、弹窗和快照持久化检查通过；确认、执行恢复、真实成果和文件授权仍需以真实任务逐项验收。

## 运行与公开范围

`module/` 包含公开业务源码、业务依赖和所属工作流，`standalone/` 包含独立壳与合成预览，`vendor/` 由主仓维护并按版本下发。`pnpm dev` 明确显示“本地预览”，不连接真实测试数据库或付费供应商。真实持久化、后台任务、授权文件和供应商连接由私有 Core 运行入口提供。

开发域名进入固定测试工作区；子仓不实现产品登录、成员、租户或通用智能体。主仓注入真实用户和工作区上下文，并按需提供跨模块入口。独立模块保留自己的输入流程。

普通 ZIP 导入、CI 和页面检查不触发付费生成、监控采集、媒体外发或客户域名发布。没有供应商配置、指定测试目标或额度时，明确记录未配置或未执行；不以合成预览替代真实验收。

## 下一轮修改

先让 `frontmind-module-delivery` 读取开发域名 `/api/version` 并导出精确线上源码、完整 SHA 和交接模板。`main` 可能含尚未上线的文档或代码，不能直接当线上基线。

Pro 按 [PRO_GUIDE.md](https://github.com/xiafanzeng/frontmind-content/blob/main/PRO_GUIDE.md) 返回 ZIP 后，delivery skill 在隔离工作树中合并、验证并部署指定子域名。验收后使用 `frontmind-module-sync` 合回业务源码；独立壳、预览数据和开发门禁不回灌主仓。源码同步不自动部署生产 Dashboard。
