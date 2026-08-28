---
name: R14 Slack Channel Integration 闭环（structural alignment scope）
description: Slack 接生产 3 commits 闭环（结构搬迁 + 88 net new tests + 测试环境 e2e）；scope 修订为 structural alignment only（dev phase 不实际接入生产，WeChat 仍是唯一在生产 channel）
metadata:
  type: project
---
# R14 Slack Channel Integration 进度（2026-08-28，scope = structural alignment only）

## 闭环

- **HEAD = `b6cb593d`**（origin/main），3 commits:
  - `ecb224e1` docs: PRD + ADR §7 trigger + R14 shift card
  - `555943cc` refactor: Slack protocol-level code 搬到 `packages/adapters/src/slack/`（mirror WeChat）+ `describeSlackFiles` empty-name fix + 5 caller 改 import + adapter 4 测试文件 81 例
  - `b6cb593d` test: slack-intake HTTP route guards 7 例
- **5 gate**：production 187 files / **1096 pass / 1 skip / 0 fail**（R13 baseline 1008；+88 net = 81 adapter + 7 intake）；archived 81/2 pre-existing（基线未动）

## scope 决议（2026-08-28 dialog 后补）

- Owner 后补指示：dev phase 目标 = target architecture 对齐；WeChat 是唯一在生产 channel；**不实际启用 Slack 接生产**
- 含义：
  - 协议级代码 + 单测 + HTTP route 守门保留（target architecture 预留位）
  - **R14.7 Owner 真实 Slack workspace e2e — cancelled**
  - **`BUTLER_V5_SLACK_ENABLED` 在生产 gateway 启用 — cancelled**
  - ADR §7 `<slack>` 行 status 保留 `in-progress`（作为 trigger 机制存在证据）+ 备注 "structural alignment done; real integration deferred indefinitely"

## 关键决策

- Slack transport = **Events API + signing secret**（HTTP webhook）—— 已写代码决定
- 协议级代码搬到 `packages/adapters/src/slack/` —— mirror WeChat adapter layout（ADR §4.1 / PRD §2.1 #1）
- apps/api 仅留编排层（`handleChannelInbound` + `deliverSlackChannelReply` + `slackBotToken` + `slackOutboundEnabled` + env guards）
- Channel Port 维持隐性承载（DESIGN §7.1 + §18 YAGNI）

## ADR §7 状态

`<slack>` 行 `in-progress`（触发日期 2026-08-28）+ 备注 "scope=structural-only; structural alignment done (commit 555943cc + b6cb593d + ecb224e1); real integration deferred indefinitely"

## 下一步

- **无**（structural alignment scope closed）
- 待 owner 真需要启用 Slack 接生产时另立 per-channel PRD：克隆 `docs/plans/templates/channel-integration-prd.md` → 新 per-channel PRD，scope 标 "real integration"，走完整 ADR §4 production-ready bar 4 项

## 相关

- [[feedback-channel-trigger-scope]] —— Owner 自报时先问 scope（real integration vs structural alignment）；R14 失误案例
- [[feedback-bash-backtick-in-commit-message]] —— commit message body 用 single-quote 避免反引号吃 SHA
- [[R13 shift handoff 2026-08-28]] —— R13 班段上下文（Channel Port Trigger ADR 起草）
- [[R12 progress 2026-08-28]] —— port migration closure
- 失误细节见 `.blackboard/shifts/2026-08-28-r14-slack-channel-handoff.md` §"我的失误"（4 条：scope drift + import 路径 + `git add <dir>` + `describeSlackFiles` empty-name fallback）