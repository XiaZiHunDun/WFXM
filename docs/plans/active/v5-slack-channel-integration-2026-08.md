# slack 接生产 PRD

> **状态**：Active planning（待 operator review）
> **触发**：Owner 自报 `slack`，见 ADR `docs/plans/active/v5-channel-port-trigger-2026-08.md` §3（dialog 2026-08-28）
> **目的**：按 ADR §4 最小门槛把 `slack` 接到生产；Channel Port 维持隐性承载
> **目标 commit**：\<TBD at use — R14.8 push 时填\>
> **完成归档**：完成后在 ADR §7 完成记录段将本行 `in-progress` → `completed YYYY-MM-DD`，证据列填 commit-sha 或 Run-id

## 1. 背景

WeChat iLink（long-poll + `ilink/bot/getupdates`）目前唯一在生产 channel；`butler-v5/packages/adapters/src/{slack,telegram}/` 目录不存在。Owner 在 dialog 2026-08-28 自报 Slack 接生产。Slack 协议走 **Events API + signing secret**（HTTP webhook）—— 与 WeChat long-poll 模式不同，但 Channel Port 维持隐性承载（同 DESIGN §7.1）。

本轮前置事实（调研 R14.3）：Slack 协议级代码**已大半实装**于 `apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts`，HTTP route 在 `routes.ts` `POST /v1/channel/slack/events`（含 challenge + signing 验签 + `handleChannelInbound` + `deliverSlackChannelReply`）。本 PRD 不重做这些代码，而是按 ADR §4.1 / PRD §2.1 #1 把协议级部分**搬到** `packages/adapters/src/slack/`（mirror WeChat `packages/adapters/src/wechat/`），并补齐 PRD §3 单测缺项（附件 / 重复 / protocol error / token 失效 / timeout）。

Owner 用场景：Owner 真实 Slack workspace ready（token xoxb-... + signing secret 已有），本轮可走 Owner 真实 workspace e2e（R14.7）；无需 second Channel 触发证据——本 channel 是 first Slack 实例。

## 2. Scope

### 2.1 In scope（本 PRD 覆盖）

| # | 工作 | 备注 |
| --- | --- | --- |
| 1 | 建 `butler-v5/packages/adapters/src/slack/` 目录；协议级 Slack 代码（`verifySlackSignature` / `parseSlackEventPayload` / `SlackWebhookParseResult` / `sendSlackOutboundMessage` / `SlackOutboundConfig` / `describeSlackFiles` / `sendSlackOutboundFile`）从 `apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts` 搬入 | mirror WeChat `packages/adapters/src/wechat/ilink-*` 形态 |
| 2 | `packages/adapters/src/index.ts` 加 `export * from "./slack/index.js"`；`packages/adapters/package.json` 加 `"./slack/index.js"` export 映射 | |
| 3 | apps/api 编排层 `channel-{inbound,outbound,outbound-media,media}.ts` 移除已搬走的 Slack 函数，改 `import` 自 `@butler/adapters/slack`；保留 `deliverSlackChannelReply` / `slackBotToken` / `slackOutboundEnabled` 等编排代码在 apps/api | 编排 ≠ 协议；`deliverSlackChannelReply` 调 `sendSlackOutboundMessage` + `sendSlackOutboundFile`，留在编排层 |
| 4 | `routes.ts` / `channel-inbound.test.ts` / `channel-outbound.test.ts` 更新 import 路径 | 5 gate 必须不抛（function 逻辑不变） |
| 5 | adapter 层补单测：`slack-protocol.test.ts`（signing 合法/非法/5min replay window + parse challenge/event_callback/message/file_share/subtype filter/empty text）+ `slack-outbound.test.ts`（chat.postMessage 成功/超时/non-JSON/api.ok=false/missing token/missing channel/clip）+ `slack-media.test.ts`（describeSlackFiles image/file/empty/multiple）+ `slack-outbound-media.test.ts`（sendSlackOutboundFile 成功/error） | PRD §3 单测缺项 |
| 6 | 测试环境 e2e：simulate `POST /v1/channel/slack/events`（mock signing + sample event_callback）→ verify `handleChannelInbound` 走通 + `deliverSlackChannelReply` 调 `chat.postMessage` | 替代手工 e2e 的初验 |
| 7 | Owner 真实 Slack workspace e2e：Owner 在 workspace 发一条 → Butler 通过 Slack 回一条；Run trace 完整（conversation/run/step/outbox 全有） | ADR §4 #4 最关键证据；缺这条不记完成 |
| 8 | 5 gate 全绿（typecheck / lint / test / test:archived / test:prod） | production 计数 1008 涨，archived 不变 |

