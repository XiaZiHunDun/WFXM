# Phase 5 — 日志与轨迹信息收集体系（P0）

> **状态**：待批准（Spec Mode）
> **目标**：在移动端窄通道场景下，让后台失败、卡住、异常可被事后定位：
> 用户只看到「错误码 + turnId 前 8 位」，Owner 可查全量 trace / 诊断。

## 1. 背景

当前问题：

- 微信 / 移动端用户看不到服务器日志，`runButlerLoop` 失败后只回一句通用降级文案，
  无法把用户反馈与服务器日志对应起来。
- `LocalTracer` 只有进程内环形缓冲（默认 500 条），进程重启即丢；
  `/v1/owner/traces` 也只能看当前进程。
- `/healthz` 只返回 `{status:"ok", wiring:"v5"}`，无法判断 DB、outbox 积压、
  待审批、最近成功 Run、trace 写队列是否异常。
- `turnId` 在 intake 生成后没有贯穿到 Run / 子代理 / 审批 / 出站回复。

## 2. 目标与非目标

### P0（本 spec）

1. 错误码注册表 + 失败回复信封（用户可反馈定位信息）。
2. `turnId` 贯穿：入站 → Run / LLM trace → 子代理 → 审批 → 出站。
3. `trace_events` 表 + 迁移；`LocalTracer` 异步批量双写（内存 + DB）。
4. 进程退出 / SIGINT / SIGTERM 前 flush；默认保留 30 天 / 20 万条。
5. `/healthz` 扩展为依赖诊断；新增 `GET /v1/owner/diagnostics`。
6. 单测 + API 诊断测试覆盖。

### 非目标（P1，不在本次）

- 微信 `日志` / `状态` 指令。
- 卡住（heartbeat）主动告警。
- 控制台诊断页。
- `pnpm trace:export` JSONL 导出 CLI。
- OTLP 外送 / 远端采集。
- 抽公共仓库（先以 `packages/*` 内的边界实现，成熟后再抽）。

## 3. 设计决策

### 3.1 边界归属

- **domain**：trace 事件结构、错误码注册表、格式化（纯函数，无 IO）。
- **runtime**：`LocalTracer` 内存环形缓冲 + 异步批量 sink。
- **persistence**：`trace_events` 表、`TraceStore`（append/list/count/prune）。
- **apps/api**：组装 sink、诊断聚合、失败信封、路由鉴权。
- 不引入新包；不新增第三方依赖；不并入 agent-eval。

### 3.2 错误码

固定短码（稳定、可 grep），注册表含标题、是否可重试、Owner 提示：

| 错误码 | 含义 | 典型来源 |
|--------|------|----------|
| `E-LLM-01` | 模型调用失败 / 超时 / 网络不可达 | `LLMUnavailable`、fetch timeout |
| `E-CTX-01` | 上下文超限 | `ContextOverflow` |
| `E-TOOL-01` | 工具执行失败 | `ToolFailed` |
| `E-POL-01` | 策略 / 审批拒绝 | `GuardRejected`、approval denied |
| `E-RUN-01` | 运行冲突 / 状态非法 | `ActiveMainRunConflict`、`CompletedMainRunReplay` |
| `E-DB-01` | 持久化失败 | `PersistenceFailed`、DB 异常 |
| `E-REQ-01` | 请求非法 | 非法 body / RunTrigger |
| `E-INT-01` | 未归类内部错误 | 兜底 |

未知错误一律 `E-INT-01`，不向用户泄露原始异常文本。

### 3.3 用户可见失败信封

普通用户只看到：

```
[E-LLM-01 · turn-172] 处理失败，已记录。请稍后再发一次；若反复出现，请把这条信息发给管理员。
```

- `turnId` 取 `turn-<ms>` 的前 8 位（字面前 8 个字符）。
- 原始错误只进 trace / 日志，不进回复。
- Owner 通过 `GET /v1/owner/traces?turnId=...` 或 `/v1/owner/diagnostics` 看全量。

