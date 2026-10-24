# 共享 UI 来源

这三个 vendor 文件精确投影自 Core 主仓 `packages/module-ui/src/dashboard/` 的同名源码；Core 基线为 `902c7460debec17b9e5bd5f154b66b61f16ae49b`。

`shared-source.patch` 是针对该 Core 基线的补丁，保留导航链接、修饰键点击及新导航行为，仅提供侧栏子内容插槽。`projection-manifest.json` 记录公开投影路径与哈希。后续 Core 集成应先应用此补丁并验证，再向模块投影，避免独立维护 vendor。此次没有修改私有 Core 主分支。

补丁使用零上下文格式。核对上述确切基线后，执行 `git apply --unidiff-zero shared-source.patch`。
