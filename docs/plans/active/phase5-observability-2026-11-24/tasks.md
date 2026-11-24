# Phase 5 P0 任务清单（2026-11-24）

对应 spec：`docs/plans/active/phase5-observability-2026-11-24/spec.md`。

## T1 — 错误码注册表 + 失败信封

- [x] 新增 `packages/domain/src/observability/error-codes.ts`
  - `TraceErrorCode`、`ERROR_CODES`、`resolveErrorCode`、`turnIdShort`、`formatFailureEnvelope`。
- [x] 新增 `packages/domain/src/observability/error-codes.test.ts`
  - `_tag` 映射、关键字兜底、未知 → `E-INT-01`、信封格式、turnId 前 8 位。

验证：`pnpm vitest run packages/domain/src/observability/error-codes.test.ts`

## T2 — TraceEvent 增加 turnId

- [x] `packages/domain/src/observability/local-trace.ts`
  - `TraceEvent.turnId`、`CreateTraceEventInput.turnId`、`createTraceEvent`、`filterTraceEvents`、OTel 输出。
- [x] `packages/runtime/src/observability/local-tracer.test.ts` 增补 turnId 过滤断言。

## T3 — trace_events 表与 TraceStore

- [x] `packages/persistence/src/schema.ts` 新增 `traceEvents`。
- [x] 新增 `packages/persistence/src/migrations/0018_trace_events.sql`。
- [x] `packages/persistence/src/migrations/run-migrations.ts` 注册 0018。
- [x] `packages/persistence/src/migrations/migrations-registry.test.ts` 断言表/索引。
- [x] 新增 `packages/persistence/src/trace-store.ts`（append/list/count/oldestCreatedAt/prune）。
- [x] `packages/persistence/src/index.ts` 导出。
- [x] 新增 `packages/persistence/src/trace-store.test.ts`。

验证：
`pnpm vitest run packages/persistence/src/trace-store.test.ts packages/persistence/src/migrations/migrations-registry.test.ts`

## T4 — LocalTracer 异步批量双写

- [x] `packages/runtime/src/observability/local-tracer.ts`
  - `TraceSink`、`sink/batchSize/flushIntervalMs` 选项、`pending/stats/flush/close`。
  - `resetSharedLocalTracer(env, opts?)` 关闭旧实例。
- [x] `local-tracer.test.ts` 新增批量 / flush / close / 失败不抛出用例。

验证：`pnpm vitest run packages/runtime/src/observability/local-tracer.test.ts`

## T5 — turnId 贯穿入站与主循环

- [x] `apps/api/src/routes/inbound.ts` 透传 turnId。
- [x] `apps/api/src/wechat-intake.ts` 透传 turnId。
- [x] `apps/api/src/channel-inbound.ts` 透传 turnId。
- [x] `apps/api/src/wechat-inbound-butler.ts`
  - `args.turnId`；LLM trace、失败 trace 带 turnId；
  - 失败回复改为 `formatFailureEnvelope`。

## T6 — turnId 贯穿子代理与审批

- [x] `apps/api/src/tools.ts` + `packages/runtime/src/delegate-runtime.ts`：
  outbox payload 增加 `turnId`（调用点不可达则退化，不阻塞）。
- [x] `apps/api/src/subagent-worker-payload.ts` + `subagent-worker.ts`：解析并写 trace。
- [x] `apps/api/src/wechat-inline-approval.ts` + `approval-resume.ts`：透传并写 trace。
- [x] 运行既有单测确认审批链路无回归。

## T7 — 组装 sink 与保留策略

- [x] `apps/api/src/wiring.ts` 增加 `traceStore`。
- [x] `apps/api/src/bootstrap-wiring.ts`
  - 创建 `createTraceStore`；
  - `resetSharedLocalTracer(env, { sink: traceStore })`；
  - 启动 prune（失败只告警）。
- [x] `apps/api/src/index.ts`
  - SIGINT/SIGTERM/收尾 `flush` + `close`；
  - 每小时 prune（`unref`）。

## T8 — 健康检查与 Owner 诊断

- [x] 新增 `apps/api/src/diagnostics.ts`（DB / outbox / approvals / runs / traces；兼容无 db）。
- [x] `apps/api/src/routes.ts` `/healthz` 改 async 并接诊断。
- [x] `apps/api/src/owner-routes/traces-procedures-tasks.ts` 新增 `GET /v1/owner/diagnostics`。
- [x] 新增 `apps/api/src/diagnostics.test.ts`。
- [x] 新增 `apps/api/src/owner-diagnostics.test.ts`。

## T9 — 全量验证与文档

- [x] `pnpm typecheck`
- [x] `pnpm lint`
- [x] 相关 vitest 全部通过（见 spec §7）
- [x] `docs/PROGRESS.md` 追加 Phase 5 P0 状态与证据

## 边界

- 不自动提交 / 推送。
- 不实现 P1（微信日志指令、卡住告警、控制台页、导出 CLI、OTLP 外送）。
- 用户可见回复不出现原始异常、堆栈、内部 ID（turnId 仅 8 位）。
