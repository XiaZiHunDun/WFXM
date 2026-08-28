# Butler v5 架构对齐交接（2026-08-21）

> **状态**：Active — 供新会话接续「实现 vs DESIGN 对齐」  
> **目标架构 SSOT**：[`butler-v5/DESIGN.md`](../../../butler-v5/DESIGN.md)  
> **生产事实 SSOT**：[`docs/architecture/v5-production-architecture-2026-08.md`](../../architecture/v5-production-architecture-2026-08.md)  
> **路线图**：[`v5-post-boundary-roadmap-2026-08.md`](v5-post-boundary-roadmap-2026-08.md)  
> **产品边界**：[`v5-product-boundaries-2026-08.md`](../decisions/v5-product-boundaries-2026-08.md)  
> **工程交接规约**：[`v5-engineering-handoff-2026-08.md`](../decisions/v5-engineering-handoff-2026-08.md)

---

## 1. 本交接解决什么问题

上一会话已完成：

1. **P3 接缝交付**（已 push `main`）：RunTrigger 四入口、MCP manifest/连接/extraProviders、生产 Capability Registry。
2. **AI 守卫 v5 迁移**（commit `3b8fc61d`）：PostToolUse vitest、PreToolUse v5 受保护文件、`.cursorrules` banner、`butler-v5/AGENTS.md` §0、分步脚本 `scripts/v5_ai_guard/`。
3. **架构差距盘点**：对照 DESIGN vs 生产实现，形成下文 §4–§6。
4. **A1 Run 恢复语义**：`RunEngine.resumeRun`；审批同 Run + capability Step；`executeInbound` 拒抢 active main。
5. **A2 读模型默认**：`BUTLER_V5_READ_MODEL` 默认 `relational`（D2.1 production flip，2026-08-28 已覆盖早期 hybrid 默认）；`recall_history` / `summarize_today` 读 0002。
6. **A3 Grant schema**：`0003` 增 `delegable` / `approval_id` / `sandbox_profile`；审批签发写入 approvalId。
7. **A4 Run 状态闭环**：cancel/expire Owner API+CLI；`waiting_external` enter/resume 最小 runtime。
8. **A5 Child Run relational**：delegate 创建 `parentRunId` Run；worker 终态写 Step。
9. **A6 Intake 抽取**：`packages/runtime/src/intake/`（conversationId + normalize → RunTrigger）。
10. **A7 Loop 收编**：多轮循环迁入 `runtime/execution/conversation-loop`；apps 薄接线。
11. **A8 Sandbox + Grant profile**：统一 sandbox 入口；审批写/升 `sandboxProfile`。
12. **审批后多轮 + waiting_external 自动 resume**：post-approval `runConversationLoop`；trusted inbound 恢复原 Run。

**下一会话主线**：对齐缺口与 P4 MVP 已收；**验收**见 [`v5-acceptance-handoff-2026-08.md`](v5-acceptance-handoff-2026-08.md)。**不**重新立项已否决能力。

---

## 2. 新会话开篇（30 秒）

1. 读 [`.blackboard/state.md`](../../../.blackboard/state.md)
2. 读本文 §4（差距）+ §6（建议顺序）
3. 改代码前读 [`butler-v5/AGENTS.md`](../../../butler-v5/AGENTS.md) §0（生产 vs 脚手架）
4. 查 env：`docs/config/reference.md` 或 `butler-v5/.env.example`
5. 改 `butler-v5/` 后：`cd butler-v5 && pnpm test`

---

## 3. 当前生产路径（事实，勿与目标混淆）

```text
CLI / iLink / HTTP / WebSocket / Channel webhooks
        → apps/api (delivery shell)
        → runButlerLoop + RunEngine.executeInbound
        → PolicyGate + CapabilityRegistry (tools + MCP extraProviders)
        → @butler/adapters (LLM, WeChat, MCP, bubblewrap)
        → packages/persistence (event_store + 0002 relational)
        → PostgreSQL / PGlite
```

**未接生产（勿当已实现）**：

- `packages/application/_archive/`
- `packages/infrastructure/_archive/`（含重复 persistence 脚手架）
- `packages/ports` Effect Tag 全栈 DI 原型

---

## 4. 已对齐（新会话不必重做）

