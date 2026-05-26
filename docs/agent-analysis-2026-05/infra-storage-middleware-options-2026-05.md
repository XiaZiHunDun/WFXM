# 数据库、存储与中间件优化方案分析（2026-05）

## 结论摘要

结合 `reference/` 下各产品的实现方式，以及 Butler 当前主线约束，我的结论是：

- **可以新增，但只建议新增本地轻量层**，优先继续沿用 `SQLite + JSONL + 本地文件`。
- **最值得新增的是派生存储层**，不是 Redis、Postgres、BullMQ 这类平台级中间件。
- **核心策略仍然是“学管线，不换栈”**：把 `claude-mem`、`Hermes`、`OpenCode` 的优秀方法抽出来，落到 Butler 现有 Python 单进程、微信单网关、本地状态架构里。

## 当前基线

Butler 现在已经有一条清晰的本地主线：

- `butler/memory/butler_memory.py`：`experience.db` + FTS5 + WAL
- `butler/memory/semantic_index.py`：`memory_vectors.db` + SQLite 向量索引 + hybrid merge + access 统计
- `butler/core/session_transcript.py`：`transcript.jsonl` 作为 append-only 会话取证主存储
- `butler/core/transcript_search.py`：已有 `search_transcript` 子集，可按关键词检索当前或最近会话
- `butler/core/transcript_index.py`：大 transcript 的尾索引能力
- `butler/runtime/push_queue.py`：`push_queue.jsonl` 作为轻量失败重试队列
- `butler/memory/observer_queue.py`：当前已是按 workspace 分片的内存队列 + `.butler/observations.db` 派生层，默认仍需 `BUTLER_MEMORY_OBSERVER_QUEUE=1` 才启用
- `butler/config_secrets.py`：`secrets.yaml` 明文 + `0600` 权限

这说明 Butler 当前不是“没有存储层”，而是已经形成了：

1. **SQLite 用于结构化检索与索引**
2. **JSONL 用于事件取证和轻量队列**
3. **文件用于人类可编辑配置与记忆 SSOT**

因此新增优化时，最自然的方向不是切换到外部数据库，而是继续把这条本地链路补完整。

## 已明确边界

根据现有决策文档，以下方向仍然不应作为当前主线：

- 不引 `claude-mem` 的 **Bun Worker + Chroma MCP**
- 不把 SQL 消息库 **替换** `transcript.jsonl`
- 不做多实例 MQ
- 不把 LangGraph / Celery / BullMQ / RabbitMQ 这类作业平台搬进 Butler core

这意味着本次讨论的“新增数据库 / 存储 / 中间件”，更准确地说应是：

- 新增 **本地派生层**
- 新增 **本地持久队列**
- 新增 **本地安全存储**

而不是新增一整套平台型基础设施。

## 推荐新增一：SQLite Observation Store

### 推荐等级

**最高优先级**

### 为什么值得做

这是我认为最有价值的一项。当前 `butler/memory/observer_queue.py` 只有：

- 进程内 `deque`
- flush 到 workspace `.butler/observations.db`

这只能算“轻量审计”，还不是完整的 memory observation 管线。

`claude-mem` 最值得学的不是 Redis/BullMQ，而是：

1. PostToolUse 异步入队
2. 观察者压缩
3. 结构化 observation 存储
4. search / timeline / fetch 渐进披露

Butler 目前已经有：

- `experience.db`
- `memory_vectors.db`
- SQLite + WAL + FTS5 的成熟用法

所以最合适的演化方式仍然是：**继续用 SQLite，把 observation 作为本地派生数据层继续做深，而不是切回平台型中间件。**

### 建议形态

建议新增一个独立的本地 SQLite 库，或者并入现有 memory 数据库的独立表组。推荐表形态：

- `pending_observations`
  - `id`
  - `session_key`
  - `tool`
  - `path`
  - `payload_preview`
  - `content_hash`
  - `status`
  - `created_at`
