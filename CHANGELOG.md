# 更新日志

本项目所有重要变更都会记录在此文件。格式基于 [Keep a Changelog v1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

> **v5 子项目发布节奏**：[butler-v5/CHANGELOG.md](butler-v5/CHANGELOG.md)
> **v5 当前能力**：[docs/architecture/v5-production-architecture-2026-08.md](docs/architecture/v5-production-architecture-2026-08.md)

## [5.0.0] - 2026-09-21

首次公开发布。本版本涵盖自 D55 cycle 起的 21 cycles × 5 ship = 105 ship 累計变更。

### 新增 (Added)

- 多渠道消息网关（微信 iLink 原生文本、图片、文件、语音入站；文本/图片/文件出站）
- 稳定 conversation stream、多轮上下文与摘要压缩
- AgentKernel 驱动的 LLM + 结构化工具循环
- 工作区文件读取、具名命令执行和文件回传
- 子代理委派、PostgreSQL Outbox 与 WebSocket 异步推送
- PostgreSQL Event Store 生产持久化 + PGlite 测试隔离
- 多 Provider LLM 与失败降级
- §18 undo 机制（5 工具/链式撤销）+ §12 自动升级候选
- 跨项目主键 recall（§18 row 3 闭环）
- 中文 NL 撤销命令 + per-line spam detect + fixture harness
- wechat task_digest + session-open digest + sweeper-notify push
- workspace-tools 独立撤销模块 + KNOWN_ENTRY_POINTS 新入口（routes/inbound.ts）
- 13 DEFAULT_*_TIMEOUT_MS 统一（packages/adapters/defaults.ts）
- /v1/owner/audit/fatigue 列表与回放 API（D64 T4）
- inline-approval-wiring 共享渠道 helper（D64 T3-wiring）
- cross-channel 集成（wechat + telegram + CLI，D64 T3-xchannel）
- AuditFatigueDetail 链路 + correlationId 12 emit sites + 22 emit sites（D66 T1b）
- createStep at fatigue checklist branch（D67 T1a）
- acceptance scenarios C/D × 4 + 4 + 4 套扩（D67 T2a-1/T2a-2）
- AuditFatigueReader shared adapter + owner-route reader swap（D69 T1）
- CrossActorReplayError typed class（D69 T3）
- isOriginAllowedForWsUpgrade 工具（D69 T4）
- UndoFn in replay.ts（D70 T1）
- owner-rate-limit.ts 工具（D70 T4）
- AuditFatigueReaderOptions.actor（D70 T3）
- AuditFatigueReaderOptions.columnActor + isBlockedMcpHost + isAllowedOutboundMediaPathReal + parseAllowlist（D71 T1/T2）
- AuditFatigueReaderOptions.columnActor 复用（D72 T1）
- Secret<T> class + isBlockedInboundHost/envAllowsPrivateInboundHosts + requireInboundSharedSecret + parseMcpTimeoutMs（D72 T4）
- lib/secure-compare + lib/dns-recheck + packages/adapters/defaults.ts（D73 T1/T2/T3）
- safeOwnerErrorString + isAllowedSubject + mapChannelErrorToOwnerJargon + channel-seen-ids + spam-detectors + DEFAULT_TELEGRAM_TEXT_TIMEOUT_MS（D74 T1/T2-T5）
- 100+ acceptance scenarios（D64 44 → D67 52 → D75 96 → 100）

### 变更 (Changed)

- **架构解耦**：从 Hermes AIAgent 解耦（[ADR-0001](docs/adr/2026-08-08-v4-to-v5-supersession.md)）
- **god-fn 批量拆解**（D75 T1）：handleOutboxMessage 拆 3 helper + workspace-tools undo 模块独立 + subagent-worker 807→773 + routes.ts channel-handler 583→81 + 新入口 routes/inbound.ts
- **§20 invariant KNOWN_ENTRY_POINTS 更新**（新增 routes/inbound.ts 入口）
- **workspace-tools re-export**（为 @butler/api 下游消费者）
- **架构层重组**：从 4-layer 到分层 model config
- **dev-engine → execution-surface 设计**
- **13 DEFAULT_*_TIMEOUT_MS 统一**（packages/adapters/defaults.ts）
- **acceptance harness 扩**（44 → 96 → 100 scenarios）
- **methodology 扩**（13 → 14 项）
- **6 sub-package 拆解**（adapters / channel / butler-core / persistence / audit / config）
- execute-tool-with-fatigue 从 runButlerLoopBody 提取（D65 T1）
- routes 拆解：memories.ts / documents.ts / traces-procedures-tasks / approvals-runs（D65 T2a-T2d）
- inline-approval-wiring 共享 channel helper（D64 T3-wiring）
- AuditEventSummary type hoist + projectIdToChannel 加 channel:telegram 前缀（D64 T3-xchannel）
- AuditFatigueDetail 嵌入 T1，删除 _typeAssertion workaround（D64 T2）
- audit emit 字段 actor threading（CQ-008 6 sites drop `?`）
- emitAuditEvent → injectAuditEvent rename 传播（D69 T5 spec cohesion）
- AuditFatigueReaderOptions.columnActor 字段加入（D71 T1）

### 修复 (Fixed)

- 21 cycles audit findings 闭环（80+ must-fix 已修复）
- fatigue_signal populate 修复（4th cycle carry，D74）
- 13-cycle CQ carry patterns 收敛（避免反复 defer）
- 47+ owner-jargon 中英文泄漏点替换为安全文案
- silent no-op 移除（CQ-010 owner-route HTTP）
- 6 knip deadcode 删除（D70 T2）
- duplicate DEFAULT_LLM_TIMEOUT_MS 移除（CQ-006 D74 T2 回归）
- hardcoded 15_000 ms 替换为 DEFAULT_TELEGRAM_TEXT_TIMEOUT_MS（CQ-007 D74 T2 回归）
- subagent-multiturn flake 闭环（D53b code health）
- audit emit actor 字段 threading 修复（CQ-008 6 sites drop `?`）
- wechat-subagent-commands 12 处 owner-jargon 泄漏替换
- channel-outbound 12 处 owner-jargon 泄漏替换
- detectSpam 6-detector extract 提取（D74 T3）
- 40 `c.text("unauthorized", 401)` sites 替换为中文 owner-facing 错误（D73 T1）
- 74 empty `} catch {}` blocks 加 observability（D73 CQ-021 + D74 T5）
- runtime DEFAULT_LLM_TIMEOUT_MS drift detector（D74 T2）
- Owner route 429 速率限制中文（D71 SO-005）
- D58 F-01..F-10 silent catches 加 observability
- D59 F-21..F-29 audit_event emit on memory/knowledge/task state transitions
- D60 god-fn split（subagent-worker / createRuntimeStore / workspace-tools）
- D60 realpathSync 失败 silent 返回绝对路径修复
- D60 markGrantConsumed 调用顺序修复（outcome 丢失）
- D61 audit completeness gap 修复（actor 字段）
- D64 F1-fatigue + F2-sensitive + F3-replay acceptance 闭环
- D66 correlationId 35 emit sites threading
- D67 F1/F2/F3 real verification + harness audit writes
- D68 acceptance harness bug fix（capture runMultiRound result.passed）
- D70 owner-route HTTP surface registration
- D72 retroactive spec reconciliation（6 stale docs）

### 安全 (Security)

- Telegram webhook replay dedup 防御（D74 SEC-001）
- slackBotToken / telegramBotToken 等敏感凭证包装为 Secret<T>（D74 SEC-006）
- WS subscribe caller forgery 防御（D73 SEC-001）
- DNS rebinding 防御（D73 SEC-002）
- IPv6 false positive 修正（D73 SEC-003 fc/fd prefix matching）
- 渠道入站共享密钥改用 timing-safe compare（D73 SEC-004）
- Telegram media cache fileId path-traversal 防御（D73 SEC-005）
- Telegram webhook timing-safe compare（D72 SEC-001）
- bot_token Secret<T> 包装（D72 SEC-002）
- WS subscribe caller binding（D72 SEC-003）
- V5_INBOUND_URL SSRF 防御（D72 SEC-004，pre-scoped D70 #4）
- MCP HTTP/SSE SSRF 防御（D71 SEC-001）
- isAllowedOutboundMediaPath realpathSync 防 symlink bypass（D71 CQ-011/SEC-019）
- HTTP headers 强化（D71 SEC-006）
- umask 加固（D71 SEC-007）
- Telegram/Slack user allowlist（D71 SEC-004/SEC-005）
- channel-config / Slack FAIL-CLOSED + wechat inbound auth（D63）
- Hono loopback bind + bodyLimit + X-Forwarded-For reject + ws-subscribe cap（D63）
- QR baseUrl SSRF 防御（D70 SEC-001）
- Owner route rate-limit 防御（D70 SEC-002）
- MCP HTTP/SSE SSRF private/loopback/link-local 防护（D70 SEC-003）
- subagent-worker LLM reply excerpt PII/secret leak 修复（D70 SEC-004）
- Slack url_verification challenge team_id allowlist + rate limit（D70 SEC-005）
- Channel outbound media path traversal 防御（D70 SEC-006）
- Audit-event detail raw LLM content echo 防御（D70 SEC-012）

[5.0.0]: https://github.com/XiaZiHunDun/WFXM/commits/b11cdfdbe2150570e345ff30d28012152cd190a3
