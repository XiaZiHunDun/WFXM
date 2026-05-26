# Butler Memory 深挖报告

## 一句话结论

Butler 的 memory 线已经有不错的基础骨架，尤其是三层 recall、hybrid 检索、post-session 提炼和 project/owner 分层；但与最强参考实现相比，最大的缺口仍然是结构化 observation 管道、session summary 可检索化、transcript recall 质量，以及 prefetch 的 index-first 策略。

## Butler 当前基线

### 已有能力

- `butler/memory/recall_layers.py`：已实现 `index -> timeline -> fetch` 三层 recall
- `butler/session_lifecycle.py`：已实现 prefetch、sync_turn、post_session、summary snapshot、prefetch cache
- `butler/memory/semantic_index.py`：已实现 SQLite 向量索引 + hybrid FTS merge + access_count
- `butler/memory/retrieval_telemetry.py`：已记录最近一次 retrieval 的 mode/fallbacks/candidates

### 明显缺口

- `butler/memory/observer_queue.py` 在本次分析时还只是轻量 observation 审计；现已升级为 PostToolUse -> workspace `.butler/observations.db` 派生层，但 observation 压缩/summary-first 消费仍可继续深化
- prefetch 仍偏 eager 全文注入
- timeline 还只围绕 experience 行，不含 session summary / prompt 混排
- transcript recall 仍弱于参考实现的 session_search 级别

## 参考来源一：Claude-Mem

`claude-mem` 对 Butler memory 线最有价值，因为它不只是“能搜到”，而是把记忆拆成了 observation、timeline、summary 和 token-economics 四个层次。

### 最值得继续学的机制

1. Progressive disclosure  
   `search -> timeline -> get_observations` 强制逐层展开  
   Butler 已有 `recall_layers` 子集，但 prefetch 仍默认直接注入全文

2. Observation 存储  
   结构化 observation：`type/title/facts/narrative/files/content_hash`  
   Butler 现已具备 workspace `.butler/observations.db` 派生层；剩余差距主要在 richer schema、timeline/search 渐进披露与 observer 压缩链路

3. Timeline anchor  
   支持 observation id / session summary id / ISO 时间 / query-auto-anchor  
   Butler timeline 仅围绕 experience id 窗口

4. Session summary  
   summary 进入 DB/向量并可 search/timeline  
   Butler 只写 `.butler/session_summary.json` 快照，尚未进入 recall

5. 异步 worker / queue  
   PostToolUse -> pending queue -> observer LLM -> SQLite/Chroma  
   Butler 现已有内存队列 + SQLite flush 子集；后续更值得学的是观察者分离与 summary-first 消费，不学 Bun/Redis/Chroma

6. 隐私过滤  
   全 private 消息可整轮跳过 observation/summarize  
   Butler private strip 覆盖仍不完整，应扩到入站、post_session、conversation sync

## 参考来源二：Hermes

`hermes-agent` 在 memory 上更像一个“编排面样本”，它提醒我们 Butler 缺的不是更多 memory 插件，而是更清晰的 manager seam 和 session_search 能力。

### 最值得继续学的机制

1. `MemoryManager`  
   统一 prefetch / sync_turn / on_session_end / tool route / single external slot  
   Butler 逻辑仍分散在 `session_lifecycle.py` 与 memory facade

2. `session_search`  
   FTS5 -> 辅助模型摘要 -> lineage 过滤 -> recent 模式  
   这对微信场景里的“上次我们怎么做的”尤其有帮助

3. Lifecycle hooks  
   `on_pre_compress`, `on_delegation`, `on_session_switch`  
   Butler 当前缺更明确的 memory 生命周期 seam

### 不值得优先搬的部分

- 外部 memory provider 生态本身
- conversation sync 的云 memory 语义

## 参考来源三：OpenCode 与 OpenClaw

这两者对 Butler memory 的价值不在“向量记忆”，而在上下文经济学与 compaction 边界设计。

### OpenCode

- 把 compaction 作为 session/message/part 状态机的一等事件
- turn-based tail 预算、anchored summary、overflow 明确建模
- 启发：Butler 需要把 memory 注入与 compaction 摘要边界分清

### OpenClaw

- pre-compaction memory flush
- post-compaction context refresh
- session visibility
- 启发：适合转译为 Butler 微信场景的 memory flush 设计

## 优先级判断

### P0

1. 把 prefetch 从 eager 全文注入改成更接近 index-first / summary-first  
   当前 token 成本最高，也最影响长会话稳定性

2. 扩大 private 内容在 memory 写入链路中的过滤覆盖面  
   这是 correctness 与隐私边界问题，不只是优化

### P1

3. 补结构化 observation 管道：持久队列 + observer LLM + 去重 hash  
   这是 Butler 与 `claude-mem` 在 memory 核心能力上的最大差距

4. 让 session summary 成为可检索实体，而不是仅文件快照  
   能显著提升 timeline、跨 session recall 与新会话预热质量

5. 增强 session_search 风格的 transcript recall  
   对“上次怎么做”的查询特别有价值

### P2

6. 补 memory lifecycle seams：pre-compress / delegation / session-switch  
   便于 memory 与 compaction、子任务、resume 边界对齐

## 不建议引入

- Bun worker + Express memory 服务
- Chroma MCP / Redis / BullMQ / Postgres 队列栈
- Hermes external memory 插件生态整体搬迁
- OpenCode 的全量 SQLite message/part 会话模型

## 最关键的判断

Butler 当前 memory 线最不该做的，是因为参考仓库很强就直接引入它们的运行时依赖。最该做的，是继续保留 Python + 本地 SQLite/索引 + 微信单网关主线，只把记忆“管线”和“边界”做得更完整。
