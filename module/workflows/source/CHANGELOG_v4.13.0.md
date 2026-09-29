# v4.13.0 — 本地Agents SDK宿主

基线：用户已提供的v4.12.8完整发行包。

主要变更：新增shared/agents_runtime.py，实际接入官方Agent/Runner和显式Chat Completions；XTY配置生效到请求指纹；按动作文件SQLite和RunState；工具前断点、完成回执复用、异常结果核对；成功submit停止。生产不接收伪造响应，不自动重试、降级、归档或删除云对象。同Job互斥，不同Job目录独立。

model_runtime默认host路由迁移；旧Managed动作匹配原指纹时仍可按原适配器显式恢复。ContextVar隔离旧路由，不修改全局默认OpenAI客户端。更新preflight、发布投影、当前手册与启动说明，增加网关自检与Job检查/备份/回执核对脚本。固定openai-agents0.22.3、openai3.16.2。

未变更：DeepSeek作者模型/参数和三遍请求合同；P0style4.12.8、两篇完整例文、第三遍Skill；Reference Pack、用户业务确认、正文与20标题分离、确定性导出；旧Managed适配器实现和历史产物。

本版SDK和网关实际联调尚未完成：构建环境无法DNS解析依赖源和网关，真实SDK测试应显式skip。验证结果详见VALIDATION_v4.13.0.md，不将模拟测试当模型质量成绩。
