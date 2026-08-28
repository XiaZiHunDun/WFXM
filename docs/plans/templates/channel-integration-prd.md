# <CHANNEL_NAME> 接生产 PRD

> **状态**：Active planning（待 operator review）
> **触发**：Owner 自报 `<CHANNEL_NAME>`，见 ADR `docs/plans/active/v5-channel-port-trigger-2026-08.md` §3
> **目的**：按 ADR §4 最小门槛把 `<CHANNEL_NAME>` 接到生产；Channel Port 维持隐性承载
> **目标 commit**：\<TBD at use\>
> **完成归档**：完成后在 ADR §7 完成记录段增一行

## 1. 背景

<一段：当前该 channel 是否存在 / Owner 用场景 / 与 WeChat 并行需求 / 是否需要 second Channel 触发证据>

## 2. Scope

### 2.1 In scope（本 PRD 覆盖）

| # | 工作 | 备注 |
| --- | --- | --- |
| 1 | 在 `butler-v5/packages/adapters/src/<CHANNEL_NAME>/` 建目录 | 协议级认证 + 消息解析 + 回复地址构造 |
| 2 | 实现入站 Trigger adapter | 与 WeChat adapter 同形，不抽公共抽象 |
| 3 | 实现出站 Outbox adapter | 走 R12 已上 Outbox |
| 4 | 单测覆盖（合法/非法/重复/附件/协议错/token 失效/超时） | 见 §3 |
| 5 | 测试环境端到端跑通 | 模拟 inbound → Run Engine → outbound |
| 6 | Owner 端到端走通一条真实对话 | ADR §4 #4（最关键证据） |
| 7 | 5 gate 全绿 | 不退化 |

### 2.2 Out of scope

- Channel Port 升 first-class —— 另立 ADR
- WeChat 退场 —— WeChat 仍唯一在生产 channel
- 多 Channel 去重 / 跨 channel Conversation —— 不在本 PRD
- Channel quota / rate limiting —— channel-internal 维护
- Channel 抽象抽取（base class / 共享协议层）—— DESIGN §7.1 + §18 YAGNI

## 3. Production-ready bar（per ADR §4）

- [ ] adapter 目录 + 入站 Trigger adapter + 出站 Outbox adapter 三件实装
- [ ] 单测：入站（合法/非法/重复/附件）、出站（文本/富媒体/重试）、错误路径（协议/token/网络）
- [ ] 测试环境端到端：simulated inbound → Run Engine → Outbox worker 发送 outbound
- [ ] **Owner 真实 workspace 端到端：Owner 发一条 → Butler 回一条，Run trace 完整**（最关键证据）
- [ ] 5 gate 全绿

## 4. 实施阶段

### Phase 1 — Adapter 实现（TDD）

先写失败的入站 / 出站单测，再实现 adapter。每个测试 commit 一次。

### Phase 2 — 端到端

测试环境模拟 → Owner 真实 workspace 端到端。

### Phase 3 — 验证 + 归档

5 gate 全绿 → ADR §7 完成记录段填一行（channel / 触发日期 / 完成日期 / 证据 commit-sha 或 Run-id）→ commit 推 origin main。

## 5. 不要做（重申）

- 不升 Channel Port 为 first-class
- 不抽 channel 公共抽象
- 不为新 channel 写 channel-portfolio 状态机
- 不复用 `_archive/packages/{application,infrastructure,contracts}` 入生产（`package-membership.test.ts` 第 (1) 守这条）
- 不为生产代码 import `r2-shim` 任何内容
- commit 用 `--no-verify`（R9.5 / R7.5 protocol）

## 6. 依赖与关系

- **触发 ADR**：`docs/plans/active/v5-channel-port-trigger-2026-08.md`
- **DESIGN**：§7.1（Channel 隐性承载 `⚪`）+ §18（第二 Channel 延后项）
- **复用 Outbox**：R12（commit `33af1722` + `278a0cc7`）
- **本模板**：`docs/plans/templates/channel-integration-prd.md`

---

> 模板：cloned from `docs/plans/templates/channel-integration-prd.md` by 触发 ADR §3；Channel Port 维持隐性承载不升 first-class。