| 项 | 证据 |
| --- | --- |
| 单一 PolicyGate + Capability 边界 | `packages/runtime/src/policy-gate.ts`, `capability-boundary.ts`, `apps/api/src/tool-boundary.ts` |
| 模型不走 ActionRequest | `packages/adapters/src/llm-provider.ts` vs capability 路径 |
| waiting_approval + ScopedGrant + 同 Run 恢复 | `approval-runtime.ts`, `run-engine.resumeRun`, `approval-resume.ts`, 微信内联/Owner API |
| 同对话串行 | `packages/runtime/src/run-coordinator.ts`, migration `runs_one_active_main_uniq` |
| RunTrigger 四入口 | `packages/domain/src/runtime/run-trigger.ts`, `wechat-inbound-butler.ts`, `channel-inbound.ts`, `owner-approval-trigger.ts`, `cli-run.ts` |
| MCP opt-in | `apps/api/src/mcp-bootstrap.ts`, `mcp-manifest.ts`, `mcp-config.ts` |
| 子代理 allowlist、禁递归 delegate | `packages/runtime/src/delegate-runtime.ts`, `apps/api/src/capability-guard.ts` |
| AI 守卫 v5 | commit `3b8fc61d`, `scripts/v5_ai_guard/` |
| 浏览器不立项 | `v5-product-boundaries` §7 Owner 记录 |

---

## 5. 部分对齐（下一主线）

### 5.1 三模块边界（Intake / Execution / Governance）

- **设计**：Intake 只做身份、标准化、去重；不含 Loop/Policy。
- **已对齐（A6）**：`packages/runtime/src/intake/` — `conversation-id` + `normalizeWechatInbound` / `normalizeChannelInbound`（conversationId / idempotency / RunTrigger）；`apps/api` routes / channel-inbound 只做协议解析、鉴权与调用 Execution。
- **仍差**：Slack/Telegram 协议解析仍在 apps；无独立 `packages/intake` 包（刻意放 runtime，避免空包）。

### 5.2 Run Engine vs Loop 双轨

- **设计**：Execution 统一 Run/Step/恢复。
- **已对齐（A7）**：多轮 Loop 主体在 `packages/runtime/src/execution/conversation-loop.ts`（`runConversationLoop` + ports）；`apps/api/wechat-inbound-butler` 只做微信接线（历史/工具/LLM）并经 `RunEngine.executeInbound` 调用。
- **已对齐（A1）**：
  - 审批恢复经 `resumeApprovedCapability` → `RunEngine.resumeRun`（**同一 runId**），写入 capability/result Step；
  - `executeInbound` 在已有 active main Run 时抛 `ActiveMainRunConflict`，不再另开抢权主 Run。
- **已对齐**：审批 resume → 完整多轮 `runConversationLoop`（可再调工具）；`executeInbound` 对 `waiting_external` + trusted/owner 入站自动 resume 同 Run。
- **仍差**：无。

### 5.3 Run 状态机未闭环

| 状态 | 现状 |
| --- | --- |
| `waiting_approval` | ✅ runtime |
| `waiting_external` | ✅ enter/resume + **可信入站自动 resume**（`RunEngine.executeInbound`） |
| `cancelled` / `expired` | ✅ A4：Owner `POST /v1/owner/runs/:id/cancel`、`expire-overdue` + CLI `butler cancel` / `expire-runs` |
| Child Run | ✅ A5：`delegate` 创建 `parentRunId` Run（`triggerSource=parent_run`）；worker 写 running→succeeded/failed + result Step |

相关文件：`run-lifecycle.ts`, `run-engine.ts`, `runtime-store.ts`, `owner-routes.ts`, `cli`.

### 5.4 ScopedGrant 字段

- **设计**（DESIGN §7.3）：`delegable`, `sandboxProfile?`, `approvalId?`, capability 一等字段。
- **已对齐（A3）**：migration `0003` + drizzle；`ScopedGrantRecord` 含 `delegable` / `approvalId` / `sandboxProfile`。
- **已对齐（A8）**：审批签发时 `run_command` / `mcp_*` 写入 `sandboxProfile=workspace-write-network-deny`；Owner `elevateNetwork` / `sandboxProfile` 可提升到 `network-allow`；执行经 ALS 传到 sandbox 入口。
- **仍差**：capability 仍在 scope JSON（可接受）。

### 5.5 Sandbox（P2）

- **设计**：Grant 业务允许 + Sandbox 技术上限；提升 profile 写入 Grant。
- **已对齐（A8）**：统一入口 `executeArgvInSandbox`（adapters）；`run_command` 使用之；MCP Provider 与 core 同走 PolicyGate ALS；profile resolve 支持 network deny/allow。
- **仍差**：read_file 仍为进程内路径约束（无 bwrap）；远程 MCP I/O 不套 bwrap（profile 作 Grant 天花板与审计）。

### 5.6 Model Port / Decision 管道

- **设计**：统一 Decision（Respond / CallCapability / StartChildRun / WaitForApproval / Finish）。
- **现状**：LLM 在 `@butler/adapters`；native tool call + JSON fallback 在 delivery shell。
- **差距**：无单一 Decision 解码层；`packages/ports` LLMService 为 archive stub。

### 5.7 读模型双轨

