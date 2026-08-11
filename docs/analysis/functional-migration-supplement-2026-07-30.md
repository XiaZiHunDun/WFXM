# 函数式架构迁移 — 补充方案

> **补充日期**：2026-07-30  
> **补充内容**：数据迁移、POC 收窄、双写一致性、明确不采用项

---

## 一、数据迁移子方案

### 1.1 现有数据资产盘点

| 数据类型 | 当前存储 | 规模（估算） | 迁移方式 |
|----------|----------|-------------|----------|
| **向量数据** | ChromaDB | ~10 万条嵌入 | ChromaDB export → pgvector import |
| **会话记录** | SQLite (aiosqlite) | ~5 万条会话 | SQLite dump → PostgreSQL import |
| **Transcript** | JSONL 文件 | ~20 万轮对话 | 文件解析 → PostgreSQL COPY |
| **记忆观察** | `observation_store.py` | ~5 万条观察 | ETL 脚本双写 |
| **配置数据** | YAML/JSON 文件 | 少量 | 手动迁移 |

### 1.2 数据迁移三阶段

```
阶段 1: 预迁移（Week 1-2）
┌─────────────────────────────────────────────────┐
│  1. 在 PostgreSQL 中创建目标表结构（Drizzle）       │
│  2. 编写 ChromaDB → pgvector 导出脚本             │
│  3. 编写数据校验脚本（比对导入前后一致性）          │
│  4. 在测试环境全量迁移一次，记录耗时和校验结果       │
│  5. 备份原始数据，标记迁移版本号                    │
└─────────────────────────────────────────────────┘

阶段 2: 双写期（与迁移并行，Week  ）
┌─────────────────────────────────────────────────┐
│  1. 新数据同时写入 ChromaDB + pgvector             │
│  2. 异步校验双写一致性                            │
│  3. 不一致数据进入修复队列                         │
│  4. 老系统数据通过 ETL 脚本增量同步                 │
└─────────────────────────────────────────────────┘

阶段 3: 切换期（Week N）
┌─────────────────────────────────────────────────┐
│  1. 冻结 ChromaDB 写入（只读模式）                  │
│  2. 最终全量同步 ChromaDB → pgvector              │
│  3. 校验数据完整性（100% 匹配）                    │
│  4. 切换向量查询到 pgvector                       │
│  5. 归档 ChromaDB 数据（保留 30 天回滚窗口）        │
│  6. 停用 ChromaDB                                 │
└─────────────────────────────────────────────────┘
```

### 1.3 ChromaDB → pgvector 迁移脚本

```python
# scripts/migrate_chroma_to_pgvector.py
# Phase 1: 一次性数据迁移脚本

import time
import hashlib
from typing import Iterator

class ChromaToPVectorMigrator:
    def __init__(self, chroma_client, pg_pool, batch_size=1000):
        self._chroma = chroma_client
        self._pg = pg_pool
        self._batch_size = batch_size
        self._migration_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
    
    def run(self):
        """执行全量迁移"""
        print(f"[Migration {self._migration_id}] Starting...")
        
        # Step 1: 导出 ChromaDB 数据
        records = self._export_chroma()
        total = len(records)
        print(f"[Migration] Exported {total} records from ChromaDB")
        
        # Step 2: 分批导入 PostgreSQL
        self._import_to_pgvector(records)
        print(f"[Migration] Imported to pgvector")
        
        # Step 3: 校验完整性
        self._verify_integrity(total)
        print(f"[Migration] Verification passed")
        
        return self._migration_id
    
    def _export_chroma(self) -> list[dict]:
        """导出 ChromaDB 全部数据"""
        collection = self._chroma.get_or_create_collection("observations")
        
        # 分批导出（避免内存溢出）
        records = []
        offset = 0
        while True:
            batch = collection.get(
                limit=self._batch_size,
                offset=offset,
                include=["embeddings", "metadatas", "documents"]
            )
            if not batch["ids"]:
                break
            
            for i, id_ in enumerate(batch["ids"]):
                records.append({
                    "id": id_,
                    "embedding": batch["embeddings"][i],
                    "metadata": batch["metadatas"][i],
                    "document": batch["documents"][i],
                })
            offset += self._batch_size
        
        return records
    
    def _import_to_pgvector(self, records: list[dict]):
        """分批导入 PostgreSQL"""
        for i in range(0, len(records), self._batch_size):
            batch = records[i:i + self._batch_size]
            
            # 使用 COPY 或批量 INSERT
            values = [
                (
                    r["id"],
                    r["embedding"],
                    r["metadata"],
                    r["document"],
                    self._migration_id,
                    time.time()
                )
                for r in batch
            ]
            
            # 批量写入
            self._pg.executemany("""
                INSERT INTO observations 
                    (id, embedding, metadata, document, migration_id, migrated_at)
                VALUES (%s, %s::vector, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
            """, values)
    
    def _verify_integrity(self, expected_count: int):
        """校验数据完整性"""
        result = self._pg.execute("""
            SELECT COUNT(*) FROM observations 
            WHERE migration_id = %s
        """, (self._migration_id,))
        actual_count = result.scalar()
        
        if actual_count < expected_count:
            raise MigrationError(
                f"Data mismatch: expected {expected_count}, got {actual_count}"
            )
        
        # 抽样校验
        sample_ids = self._chroma.get(limit=100)["ids"]
        for id_ in sample_ids:
            chroma_data = self._chroma.get(ids=[id_])
            pg_data = self._pg.execute(
                "SELECT * FROM observations WHERE id = %s", (id_,)
            ).fetchone()
            
            if not pg_data:
                raise MigrationError(f"Missing record in pgvector: {id_}")
        
        print(f"[Migration] Verified {actual_count}/{expected_count} records")
```

