# Phase 3c 遗留清理 Spec — 管家能力面补全 + 渠道 cutover 灰度

> 状态：待批准 | 日期：2026-11-23 | 上游方案：[phase3c-channel-product-2026-11-23.md](../phase3c-channel-product-2026-11-23.md) §6

## 1. 目标

补齐 §6 列出的三项 cutover 前置条件，使 Slack / Telegram / generic channel 可以在**不改旧入口行为**的前提下按渠道灰度切到 ButlerRuntime，并可一键回退。

1. 管家路径补齐撤销边界、重试、诊断（PC-03）。
2. per-channel 灰度开关 + 回滚，默认 legacy（C3）。
3. 关键能力外部契约测试。

## 2. 非目标

- 不做质量门、子代理迁移。
- 不做自动文件回滚：任务层没有 undo 栈，自动回滚风险不可控；`/undo` 只给边界说明与手工回滚指引。
- 不切换生产默认入口；本 spec 交付的是开关与能力，不是上线动作。

## 3. 能力契约

### 3.1 管家规则（`packages/runtime/src/butler/rule-router.ts`）

`ButlerRuleAction` 新增：

```ts
| { kind: "retry"; name: string; taskId?: string }
| { kind: "diagnose"; name: string }
| { kind: "undo"; name: string }
```

帮助文案在 `/new` 之后追加：

```
/retry [任务ID] 重试失败或中断的任务
/diagnose 诊断当前会话与任务状态
/undo 查看撤销边界（不支持自动撤销）
```

匹配规则（只认显式命令；顺序放在 `status` / `tasks` / `new` 之后、审批之前）：

| 输入 | 结果 |
|------|------|
| `/retry`、`重试`、`重试刚才`、`重试上次`、`重试上一个任务`、`重试任务` | `{kind:"retry", name:"retry"}` |
| `/retry <id>` | `{kind:"retry", taskId:id}` |
| `/diagnose`、`诊断`、`诊断一下` | `{kind:"diagnose", name:"diagnose"}` |
| `/undo`、`撤销`、`撤销刚才`、`撤销上一步` | `{kind:"undo", name:"undo"}` |

### 3.2 运行时行为（`packages/runtime/src/butler/butler-runtime.ts`）

`handle()` 调 `applyRule` 时传入当前 `session`；新增三条分支。

**retry**

1. 任务层未接入 → `任务层尚未接入，暂时无法重试。`
2. 无 `tasks.retry` → `任务层暂不支持重试。`
3. 显式 `taskId` 不存在 → `没有找到任务 <id>。`
4. 无 `taskId`：从 `tasks.list(projectId)` 取 `conversationId === input.conversationId` 的最后一项；无 → `当前没有可重试的任务。`
5. 状态为 `running` → `任务 <id> 正在执行，稍后用 /status 查看。`
6. 状态为 `paused` → `任务 <id> 正在等待审批，请先确认或拒绝。`
7. 调用 `tasks.retry(taskId)`；返回 `null` → `任务 <id> 当前无法重试。`
8. 成功：`已重新执行任务 <id>（<状态>）。` 复用 `describeTask` / `buildApprovalNotice` 风格补充结果与待审批提示，返回 `taskId`。

**diagnose**（确定性文本，不调模型）

```
【诊断】
项目：<projectId | 未绑定>
会话：<conversationId 前 8 位>
任务：执行中 N / 待审批 N / 失败 N / 其他 N
待审批：<taskId 列表>            # 仅当存在
最近任务：<taskId>（<状态>）：<error 截断 120>   # 最多 3 条，仅当存在
长期记忆：已接入 / 未接入
可用：/status 查看任务，/retry 重试，/tasks 列出任务
```

- 任务层未接入 → `任务层：未接入`。
- `tasks.list` 抛错 → `任务层：查询失败`，其余行照常输出。

**undo**（固定边界文案）

```
管家的文件改动由任务层执行，暂不支持自动撤销。可以先用 /status 查看任务结果；需要回滚时，在项目目录用 git diff 确认改动后手工处理。
```

### 3.3 任务端口（`packages/runtime/src/butler/pi-task-adapter.ts`）

已在 `packages/ports/src/core/butler-task.ts` 增加可选 `retry?`。适配器实现：

1. `runner.load(taskId)` 为 `null` → 返回 `null`。
2. 在 `inFlight` 中 → 返回 `statusOf(taskId)`（running）。
3. `paused` 且有 `pendingStep` → 返回 `statusOf(taskId)`，**不自动批准**。
4. `paused` 无 `pendingStep` → `runner.resume(taskId, {approved:true})`。
5. 其他（failed / idle / closed）→ 取 `record.snapshot.summary` 作为 goal；为空返回 `null`；否则 `runner.start(taskId, goal, turnOptions)`。
6. 统一 `await track(...)` 后返回 `(await statusOf(taskId)) ?? toRef(record)`。

### 3.4 渠道开关（`apps/api/src/channel-config.ts`）