### 3.4 turnId 贯穿

- `normalizeWechatInbound` / `normalizeChannelInbound` 已生成 `turnId`，无需改。
- `runButlerLoop` 新增可选 `turnId`，写入：
  - 所有 LLM `step` trace 的 `detail.turnId` 与一等字段 `turnId`；
  - 失败 `run` trace；
  - 审批 `approval` trace。
- `routeWechatIntake` / `inbound.ts` / `channel-inbound.ts` 透传。
- 子代理：`delegate_to_subagent` 的 outbox payload 增加 `turnId`；
  `subagent-worker` 解析后写入子代理 LLM trace。若调用点无法拿到 turnId，
  退化为只记录 `parentRunId`，不阻塞主流程。
- 审批恢复：`tryWechatInlineApproval` → `resumeApprovedCapability` →
  `continueLoopAfterCapability` 透传 `turnId`，写入 trace。

### 3.5 trace 双写

- `TraceEvent` 新增一等字段 `turnId: string | null`（向后兼容，默认 null）。
- `LocalTracer`：
  - `record` 仍同步写环形缓冲；
  - 配置 `sink` 时进入队列，达到批量阈值（默认 50）或间隔（默认 2000ms）
    异步写入；
  - `flush()` 手动刷；`close()` 清定时器 + flush；
  - sink 失败计数并丢弃该批（只记 stderr），绝不阻塞主流程；
  - 定时器 `unref()`，不阻止进程退出。
- 启动时 `resetSharedLocalTracer(env, { sink: traceStore })`；
  SIGINT / SIGTERM / 进程收尾统一 flush。
- 保留策略：启动时 + 每小时（unref）执行 `prune`：
  - `BUTLER_V5_TRACE_RETENTION_DAYS` 默认 30；
  - `BUTLER_V5_TRACE_MAX_ROWS` 默认 200000。

### 3.6 健康检查与诊断

`GET /healthz` 保持 200/503 语义，附加：

- `db`: ok / latency_ms；
- `outbox`: 按状态计数、最老待投递延迟；
- `approvals`: 待审批 step 数；
- `runs`: 最近成功 Run 时间；
- `traces`: 内存条数、写队列待刷数、丢弃数、持久化总行数。
- 无 `wiring.db`（历史单测 stub）时降级为 `status:"ok"`，不 503。

`GET /v1/owner/diagnostics`：
- 复用同一聚合结果；
- 增加错误码注册表、trace 配置（enabled/redact/exporter/保留策略）；
- 仅 loopback Owner 可访问，沿用 `ownerAuthorized`。

## 4. 数据结构

### 4.1 `trace_events`

```sql
CREATE TABLE IF NOT EXISTS trace_events (
  id uuid PRIMARY KEY NOT NULL,
  kind text NOT NULL,
  name text NOT NULL,
  status text NOT NULL,
  turn_id text,
  conversation_id text,
  run_id text,
  step_id text,
  parent_run_id text,
  subject text,
  trigger_source text,
  capability text,
  policy_decision text,
  grant_id text,
  waiting_step_id text,
  duration_ms integer,
  token_input integer,
  token_output integer,
  token_total integer,
  cost_usd double precision,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL
);
```

索引：`(created_at)`、`(run_id, created_at)`、`(conversation_id, created_at)`、
`(turn_id, created_at)`、`(kind, created_at)`。

不建外键：trace 需在 Run / conversation 清理后仍可追溯，且避免写入顺序耦合。

### 4.2 诊断返回（示例）

```json
{
  "status": "ok",
  "wiring": "v5",
  "checks": {
    "db": { "status": "up", "latency_ms": 1 },
    "outbox": { "pending": 0, "failed": 0, "oldest_pending_age_ms": 0 },
    "approvals": { "waiting": 0 },
    "runs": { "last_succeeded_at": "2026-11-24T09:00:00.000Z" },
    "traces": { "memory": 42, "pending_write": 0, "dropped": 0, "persisted": 1024 }
  },
  "trace": { "enabled": true, "redact": true, "exporter": "off", "retention_days": 30, "max_rows": 200000 }
}
```