### 1.4 Transcript JSONL → PostgreSQL 迁移

```python
# scripts/migrate_transcripts_to_postgres.py

import json
from pathlib import Path

class TranscriptMigrator:
    def run(self, transcript_dir: str):
        """迁移 transcript.jsonl 文件到 PostgreSQL"""
        transcript_path = Path(transcript_dir)
        
        for jsonl_file in transcript_path.glob("**/transcript.jsonl"):
            session_id = jsonl_file.parent.name
            
            # 逐行解析 JSONL
            records = []
            with open(jsonl_file) as f:
                for line_num, line in enumerate(f, 1):
                    try:
                        record = json.loads(line)
                        record["session_id"] = session_id
                        record["line_number"] = line_num
                        records.append(record)
                    except json.JSONDecodeError:
                        self._log_warning(f"Corrupt line {line_num} in {jsonl_file}")
            
            # 批量写入 PostgreSQL
            self._insert_transcript_batch(records)
    
    def _insert_transcript_batch(self, records: list[dict]):
        """批量插入 transcript"""
        # 使用 COPY 命令（高性能）
        columns = ["session_id", "role", "content", "timestamp", "metadata", "line_number"]
        
        with self._pg.copy(
            f"COPY transcripts ({', '.join(columns)}) FROM STDIN"
        ) as copy:
            for record in records:
                row = (
                    record["session_id"],
                    record["role"],
                    record["content"],
                    record.get("timestamp"),
                    json.dumps(record.get("metadata", {})),
                    record["line_number"],
                )
                copy.write(row)
```

### 1.5 数据校验与回滚

```python
# scripts/verify_data_migration.py

class MigrationVerifier:
    """数据迁移校验器"""
    
    def verify(self, migration_id: str):
        """全量校验"""
        checks = [
            self._check_record_count(migration_id),
            self._check_embedding_dimensions(migration_id),
            self._check_metadata_integrity(migration_id),
            self._check_document_content(migration_id),
            self._check_id_consistency(migration_id),
        ]
        
        results = [check() for check in checks]
        
        if all(results):
            print("[Verification] ALL CHECKS PASSED")
        else:
            failed = [i for i, r in enumerate(results) if not r]
            raise VerificationError(f"Failed checks: {failed}")
    
    def rollback(self, migration_id: str):
        """回滚迁移（删除本次迁移的数据）"""
        self._pg.execute("""
            DELETE FROM observations WHERE migration_id = %s
        """, (migration_id,))
        print(f"[Rollback] Deleted data for migration {migration_id}")
```

---

## 二、POC 收窄方案

### 2.1 原 POC 范围（过宽）

```
❌ 原范围：
  - 实现完整 Agent Loop
  - 支持多轮对话
  - 11 个工具
  - 完整 LLM retry
  - 上下文压缩
```

### 2.2 收窄后 POC 范围（聚焦 3 个最高风险验证点）