- **设计**：当前状态表（0002）为业务事实；Message 不可变 append-only。
- **已对齐（D2.1 production flip，2026-08-28）**：默认 `BUTLER_V5_READ_MODEL=relational`（覆盖原 A2 hybrid 默认；代码 `packages/domain/src/runtime/store-contract.ts` `DEFAULT_READ_MODEL_SOURCE = "relational"` + 测试 `store-contract.test.ts:9-22` 锁定）；`recall_history` / `summarize_today` 仅读 0002；`event_store` 保留作 audit / outbox / 兼容；入站时 `backfillConversation` 可将 legacy 事件流一次性投影到 relational；`hybrid` opt-in 仅迁移期需要 event 回退。

### 5.8 Channel / Trigger

- WeChat ✅（`packages/adapters/src/wechat/`）
- Slack/Telegram/通用 API ⚠️ opt-in，逻辑在 `apps/api`，不在 adapters 包
- Schedule ✅ MVP（opt-in `BUTLER_V5_SCHEDULE_ENABLED`；`buildScheduleRunTrigger` + worker）
- Webhook Trigger ⚠️ Channel 入口已有；独立 webhook schedule 源未单开

### 5.9 MCP 注册契约（P3 Done — GitHub #3 + manifest provider 骨架 2026-08-25）

- ✅ manifest gate、consent、transport、extraProviders、multi-server bootstrap
- ✅ per-tool ScopedGrant（`scope.mcp` + `grantMatchesAction`）；Child Run 默认无 MCP（`ALLOWED_CAPABILITIES` 闭集）
- ✅ Provider 卸载 / consent 失效 → `revokeScopedGrantsForMcpServer`（fail-closed）
- ✅ manifest 声明 `defaultRisk` / `defaultSandboxProfile` / `auditPolicy`；Owner `GET /v1/owner/mcp/status` 返回 `provider`
- ✅ MCP 执行 trace 含 tool risk + provider 元数据 + Grant mcp scope
- ✅ Owner `POST .../revoke-grants` + `butler mcp revoke-grants`
- opt-in：`BUTLER_V5_MCP_READONLY_AUTO_ALLOW=1` — owner + manifest `risk=low` 免逐次 Ask

### 5.10 ActionRequest 命名

- 已有 ADT：`packages/domain/src/governance/types.ts` + `policy-gate.actionRequestFromTool`。
- 与 DESIGN 字段名（actor/capability/argumentsDigest）略异，语义已基本统一。

---

## 6. 刻意未做（不要在新会话当 backlog 强推）

| 项 | 依据 |
| --- | --- |
| 浏览器 / Playwright | Owner 2026-08-21 不立项 |
| 本地控制面完整 UI | Owner 2026-08-21 **不立项**；继续 API/CLI |
| Heartbeat / Schedule | **MVP 已交付**（默认关）；cron 表达式 / 微信推送后续按需 |
| Durable Memory / Project Knowledge | **Durable Memory MVP 已交付**；Project Knowledge 未开 |
| 文档 ingest | **MVP 已交付**（plaintext/markdown/pdf+预提取文本）；OCR/RAG 未开 |
| 本地 tracing / OTEL | **MVP 已交付**（本地缓冲 + 可选 stdout）；无外部 APM |
| Task / Procedure | **MVP 已交付**（跨对话待办 + 线性模板；`source=task`） |
| Effect 全栈 Application/Port DI | DESIGN 已裁决不强制；`_archive` 勿接生产 |
| v4 功能机械搬运 | 产品边界 |

---

## 7. 建议对齐顺序（下一会话可照此立项）

每步应：**小 PR / 单 commit 主题 + `pnpm test` + 必要时补 architecture test**。

| 序 | 主题 | 目标 | 主要触点 |
| --- | --- | --- | --- |
| **A1** | Run 恢复语义 | ✅ 审批后 `resumeRun` 同一 Run + capability Step；`executeInbound` 拒抢 active main | `run-engine.ts`, `approval-resume.ts`, `wechat-inbound-butler.ts` |
| **A2** | 读模型默认 | ✅ 默认 `relational`（D2.1 production flip 2026-08-28 覆盖原 hybrid 默认） | `store-contract.ts`, `tools.ts`, `.env.example`, docs |
| **A3** | Grant schema 扩展 | ✅ `delegable` / `approval_id` / `sandbox_profile`（0003） | `0003_scoped_grant_fields.sql`, `schema.ts`, `approval-runtime.ts` |
| **A4** | Run 状态闭环 | ✅ cancel/expire API+CLI；waiting_external 最小 lifecycle | `run-lifecycle.ts`, `owner-routes.ts`, `cli` |
| **A5** | Child Run relational | ✅ `parentRunId` Run + worker 写 Run/Step | `delegate-runtime.ts`, `subagent-worker.ts`, `tools.ts` |
| **A6** | Intake 抽取 | ✅ `runtime/intake`：normalize + conversationId；apps 只协议/鉴权 | `packages/runtime/src/intake/`, `routes.ts`, `channel-inbound.ts` |
| **A7** | Loop 收编 | ✅ `runtime/execution/conversation-loop`；apps 仅接线 | `execution/conversation-loop.ts`, `wechat-inbound-butler.ts` |
| **A8** | Sandbox 扩面 + Grant profile | ✅ 统一 `executeArgvInSandbox`；Grant 写/升 sandboxProfile；ALS 传递 | `sandbox/*`, `bubblewrap-runner.ts`, `approval-runtime.ts`, `workspace-tools.ts` |
| **按需** | Project Knowledge | 有 Owner 场景再单独立项；**Web UI / 浏览器已不立项**；P4 MVP 链已交付 | P4 roadmap |