```ts
export type ChannelEngine = "legacy" | "butler"
export function resolveChannelEngine(env: NodeJS.ProcessEnv, channelId: string): ChannelEngine
export function resolveChannelProjectId(channelId: string, env: NodeJS.ProcessEnv): string
```

- `resolveChannelEngine`：先读 `BUTLER_V5_<CHANNEL>_ENGINE`（channelId 大写、非字母数字转 `_`），再读 `BUTLER_V5_CHANNEL_ENGINE`；仅值 `butler`（忽略大小写/空白）生效，否则 `legacy`。
- `resolveChannelProjectId`：解析 `BUTLER_V5_CHANNEL_PROJECTS`（JSON object，channelId → projectId）；命中返回；否则 `BUTLER_V5_DEFAULT_PROJECT_ID`；再否则 `wechat`。JSON 非法时静默回退。

`packages/ports/src/core/channel.ts` 的 `ChannelKind` 增加 `"generic"`。

### 3.5 运行时提供者（新文件 `apps/api/src/butler-runtime-provider.ts`）

```ts
export interface ButlerOwnerRef {
  readonly channelKind: ChannelKind
  readonly address: string
  readonly threadTs?: string
}
export interface ButlerRuntimeProvider {
  assembly(): Promise<ButlerAssembly>
  rememberOwner(conversationId: string, owner: ButlerOwnerRef): void
}
export function createButlerRuntimeProvider(
  wiring: Wiring,
  options?: {
    env?: NodeJS.ProcessEnv
    memory?: { butler?: ButlerMemoryPort; task?: TaskMemoryPort }
    createAssembly?: (wiring: Wiring, env: NodeJS.ProcessEnv) => ButlerAssembly | Promise<ButlerAssembly>
    push?: (input: { owner: ButlerOwnerRef; text: string }) => Promise<TaskSettledPushResult>
  },
): ButlerRuntimeProvider
```

- 内部缓存 `assembly` Promise，失败不缓存。
- `createButlerAssembly` 参数与现 `routes/butler.ts` 一致：`db`、`projects: parseProjectRoots(env)`、`env`、`detachedTasks: envTruthy(BUTLER_V5_DETACHED_TASKS)`、`resolveProjectName: resolveWechatProjectAlias`、detached 时 `onTaskSettled: notifier`、记忆端口。
- `notifier` 用 `createTaskSettledNotifier<ButlerOwnerRef>`。
- 默认 `push` 按 `owner.channelKind` 分发：
  - `wechat` → `sendWechatProactiveNotify({to: address, text, env})`
  - `slack` → `slackBotToken(env).unwrap()`；缺失返回 `{ok:false, reason:"BUTLER_V5_SLACK_BOT_TOKEN 未配置"}`；否则 `deliverSlackChannelReply({token, channel: address, reply: text, threadTs?})`
  - `telegram` → `telegramBotToken(env).unwrap()`；缺失返回可读 reason；否则 `deliverTelegramChannelReply({token, chatId: address, reply: text})`
  - `generic` → `{ok:false, reason:"generic channel has no proactive transport"}`

`apps/api/src/butler-inbound.ts` 的 `createTaskSettledNotifier` 泛型化：

```ts
export interface TaskSettledPushInput<TOwner = string> { readonly owner: TOwner; readonly text: string }
export function createTaskSettledNotifier<TOwner = string>(args: {
  approvalNotice: (taskId: string) => Promise<{ text: string } | null>
  resolveOwner: (conversationId: string) => TOwner | undefined
  push: (input: TaskSettledPushInput<TOwner>) => Promise<TaskSettledPushResult>
  logger?: ...
}): (ref: ButlerTaskRef) => Promise<void>
```

同步把 `butler-inbound.test.ts` 中 3 处 push 断言从 `input.to` 改为 `input.owner`。

### 3.6 项目根解析拆分（新文件 `apps/api/src/butler-projects.ts`）

- `parseProjectRoots` 从 `routes/butler.ts` 原样移出。
- `routes/butler.ts` 改为 `import` 并 `export { parseProjectRoots }`，保持 `routes/butler.test.ts` 的 `from "./butler.js"` 不破。

### 3.7 路由改造

**`apps/api/src/routes/butler.ts`**

- `ButlerRoutesOptions` 增加 `provider?: ButlerRuntimeProvider`。
- 删除本地 `cached` / `owners` / `detached` / `notifier`；未传 `provider` 时内部 `createButlerRuntimeProvider(wiring, {env, memory, createAssembly})`。
- handler 用 `provider.assembly()`；`provider.rememberOwner(conversationId, {channelKind:"wechat", address: subject})`。

**`apps/api/src/channel-inbound.ts`**