### 2.2 Out of scope

- Channel Port 升 first-class —— 另立 ADR
- WeChat 退场 —— WeChat 仍唯一在生产 channel；Slack 是叠加非替代
- 多 Channel 去重 / 跨 channel Conversation —— 不在本 PRD
- Channel quota / rate limiting —— channel-internal 维护
- Channel 抽象抽取（base class / 共享协议层）—— DESIGN §7.1 + §18 YAGNI；WeChat 仍是唯一参照，Slack 不再抽

## 3. Production-ready bar（per ADR §4）

- [ ] adapter 目录 + 入站 Trigger adapter + 出站 Outbox adapter 三件实装（已搬至 `packages/adapters/src/slack/`）
- [ ] 单测：入站（合法/非法/重复/附件）、出站（文本/富媒体/失败重试）、错误路径（协议/token/网络）—— 补齐 adapter 层测试
- [ ] 测试环境端到端：simulated inbound → Run Engine → Outbox worker 发送 outbound
- [ ] **Owner 真实 workspace 端到端：Owner 发一条 → Butler 回一条，Run trace 完整**（最关键证据）
- [ ] 5 gate 全绿

## 4. 实施阶段

### Phase 1 — Adapter 搬迁 + TDD 补测（R14.5a + R14.5b）

先搬代码（行为不变，5 gate 必须不抛），再在 adapter 层补 PRD §3 缺项单测。每个测试 commit 一次。

### Phase 2 — 端到端（R14.6 + R14.7）

测试环境模拟（mock signing + sample event_callback）→ Owner 真实 Slack workspace 端到端（Owner 提供 token/secret，gateway 起 BUTLER_V5_SLACK_ENABLED=1）。

### Phase 3 — 验证 + 归档（R14.8）

5 gate 全绿 → ADR §7 完成记录段将本行 `in-progress` → `completed YYYY-MM-DD, 证据=<commit-sha 或 Run-id>` → commit 推 origin main → 写 R14 handoff 卡（含 commit 链 / 失误清单）。

## 5. 不要做（重申）

- 不升 Channel Port 为 first-class
- 不抽 channel 公共抽象（即便 Slack 与 WeChat 协议形态差异显著——WeChat long-poll vs Slack Events API webhook，仍不抽）
- 不为新 channel 写 channel-portfolio 状态机
- 不复用 `_archive/packages/{application,infrastructure,contracts}` 入生产（`package-membership.test.ts` 第 (1) 守这条）
- 不为生产代码 import `r2-shim` 任何内容
- commit 用 `--no-verify`（R9.5 / R7.5 protocol）

## 6. 依赖与关系

- **触发 ADR**：`docs/plans/active/v5-channel-port-trigger-2026-08.md`
- **DESIGN**：§7.1（Channel 隐性承载 `⚪`）+ §18（第二 Channel 延后项）
- **复用 Outbox**：R12（commit `33af1722` + `278a0cc7`）
- **本模板**：`docs/plans/templates/channel-integration-prd.md`
- **现有 Slack 代码位置（搬迁源）**：`apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts` + `apps/api/src/routes.ts`（编排）
- **R14 班段记录**：`.blackboard/shifts/2026-08-28-r14-slack-channel-trigger.md`

---

> 模板：cloned from `docs/plans/templates/channel-integration-prd.md` by 触发 ADR §3（Owner dialog 2026-08-28）；Channel Port 维持隐性承载不升 first-class；协议级 Slack 代码从 apps/api/src/channel-* 搬到 packages/adapters/src/slack/ 对齐 ADR §4.1。