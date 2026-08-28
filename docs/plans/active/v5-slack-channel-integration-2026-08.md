# slack 接生产 PRD（structural alignment scope）

> **状态**：Structural alignment scope closed (2026-08-28)
> **触发**：Owner 自报 `slack`，见 ADR `docs/plans/active/v5-channel-port-trigger-2026-08.md` §3（dialog 2026-08-28）
> **目的**：对齐 target architecture（DESIGN §7.1 Channel 隐性承载 + §18 多 channel 预留位）—— Slack 协议级代码搬到 `packages/adapters/src/slack/` mirror WeChat adapter layout
> **scope 决议（2026-08-28 dialog 补充）**：dev phase 目标 = target architecture 对齐；WeChat 是唯一在生产 channel；**不实际接入 Slack 到生产**；real workspace e2e + `BUTLER_V5_SLACK_ENABLED` 启用 deferred indefinitely，直到 owner 真需要时另立 PRD 触发
> **目标 commit（已落地）**：`ecb224e1`（PRD + ADR §7 trigger + R14 shift 卡）→ `555943cc`（refactor + fix + adapter 4 测试文件）→ `b6cb593d`（slack-intake HTTP route guards）
> **完成归档**：scope closed 2026-08-28；ADR §7 `<slack>` 行 status `in-progress` + 备注"structural alignment done; real integration deferred indefinitely"

## 1. 背景

WeChat iLink（long-poll + `ilink/bot/getupdates`）目前唯一在生产 channel；`butler-v5/packages/adapters/src/{slack,telegram}/` 目录之前不存在。Owner 在 dialog 2026-08-28 自报 Slack 接生产，本轮目标 = 把 Slack 协议级代码**对齐**到 target architecture 位（DESIGN §7.1 + §18），与 WeChat `packages/adapters/src/wechat/` 形态一致；本轮**不**实际启用 Slack 接生产。Slack 协议走 **Events API + signing secret**（HTTP webhook）—— 与 WeChat long-poll 模式不同，但 Channel Port 维持隐性承载。

前置事实（调研 R14.3）：Slack 协议级代码已大半实装于 `apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts`，HTTP route 在 `routes.ts` `POST /v1/channel/slack/events`。本 PRD 不重做这些代码，而是按 ADR §4.1 / PRD §2.1 把协议级部分**搬到** `packages/adapters/src/slack/`，并补齐 adapter 层单测（PRD §3 缺项：附件 / 重复 / protocol error / token 失效 / timeout）+ HTTP route guard 集成测试。

**scope 边界**：WeChat 是当前唯一在生产 channel（dev phase 不变）；Slack 代码保留在 `packages/adapters/src/slack/` 作为 target architecture 预留位 / 未来真要接生产时的代码起点；HTTP route 仍可路由（由 `BUTLER_V5_SLACK_ENABLED` env 守门，缺省关），不影响 WeChat 路径。

## 2. Scope

### 2.1 In scope（本 PRD 覆盖）

| # | 工作 | 备注 |
| --- | --- | --- |
| 1 | 建 `butler-v5/packages/adapters/src/slack/` 目录；协议级 Slack 代码（`verifySlackSignature` / `parseSlackEventPayload` / `SlackWebhookParseResult` / `sendSlackOutboundMessage` / `SlackOutboundConfig` / `describeSlackFiles` / `sendSlackOutboundFile` + 3 共享类型 `ChannelMediaKind` / `ChannelInboundMedia` / `ChannelMediaContent`）从 `apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts` 搬入 | mirror WeChat `packages/adapters/src/wechat/ilink-*` 形态 |
| 2 | `packages/adapters/src/index.ts` 加 `export * from "./slack/index.js"`；`packages/adapters/package.json` 加 `"./slack/index.js"` export 映射 | |
| 3 | apps/api 编排层 `channel-{inbound,outbound,outbound-media,media}.ts` 移除已搬走的 Slack 函数，改 `import` 自 `@butler/adapters/slack/index.js`；保留 `deliverSlackChannelReply` / `slackBotToken` / `slackOutboundEnabled` 等编排代码在 apps/api | 编排 ≠ 协议；`deliverSlackChannelReply` 调 `sendSlackOutboundMessage` + `sendSlackOutboundFile`，留在编排层 |
| 4 | `routes.ts` / `channel-{inbound,outbound,media}.test.ts` 更新 import 路径 | 5 gate 必须不抛（function 逻辑不变） |
| 5 | adapter 层补单测：`slack-protocol.test.ts`（33 例：signing 合法/非法/5min replay window + parse challenge/event_callback/message/file_share/subtype filter/empty text/threadTs）+ `slack-media.test.ts`（20 例：describeSlackFiles image/file/empty/multiple/audio/video/whitespace）+ `slack-outbound.test.ts`（17 例：chat.postMessage 成功/超时/non-JSON/api.ok=false/missing token/missing channel/clip）+ `slack-outbound-media.test.ts`（11 例：sendSlackOutboundFile 成功/error/timeout/FormData）| PRD §3 单测缺项 |
| 6 | 测试环境 e2e：`apps/api/src/slack-intake.test.ts` 7 例 HTTP route guard 集成测试（POST `/v1/channel/slack/events` 的 disabled-404 / wrong-sig-401 / tampered-401 / replay-401 / valid-challenge-200 / unsigned-200 / bad-json-400 路径） | route 层 e2e；不含 Run Engine 真实通路 |
| 7 | 5 gate 全绿 | production 1096 / 1 / 0；archived 81 / 2 pre-existing 未变 |

### 2.2 Out of scope（**deferred until real integration PRD**）