## 5. 精确改动清单

### 5.1 domain

| 文件 | 改动 |
|------|------|
| `packages/domain/src/observability/error-codes.ts`（新增） | `TraceErrorCode`、`ERROR_CODES`、`resolveErrorCode(err)`、`turnIdShort(turnId)`、`formatFailureEnvelope({code,turnId})` |
| `packages/domain/src/observability/local-trace.ts` | `TraceEvent.turnId`、`CreateTraceEventInput.turnId`、`createTraceEvent` 映射、`filterTraceEvents` 支持 `turnId`、OTel 行增加 `butler.turnId` |
| `packages/domain/src/observability/error-codes.test.ts`（新增） | 错误映射、信封格式、turnId 截断、未知错误兜底 |

### 5.2 runtime

| 文件 | 改动 |
|------|------|
| `packages/runtime/src/observability/local-tracer.ts` | 新增 `TraceSink`；`createLocalTracer(env, { writeStdout?, sink?, batchSize?, flushIntervalMs? })`；`pending()` / `stats()` / `flush()` / `close()`；`resetSharedLocalTracer(env, opts?)` 先关闭旧实例 |
| `packages/runtime/src/observability/local-tracer.test.ts` | 新增 sink 批量、flush、close、sink 失败不抛出、disabled 不写 sink 用例 |

### 5.3 persistence

| 文件 | 改动 |
|------|------|
| `packages/persistence/src/schema.ts` | 新增 `traceEvents` 表定义（字段见 §4.1） |
| `packages/persistence/src/migrations/0018_trace_events.sql`（新增） | 建表 + 5 个索引 |
| `packages/persistence/src/migrations/run-migrations.ts` | 注册 `0018_trace_events.sql` |
| `packages/persistence/src/migrations/migrations-registry.test.ts` | 断言包含 `trace_events` 与索引 |
| `packages/persistence/src/trace-store.ts`（新增） | `createTraceStore(db)`：`append` / `list` / `count` / `oldestCreatedAt` / `prune({retainDays,maxRows,now})` |
| `packages/persistence/src/index.ts` | 导出 `createTraceStore` 与类型 |
| `packages/persistence/src/trace-store.test.ts`（新增） | append/list 过滤（runId/conversationId/turnId/kind/limit）、prune 按时间与行数、空表 |

### 5.4 apps/api

| 文件 | 改动 |
|------|------|
| `apps/api/src/wechat-inbound-butler.ts` | `args.turnId?`；LLM trace 与失败 trace 带 turnId；失败回复改为 `formatFailureEnvelope` + 提示；记录 `run/failure` error trace |
| `apps/api/src/wechat-intake.ts` | `routeWechatIntake` 新增 `turnId?`；透传 `runButlerLoop` |
| `apps/api/src/routes/inbound.ts` | 传 `turnId: value.turnId` / `normalized.value.turnId` |
| `apps/api/src/channel-inbound.ts` | 传 `turnId` 给 `runButlerLoop` |
| `apps/api/src/tools.ts` | `makeWeibutlerTools` 接受 `turnId?`；delegate 调用透传（读文件确认调用点后做最小改动） |
| `packages/runtime/src/delegate-runtime.ts` | `delegateToSubagent` 输入 `turnId?`，outbox payload 写入 |
| `apps/api/src/subagent-worker-payload.ts` | 解析 `turnId` |
| `apps/api/src/subagent-worker.ts` | `runChildLlm` 接收 turnId，写入 LLM trace |
| `apps/api/src/approval-resume.ts` | `resumeApprovedCapability` / `continueLoopAfterCapability` 可选 turnId，写 trace |
| `apps/api/src/wechat-inline-approval.ts` | 接收 `turnId` 并透传恢复流程 |
| `apps/api/src/wiring.ts` | 新增 `traceStore: TraceStore | null`（配置可选） |
| `apps/api/src/bootstrap-wiring.ts` | 创建 `traceStore`；`resetSharedLocalTracer(env,{sink})`；启动 prune |
| `apps/api/src/diagnostics.ts`（新增） | `collectDiagnostics(wiring)`：DB/outbox/approvals/runs/traces 聚合，兼容无 db 的 stub |
| `apps/api/src/routes.ts` | `/healthz` 改 async，使用 `collectDiagnostics`，ok→200 / degraded→503 |
| `apps/api/src/owner-routes/traces-procedures-tasks.ts` | 新增 `GET /v1/owner/diagnostics`（ownerAuthorized） |
| `apps/api/src/index.ts` | SIGINT/SIGTERM/收尾 flush + close tracer；启动 1h 保留清理（unref） |
| `apps/api/src/diagnostics.test.ts`（新增） | 空库健康；插入 waiting approval / outbox / run 后计数与 latency；无 db stub 返回 ok |
| `apps/api/src/owner-diagnostics.test.ts`（新增） | Owner 路由返回 checks + trace 配置；非授权路径（有 X-Forwarded-For）拒绝 |