#### 验证点 1：上下文压缩管线（ContextPipeline 的多阶段 pipe 组合）

```typescript
// src/poc/context-pipeline.test.ts
// 验证：多阶段 pipe 组合的类型安全和可组合性

import { Effect, pipe } from "effect"

// 目标：验证 Effect 能否表达 Butler 的 ContextPipeline 五阶段

// Stage 1: tool_prune（分级 micro 剪枝）
const toolPrune = (messages: Message[]) =>
  Effect.succeed(messages.filter(m => !isLargeToolResult(m)))

// Stage 2: compress_context（阈值门控压缩）
const compressContext = (messages: Message[]) =>
  Effect.gen(function* (_) {
    if (estimateTokens(messages) > TOKEN_THRESHOLD) {
      const summary = yield* _(llmSummarize(messages))
      return [...summary, ...messages.slice(-5)]
    }
    return messages
  })

// Stage 3: post_compact（锚点重注入）
const postCompact = (messages: Message[]) =>
  Effect.succeed([
    ...messages,
    { role: "system", content: "MEMORY: ..." },
    { role: "system", content: "TASKS: ..." },
  ])

// Stage 4: repair_message_sequence
const repairSequence = (messages: Message[]) =>
  Effect.succeed(deduplicateToolMessages(messages))

// Stage 5: sanitize_api
const sanitizeApi = (messages: Message[]) =>
  Effect.succeed(removeThinkingOnly(messages))

// 组合为管线
const contextPipeline = pipe(
  toolPrune,
  compressContext,
  postCompact,
  repairSequence,
  sanitizeApi
)

// 验证指标
// ✅ 类型安全：全链路类型推断正确
// ✅ 可组合：每个阶段可独立测试和替换
// ✅ 性能：1000 条消息处理 < 10ms
// ✅ 并发：多会话管线可并行执行
```

#### 验证点 2：LLM retry/failover 链（Effect.retry + Schedule 表达力）

```typescript
// src/poc/llm-retry-chain.test.ts
// 验证：Effect 的重试、超时、failover 能力

import { Effect, Schedule, Clock, Fiber } from "effect"

// 场景：模拟 Butler 的 llm_retry 逻辑
// 1. 空内容重试（最多 3 次）
// 2. schema 降级重试（最多 2 次）
// 3. 压缩回退（1 次）
// 4. Provider failover（3 家厂商）
// 5. 超时（30 秒）

const callLLMWithRetry = (messages: Message[]) =>
  Effect.gen(function* (_) {
    const providers = ["minimax", "anthropic", "deepseek"]
    let lastError: LLMError | null = null
    
    for (const provider of providers) {
      try {
        // 5. 超时控制
        const result = yield* _(
          callProvider(provider, messages).pipe(
            Effect.timeout("30 seconds")
          )
        )
        
        // 1. 空内容检测
        if (isEmptyResponse(result)) {
          // 带退避的重试（最多 3 次）
          const retried = yield* _(
            callProvider(provider, messages).pipe(
              Effect.retry(
                Schedule.spaced("1 second").pipe(
                  Schedule.exponentialBackoff("1 second"),
                  Schedule.recurs(2)
                )
              )
            )
          )
          return retried
        }
        
        // 2. Schema 错误降级
        if (hasSchemaError(result)) {
          const downgraded = yield* _(
            callProviderWithSimplifiedSchema(provider, messages).pipe(
              Effect.retry(Schedule.recurs(1))
            )
          )
          return downgraded
        }
        
        return result
      } catch (error) {
        lastError = error as LLMError
        continue
      }
    }
    
    // 3. 压缩回退
    const compressedMessages = yield* _(compressMessages(messages))
    return yield* _(callLLMWithRetry(compressedMessages))
  })

// 验证指标
// ✅ 重试语义：与 Butler v4 llm_retry.py 行为一致
// ✅ 超时控制：30 秒硬性超时
// ✅ Failover：3 家厂商按顺序切换
// ✅ 可观测：重试次数、失败原因可追踪
```

#### 验证点 3：并行工具批调度（Effect.all + Fiber 并发模型）

