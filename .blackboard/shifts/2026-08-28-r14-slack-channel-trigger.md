---
date: 2026-08-28
produced: [shift-card]
---
# Butler v5 — R14 Slack Channel Integration 班段

- **Trigger**：Owner 自报 Slack 接生产（dialog 2026-08-28）；按 ADR `docs/plans/active/v5-channel-port-trigger-2026-08.md` §3 trigger 机制 + §4 production-ready bar
- **ADR §7 已增**：`<slack>: triggered 2026-08-28, status: in-progress`
- **决策**（owner dialog 2026-08-28）：
  1. 协议级 Slack 代码从 `apps/api/src/{channel-inbound,channel-outbound,channel-media,channel-outbound-media}.ts` 搬到 `packages/adapters/src/slack/`（对齐 ADR §4.1 / PRD §2.1 #1；mirror WeChat `packages/adapters/src/wechat/`）
  2. Owner 真实 Slack workspace ready（token xoxb- + signing secret 已有）
- **当前态**：HEAD = `5aac4046`；5 gate = production 1008/1/0, archived 81/2
- **PRD**：clone `docs/plans/templates/channel-integration-prd.md` → `docs/plans/active/v5-slack-channel-integration-2026-08.md`
- **现有 Slack 代码位置**：
  - 入站协议：`apps/api/src/channel-inbound.ts` `verifySlackSignature` / `parseSlackEventPayload` / `SlackWebhookParseResult`
  - 出站协议：`apps/api/src/channel-outbound.ts` `sendSlackOutboundMessage` / `SlackOutboundConfig`
  - 出站编排：`apps/api/src/channel-outbound.ts` `deliverSlackChannelReply` / `slackBotToken` / `slackOutboundEnabled`（保留在 apps/api，编排层）
  - 媒体：`apps/api/src/channel-media.ts` `describeSlackFiles` + `apps/api/src/channel-outbound-media.ts` `sendSlackOutboundFile`
  - HTTP route：`apps/api/src/routes.ts` `POST /v1/channel/slack/events`（含 challenge + signing 验签 + `handleChannelInbound` + `deliverSlackChannelReply`）
  - 测试：`apps/api/src/channel-inbound.test.ts`（4 例 slack）+ `apps/api/src/channel-outbound.test.ts`（1 例 slack）—— 覆盖率薄，按 PRD §3 缺：附件、重复、protocol error、token 失效、timeout
- **执行顺序**：
  1. R14.5a structural move（搬运 6 函数 + 更新 caller + 5 gate 不退化）
  2. R14.5b adapter 层补单测（PRD §3 缺项）
  3. R14.6 测试环境 e2e（simulate Slack event POST → verify response）
  4. R14.7 Owner 真实 Slack workspace e2e（Owner 发一条 → Butler 回一条；Run trace 完整）
  5. R14.8 ADR §7 增 slack completed 行 + per-channel PRD §3 勾选 + commit push
- **完工后**：本卡补"完成态 / commit-sha / Run-id / 不要做 / 失误"段 + commit push

## scope 决议（2026-08-28 dialog 補充，本班段后）

- Owner 后补指示：**当前 dev phase 目标 = target architecture 对齐；WeChat 仍是唯一在生产 channel；不实际启用 Slack 接生产**。
- 含义：
  1. 协议级代码搬到 `packages/adapters/src/slack/`（mirror WeChat）作为**target architecture 预留位**——保留 ✓
  2. adapter 层 81 例单测 + HTTP route guard 7 例——保留 ✓
  3. **R14.7 Owner 真实 Slack workspace e2e — cancelled**（不再 deferred；不在 scope）
  4. **`BUTLER_V5_SLACK_ENABLED` 在生产 gateway 启用 — cancelled**
  5. ADR §7 `<slack>` 行保留 `in-progress`（trigger signal 留下但 real integration 不在 plan），备注改为 "structural alignment done; real integration deferred indefinitely"
- 同步：per-channel PRD scope 改为"structural alignment scope closed"；`.blackboard/shifts/2026-08-28-r14-slack-channel-handoff.md` 重写下一步段为"无；待 owner 真需求出现另立 per-channel PRD"；commit `docs(slack): scope revised to structural alignment only`
- 教训（feedback）：[[feedback-channel-trigger-scope]] —— Owner 自报 channel 时先问 scope（real integration vs structural alignment）不要默认前者