# Phase 1 遗留补齐：审批 TTL 可配置与到期语义 + 入站乱序防护

> 状态：待审批
> 日期：2026-11-23
> 范围：只处理 `docs/PROGRESS.md` Phase 1 遗留表中的「审批超时过期」与「乱序到达」两项；不涉及 capped 分支真机验证与 compose 告警。

## 1. 现状与缺口

### 1.1 审批 TTL

已存在但未闭环：

| 层 | 现状 | 缺口 |
|----|------|------|
| pi 任务层 | `PiTaskRunner` 已有 `approvalTtlMs`（默认 30 分钟，`<=0` 关闭），`resume()` 在 `pendingStep.requestedAt` 超时后清空 pending 并返回「审批已过期，本步未执行。」；测试已覆盖 | 组合根 `createButlerAssembly` 未接环境变量，TTL 不可配置 |
| 管家层 | `PiTaskPortAdapter.approve()` 只返回 `ButlerTaskRef`，`ButlerRuntime` 无法得知「过期/重复」 | 到期后仍回复「已确认，继续执行 …」，并把旧 `lastReply` 当执行结果，语义错误 |
| 任务快照 | `settleLocked()` 只写 messages，不更新 `snapshot.lastReply` | `/status` 等出口看不到「审批已过期」 |
| legacy RunEngine | `approveWaitingStep()` 已按 `pending.expiresAtMs` 拒绝（15 分钟，见 `packages/domain/src/governance/types.ts:185`） | `wechat-inline-approval.ts` 对所有 `alreadyProcessed` 统一回「该操作已处理」，未区分过期 |

### 1.2 乱序到达

- 入站入口：`handleChannelInbound()`（Slack / Telegram / generic）与 `runIlinkPollCycle()`（微信）。
- 已有：按 `messageId` 或「内容指纹 + 60s 窗口」的重复投递去重；事件按到达顺序追加。
- 缺失：同一会话内较早的消息晚到时，会按到达顺序执行，可能覆盖新会话状态；无会话级序号/时间窗判断，也无拒绝观测。
- 可用排序元数据：
  - Slack `event.ts`（秒级小数，单调递增）；
  - Telegram `message.message_id`（同一 chat 单调递增）与 `message.date`（秒级时间戳）；
  - iLink `create_time` / `msg_time`（若上游提供；当前 `inboundFromIlinkMsg` 未提取）。

## 2. 设计决策

### 2.1 审批 TTL

1. **单一 TTL 来源**：继续由 `PiTaskRunner.approvalTtlMs` 负责判定，不在管家层重复计时。
2. **环境变量**：`BUTLER_V5_APPROVAL_TTL_MS`
   - 未设置：不显式传参，沿用 runner 默认 30 分钟；
   - 有限正数：作为 TTL；
   - `0` 或负数：关闭过期判定；
   - 非法值：沿用默认并 `logger.warn`（不阻断启动）。
3. **端口表达结果**：`ButlerTaskRef` 新增可选 `approvalOutcome?: "approved" | "denied" | "expired" | "duplicate"`；仅 `approve()` 返回值携带，`status/list` 不填。保持端口方法签名不变，避免改动所有桩实现。
4. **适配器映射**：`createPiTaskPortAdapter.approve()` 根据 `PiTaskTurnResult.traces` 映射：
   - 含 `approval:expired` → `expired`
   - 含 `approval:duplicate` → `duplicate`
   - 否则按 `approved` 入参映射 `approved` / `denied`
5. **快照补全**：`settleLocked()` 写 `snapshot.lastReply = text` 并清除 `lastError`，使 `/status` 与详情一致。
6. **管家文案**：`handleApprovalCallback()` 与规则分支 `approve` 在调用 `tasks.approve()` 后先判 `approvalOutcome`：
   - `expired` → 「审批已过期，本步未执行。」
   - `duplicate` → 「该审批已处理，未重复执行。」
   - 其余维持现有「已确认/已拒绝」文案。
7. **legacy 文案**：`wechat-inline-approval.ts` 对 `alreadyProcessed` 且 `reason` 含 `expired` 回「审批已过期，本步未执行。」；其余维持原文案。`owner-routes` 已正确映射，不改。

### 2.2 乱序到达