- **Owner 真实 Slack workspace e2e**（ADR §4 #4）—— 待 Owner 真需要接入生产时另立 per-channel PRD 触发，本轮不计入
- **`BUTLER_V5_SLACK_ENABLED=1` + `BUTLER_V5_SLACK_BOT_TOKEN` + `BUTLER_V5_SLACK_SIGNING_SECRET` 在生产 gateway 启用** —— 同上 deferred
- Channel Port 升 first-class —— 另立 ADR（不因 Slack 触发；DESIGN §7.1 仍 ⚪ 隐性承载）
- WeChat 退场 —— WeChat 仍唯一在生产 channel
- 多 Channel 去重 / 跨 channel Conversation —— 真出现 Owner 实际场景再立 ADR
- Channel quota / rate limiting —— channel-internal 维护
- Channel 抽象抽取（base class / 共享协议层）—— DESIGN §7.1 + §18 YAGNI；WeChat + Slack 已是 2 channel 但抽象仍待真需求

## 3. Structural alignment bar（current phase scope 已闭环）

| # | bar | 状态 | 证据 commit |
| --- | --- | --- | --- |
| 1 | adapter 目录 + 入站 Trigger adapter + 出站 Outbox adapter 三件实装至 `packages/adapters/src/slack/` | ✅ done | `555943cc` |
| 2 | 单测覆盖入站（合法/非法/重复/附件）+ 出站（文本/富媒体/失败重试）+ 错误路径（协议/token/网络）= 81 例 | ✅ done | `555943cc` |
| 3 | 测试环境 e2e：HTTP route guard 集成测试 7 例（不含 Run Engine 真实通路） | ✅ done | `b6cb593d` |
| 4 | 5 gate 全绿（typecheck / lint / test / test:archived） | ✅ done | `555943cc` + `b6cb593d` |

**production**: 1008 → 1096（+88 net = 81 adapter + 7 intake），1 skip，0 fail
**archived**: 81 / 2 pre-existing（run-loop rot，R12 已知债，未变）

## 4. 实施阶段（已落地）

### Phase 1 — Adapter 搬迁 + 单测补齐（commit `555943cc`）

把 6 协议级 Slack 函数 + 3 共享类型从 `apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts` 搬到 `packages/adapters/src/slack/{slack-media,slack-protocol,slack-outbound,slack-outbound-media,index}.ts`（mirror WeChat）。apps/api 编排层保留（`handleChannelInbound` + `deliverSlackChannelReply` + env helpers）。5 caller 改 import。inline fix `describeSlackFiles` empty-name fallback。同（commit 末尾含 81 adapter 例单测（slack-protocol 33 + slack-media 20 + slack-outbound 17 + slack-outbound-media 11）。

### Phase 2 — 测试环境 e2e（commit `b6cb593d`）

`apps/api/src/slack-intake.test.ts` 7 例 HTTP route guard 集成测试（POST `/v1/channel/slack/events` 的 404/401/200/400 路径）。用 `{ eventStore: null as never }` 轻量 wiring mock —— 跑 route guard 层而非 Run Engine 真实通路。

### Phase 3 — 归档（commit `ecb224e1`）

PRD 写就（scope closed）+ ADR §7 `<slack>` 行 status `in-progress` 触发记录 + `.blackboard/shifts/2026-08-28-r14-slack-channel-trigger.md` R14 trigger 卡。

## 5. 不要做（重申）

- 不升 Channel Port 为 first-class（DESIGN §7.1 + ADR §2.1 #4）
- 不抽 channel 公共抽象（即便 WeChat + Slack 已 2 channel —— DESIGN §7.1 + §18 YAGNI；待真需求）
- 不为新 channel 写 channel-portfolio 状态机
- 不复用 `_archive/packages/{application,infrastructure,contracts}` 入生产（`package-membership.test.ts` 第 (1) 守这条）
- 不为生产代码 import `r2-shim` 任何内容
- 不在本 dev cycle 启用 `BUTLER_V5_SLACK_ENABLED` 或 owner 真实 workspace e2e（deferred until另立 PRD）
- commit 用 `--no-verify`（R9.5 / R7.5 / R11.1 protocol）

## 6. 依赖与关系

- **触发 ADR**：`docs/plans/active/v5-channel-port-trigger-2026-08.md`（§3 trigger 机制 + §7 完成记录段；本 PRD `<slack>` 行 status `in-progress` + 备注 structural alignment done）
- **DESIGN**：§7.1（Channel 隐性承载 `⚪`）+ §18（第二 Channel 延后项）
- **复用 Outbox**：R12（commit `33af1722` + `278a0cc7`）—— structural-only scope 不实际派发 outbox 项
- **本模板**：`docs/plans/templates/channel-integration-prd.md`
- **搬迁源（apps/api 原位，已 empty）**：`apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts`（protocol 部分 已已搬走，剩余编排）+ `apps/api/src/routes.ts`（route 表）
- **R14 trigger 卡**：`.blackboard/shifts/2026-08-28-r14-slack-channel-trigger.md`
- **R14 handoff 卡**：`.blackboard/shifts/2026-08-28-r14-slack-channel-handoff.md`

---

> 模板：cloned from `docs/plans/templates/channel-integration-prd.md` by 触发 ADR §3（Owner dialog 2026-08-28）；Channel Port 维持隐性承载不升 first-class；协议级 Slack 代码从 apps/api/src/channel-* 搬到 packages/adapters/src/slack/ 对齐 ADR §4.1。Scope 决议（2026-08-28 dialog 补充）：structural alignment only，real integration deferred indefinitely。