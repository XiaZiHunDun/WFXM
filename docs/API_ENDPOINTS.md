# Butler v5 — HTTP / WebSocket API Inventory

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計) | **读者**: Owner / Integrator / Contributor
> **关系**:
> - 功能视角（owner 能做什么）→ [`FEATURES.md`](FEATURES.md)
> - 目标架构 → [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) §8 (Triggers) + §10 (Governance)
> - 当前生产实现事实 → [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md)
> - D-series 累計 → [`ROADMAP.md`](ROADMAP.md)
> - 自托管指南（含 compose / healthcheck / inbound secret env）→ [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md)
> - 生产加固（secrets + 容器 + 网络）→ [`deployment/production-hardening.md`](deployment/production-hardening.md)
> - Agent 入口 → [`../AGENTS.md`](../AGENTS.md)

---

## 图例

- ✅ **已 ship**（handler 实装 + route 注册 + 入参校验 + 测试覆盖）
- 🟡 **已 ship 子集**（handler 实装但部分边界条件未完全验证）
- 📅 **延后 / stub**（route 注册但 handler 是 placeholder / 等待真触发）
- ❌ **明确 decline**（route 已删或合并）

## §1 Auth & Rate limit 总览

> D70 T4 SEC-002 闭环 → D71 T4 SO-005 owner-jargon 中文 rate-limit message。

| 维度 | 范围 | 详情 | Source 指针 |
|------|------|------|-------------|
| **Owner rate-limit** | 全部 `/v1/owner/*` | 120/min in-memory sliding window；env-tunable；key = `"owner"`（loopback）/ 未来 bearer subject | [`apps/api/src/owner-routes.ts:28`](../butler-v5/apps/api/src/owner-routes.ts), [`apps/api/src/lib/owner-rate-limit.ts`](../butler-v5/apps/api/src/lib/owner-rate-limit.ts) |
| **Inbound shared secret** | 全部 `/v1/wechat/inbound` + `/v1/channel/inbound` + `/v1/ws/subscribe` | `x-inbound-secret` header = `BUTLER_V5_INBOUND_SHARED_SECRET`（demo 默认 `test-inbound-secret-9c2f`） | [`apps/api/src/routes/inbound.ts`](../butler-v5/apps/api/src/routes/inbound.ts), [`routes/ws-subscribe.ts`](../butler-v5/apps/api/src/routes/ws-subscribe.ts) |
| **Slack signing secret** | `/v1/channel/slack/events` | Slack `X-Slack-Signature` HMAC + `X-Slack-Request-Timestamp` 防 replay；fail-closed (D63 T3 SEC-006) | [`apps/api/src/routes/slack-events.ts`](../butler-v5/apps/api/src/routes/slack-events.ts), [`packages/adapters/src/slack/`](../butler-v5/packages/adapters/src/slack/) |
| **Telegram secret_token** | `/v1/channel/telegram/webhook` | Telegram 自定义 `X-Telegram-Bot-Api-Secret-Token` | [`apps/api/src/routes/telegram-webhook.ts`](../butler-v5/apps/api/src/routes/telegram-webhook.ts) |
| **WeChat iLink token** | iLink 长轮询 | `BUTLER_V5_ILINK_TOKEN`；Channel Port iLink impl 注入（DESIGN §7.1 🟡） | [`apps/api/src/ilink-config.ts`](../butler-v5/apps/api/src/ilink-config.ts), [`packages/adapters/src/wechat/`](../butler-v5/packages/adapters/src/wechat/) |
| **`/health` no auth** | `/health` + `/health/live` | DESIGN §20 NON_LLM 2-tier；K8s/Docker 探针专用 | [`apps/api/src/routes/health.ts`](../butler-v5/apps/api/src/routes/health.ts) |

## §2 健康 / 探针（Health & Probe）