1. **判定位置**：
   - `handleChannelInbound()` 内、规范化之后、追加 `ConversationStarted` 事件之前（覆盖 Slack / Telegram / generic，legacy 与 butler 两种引擎）。
   - `runIlinkPollCycle()` 内、`postInbound()` 之前（微信，避免产生空回复或额外出站）。
2. **新模块** `apps/api/src/inbound-ordering.ts`：
   - 进程内 `Map<string, { lastSequence?, lastOccurredAtMs? }>`，key = `${channelId}:${conversationId}`；
   - `checkInboundOrder({ channelId, conversationId, sequence?, occurredAtMs?, nowMs?, env? })`：
     - `sequence` 为有限数且严格小于已见最大序号 → 拒绝 `stale_sequence`（相等视为重复投递，交给既有幂等/回放路径）；
     - `occurredAtMs` 为有限正数且 `< 已见最大时间 - 窗口` → 拒绝 `stale_timestamp`；
     - 通过则更新最大值；无排序元数据时恒通过；
   - 窗口 `BUTLER_V5_INBOUND_ORDER_WINDOW_MS`，默认 `120000`，`0` 关闭时间窗判定；非法值用默认；
   - Map 上限 5000，超出按插入顺序淘汰；导出 `resetInboundOrdering()` 仅供测试。
3. **拒绝行为**：
   - 不追加会话事件、不启动 run、不发出站；
   - `ChannelInboundResult` 新增 `skipped?: boolean` 与 `skipReason?: "stale_sequence" | "stale_timestamp"`；
   - `traces` 追加 `inbound-order:<reason>`；Slack/Telegram/generic 的 HTTP 响应带 `skipped` / `skipReason`（200），可观测；
   - legacy Slack/Telegram 路由在 `result.skipped === true` 时跳过出站发送。
4. **元数据接线**：
   - Slack `parseSlackEventPayload()` 的 message 结果新增 `sequence`（`Number(ts)`）与 `occurredAtMs`（`ts*1000`）；
   - Telegram `parseTelegramUpdate()` 的 message 结果新增 `sequence`（数字 `message_id`）与 `occurredAtMs`（`date*1000`）；
   - generic `/v1/channel/inbound` body 新增可选 `sequence`、`occurredAtMs`；
   - `inboundFromIlinkMsg()` 从 `create_time` / `msg_time` 提取 `occurredAtMs`（`<1e12` 视为秒），由 poller 传入守卫；缺失则 no-op。
5. **已知边界**（写入文档，不在本次扩展）：进程内状态，多进程部署不共享；跨重启不保留；iLink 未提供时间戳时仅依赖轮询顺序与去重。

## 3. 变更清单

### 3.1 代码

| 文件 | 变更 |
|------|------|
| `apps/api/src/butler-assembly.ts` | 新增 `resolvePiApprovalTtlMs(env)`；`ButlerAssemblyOptions.approvalTtlMs?`；构造 `PiTaskRunner` 时传 `approvalTtlMs` |
| `packages/ports/src/core/butler-task.ts` | 新增 `ButlerTaskApprovalOutcome` 与 `ButlerTaskRef.approvalOutcome?` |
| `packages/runtime/src/butler/pi-task-adapter.ts` | `approve()` 捕获 `PiTaskTurnResult`，映射并回填 `approvalOutcome` |
| `packages/runtime/src/execution/pi-task-runner.ts` | `settleLocked()` 写 `snapshot.lastReply`、清除 `lastError`（如存在） |
| `packages/runtime/src/butler/butler-runtime.ts` | 卡片回调与规则 `approve` 分支按 `approvalOutcome` 输出过期/重复文案 |
| `apps/api/src/wechat-inline-approval.ts` | `alreadyProcessed` 且 reason 含 `expired` → 过期文案 |
| `apps/api/src/inbound-ordering.ts` | 新建：窗口常量、环境变量解析、守卫、测试重置 |
| `apps/api/src/channel-inbound.ts` | 入参新增 `sequence?` / `occurredAtMs?`；规范化后守卫；结果新增 `skipped` / `skipReason` |
| `packages/adapters/src/slack/slack-protocol.ts` | message 结果新增 `sequence?` / `occurredAtMs?` |
| `apps/api/src/channel-inbound.ts`（`parseTelegramUpdate`） | message 结果新增 `sequence?` / `occurredAtMs?` |
| `apps/api/src/routes/slack-events.ts` | 透传排序元数据；`skipped` 时跳过 legacy 出站 |
| `apps/api/src/routes/telegram-webhook.ts` | 同上 |
| `apps/api/src/routes/inbound.ts` | generic body 新增可选排序字段并透传 |
| `packages/adapters/src/wechat/ilink-protocol.ts` | `IlinkInbound` 新增 `occurredAtMs?`；从 `create_time` / `msg_time` 提取 |
| `apps/api/src/ilink-poller.ts` | `postInbound` 前调用守卫；拒绝时 `skipped += 1` 并记录日志 |