**顺序约束**（来自 roadmap）：A3/A8 依赖 P1 稳定；A7 不要早于 A1/A5；新入口仍走 RunTrigger，禁止第三套 Policy/状态机。

---

## 8. 关键路径速查

| 用途 | 路径 |
| --- | --- |
| 微信 Loop | `butler-v5/apps/api/src/wechat-inbound-butler.ts` |
| Run 引擎 | `butler-v5/packages/runtime/src/run-engine.ts` |
| 审批 | `butler-v5/packages/runtime/src/approval-runtime.ts` |
| 工具边界 | `butler-v5/apps/api/src/tool-boundary.ts` |
| Policy | `butler-v5/packages/runtime/src/policy-gate.ts` |
| 子代理 | `butler-v5/apps/api/src/subagent-worker.ts` |
| Intake | `butler-v5/packages/runtime/src/intake/` |
| Conversation Loop | `butler-v5/packages/runtime/src/execution/conversation-loop.ts` |
| Schema | `butler-v5/packages/persistence/src/migrations/0001_initial.sql`, `0002_target_runtime.sql` |
| RunTrigger | `butler-v5/packages/domain/src/runtime/run-trigger.ts` |
| 状态转移纯函数 | `butler-v5/packages/domain/src/runtime/transitions.ts` |
| Architecture tests | `butler-v5/tests/architecture/` |

---

## 9. 验收命令

```bash
# 全量（必跑）
cd butler-v5 && pnpm test

# 架构/边界子集
cd butler-v5 && pnpm exec vitest run tests/architecture/ --reporter=dot

# 治理/审批
cd butler-v5 && pnpm exec vitest run packages/runtime/src/approval-runtime.test.ts apps/api/src/wechat-inline-approval.test.ts -q

# Run 引擎
cd butler-v5 && pnpm exec vitest run packages/runtime/src/run-engine.test.ts packages/runtime/src/run-coordinator.test.ts -q

# 读模型 backfill
cd butler-v5 && pnpm exec vitest run packages/persistence/src/runtime-backfill.test.ts -q
```

PostToolUse 快速冒烟（不跑 vitest）：

```bash
python3 scripts/ai_guard/post_tool_use_hook.py --match-only \
  butler-v5/apps/api/src/wechat-inbound-butler.ts
```

---

## 10. 不要做

- 不要把 `packages/application/_archive` 或 `infrastructure/_archive` 接回生产。
- 不要新建第二套 schema（`infrastructure` 旧 persistence 禁止接入）。
- 不要恢复 v4 `butler/` 为产品主线。
- 不要立项浏览器、RAG Studio、全量 MCP Marketplace。
- 修改 `scripts/ai_guard/*.py`、`.cursorrules`、`.claude/settings.json` 需 `[MANUAL-OVERRIDE]`；可用 `scripts/v5_ai_guard/` 分步脚本。
- 不要用 `docs/history/` 或 v4 文档推断 v5 实现。

---

## 11. 相关 commits（本线近期）

| Commit | 摘要 |
| --- | --- |
| `3b8fc61d` | AI 守卫 v5 迁移 [MANUAL-OVERRIDE] |
| `c919b44e` | 浏览器不立项 + AI 守卫排期文档 |
| `ed1ca8cb` | MCP extraProviders |
| `055545de` | CLI `butler run` + production capability registry |
| `61e69feb` | Owner API RunTrigger + manifest MCP |
| `fb8d9881` | RunTrigger 入站 + MCP manifest gate |

本地备份（AI 守卫迁移前）：`.backup/v5-ai-guard/LATEST` → `20260821-110247`

---

## 12. 上一班结论（给下一 Agent 的一句话）

**开发已收口**；下一班做验收，SSOT：[`v5-acceptance-handoff-2026-08.md`](v5-acceptance-handoff-2026-08.md)（`pnpm test:p4-acceptance` 起）。