- `observations`
  - `id`
  - `session_key`
  - `source_type`
  - `title`
  - `facts_json`
  - `narrative`
  - `file_path`
  - `content_hash`
  - `created_at`
- `observations_fts`
  - `title`
  - `narrative`
  - `file_path`
  - `session_key`

### 能带来的收益

- observation 不再只停留在轻量审计行，而能继续往 timeline / search / file-context 派生层扩展
- 能支持 `timeline` / `search` / `file-context` 三类能力
- 能为后续 `index-first recall` 提供真正的数据基础
- 能减少 PostSession 批量提炼遗漏中间工具细节的问题

### 依赖判断

- **新增基础设施**：不需要
- **新增 pip 依赖**：不需要
- **推荐实现方式**：继续用现有标准库 `sqlite3` 模式；若后续需要异步 worker，再评估是否单独引入 `aiosqlite`

### 参考来源

- `claude-mem`：observer queue / structured observations
- `Hermes`：session search / recall lifecycle

## 推荐新增二：Transcript 派生读模型

### 推荐等级

**高优先级**

### 为什么值得做

我不建议把 `transcript.jsonl` 替换掉，但很建议给它加一个**派生读模型**。

当前 transcript 这条线的定位是正确的，而且已经有 `search_transcript` 子集：

- append-only
- 取证
- 简单索引与尾部索引
- 关键词级 transcript 搜索
- retention / tombstone

但它目前仍不特别适合直接承担更强的 session read-model 场景：

- session_search
- compact summary 检索
- 跨会话调查
- “上次这个问题怎么解决的”这类 history recall

也就是说，Butler **不是没有 transcript 搜索**，而是已有能力更偏轻量子集。`Hermes` 和 `OpenCode` 在这方面的启发不是“必须上完整 SQL 会话库”，而是：

- **事件主存储**可以保留
- **查询体验**应由派生读模型负责

### 建议形态

建议保留：

- `transcript.jsonl` 作为 SSOT

新增：

- `session_read_model.db`

建议表形态：

- `session_events`
  - `id`
  - `session_key`
  - `type`
  - `content_preview`
  - `tool`
  - `ts`
- `session_summaries`
  - `id`
  - `session_key`
  - `summary_type`
  - `summary_text`
  - `created_at`
- `session_events_fts`
  - `content_preview`
  - `tool`
  - `session_key`

### 能带来的收益

- 给 transcript 提供真正的搜索层
- 提升 `/诊断`、RCA、session history 回看质量
- 为后续 memory timeline 混排提供基础
- 支撑 delegate / workflow 的审计查询

### 依赖判断

- **新增基础设施**：不需要
- **新增 pip 依赖**：不需要
- **推荐实现方式**：SQLite FTS5 派生索引，异步或 post-commit 更新

### 参考来源

- `Hermes`：`session_search`
- `OpenCode`：read model / projector 思路

## 推荐新增三：加密的 Secrets Storage

### 推荐等级

**中高优先级**

### 为什么值得做

这项不是性能优化，而是存储安全优化。

当前 `butler/config_secrets.py` 已经做了两件事：

- API key 不必进 `config.yaml`
- `secrets.yaml` 自动收紧到 `0600`

这已经比直接写配置文件好，但它本质上仍是**明文静态存储**。

现有路线图也已经把这一项列为可选 backlog，因此这是一个非常自然、边界清晰的增强项。

### 建议形态

保留现有：

- `~/.butler/secrets.yaml`

增加：

- `encrypted: true`
- `ciphertext: ...`
- `key_id: local`

或保持 provider 结构不变，仅对 `api_key` 做透明加解密。

### 能带来的收益

- 凭证静态泄露风险更低
- 不需要引入 Vault/KMS
- 不改变 Butler 本地配置语义

### 依赖判断