```typescript
// src/poc/parallel-tools.test.ts
// 验证：Effect Fiber 的并发调度能力

import { Effect, Fiber, Queue, Semaphore } from "effect"

// 场景：模拟 Butler 的 parallel_tools 逻辑
// 1. 工具并行执行（最多 5 个并发）
// 2. 单个工具失败不影响其他
// 3. 支持中断（interrupt）和 halt
// 4. 结果按完成顺序收集

const executeToolsParallel = (
  tools: ToolCall[],
  maxConcurrency: number = 5
) =>
  Effect.gen(function* (_) {
    const semaphore = yield* _(Semaphore.make(maxConcurrency))
    
    // 为每个工具创建 Fiber
    const fibers = tools.map((tool) =>
      Effect.acquireRelease(
        semaphore.acquire,
        () => semaphore.release
      ).pipe(
        Effect.zipRight(executeTool(tool)),
        Effect.fork
      )
    )
    
    // 等待所有 Fiber 完成
    const results = yield* _(
      Effect.all(fibers.map(
        (fiber) => Effect.race(
          fiber.join,
          Effect.timeout("30 seconds")
        )
      ))
    )
    
    return results
  })

// 验证指标
// ✅ 并发控制：最多 N 个工具同时执行
// ✅ 失败隔离：单个工具失败不影响其他
// ✅ 中断支持：可随时中断所有工具
// ✅ 性能：5 个并发工具 < 串行的 3 倍耗时
// ✅ 结果排序：支持按完成时间排序
```

### 2.3 POC 交付清单（收窄版）

| # | 交付物 | 内容 | 预计时间 |
|---|--------|------|----------|
| 1 | ContextPipeline 验证 | 5 阶段 pipe 组合 + 性能测试 | 3 天 |
| 2 | LLM Retry 验证 | 重试/超时/failover 链 + 语义对比 | 4 天 |
| 3 | Parallel Tools 验证 | Fiber 并发 + 信号量控制 + 性能测试 | 3 天 |
| 4 | 验证报告 | 3 项验证的详细报告 + 基准测试对比 | 2 天 |

**总计**：2 周（10 个工作日）

### 2.4 POC 验收标准

| 验证点 | 通过条件 | 阻塞条件 |
|--------|----------|----------|
| ContextPipeline | 5 阶段 pipe 组合类型安全，性能 > Python 版 150% | 阶段间类型不兼容 |
| LLM Retry | 所有重试路径与 Python 版行为一致 | 重试语义偏差 |
| Parallel Tools | 并发执行正确，性能 > Python 版 200% | 并发结果错误 |

---

## 三、Outbox Pattern 双写一致性保障

### 3.1 双写一致性问题

```
问题场景：
  用户请求 → 写入 TS 新系统
           → 异步镜像 → 写入 Python 老系统

风险：
  1. TS 写入成功，Python 写入失败 → 数据不一致
  2. Python 写入延迟 → 读取时拿到旧数据
  3. 两边同时修改同一条数据 → 冲突
```

### 3.2 Outbox Pattern 设计

```
┌─────────────────────────────────────────────────────┐
│                  Outbox Pattern                     │
│                                                     │
│  Step 1: 主事务（同步，保证一致性）                   │
│  ┌─────────────────────────────────────────────┐   │
│  │  BEGIN TRANSACTION                          │   │
│  │    1. 写入主业务数据（TS 系统）                 │   │
│  │    2. 写入 outbox_events 表                   │   │
│  │  COMMIT                                     │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  Step 2: 异步派发（最终一致性）                      │
│  ┌─────────────────────────────────────────────┐   │
│  │  后台 Worker 轮询 outbox_events              │   │
│  │    → 读取待派发事件                          │   │
│  │    → 发送到 Python 老系统                     │   │
│  │    → 标记事件为已处理                         │   │
│  │    → 失败则重试（指数退避）                    │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  Step 3: 不一致修复                                │
│  ┌─────────────────────────────────────────────┐   │
│  │  定期校验 Worker                              │   │
│  │    → 比对 TS 和 Python 数据                   │   │
│  │    → 不一致记录到 repair_queue               │   │
│  │    → 补偿事务修复                             │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 3.3 PostgreSQL Outbox Schema

```sql
-- outbox_events 表
CREATE TABLE outbox_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type  VARCHAR(50) NOT NULL,    -- 如 "observation"
    aggregate_id    VARCHAR(255) NOT NULL,   -- 如 "obs_12345"
    event_type      VARCHAR(50) NOT NULL,    -- 如 "created", "updated"
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ,
    error_message   TEXT,
    retry_count     INT NOT NULL DEFAULT 0,
    max_retries     INT NOT NULL DEFAULT 5,
    
    -- 索引
    INDEX idx_outbox_unprocessed 
      (processed_at NULLS FIRST, created_at),
    INDEX idx_outbox_aggregate 
      (aggregate_type, aggregate_id)
);