- `ChannelInboundInput` 增加 `engine?: ChannelEngine`、`butler?: ButlerRuntimeProvider`、`channel?: ChannelPort`、`ownerThreadTs?: string`。
- `ChannelInboundResult` 增加 `delivered?: boolean`、`deliveryReason?: string`。
- 写入事件后，若 `engine === "butler"`：
  1. 无 `butler` → `ChannelInboundError(..., 503)`。
  2. `provider.assembly()` 抛错 → `ChannelInboundError("butler runtime unavailable: ...", 503)`。
  3. `rememberOwner(conversationId, {channelKind, address: subject, ownerThreadTs?})`。
  4. 无 `channel` 时用 no-op（`sendText` 返回 `{ok:true,messageId:null}`）。
  5. `handleButlerInbound(...)`，`projectId = resolveChannelProjectId(channelId, process.env)`，`content = value.content`，`conversationId/userId = value`。
  6. 返回 `meta {iterations:0, toolCalls:0, finalDecision:"Respond", traces}` + `delivered` / `deliveryReason`。
- `engine` 缺省或 `legacy`：保持现 `runButlerLoop` 行为不变。

**`apps/api/src/routes/slack-events.ts` / `telegram-webhook.ts`**

- 签名加 `butler?: ButlerRuntimeProvider`。
- `engine = resolveChannelEngine(process.env, "slack" | "telegram")`。
- butler 模式：构造真实 `ChannelPort`（slack：`deliverSlackChannelReply` + token/channel/threadTs；telegram：`deliverTelegramChannelReply` + token/chatId），传给 `handleChannelInbound`，**路由不再二次投递**；`delivered` 取 `result.delivered`。Slack 传 `ownerThreadTs`。
- legacy 模式：保持现有出站逻辑。

**`apps/api/src/routes/inbound.ts`**

- `registerInboundRoutes(app, wiring, butler?)`。
- `/v1/channel/inbound` 计算 `engine = resolveChannelEngine(process.env, body.channelId)` 并透传 `engine` / `butler`；无 `channel`，由 `handleChannelInbound` 用 no-op，响应体回传 `reply`。

**`apps/api/src/routes.ts`**

- 创建一次 `createButlerRuntimeProvider(wiring, {memory})`，传给 `registerButlerRoutes`、`registerSlackEventsRoutes`、`registerTelegramWebhookRoutes`、`registerInboundRoutes`。

### 3.8 配置与文档

- `.env.example` 增加注释与示例：`BUTLER_V5_CHANNEL_ENGINE`、`BUTLER_V5_SLACK_ENGINE`、`BUTLER_V5_TELEGRAM_ENGINE`、`BUTLER_V5_CHANNEL_PROJECTS`、`BUTLER_V5_DEFAULT_PROJECT_ID`，标注默认 legacy。
- `docs/plans/active/phase3c-channel-product-2026-11-23.md` §6 更新边界表与开关说明，§7 追加本次交付记录。
- `docs/PROGRESS.md` 增加遗留清理小节并从表中划掉已闭环项。
- `docs/FEATURES.md` §1 入口说明与 butler 行同步。

## 4. 测试与验收

### 4.1 新增/修改测试

| 文件 | 覆盖 |
|------|------|
| `packages/runtime/src/butler/butler-runtime.test.ts` | 规则匹配；retry 无任务/不支持/inherit 最后任务/running/paused/成功；diagnose 计数与降级；undo 边界文案。`fakeTasks` 增加 `retry` |
| `packages/runtime/src/butler/pi-task-adapter.test.ts` | failed 任务 `retry` 重跑成功；`paused` + pending 不批准并返回 paused；未知任务返回 null |
| `apps/api/src/butler-channel-cutover.test.ts`（新建） | fake provider + fake wiring.eventBridge：`engine=butler` 走 `/help` 规则并经 channel 投递；`engine=legacy` 保持旧行为；provider 缺失 -> 503 |
| `apps/api/src/channel-config.test.ts` | engine 解析优先级、非 butler 回退、project 解析与非法 JSON 回退 |

测试需设置 `BUTLER_V5_CHANNEL_ALLOWLIST` 并复原 `process.env`。

### 4.2 命令

```bash
pnpm exec prettier --write <changed files>
pnpm test
pnpm typecheck && pnpm lint && pnpm format:check
pnpm verify:butler
```

`scripts/chat-scenarios/rules.json` 追加：
- `/diagnose`：`rule: "diagnose"`，`mustContain: ["【诊断】"]`
- `/undo`：`rule: "undo"`，`mustContain: ["暂不支持自动撤销"]`
- `/retry`：`rule: "retry"`，`mustContain: ["没有可重试"]`（fixture 下无任务）

## 5. 风险与回退

- 默认 `legacy`，开关未设置时行为与今天完全一致；回退只需清空 `*_ENGINE`。
- 只读/幂等边界：`retry` 对 `paused` 带 pending 的任务不自动批准；`undo` 不执行任何文件操作。
- `diagnose` 不调用模型，无 token 成本，失败降级为可读文本。

## 6. 审批点

请确认：
1. 接受 `/undo` 只给边界说明、不实现自动回滚。
2. 接受 cutover 以 env 开关交付，生产默认仍为 legacy。
3. 接受上述文件清单与测试口径。