### 3.2 测试

| 文件 | 用例 |
|------|------|
| `apps/api/src/inbound-ordering.test.ts` | 序号回退拒绝、序号前进通过、时间窗内通过、超窗拒绝、`window=0` 关闭、无元数据 no-op、Map 淘汰 |
| `apps/api/src/channel-inbound.test.ts` | 旧序号消息不追加事件、不运行、`skipped=true`、trace 正确；新序号照常 |
| `packages/adapters/src/slack/slack-protocol.test.ts` | `ts` → `sequence` / `occurredAtMs` |
| `apps/api/src/channel-inbound.test.ts`（telegram 解析） | `date` / 数字 `message_id` → `sequence` / `occurredAtMs` |
| `apps/api/src/ilink-poller.test.ts` | 带旧时间戳的消息不调用 `postInbound`、计入 `skipped` |
| `packages/runtime/src/butler/pi-task-adapter.test.ts` | 过期审批返回 `approvalOutcome="expired"`、pending 清空、`lastReply` 含「过期」 |
| `packages/runtime/src/execution/pi-task-runner.test.ts` | 现有过期用例补断言 `snapshot.lastReply` |
| `packages/runtime/src/butler/butler-runtime.test.ts` | 过期审批回复含「过期」且不含「已确认」；重复审批回「未重复执行」 |
| `apps/api/src/butler-assembly.test.ts` | `BUTLER_V5_APPROVAL_TTL_MS` 解析（正数 / 0 / 非法） |
| `apps/api/src/wechat-inline-approval.test.ts` | 过期 `alreadyProcessed` 回复过期文案 |

### 3.3 文档

| 文件 | 变更 |
|------|------|
| `docs/PROGRESS.md` | Phase 1 遗留表移除两项或标为已闭环，新增「Phase 1 遗留清理（2026-11-23）」小节与复跑证据 |
| `docs/FEATURES.md` | 补充审批 TTL 可配置、到期语义、入站乱序防护与边界 |
| `README.md` | 若存在环境变量表，补 `BUTLER_V5_APPROVAL_TTL_MS`、`BUTLER_V5_INBOUND_ORDER_WINDOW_MS` |

## 4. 验证

1. 定向：
   - `pnpm vitest run apps/api/src/inbound-ordering.test.ts apps/api/src/channel-inbound.test.ts apps/api/src/ilink-poller.test.ts apps/api/src/butler-assembly.test.ts apps/api/src/wechat-inline-approval.test.ts`
   - `pnpm vitest run packages/runtime/src/butler/pi-task-adapter.test.ts packages/runtime/src/butler/butler-runtime.test.ts packages/runtime/src/execution/pi-task-runner.test.ts packages/adapters/src/slack/slack-protocol.test.ts`
2. 全量：`pnpm typecheck && pnpm lint && pnpm format:check && pnpm test`
3. 管家链路：`pnpm verify:butler`
4. 反向验证：临时把窗口设为 `0` 或删除 `requestedAt`，确认过期/乱序用例会失败（不提交）。

## 5. 验收口径

- 过期审批：管家回复不再出现「已确认，继续执行」，任务 pending 清空，`/status` 显示过期说明；TTL 可由 `BUTLER_V5_APPROVAL_TTL_MS` 调整。
- legacy 审批：过期时回复「审批已过期，本步未执行。」。
- 乱序入站：旧序号/超窗消息不追加事件、不执行、不发送；响应与 trace 可观测；新消息不受影响。
- 全量检查全绿，文档同步。

## 6. 不做的范围

- 不引入跨进程/持久化的全局会话序号表；
- 不改事件存储 `occurredAt` 的写入语义；
- 不处理 capped 分支真机验证与 compose 首次部署告警；
- 不提交代码（完成后汇报，由用户决定）。