> D77 T5 `4d423c11` ship /health endpoint（liveness + readiness）；DESIGN §20 NON_LLM 2-tier 锁定。

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/health` | 无 | K8s/Docker 探针；liveness + readiness 综合 | [`apps/api/src/routes/health.ts:48`](../butler-v5/apps/api/src/routes/health.ts) | ✅ (D77 T5) |
| GET | `/health/live` | 无 | 纯 liveness（进程存活） | [`apps/api/src/routes/health.ts:84`](../butler-v5/apps/api/src/routes/health.ts) | ✅ (D77 T5) |

## §3 通道入站 Webhook（Channel Inbound）

> DESIGN §8 — Channel webhook 是 driving adapter 子类；负责协议级认证 / 标准化 / 配对 / 去重；归一化为 RunTrigger。

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| POST | `/v1/wechat/inbound` | `x-inbound-secret` | 微信内部 POST 入口（demo / 集成 / 测试主路径） | [`apps/api/src/routes/inbound.ts:24`](../butler-v5/apps/api/src/routes/inbound.ts) | ✅ |
| POST | `/v1/channel/inbound` | `x-inbound-secret` | 通用 channel 入口（iLink 内部使用） | [`apps/api/src/routes/inbound.ts:202`](../butler-v5/apps/api/src/routes/inbound.ts) | ✅ |
| POST | `/v1/channel/slack/events` | Slack signing secret | Slack Events API webhook；fail-closed；HMAC + replay 防 | [`apps/api/src/routes/slack-events.ts:29`](../butler-v5/apps/api/src/routes/slack-events.ts) | ✅ (D63 T3 SEC-006) |
| POST | `/v1/channel/telegram/webhook` | Telegram secret_token | Telegram Bot API webhook | [`apps/api/src/routes/telegram-webhook.ts:32`](../butler-v5/apps/api/src/routes/telegram-webhook.ts) | 🟡 (route ready, no adapter dir) |

## §4 WebSocket 订阅

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| POST | `/v1/ws/subscribe` | `x-inbound-secret` | WebSocket 长连接订阅 Run/Step 状态变更；订阅 cap（D63 T3 SEC-019） | [`apps/api/src/routes/ws-subscribe.ts:32`](../butler-v5/apps/api/src/routes/ws-subscribe.ts) | ✅ |

## §5 Owner HTTP API（`/v1/owner/*`）

> 全部 `/v1/owner/*` 走 owner-rate-limit（120/min）+ loopback 控制面。**当前无 bearer auth**（per D71+ 计划）。

### §5.1 Memories

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/memories` | owner-loopback | 列 Durable Memory（支持 `status/limit/offset/projectId`） | [`owner-routes/memories.ts:23`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ |
| POST | `/v1/owner/memories` | owner-loopback | 创建记忆（强 dedup：trigram Jaccard ≥0.85 → 409） | [`owner-routes/memories.ts:64`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ (G2 D41) |
| POST | `/v1/owner/memories/:memoryId/confirm` | owner-loopback | 确认单条记忆 | [`owner-routes/memories.ts:167`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ |
| POST | `/v1/owner/memories/:memoryId/reject` | owner-loopback | 拒绝单条记忆 | [`owner-routes/memories.ts:200`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ |
| POST | `/v1/owner/memories/:memoryId/rollback-auto-promote` | owner-loopback | 撤销 G4 3d auto-promote（7d 窗口内） | [`owner-routes/memories.ts:234`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ (G4 D42) |
| DELETE | `/v1/owner/memories/:memoryId` | owner-loopback | 删除记忆 | [`owner-routes/memories.ts:238`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ |
| POST | `/v1/owner/memories/confirm-batch` | owner-loopback | 批量 confirm（partial-failure OK） | [`owner-routes/memories.ts:347`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ (G3 D39) |
| POST | `/v1/owner/memories/reject-batch` | owner-loopback | 批量 reject | [`owner-routes/memories.ts:386`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ (G3 D39) |

### §5.2 Project Knowledge

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/project-knowledge` | owner-loopback | 列项目知识 | [`owner-routes/project-knowledge.ts:24`](../butler-v5/apps/api/src/owner-routes/project-knowledge.ts) | ✅ |
| GET | `/v1/owner/project-knowledge/:itemId` | owner-loopback | 查单条项目知识 | [`owner-routes/project-knowledge.ts:39`](../butler-v5/apps/api/src/owner-routes/project-knowledge.ts) | ✅ |
| POST | `/v1/owner/project-knowledge` | owner-loopback | 新增项目知识条目 | [`owner-routes/project-knowledge.ts:48`](../butler-v5/apps/api/src/owner-routes/project-knowledge.ts) | ✅ |
| POST | `/v1/owner/project-knowledge/sync` | owner-loopback | 触发项目知识源 sync（glob/watch worker） | [`owner-routes/project-knowledge.ts:138`](../butler-v5/apps/api/src/owner-routes/project-knowledge.ts) | ✅ |
| DELETE | `/v1/owner/project-knowledge/:itemId` | owner-loopback | 删除项目知识条目 | [`owner-routes/project-knowledge.ts:157`](../butler-v5/apps/api/src/owner-routes/project-knowledge.ts) | ✅ |

### §5.3 Documents

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/documents` | owner-loopback | 列 document | [`owner-routes/documents.ts:22`](../butler-v5/apps/api/src/owner-routes/documents.ts) | ✅ |
| GET | `/v1/owner/documents/:documentId` | owner-loopback | 查单条 document | [`owner-routes/documents.ts:39`](../butler-v5/apps/api/src/owner-routes/documents.ts) | ✅ |
| POST | `/v1/owner/documents` | owner-loopback | 新增 document | [`owner-routes/documents.ts:48`](../butler-v5/apps/api/src/owner-routes/documents.ts) | ✅ |
| POST | `/v1/owner/documents/:documentId/promote-memory` | owner-loopback | document → durable memory（upgrade） | [`owner-routes/documents.ts:118`](../butler-v5/apps/api/src/owner-routes/documents.ts) | ✅ |
| POST | `/v1/owner/documents/:documentId/promote-project-knowledge` | owner-loopback | document → project knowledge（upgrade） | [`owner-routes/documents.ts:122`](../butler-v5/apps/api/src/owner-routes/documents.ts) | ✅ |
| DELETE | `/v1/owner/documents/:documentId` | owner-loopback | 删除 document | [`owner-routes/documents.ts:164`](../butler-v5/apps/api/src/owner-routes/documents.ts) | ✅ |

### §5.4 Conversations & Schedule

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/conversations` | owner-loopback | 列 conversations | [`owner-routes/conversations-schedule.ts:14`](../butler-v5/apps/api/src/owner-routes/conversations-schedule.ts) | ✅ |
| GET | `/v1/owner/conversations/:conversationId/messages` | owner-loopback | 查 conversation 消息流 | [`owner-routes/conversations-schedule.ts:24`](../butler-v5/apps/api/src/owner-routes/conversations-schedule.ts) | ✅ |
| POST | `/v1/owner/schedule/tick` | owner-loopback | 手动触发 schedule tick（绕过 cron） | [`owner-routes/conversations-schedule.ts:40`](../butler-v5/apps/api/src/owner-routes/conversations-schedule.ts) | ✅ |

### §5.5 Approvals & Runs

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/approvals` | owner-loopback | 列 waiting_approval steps | [`owner-routes/approvals-runs.ts:19`](../butler-v5/apps/api/src/owner-routes/approvals-runs.ts) | ✅ |
| POST | `/v1/owner/approvals/:stepId/approve` | owner-loopback | 批准 waiting step（签发 `remainingUses=1` Grant） | [`owner-routes/approvals-runs.ts:45`](../butler-v5/apps/api/src/owner-routes/approvals-runs.ts) | ✅ |
| POST | `/v1/owner/approvals/:stepId/deny` | owner-loopback | 拒绝 waiting step | [`owner-routes/approvals-runs.ts:47`](../butler-v5/apps/api/src/owner-routes/approvals-runs.ts) | ✅ |
| POST | `/v1/owner/runs/:runId/cancel` | owner-loopback | 取消活动 Run | [`owner-routes/approvals-runs.ts:67`](../butler-v5/apps/api/src/owner-routes/approvals-runs.ts) | ✅ |
| POST | `/v1/owner/runs/expire-overdue` | owner-loopback | 批量过期 overdue runs | [`owner-routes/approvals-runs.ts:106`](../butler-v5/apps/api/src/owner-routes/approvals-runs.ts) | ✅ |

### §5.6 Tasks & Procedures & Traces

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/traces` | owner-loopback | 列 traces（local dev artifact） | [`owner-routes/traces-procedures-tasks.ts:17`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |
| POST | `/v1/owner/traces/clear` | owner-loopback | 清空 traces | [`owner-routes/traces-procedures-tasks.ts:48`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |
| GET | `/v1/owner/procedures` | owner-loopback | 列 procedures | [`owner-routes/traces-procedures-tasks.ts:54`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |
| POST | `/v1/owner/procedures` | owner-loopback | 新增 procedure | [`owner-routes/traces-procedures-tasks.ts:61`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |
| GET | `/v1/owner/tasks` | owner-loopback | 列 tasks | [`owner-routes/traces-procedures-tasks.ts:114`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |
| POST | `/v1/owner/tasks` | owner-loopback | 新增 task | [`owner-routes/traces-procedures-tasks.ts:132`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |
| POST | `/v1/owner/tasks/:taskId/run` | owner-loopback | 触发 task run | [`owner-routes/traces-procedures-tasks.ts:187`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |
| POST | `/v1/owner/tasks/:taskId/done` | owner-loopback | 标记 task done | [`owner-routes/traces-procedures-tasks.ts:189`](../butler-v5/apps/api/src/owner-routes/traces-procedures-tasks.ts) | ✅ |

### §5.7 Audit & Fatigue

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/audit/fatigue` | owner-loopback | 查 owner 视角疲劳信号（4th cycle carry） | [`owner-routes/audit-fatigue.ts:123`](../butler-v5/apps/api/src/owner-routes/audit-fatigue.ts) | ✅ (D74 T3) |
| POST | `/v1/owner/audit/fatigue/replay` | owner-loopback | 重放 fatigue signal（batch ≤1000 ids） | [`owner-routes/audit-fatigue.ts:131`](../butler-v5/apps/api/src/owner-routes/audit-fatigue.ts) | ✅ |

### §5.8 MCP

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/mcp/status` | owner-loopback | 查 MCP servers 状态 | [`owner-routes/mcp.ts:17`](../butler-v5/apps/api/src/owner-routes/mcp.ts) | ✅ |
| POST | `/v1/owner/mcp/servers/:serverId/revoke-grants` | owner-loopback | 撤销 server 全部 grant | [`owner-routes/mcp.ts:83`](../butler-v5/apps/api/src/owner-routes/mcp.ts) | ✅ |

### §5.9 Usage

| Method | Path | Auth | 用途 | Source 指针 | 状态 |
|--------|------|------|------|------------|------|
| GET | `/v1/owner/usage` | owner-loopback | 查 LLM 用量统计（token + costUsd） | [`owner-routes/usage.ts:175`](../butler-v5/apps/api/src/owner-routes/usage.ts) | ✅ (D44 product-layer) |

## §6 总览 / 统计

| Surface | 端点数 | Files |
|---------|--------|-------|
| Health & Probe | 2 | `routes/health.ts` |
| Channel Inbound Webhook | 4 | `routes/{inbound,slack-events,telegram-webhook}.ts` |
| WebSocket | 1 | `routes/ws-subscribe.ts` |
| Owner HTTP API | **40** | 9 sub-routers in `owner-routes/` (3 split helpers: `approvals-approve.ts` / `memories-rollback.ts` / `documents-promote-memory.ts`) |
| **Total** | **47** | **14 main + 3 split = 17 handler files** |

**§2-§5 routes 合计 47 endpoint**（2 health + 4 channel + 1 WS + 40 owner）。

## §7 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 功能清单（owner 能干什么） | [`FEATURES.md`](FEATURES.md) |
| 目标架构（Triggers / Run / Governance） | [`../butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) §8 + §10 |
| 当前生产实现事实 | [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) |
| 自托管指南（env 变量 + docker） | [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md) |
| 生产加固（secrets + 容器 + 网络） | [`deployment/production-hardening.md`](deployment/production-hardening.md) |
| 端口契约清单 | [`../butler-v5/packages/ports/port-catalog.md`](../butler-v5/packages/ports/port-catalog.md) |
| Rate-limit 实现 | [`apps/api/src/lib/owner-rate-limit.ts`](../butler-v5/apps/api/src/lib/owner-rate-limit.ts) |

---

**End of API_ENDPOINTS.md** | D80 cycle 26 inventory batch | **47 endpoint / 14 main + 3 split handler files / 5 categories**