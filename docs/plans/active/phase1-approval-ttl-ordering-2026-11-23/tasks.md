# 任务清单：Phase 1 审批 TTL + 入站乱序

> 依赖：`spec.md` 审批通过后执行。每完成一项即更新状态。
> 状态：全部完成（2026-11-23）。

## T1 审批 TTL 组合根可配置

- [x] `apps/api/src/butler-assembly.ts`
  - 新增 `export function resolvePiApprovalTtlMs(env?: NodeJS.ProcessEnv): number | undefined`
    - 未设置 → `undefined`
    - 有限正数 → 数值
    - `0` / 负数 → `0`
    - 非法 → `undefined` 并 `logger.warn`
  - `ButlerAssemblyOptions` 新增 `approvalTtlMs?: number`
  - 构造 `PiTaskRunner` 时合并：`options.approvalTtlMs ?? resolvePiApprovalTtlMs(env)`，仅在有值时写入
- [x] 测试：`apps/api/src/butler-assembly.test.ts` 覆盖正数、0、非法

## T2 审批结果端口与适配器

- [x] `packages/ports/src/core/butler-task.ts`：新增 `ButlerTaskApprovalOutcome`；`ButlerTaskRef.approvalOutcome?`
- [x] `packages/runtime/src/butler/pi-task-adapter.ts`：`approve()` 捕获 `PiTaskTurnResult.traces` 映射 `approvalOutcome`
- [x] `packages/runtime/src/execution/pi-task-runner.ts`：`settleLocked()` 写 `snapshot.lastReply` 并清除旧 `lastError`
- [x] 测试：`pi-task-adapter.test.ts` 过期；`pi-task-runner.test.ts` 补 `lastReply` 断言

## T3 管家与 legacy 到期文案

- [x] `packages/runtime/src/butler/butler-runtime.ts`
  - 卡片回调：`expired` / `duplicate` 优先返回明确文案
  - 规则 `approve` 分支：同上
- [x] `apps/api/src/wechat-inline-approval.ts`：`alreadyProcessed` 且 reason 含 `expired` → 过期文案
- [x] 测试：`butler-runtime.test.ts`、`wechat-inline-approval.test.ts`

## T4 入站排序守卫

- [x] 新建 `apps/api/src/inbound-ordering.ts`
  - 常量与 `resolveInboundOrderWindowMs`
  - `checkInboundOrder`（序号优先、时间窗兜底、no-op 兼容）
  - `resetInboundOrdering`（测试）
- [x] 测试：`apps/api/src/inbound-ordering.test.ts`

## T5 渠道元数据提取

- [x] `packages/adapters/src/slack/slack-protocol.ts`：message 结果新增 `sequence` / `occurredAtMs`
- [x] `apps/api/src/channel-inbound.ts` 的 `parseTelegramUpdate`：新增 `sequence` / `occurredAtMs`
- [x] `packages/adapters/src/wechat/ilink-protocol.ts`：`IlinkInbound.occurredAtMs`，提取 `create_time` / `msg_time`
- [x] 测试：`slack-protocol.test.ts`、Telegram 解析用例

## T6 入口接线与拒绝行为

- [x] `apps/api/src/channel-inbound.ts`
  - 入参与结果类型扩展
  - 规范化后、事件追加前守卫
  - 拒绝返回 `skipped` / `skipReason` / trace
- [x] `apps/api/src/routes/slack-events.ts`、`routes/telegram-webhook.ts`：透传元数据；跳过 legacy 出站
- [x] `apps/api/src/routes/inbound.ts`：generic body 透传可选字段
- [x] `apps/api/src/ilink-poller.ts`：`postInbound` 前守卫，拒绝计 `skipped` 并记录
- [x] 测试：`channel-inbound.test.ts`、`ilink-poller.test.ts`

## T7 全量验证

- [x] `pnpm typecheck`
- [x] `pnpm lint`
- [x] `pnpm format:check`
- [x] `pnpm test` → 279 文件 / 2,423 通过 / 2 skipped
- [x] `pnpm verify:butler` → 3 场景 / 13 轮全过
- [x] 过期/乱序用例已由定向测试覆盖（过期：adapter/runner/butler；乱序：ordering/channel/poller）

## T8 文档

- [x] `docs/PROGRESS.md`：Phase 1 遗留闭环 + 证据
- [x] `docs/FEATURES.md`：能力与边界
- [x] `docs/ENV.md`：`BUTLER_V5_APPROVAL_TTL_MS`、`BUTLER_V5_INBOUND_ORDER_WINDOW_MS`
- [x] `docs/plans/README.md`：方案索引
