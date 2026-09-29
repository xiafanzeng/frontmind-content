# Pro 开发说明：内容制作

基于 delivery skill 导出的准确线上 SHA 修改 https://github.com/xiafanzeng/frontmind-content 。使用同版本源码 ZIP；不要猜测当前线上版本。

- 修改 `module/client/`、`module/server/`、`module/schema/`、`module/worker/`、`module/workflows/` 内本轮相关文件。
- 具体 API/业务实现入口见 `module/API_DEVELOPMENT.md`。新接口可注册在 `module/server/http-api.ts`，实际地址 `/api/modules/content/<路径>`，真实部署会装载此文件。
- `standalone/` 修改仅影响子域名独立壳。共用样式/组件在 `vendor/`，通过主仓维护；不要改变未涉及的样式和流程。
- 保留身份归属、幂等、事务、费用预留、确认和恢复语义。客户端提供的 owner/租户参数不能代替服务器上下文。
- 新增依赖须写入 `module/package.json` 并更新子仓根锁文件；不要忽略编译失败或用预览数据替代真实 API。
- 不包含 `.git`、环境文件、真实 Key、客户数据、构建缓存、部署目标或私有主仓源码。

返回 `pro-update.zip`：

```text
handoff.json
HANDOFF.md
files/module/...
files/standalone/...
```

`handoff.json` 保留 formatVersion=1、module=content、准确 baseCommit、mode=changes；删除路径写入 delete，缺失文件不代表删除。HANDOFF.md 写清本轮需求、文件、依赖、实际验证和未验证内容。

用户要求发布子域名时，delivery 校验三方合并、检查/构建、推送 GitHub、部署并核对 moduleSha/coreSha。GitHub 提交成功不等于网站已更新。sync 合回源码不等于自动发布生产 Dashboard。
