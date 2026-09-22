# Butler v5 — Feature Inventory

> **生成日期**: 2026-09-22 | **状态**: post-D79 (127 ship 累計) | **读者**: Owner / Contributor / 用户
> **关系**:
> - 目标架构（SSOT）→ [`butler-v5/DESIGN.md`](../butler-v5/DESIGN.md)
> - 当前实现事实 → [`docs/architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md)
> - D-series 累計 → [`docs/ROADMAP.md`](ROADMAP.md)
> - Owner FAQ → [`docs/FAQ.md`](FAQ.md)
> - 文档分层手册 → [`docs/DOCUMENTATION.md`](DOCUMENTATION.md)
> - 端口清单 → [`../butler-v5/packages/ports/port-catalog.md`](../butler-v5/packages/ports/port-catalog.md)
> - Agent 入口 → [`../AGENTS.md`](../AGENTS.md)

---

## 图例

- ✅ **已 ship**（生产可用；入口文档 + 守门齐全）
- 🟡 **已 ship 子集**（核心可生产，外延未完）
- 📅 **延后**（DESIGN §18 trigger 条件未达；D53c reeval 0 新 evidence）
- ❌ **明确 decline**（D51 — 实证不可行；保留记录但不启）

## §1 入站与触发（Triggers）

> DESIGN §8 — 所有入口归一化为 `RunTrigger`；`source` ∈ `channel | cli | api | webhook | schedule | parent_run`。

| 功能名 | Owner 能干什么 | 依赖 | Source 指针 | 状态 |
|--------|--------------|------|------------|------|
| **WeChat iLink 入站** | 通过微信发消息（文本/附件/命令）触发 Run | `wechat-gateway`, `BUTLER_V5_INBOUND_SHARED_SECRET`, iLink | [`apps/api/src/wechat-intake.ts`](../butler-v5/apps/api/src/wechat-intake.ts), [`ilink-poller.ts`](../butler-v5/apps/api/src/ilink-poller.ts), DESIGN §8 | ✅ |
| **WeChat 会话状态 / digest** | 跨重启恢复 waiting Run；session-open 时把上次离开时摘要前置 | durable memory, session-state | [`apps/api/src/wechat-session-state.ts`](../butler-v5/apps/api/src/wechat-session-state.ts), [`wechat-session-digest.ts`](../butler-v5/apps/api/src/wechat-session-digest.ts) | ✅ (B-session-digest `076a0b45`) |
| **WeChat 内联命令** | `/最近` `/记忆` `/待办` `/撤销` `/重试` `/诊断` `/确认记忆` `/记住` `/记忆候选` `/audit` | wechat-intake-llm, command registry | [`apps/api/src/wechat-inbound-commands.ts`](../butler-v5/apps/api/src/wechat-inbound-commands.ts), [`wechat-memory-commands.ts`](../butler-v5/apps/api/src/wechat-memory-commands.ts) | ✅ |
| **WeChat inline approval** | 回复 `y` / `👌` / `✅` / `👍` / `❌` / `👎` 真实恢复 Run | approval-runtime | [`apps/api/src/wechat-inline-approval.ts`](../butler-v5/apps/api/src/wechat-inline-approval.ts), [`wechat-approval-trigger.ts`](../butler-v5/apps/api/src/owner-approval-trigger.ts) | ✅ (D44 P0 `69dc924c`) |
| **WeChat 多 tool chain 撤销** | 单条 `/撤销` 撤回整链 tool 调用 | workspace-tools-undo | [`apps/api/src/workspace-tools-undo.ts`](../butler-v5/apps/api/src/workspace-tools-undo.ts) | ✅ (D49 `45bb28f7`) |
| **WeChat task digest (1h throttle)** | sweeper 自动 push 待处理 task 摘要 | sweeper-notify | [`apps/api/src/wechat-sweeper-notify.ts`](../butler-v5/apps/api/src/wechat-sweeper-notify.ts) | ✅ (P3 `71e0b44c`) |
| **Slack 事件入站** | 通过 Slack 触发 Run（events API） | slack SDK + webhook | [`apps/api/src/routes/slack-events.ts`](../butler-v5/apps/api/src/routes/slack-events.ts), [`packages/adapters/src/slack/`](../butler-v5/packages/adapters/src/slack/) (5 文件) | 🟡 (skeleton, 经 channel-outbound 直连) |
| **Telegram Webhook 入站** | 通过 Telegram 触发 Run | telegram webhook | [`apps/api/src/routes/telegram-webhook.ts`](../butler-v5/apps/api/src/routes/telegram-webhook.ts) | 📅 (no adapter dir) |
| **owner-direct CLI** | 本地命令行触发 Run / 调试 | cli + node:test | [`butler-v5/cli/src/index.ts`](../butler-v5/cli/src/index.ts), [`wechat-login.ts`](../butler-v5/cli/src/wechat-login.ts) | ✅ |
| **HTTP `POST /v1/wechat/inbound`** | 内部 POST 触发（demo / 集成 / 测试） | `x-inbound-secret` | [`apps/api/src/routes/inbound.ts`](../butler-v5/apps/api/src/routes/inbound.ts) | ✅ |
| **Owner HTTP API `/v1/owner/*`** | CRUD memories / tasks / procedures / projects / approvals / audit / usage | owner-routes | [`apps/api/src/owner-routes.ts`](../butler-v5/apps/api/src/owner-routes.ts) | ✅ |
| **WebSocket 订阅** | 长连接订阅 Run/Step 状态变更 | ws-subscribe | [`apps/api/src/routes/ws-subscribe.ts`](../butler-v5/apps/api/src/routes/ws-subscribe.ts) | ✅ |
| **Schedule / Cron 定时触发** | 周期或单次定时启动 Run | schedule-run + schedule-worker | [`apps/api/src/schedule-run.ts`](../butler-v5/apps/api/src/schedule-run.ts), [`schedule-worker.ts`](../butler-v5/apps/api/src/schedule-worker.ts) | ✅ |
| **parent_run (Subagent)** | 子 Run 由 `delegate-runtime` 直接触发，不反向 Intake | delegate-runtime | [`packages/runtime/src/delegate-runtime.ts`](../butler-v5/packages/runtime/src/delegate-runtime.ts), DESIGN §8 | ✅ |

## §2 对话 / Run / 审批（Conversation / Run / Approval）

> DESIGN §4 (5 聚合) + §6 (Application 单例 RunEngine) + §10 (Governance) + §13 (风险三分类)。

| 功能名 | Owner 能干什么 | 依赖 | Source 指针 | 状态 |
|--------|--------------|------|------------|------|
| **Conversation 聚合** | 长期交互容器；跨 Run 持续；channel 映射 | RuntimeStore | [`packages/domain/src/conversation/`](../butler-v5/packages/domain/src/conversation/) | ✅ |
| **Run 状态机** | `queued → running → waiting_approval/waiting_external → succeeded/failed/cancelled/expired` | RunEngine | [`packages/domain/src/runtime/types.ts`](../butler-v5/packages/domain/src/runtime/types.ts), DESIGN §4.2 | ✅ |
| **Step 记录** | Run 内每次模型/能力/审批/结果（immutable tracer） | runtimeStore.createStep | [`packages/runtime/src/run-engine.ts`](../butler-v5/packages/runtime/src/run-engine.ts) | ✅ |
| **ScopedGrant (12 字段)** | 副作用授权票据：`subject/capability/scope/expiresAt/remainingUses/delegable/sandboxProfile/networkAllowlist` + DB `id/runId/createdAtMs` | governance | [`packages/domain/src/governance/types.ts`](../butler-v5/packages/domain/src/governance/types.ts), DESIGN §10.3 | ✅ |
| **RunEngine (单例)** | 唯一工作单元执行器；7 职责 = trigger/Model Port/Decision/ActionRequest/Policy Gate/Step persist/预算 | runtime | [`packages/runtime/src/run-engine.ts`](../butler-v5/packages/runtime/src/run-engine.ts), DESIGN §6 | ✅ |
| **5-tag ModelDecision ADT** | `Respond / CallCapability / StartChildRun / WaitForApproval / Finish` | decoder | [`packages/domain/src/runtime/decision.ts`](../butler-v5/packages/domain/src/runtime/decision.ts), DESIGN §6.2 | ✅ |
| **Decoder 失败 retry** | decode 失败注入 system msg + max retries；超限后 Respond 含 raw | conversation-loop | DESIGN §6.2 line 269 | ✅ |
| **waiting_approval Step** | 高风险动作等待 owner 确认；持久化动作摘要+过期+响应主体 | policy-gate | [`packages/runtime/src/approval-runtime.ts`](../butler-v5/packages/runtime/src/approval-runtime.ts), DESIGN §10.2 | ✅ |
| **approval-resume** | 重启 / 审批后安全恢复（lock + concurrency） | approval-runtime | [`apps/api/src/approval-resume.ts`](../butler-v5/apps/api/src/approval-resume.ts) | ✅ |
| **Subagent 委派** | 把子任务委派给配置化角色（child run + 收窄 grants） | delegate-runtime | [`packages/runtime/src/delegate-runtime.ts`](../butler-v5/packages/runtime/src/delegate-runtime.ts) | ✅ |
| **delegation-grants** | 子 Run 权限不宽于父（per-capability narrowing） | governance | [`apps/api/src/delegation-grants.ts`](../butler-v5/apps/api/src/delegation-grants.ts), DESIGN §4.2 | ✅ |
| **delegate-capabilities** | 子 Run 可用 capability 子集解析 | runtime | [`apps/api/src/delegate-capabilities.ts`](../butler-v5/apps/api/src/delegate-capabilities.ts) | ✅ |
| **subagent-worker** | 长跑 subagent 的 process / payload / rejection handling | runtime | [`apps/api/src/subagent-worker*.ts`](../butler-v5/apps/api/src/subagent-worker.ts) | ✅ |

## §3 知识与记忆（Knowledge / Memory）

> DESIGN §12 — 3 层：Transcript / Durable Memory / Project Knowledge；§18 row 3 G1-G5 治理链路已闭环。

| 功能名 | Owner 能干什么 | 依赖 | Source 指针 | 状态 |
|--------|--------------|------|------------|------|
| **Conversation Message (Transcript)** | 不可变原始消息；保留策略约束 | RuntimeStore | [`packages/domain/src/conversation/`](../butler-v5/packages/domain/src/conversation/) | ✅ |
| **Durable Memory 候选 / 确认 / 拒绝 / 回滚** | 模型产出 owner 偏好候选；可 confirm/reject/rollback | `durable_memories` 表 | [`packages/domain/src/knowledge/durable-memory.ts`](../butler-v5/packages/domain/src/knowledge/durable-memory.ts) | ✅ |
| **G3 批量 UI** | 微信 `/记忆候选` + `POST /v1/owner/memories/confirm-batch\|reject-batch` | owner-routes | [`apps/api/src/owner-routes/memories.ts`](../butler-v5/apps/api/src/owner-routes/memories.ts) | ✅ (D39 `47b97352`) |
| **G1 7d 过期清理** | stale candidate 自动 expire（opt-in sweeper） | sweeper | [`apps/api/src/candidate-expires-sweeper.ts`](../butler-v5/apps/api/src/candidate-expires-sweeper.ts) | ✅ (D40 `a217b8fe`) |
| **G2 重复检测 (trigram Jaccard)** | ≥0.85 返回 409 + existingMemoryId；`force=true` bypass | recall | [`apps/api/src/owner-routes/memory-dedup.ts`](../butler-v5/apps/api/src/owner-routes/memory-dedup.ts) | ✅ (D41 `7a3c6c7b`) |
| **G4 3d 自动 promote + 7d 撤销** | candidate 3d 自动 confirmed；owner 7d rollback window + audit | sweeper | [`apps/api/src/auto-promote-sweeper.ts`](../butler-v5/apps/api/src/auto-promote-sweeper.ts), [`auto-promote-config.ts`](../butler-v5/apps/api/src/auto-promote-config.ts) | ✅ (D42 `55e4f46a`) |
| **G5 跨 project recall** | `recall_project_knowledge` 可指定 `projectId` 或 `*`；结果带 `[projectId]` 标签 | recall | [`apps/api/src/owner-routes/project-knowledge.ts`](../butler-v5/apps/api/src/owner-routes/project-knowledge.ts) | ✅ (D43 `53f0835a`) |
| **Project Knowledge** | 项目文档源（glob / watch / sync） | `project_knowledge_items` | [`packages/domain/src/knowledge/project-knowledge.ts`](../butler-v5/packages/domain/src/knowledge/project-knowledge.ts) | ✅ |
| **Document ingest** | 文档解析入项目知识库 | knowledge-sources-config | [`apps/api/src/project-knowledge-sources-config.ts`](../butler-v5/apps/api/src/project-knowledge-sources-config.ts) | ✅ |
| **Working Set (有预算上下文)** | 模型输入 = recent + rolling summary + uncompressed steps + selected memory | runtime | [`packages/runtime/src/working-set.ts`](../butler-v5/packages/runtime/src/working-set.ts), DESIGN §6.1 | ✅ |
| **Context Compaction** | 滚动摘要 / 截断（不删 Transcript） | working-set | [`packages/runtime/src/working-set.ts`](../butler-v5/packages/runtime/src/working-set.ts), DESIGN §6.1 | ✅ |
| **durable-memory-inject** | 模型 working-set 注入候选记忆 | runtime | [`apps/api/src/durable-memory-inject.ts`](../butler-v5/apps/api/src/durable-memory-inject.ts) | ✅ |

## §4 工作区工具（Workspace Tools）

> DESIGN §9 — 所有副作用通过 Capability Provider 注册 + §10 Policy Gate；workspace-tools 是 default registered set。

| 功能名 | Owner 能干什么 | 依赖 | Source 指针 | 状态 |
|--------|--------------|------|------------|------|
| **read_file** | 读工作区文件（path 校验 + 内容返回） | capability-boundary | [`apps/api/src/workspace-tools.ts`](../butler-v5/apps/api/src/workspace-tools.ts) | ✅ |
| **write_file** | 写工作区文件（low/medium risk；workspace-relative path 限制） | policy-gate | [`apps/api/src/workspace-tools.ts`](../butler-v5/apps/api/src/workspace-tools.ts) | ✅ (D79 T1 lesson #2) |
| **run_command (allowlist)** | 跑允许列表内命令（`ls/cat/grep/find/...`） | `ALLOWED_RUN_COMMANDS` | [`apps/api/src/workspace-tools.ts`](../butler-v5/apps/api/src/workspace-tools.ts) | ✅ |
| **single-file undo** | 写文件可单步 undo | undo-stack | [`apps/api/src/workspace-tools-undo.ts`](../butler-v5/apps/api/src/workspace-tools-undo.ts) | ✅ |
| **multi-tool chain undo** | `/撤销` 撤回整链 | undo-stack | [`apps/api/src/workspace-tools-undo.ts`](../butler-v5/apps/api/src/workspace-tools-undo.ts) | ✅ (D49) |
| **Bubblewrap sandbox (partial)** | 高风险 sandbox profile 走 bubblewrap 隔离 | sandbox profiles | [`packages/adapters/src/sandbox/`](../butler-v5/packages/adapters/src/sandbox/), R16 | 🟡 |
| **Host credentials** | `run_command` 注入凭证；fail-closed | credential-provider | [`packages/adapters/src/credentials/host-credentials.ts`](../butler-v5/packages/adapters/src/credentials/host-credentials.ts) | ✅ (R10 P2) |
| **MCP provider bootstrap** | 远程副作用能力接入 | mcp-bootstrap | [`apps/api/src/mcp-bootstrap.ts`](../butler-v5/apps/api/src/mcp-bootstrap.ts) | ✅ |
| **MCP readonly 政策** | MCP 工具分级 read-only | mcp-readonly-policy | [`apps/api/src/mcp-readonly-policy.ts`](../butler-v5/apps/api/src/mcp-readonly-policy.ts) | ✅ |
| **MCP manifest** | 工具 manifest 描述 + 信任 | mcp-manifest | [`apps/api/src/mcp-manifest.ts`](../butler-v5/apps/api/src/mcp-manifest.ts) | ✅ |
| **MCP tools dispatch** | 已注册 MCP 工具路由 | mcp-tools | [`apps/api/src/mcp-tools.ts`](../butler-v5/apps/api/src/mcp-tools.ts) | ✅ |
| **Browser capability** | bubblewrap + Playwright 共享 session | sandbox | DESIGN §7.1 条件准入 | 🟡 (R16 partial) |
| **Network allowlist (P2b)** | `ScopedGrant.networkAllowlist` 限制 workspace write 类跨网络出口 | governance | DESIGN §10.3 line 459 | 🟡 |

## §5 权限与治理（Policy / Governance）

> DESIGN §10 — ActionRequest → Policy → waiting_approval → ScopedGrant → Provider；§13 风险三分类；10 GUARD。

| 功能名 | Owner 能干什么 | 依赖 | Source 指针 | 状态 |
|--------|--------------|------|------------|------|
| **Policy Gate (单例)** | `Allow / Deny(reason) / RequireApproval(approver)` | domain.permissions | [`packages/runtime/src/policy-gate.ts`](../butler-v5/packages/runtime/src/policy-gate.ts), DESIGN §10.1 | ✅ |
| **风险三分类** | auto / grant-required / always-confirm | PermissionPolicy | [`packages/domain/src/permissions/types.ts`](../butler-v5/packages/domain/src/permissions/types.ts), DESIGN §13 | ✅ |
| **Capability guard** | 注册表唯一入口；`CapabilityRegistry.register` 同步 | registry | [`apps/api/src/capability-guard.ts`](../butler-v5/apps/api/src/capability-guard.ts) | ✅ |
| **approval-runtime** | 等待 + 恢复 + 拒绝/过期路径；Always-confirm `remainingUses=1` | runtime | [`packages/runtime/src/approval-runtime.ts`](../butler-v5/packages/runtime/src/approval-runtime.ts) | ✅ |
| **owner-approval-trigger** | owner 触发 approval 流程 | owner | [`apps/api/src/owner-approval-trigger.ts`](../butler-v5/apps/api/src/owner-approval-trigger.ts) | ✅ |
| **ActionRequest 5 字段** | `subject / kind / risk / digest / payload` | governance | DESIGN §10 audit state | ✅ |
| **G-1 IntentReceipt 证据门控** | run 必有 trigger + 预算 + idempotency | governance | DESIGN §20 invariant list | ✅ |
| **G-2 承重代码保护** | core 不 import 适配器；arch tests 锁定 | architecture tests | [`tests/architecture/section3-dependency-rules.test.ts`](../butler-v5/tests/architecture/section3-dependency-rules.test.ts) | ✅ |
| **G-3 Owner 离线策略** | owner 离线阈值（`GUARDS_OWNER_OFFLINE_THRESHOLD_MS`） | guards | env config | ✅ |
| **G-4 HUMAN 签名验证** | 敏感路径 `commit -m [MANUAL-OVERRIDE]` 强制人工 | handoff | `.cursorrules` + AGENTS.md §4 | ✅ |
| **G-5 多文件链路校验** | 一次写多文件一致性 | workspace-tools | [`apps/api/src/workspace-tools.ts`](../butler-v5/apps/api/src/workspace-tools.ts) | ✅ |
| **G-6 2 级验证选择** | low/medium (Grant) + always-confirm (per-action) | policy-gate | DESIGN §13 | ✅ |
| **G-7 角色分离** | author / reviewer 分离；M9 owner-jargon / inline-approval 改 reply 字符串必须同 batch 改测试 | handoff | AGENTS.md + D63 T2 lesson | ✅ |
| **G-8 3 层自愈** | 重试 → 回滚 → escalate | run-engine | runtime | ✅ |
| **G-9 反模式归档** | `docs/history` 不作实现依据 | docs | [`docs/history/`](../docs/history/), AGENTS.md §3 | ✅ |
| **G-10 混沌演练** | `GUARDS_CHAOS_ENABLED` 开关 | guards | env config | ✅ |

## §6 审计与可观测（Audit / Observability）

> DESIGN §11 (混合数据模型) + §14 (可靠性与可观测) — 14/14 字段捕获 (D21+D23+D24)。

| 功能名 | Owner 能干什么 | 依赖 | Source 指针 | 状态 |
|--------|--------------|------|------------|------|
| **audit_events 表 (append-only)** | 安全拒绝 + 越界 + always-confirm 不可变记录 | persistence | [`packages/persistence/src/event-bridge.ts`](../butler-v5/packages/persistence/src/event-bridge.ts), DESIGN §11.2 | ✅ |
| **exec-audit** | capability 执行审计（含 policy decision + grant id） | runtime | [`apps/api/src/exec-audit.ts`](../butler-v5/apps/api/src/exec-audit.ts) | ✅ |
| **audit-log (owner query)** | owner 查审计流（带过滤 + 分页） | owner-routes | [`apps/api/src/audit-log.ts`](../butler-v5/apps/api/src/audit-log.ts) | ✅ |
| **audit-fatigue signal** | owner 视角疲劳信号（4th cycle carry D74 T3） | runtime | [`apps/api/src/owner-routes/audit-fatigue.ts`](../butler-v5/apps/api/src/owner-routes/audit-fatigue.ts) | ✅ (D74 T3) |
| **audit emit actor** | `currentOwnerActor()` 单一来源（`owner-direct` / `subagent-worker`） | runtime | D73 T4 `cccb6e87` [MANUAL-OVERRIDE] | ✅ |
| **TraceEvent 14 字段** | `conversationId/runId/stepId/parentRunId/subject/triggerSource/capability/policyDecision/grantId/waitingStepId/durationMs/token/costUsd` + retry/终止原因 in `detail` | trace | [`tests/architecture/section14-*.test.ts`](../butler-v5/tests/architecture/), DESIGN §14 | ✅ |
| **LLM pricing (env-driven)** | `BUTLER_V5_PRICING_<MODEL>_*_PER_MTOK` 实时填 costUsd；缺 = null | llm-pricing | [`apps/api/src/llm-pricing.ts`](../butler-v5/apps/api/src/llm-pricing.ts), DESIGN §14 | ✅ |
| **Model Port (5 providers)** | Anthropic / OpenAI / DeepSeek / DashScope / MiniMax；`resolveModelForRole(env, role)` | model-port | [`packages/ports/src/core/model-port.ts`](../butler-v5/packages/ports/src/core/model-port.ts), [`packages/adapters/src/model-router.ts`](../butler-v5/packages/adapters/src/model-router.ts) | ✅ (D44 P5) |
| **LLM fallback + 用量记账** | provider 失败转移 + 计量 | model-router | [`packages/adapters/src/model-router.ts`](../butler-v5/packages/adapters/src/model-router.ts) | ✅ |
| **Outbox (事务后异步)** | 出站 Channel + Child Run 派发 + 事务后通知 | outbox | [`packages/persistence/src/outbox.ts`](../butler-v5/packages/persistence/src/outbox.ts), DESIGN §11.3 | ✅ |
| **runtime-store (postgres)** | Drizzle/postgres 生产 store | persistence | [`packages/persistence/src/runtime-store.ts`](../butler-v5/packages/persistence/src/runtime-store.ts) | ✅ |
| **memory runtime-store (in-memory)** | 第二持久化实现（demo / 测试） | persistence | [`packages/persistence/src/memory/runtime-store.ts`](../butler-v5/packages/persistence/src/memory/runtime-store.ts) | ✅ (D46 触发) |
| **`/诊断` 入口** | owner 视角健康快照 + 阈值 | diagnostic-thresholds | [`docs/ops/diagnostic-thresholds.md`](ops/diagnostic-thresholds.md) | ✅ |
| **`/health` (liveness + readiness)** | K8s/Docker 健康探针；§20 KNOWN_ENTRY_POINTS non-LLM 2-tier | health route | [`apps/api/src/routes/health.ts`](../butler-v5/apps/api/src/routes/health.ts) | ✅ (D77 T5 `4d423c11`) |

## §7 运维与部署（Operations / Deployment）

> DESIGN §16 (单机自托管模块化单体) + D77 cycle 23 部署 7 件套 + D79 cycle 25 demo 4 件套 + D76 cycle 22 OSS 5 件套。

| 功能名 | Owner 能干什么 | 依赖 | Source 指针 | 状态 |
|--------|--------------|------|------------|------|
| **Dockerfile (multi-stage + multi-arch)** | 镜像构建（production deps） | docker | [`../Dockerfile`](../Dockerfile), `.dockerignore` | ✅ (D77 T1 `aa392db3`) |
| **docker-compose.yml** | 本地 postgres + butler 启动（healthcheck + read_only + resource limits） | compose | [`../docker-compose.yml`](../docker-compose.yml) | ✅ (D77 T4 `29c99d67`) |
| **release.yml (multi-arch CI/CD)** | tag push → ghcr.io + cosign sign + SBOM | github actions | [`.github/workflows/release.yml`](../.github/workflows/release.yml) | ✅ (D77 T2 `c4a729f8`) |
| **dependabot (npm/github-actions/docker)** | 周依赖更新 | dependabot | [`.github/dependabot.yml`](../.github/dependabot.yml) | ✅ (D77 T3 `4b085b82`) |
| **production-hardening.md** | 7 节 + 13 ❌ anti-patterns（secrets + 容器 + 网络） | — | [`deployment/production-hardening.md`](deployment/production-hardening.md) | ✅ (D77 T6 `cea04051`) |
| **`pnpm demo` (zero-LLM REPL)** | 本地试玩（无需 Docker / API key；脚本化 fixture LLM + 内存 PGlite） | acceptance-harness | [`butler-v5/scripts/demo.ts`](../butler-v5/scripts/demo.ts) | ✅ (D79 T1 `b6a30a6e`) |
| **SELF-HOSTING.md** | §0-§10 自托管完整路径（前置 + docker + demo + 安全 + 升级） | docker + demo | [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md) | ✅ (D79 T3 `9bd60e49`) |
| **Acceptance harness + 41+ scenarios** | 自动化验收（3 E-demo scenarios 已加） | vitest + harness | [`butler-v5/tests/acceptance/scenarios/`](../butler-v5/tests/acceptance/scenarios/) | ✅ (D52 + D79 T2) |
| **recordings-archive (v1→v7)** | baseline recordings + diff-real-llm 脚本 | harness | [`tests/acceptance/scenarios/recordings-archive/`](../butler-v5/tests/acceptance/scenarios/recordings-archive/) | ✅ |
| **Methodology check (19·19)** | ENGINEERING + PRODUCT 双向校验 | dev-quality-gate | [`apps/api/src/dev-quality-gate.ts`](../butler-v5/apps/api/src/dev-quality-gate.ts) | ✅ |
| **CHANGELOG (Keep-a-Changelog v1.1.0)** | D55→D79 127-ship 回填 | changelog | [`../CHANGELOG.md`](../CHANGELOG.md) | ✅ (D76 T1 `600c2975`) |
| **OSS CoC + SECURITY + Issue + PR 模板** | 社区门面 | github | [`.github/ISSUE_TEMPLATE/`](../.github/ISSUE_TEMPLATE/), [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) | ✅ (D76 T2-T4) |
| **Docs 5 件套** | ROADMAP + Mermaid 4 图 + FAQ 10 段 + docs index 13 子目录 + AGENTS.md dedup | — | [`ROADMAP.md`](ROADMAP.md), [`architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md), [`FAQ.md`](FAQ.md), [`README.md`](README.md), [`../AGENTS.md`](../AGENTS.md) | ✅ (D78 `db4c1f67`..`9c5dc438`) |

## §8 待 ship / DESIGN §18 deferral 状态

> **触发条件见** DESIGN §18 + D53c deferral reeval (2026-09-11)。**0 新 evidence, 状态保持**。无新 trigger 不进入路线图（DESIGN §18 line 830 硬规则）。

| 项 | 触发条件 | 当前状态 | Source 指针 |
|----|----------|----------|-------------|
| **独立 approvals 表** | 当前 `waiting_approval` Step 字段承载够用 | 📅 not trigger | DESIGN §11.4 + §18 |
| **独立 memory_records 表** | Durable Memory 走 §12 `durable_memories` 足够 | 📅 not trigger | DESIGN §18 |
| **全量 Projection / 独立读库** | owner 实测查询延迟超预算 | 📅 not trigger (41/41 pass) | DESIGN §11.4 |
| **Snapshot + DeltaChannel** | 运行历史 p95 超预算；当前 D53a snapshot 是 test artifact 非 prod API | 📅 not trigger | DESIGN §11.4 |
| **Command Bus / Query Bus** | owner 实测同步耦合严重 | 📅 not trigger | DESIGN §11.4 |
| **通用 Event Bus** | DESIGN §7 line 60 explicit 默认直调 | 📅 not trigger | DESIGN §11.4 |
| **Kafka / Redis Stream / 独立 Broker** | 单进程故障隔离实测不足 | 📅 not trigger | DESIGN §11.4 |
| **Telegram Channel 完整化** | wechat + slack 已承载；telegram 无触发 | 📅 not trigger | DESIGN §18 |
| **浏览器 UI (第二 Loop)** | DESIGN §7.1 条件准入 | 📅 半 trigger (R16 partial) | DESIGN §7.1 |
| **外部 OTEL exporter** | 本地 trace 无法定位生产问题 | 📅 not trigger | DESIGN §18 |
| **独立 worker 进程** | 同进程 Outbox worker 资源隔离不足 | 📅 not trigger | DESIGN §18 |
| **LLM 输出质量量化** | temperature model 单 round 不可靠；multi-round methodology 待 owner 撞真问题 | ❌ declined | D51 + D53c |
| **Approval trust mode** | 35 场景 9 次非 read-only approval 够表达；扩 fixture 成本 > 价值 | ❌ declined | D51 + D53c |
| **v8 Real-LLM candidates A/B/C** | 3/3 实证 revert；候选 D 等 owner hand-trial 1 周踩真问题 | ❌ resource exhausted | [`plans/active/v5-real-llm-v8-iteration-2026-09.md`](plans/active/v5-real-llm-v8-iteration-2026-09.md) |

---

## §9 跨文件指针

| 需求 | 读这里 |
|------|--------|
| 目标架构（DESIGN SSOT） | [`butler-v5/DESIGN.md`](../butler-v5/DESIGN.md) |
| 当前生产实现事实 | [`architecture/v5-production-architecture-2026-08.md`](architecture/v5-production-architecture-2026-08.md) |
| 端口契约清单 | [`../butler-v5/packages/ports/port-catalog.md`](../butler-v5/packages/ports/port-catalog.md) |
| D-series 累計 + 维度候选 | [`ROADMAP.md`](ROADMAP.md) |
| Owner FAQ（D-series / audit-driven / 节奏判据） | [`FAQ.md`](FAQ.md) |
| 视觉架构图（Mermaid 4 张） | [`architecture/v5-current-state-diagrams.md`](architecture/v5-current-state-diagrams.md) |
| 文档分层手册 | [`DOCUMENTATION.md`](DOCUMENTATION.md) |
| 文档索引卡片（"我要…"） | [`README.md`](README.md) |
| Agent 入口 | [`../AGENTS.md`](../AGENTS.md) |
| 自托管指南 | [`deployment/SELF-HOSTING.md`](deployment/SELF-HOSTING.md) |
| 生产加固指南 | [`deployment/production-hardening.md`](deployment/production-hardening.md) |

---

**End of FEATURES.md** | D80 cycle 26 inventory batch | **7 类别 / 60+ 功能**（§1-§7）/ 14 deferral 项（§8）| 全部 ✅ 或 🟡；§8 仅留 DESIGN §18 trigger-条件未达 / declined 记录