-- repair_queue 表（不一致修复）
CREATE TABLE repair_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system   VARCHAR(20) NOT NULL,   -- "ts" or "python"
    target_system   VARCHAR(20) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       VARCHAR(255) NOT NULL,
    source_hash     VARCHAR(64) NOT NULL,   -- SHA-256
    target_hash     VARCHAR(64),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    repaired_at     TIMESTAMPTZ,
    error_message   TEXT
);
```

### 3.4 Outbox Worker 实现

```typescript
// src/infrastructure/outbox/outbox-worker.ts

import { Effect, Queue, Schedule } from "effect"

// Outbox Worker：异步派发事件到 Python 老系统
const outboxWorker = Effect.gen(function* (_) {
  const pg = yield* _(PostgresPool)
  const pythonClient = yield* _(PythonBridgeClient)

  // 轮询间隔：每 500ms 检查一次
  const pollInterval = Schedule.spaced("500 millis")

  // 主循环
  const run = Effect.repeat(
    Effect.gen(function* (_) {
      // 1. 读取待处理事件
      const events = yield* _(
        pg.query`
          SELECT * FROM outbox_events
          WHERE processed_at IS NULL
          ORDER BY created_at
          LIMIT 100
        `
      )

      if (events.length === 0) {
        return
      }

      // 2. 批量发送到 Python
      for (const event of events) {
        try {
          yield* _(
            pythonClient.syncEntity({
              type: event.aggregateType,
              id: event.aggregateId,
              data: event.payload,
            })
          )

          // 3. 标记为已处理
          yield* _(
            pg.query`
              UPDATE outbox_events
              SET processed_at = NOW()
              WHERE id = ${event.id}
            `
          )
        } catch (error) {
          // 4. 失败处理
          yield* _(
            pg.query`
              UPDATE outbox_events
              SET retry_count = retry_count + 1,
                  error_message = ${String(error)}
              WHERE id = ${event.id}
            `
          )

          // 超过最大重试次数 → 进入修复队列
          if (event.retry_count + 1 >= event.maxRetries) {
            yield* _(
              pg.query`
                INSERT INTO repair_queue 
                  (source_system, target_system, entity_type, entity_id)
                VALUES ('ts', 'python', ${event.aggregateType}, ${event.aggregateId})
              `
            )
          }
        }
      }
    }),
    pollInterval
  )

  // 优雅关闭
  return yield* _(
    Effect.acquireRelease(
      Effect.succeed(undefined),
      () => Effect.log("Outbox worker shutting down")
    )
  ).pipe(run)
})
```

### 3.5 一致性校验与修复

```typescript
// src/infrastructure/outbox/consistency-checker.ts