- **新增基础设施**：不需要
- **新增 pip 依赖**：若常驻微信部署，`cryptography` 已在 `wechat` extra 可用；若是 CLI-only 安装，则可能需要单独补依赖
- **推荐实现方式**：Fernet 本地加密，继续保留文件形态

### 参考来源

- Dify 对标里已提到 credential-at-rest 子集

## 可选新增四：统一本地 Job Queue

### 推荐等级

**第二阶段可选**

### 为什么可考虑

Butler 现在已经有几类“像队列但还未统一”的能力：

- observation queue
- push retry queue
- 部分 delegate / completion 异步通知（含现有 async delegate 子集）

如果后续要继续增强异步能力，最合理的不是上 Redis，而是做一个本地统一 job queue，把这些离散能力收敛到同一套状态机。

### 建议形态

建议是单机 SQLite job queue：

- `jobs`
  - `id`
  - `kind`
  - `payload_json`
  - `status`
  - `retry_count`
  - `available_at`
  - `created_at`
- `job_attempts`
  - `job_id`
  - `error`
  - `attempted_at`

### 适合承接的任务

- observation 压缩任务
- push retry 任务
- completion notification 延迟任务

### 为什么不是第一波

- 价值明确，但不如 observation store 直接
- 如果过早抽象统一队列，容易先做平台化，再回头找业务

## 不建议新增的项

以下方向即使参考产品里用了，我也不建议 Butler 当前引入：

### Redis / BullMQ

不建议原因：

- 当前单机单写者模型不需要
- 会把 observation / push retry 这种本地问题过度平台化
- 与既有 “不做多实例 MQ” 的边界冲突

来源：

- `claude-mem`
- 其他 Node 平台型参考实现

### Postgres

不建议原因：

- Butler 不是多租户 SaaS 平台
- 当前数据规模和并发模型都不需要
- 会把本地部署复杂度抬高太多

来源：

- `claude-mem`
- `LobeHub`

### RabbitMQ / Celery

不建议原因：

- Butler 不是作业平台
- 当前 workload 更适合单机本地 retry
- 与 LangChain/Dify 那类编排平台边界不一致

### Chroma / 外部向量数据库

不建议原因：

- Butler 已经有 `semantic_index.py`
- 当前问题在 recall 管线和 observation 结构化，不在向量引擎本身
- 引入外部向量库会先增加运维成本，后增加真实收益

### 完整 SQL 消息库替换 `transcript.jsonl`

不建议原因：

- 当前决策文档已明确：`transcript.jsonl` 继续保留
- 真正缺的是读模型与检索层，不是替换主存储

## 分层建议

如果按“现在就该做 / 可以准备 / 暂不建议”三层来排，我建议是：

### 第一层：现在就值得做

1. SQLite observation store
2. transcript 派生 read model
3. secrets.yaml Fernet 加密（对常驻微信部署更优先；CLI-only 可放回 backlog）

### 第二层：有空再做

4. 统一本地 job queue

### 第三层：当前不建议

5. Redis / BullMQ
6. Postgres
7. RabbitMQ / Celery
8. Chroma
9. SQL 消息库替换 `transcript.jsonl`

## 最终判断

如果只问一句话结论，那么答案是：

**Butler 在数据库、存储、中间件层面最值得新增的，不是外部基础设施，而是本地 SQLite 派生层。**

最值得先推进的 3 项分别是：

1. **SQLite observation store**
2. **transcript 派生读模型**
3. **加密的 secrets storage**

它们都符合当前边界：

- 不改 Butler v4 主架构
- 不引入重型外部依赖
- 能直接提升 memory、history recall、运维与安全质量

## 文档定位

这份文档属于**分析与建议材料**，不是架构或路线图的最终裁决文档。

- 架构事实仍以 `docs/architecture/v4-architecture.md` 与代码为准
- 是否做、何时做、哪些明确不做，仍以 `docs/plans/decisions/roadmap-backlog-and-boundaries-2026-05.md` 为准