### 5.5 文档

| 文件 | 改动 |
|------|------|
| `docs/PROGRESS.md` | 追加 Phase 5 P0 状态与验证证据（实施完成后） |

## 6. 配置项

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `BUTLER_V5_TRACE` | `1` | 总开关 |
| `BUTLER_V5_TRACE_REDACT` | `1` | 脱敏 |
| `BUTLER_V5_TRACE_MAX_EVENTS` | `500` | 内存环形缓冲 |
| `BUTLER_V5_TRACE_BATCH_SIZE` | `50` | 批量写阈值 |
| `BUTLER_V5_TRACE_FLUSH_MS` | `2000` | 定时 flush |
| `BUTLER_V5_TRACE_RETENTION_DAYS` | `30` | 保留天数 |
| `BUTLER_V5_TRACE_MAX_ROWS` | `200000` | 最大行数 |
| `BUTLER_V5_OTEL_EXPORTER` | `off` | 现有 stdout 导出保持 |

## 7. 验证方案

```bash
pnpm vitest run packages/domain/src/observability/error-codes.test.ts
pnpm vitest run packages/runtime/src/observability/local-tracer.test.ts
pnpm vitest run packages/persistence/src/trace-store.test.ts
pnpm vitest run packages/persistence/src/migrations/migrations-registry.test.ts
pnpm vitest run apps/api/src/diagnostics.test.ts apps/api/src/owner-diagnostics.test.ts
pnpm vitest run apps/api/src/wechat-inbound-butler.test.ts apps/api/src/wechat-inline-approval.test.ts
pnpm typecheck
pnpm lint
```

补充人工验证（可选）：

1. 启动 API，制造一次 LLM 失败（错误 key / 断网）→ 微信侧收到
   `[E-LLM-01 · turn-...]`；`/v1/owner/traces?turnId=...` 能查到同 turnId 的
   `run/failure` 与 `step/llm_call`。
2. `/healthz` 在 DB 正常时 200，停库后 503；`/v1/owner/diagnostics` 可看到
   outbox / 待审批 / trace 队列。

## 8. 风险与回滚

- **写入放大**：默认 2000ms / 50 条批量，失败即丢弃，不重试；trace 关闭时
  sink 完全不接收。风险低。
- **迁移**：纯 `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`，
  对现有库幂等，可安全重复执行。
- **Wiring 形状变化**：`traceStore` 为可选 nullable，测试 wiring 不传仍可运行。
- **回滚**：删除 0018 迁移注册（或保留表不使用）即可停止双写；
  `BUTLER_V5_TRACE=0` 一键熔断。

## 9. 审批

批准后按 `tasks.md` 顺序实施；完成后运行 §7 验证并汇报，**不自动提交 / 推送**。
