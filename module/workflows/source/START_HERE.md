# 从当前客户开始

先读 [README.md](README.md) 的通用运行入口和版本兼容说明，再执行 `./scripts/frontmind preflight`。输入本轮客户资料、品牌和问题，使用 `article` 或独立 `p0` 入口。不要默认执行客户案例脚本。

P01：单主体自然品宣。P02：定位中让用户选择两家竞品，加上自己共三家。两类标题均为 5 个正式推荐＋5 个场景卖点。P0 与历史任务保留原流程。

需要 3—12 家横向选购稿时，新建 `article --genre industry_roundup`，按顺序重复 `--subject` 填入主品牌与比较品牌，并重复 `--dimension` 指定 2—8 个共同维度。新任务可用 `--focus` 缩小产品／功能范围、`--reader-question` 固定要回答的问题、`--exclude-topic` 排除无关主题；详见 README。行业盘点校验型号对应的证据和对比矩阵。Windows 请用 `scripts\frontmind.cmd`。

新建任务采用 `fdnv2-focus-2`：蓝图优先组织细分场景、读者问题和有证据的技术路线，初稿避免重复注入材料，并按问题写有条件的结论。历史任务继续使用其冻结版本；离线测试不会验证真实文章文风。

行业盘点交付校验未过时使用 `continue --repair-facts` 返工；否决具体事实可同时加 `--reject-fact-claim Fxx`。实际问题与快照路径保存在 Job 内。

历史台心案例在 customer_inputs，不能将其中的科室、篇幅、十一家名单或旧授权作为新任务要求。改动及离线验收参见 FIX_v4.13.2_Final_v16_3.md。