const consistencyChecker = Effect.gen(function* (_) {
  const pg = yield* _(PostgresPool)
  const pythonClient = yield* _(PythonBridgeClient)

  // 定期一致性校验（每小时）
  const checkInterval = Schedule.spaced("1 hour")

  const run = Effect.repeat(
    Effect.gen(function* (_) {
      // 1. 获取最近 24 小时的实体
      const entities = yield* _(
        pg.query`
          SELECT entity_type, entity_id, hash 
          FROM observations 
          WHERE updated_at > NOW() - INTERVAL '24 hours'
        `
      )

      for (const entity of entities) {
        try {
          // 2. 从 Python 获取对应实体
          const pythonEntity = yield* _(
            pythonClient.getEntity(entity.entityType, entity.entityId)
          )

          // 3. 比对 hash
          if (entity.hash !== pythonEntity.hash) {
            // 4. 不一致 → 加入修复队列
            yield* _(
              pg.query`
                INSERT INTO repair_queue
                  (source_system, target_system, entity_type, entity_id, 
                   source_hash, target_hash)
                VALUES 
                  ('ts', 'python', 
                   ${entity.entityType}, ${entity.entityId},
                   ${entity.hash}, ${pythonEntity.hash})
              `
            )
          }
        } catch {
          // Python 端不存在该实体 → 补写
          yield* _(
            pythonClient.syncEntity({
              type: entity.entityType,
              id: entity.entityId,
              data: yield* _(pg.query`
                SELECT * FROM observations WHERE id = ${entity.entityId}
              `),
            })
          )
        }
      }
    }),
    checkInterval
  )

  return run
})
```

---

## 四、明确不采用项清单

### 4.1 POC 阶段不采用项

| # | 技术 | 不采用原因 | 风险 |
|---|------|-----------|------|
| 1 | **Event Sourcing 全量引入** | 复杂度高，POC 阶段无必要 | 范围蔓延 |
| 2 | **CQRS 全量分离** | 读写分离对 POC 过于复杂 | 范围蔓延 |
| 3 | **Scala 双语言** | 团队无法同时掌握两种函数式语言 | 交付延迟 |
| 4 | **fp-ts 与 Effect-TS 混用** | 两个库的概念重叠，增加认知负担 | 可维护性 |
| 5 | **WASM 沙箱** | 技术不成熟，不是 POC 验证重点 | 风险过高 |
| 6 | **Kafka/RabbitMQ** | 消息队列引入过早 | 运维复杂度 |
| 7 | **全量 MCP Host 重写** | MCP 协议复杂，POC 阶段不涉及 | 范围蔓延 |

### 4.2 迁移全期不采用项

| # | 技术 | 不采用原因 | 替代方案 |
|---|------|-----------|----------|
| 1 | **Rust 重写** | 团队无法掌握 | TypeScript + Effect-TS |
| 2 | **ZIO 替代 Effect-TS** | Scala 生态在 AI 领域支持弱 | Effect-TS 已足够 |
| 3 | **DynamoDB/MongoDB** | PostgreSQL + pgvector 更适合 | PostgreSQL |
| 4 | **gRPC 全量替换** | 保留 Python 通信的 HTTP fallback | HTTP + JSON |
| 5 | **自研 ORM** | Drizzle 已足够强大 | Drizzle ORM |
| 6 | **分布式追踪全量引入** | 先实现核心功能 | OpenTelemetry 最小化接入 |

### 4.3 明确采用项

| # | 技术 | 采用原因 | 预期收益 |
|---|------|---------|----------|
| 1 | **TypeScript 5.5+** | 类型安全、生态成熟 | 减少运行时错误 |
| 2 | **Effect-TS 3.x** | Fiber、Layer、Schedule | 统一并发模型 |
| 3 | **Zod 3.x** | Schema 校验 | 类型安全的数据验证 |
| 4 | **Drizzle ORM** | 类型安全的 SQL 构建 | 数据库访问类型安全 |
| 5 | **PostgreSQL + pgvector** | 关系型 + 向量一体化 | 简化存储架构 |
| 6 | **Hono** | 轻量 HTTP 框架 | 高性能 Web 服务 |
| 7 | **Vitest** | 与 TS 深度集成的测试框架 | 高效测试开发 |
| 8 | **Outbox Pattern** | 最终一致性保障 | 双写数据一致性 |

---

## 五、更新后的时间线

| 阶段 | 内容 | 周期 | 关键产出 |
|------|------|------|----------|
| **Week 1-2** | **POC 验证（收窄版）** | 2 周 | ContextPipeline/LLM Retry/Parallel Tools 三项验证报告 |
| **Week 3-4** | **Phase 0：基础设施 + ACL** | 2 周 | 项目骨架、Outbox、数据迁移脚本 |
| **Week 5** | **预迁移：ChromaDB → pgvector** | 1 周 | 数据迁移完成、校验通过 |
| **Week 6-8** | **Phase 1：低风险模块** | 3 周 | permissions/、ops/ 迁移完成 |
| **Week 9-12** | **Phase 2：中等风险模块** | 4 周 | transport/、mcp/、skills/ 迁移完成 |
| **Week 13-16** | **Phase 3：核心业务模块** | 4 周 | memory/、tools/ 迁移完成 |
| **Week 17-22** | **Phase 4：最高风险模块** | 6 周 | core/、gateway/ 迁移完成 |
| **Week 23-24** | **收尾：文档 + 测试 + 退役** | 2 周 | 完整文档、Python 代码归档 |

**总计**：约 6 个月（POC + 全量迁移 + 收尾）
