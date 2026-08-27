# Butler v5 生产架构事实（2026-08）

> **状态**：Current  
> **用途**：描述正在接收真实流量的实现，不描述未接线的目标架构  
> **目标架构**：[`../../butler-v5/DESIGN.md`](../../butler-v5/DESIGN.md)
> **产品边界**：[`v5-product-boundaries-2026-08.md`](../plans/decisions/v5-product-boundaries-2026-08.md)  
> **部署与历史交接**：[`v5-r10-handoff.md`](v5-r10-handoff.md)

---

## 1. 架构裁决

Butler v5 采用**生产路径优先的模块化单体**：

```text
CLI / iLink Poller / HTTP / WebSocket
                  │
                  ▼
          apps/api delivery shell
                  │
                  ▼
   RunEngine / RunCoordinator / PolicyGate (opt-in)
             │                  │
             ▼                  ▼
       LLM / WeChat adapters   persistence
             │                  │
             │                  ├─ event_store (compat)
             │                  └─ conversations/messages/runs/steps (0002)
             ▼
                         PostgreSQL
```

P0–P2 迁移已落地；P1.0–P1.4 治理链路已接入生产：`RunEngine` 收口微信入站 Run；`RuntimeStore` 双写关系表；`PolicyGate` + `CapabilityRegistry` 统一工具执行；`waiting_approval` Step + Owner API/CLI + 微信内联「确认/拒绝」；`ScopedGrant` 一次性扣减；`audit_events` 双写子代理审计；`BUTLER_V5_READ_MODEL` 控制读模型（默认 `relational`，0002 messages）；`BUTLER_V5_SANDBOX=bubblewrap` 时 `run_command` fail-closed 走 bubblewrap。

当前生产 Loop 是 `apps/api/src/wechat-inbound-butler.ts` 的 async/await 编排。已归档的 `_archive/packages/{application,infrastructure,contracts}` 是重构期脚手架，只有自身测试，不在生产调用链上。

因此：

- 不再声称生产流量经过完整 Effect Application/Port DI；
- 不为兑现旧图而重写已工作的 Loop；
- 仅在权限、数据一致性或可测试性需要时，从 delivery shell 提取稳定的纯策略与 runtime service；
- 未接线脚手架不能作为“已实现”证据。

---

## 2. 进程与入口

`butler-v5/cli/src/index.ts` 的 `butler start`：

1. 动态加载 `@butler/api`；
2. 启动 Hono HTTP；
3. Hono 监听后按配置启动原生 iLink poller；
4. 按配置可选启动 WebSocket + subagent outbox worker（`BUTLER_V5_SUBAGENT_ENABLED=1`）与 schedule worker；
5. SIGINT/SIGTERM 关闭 HTTP、WS、poller 与数据库连接。

生产由 `butler-v5-gateway.service` 运行，默认：

- HTTP：`PORT=3000`；
- WebSocket：**opt-in**（`BUTLER_V5_SUBAGENT_ENABLED=1`）；由 `WS_PORT` 配置，默认 3001，绑定 loopback；
- PostgreSQL 与 wechat mock：Docker Compose；
- 凭证：`~/.config/butler-v5/env`；
- 工作目录：`butler-v5/`。

## 3. 微信主路径

```text
WeChat phone
  → Tencent iLink getupdates
  → apps/api ilink-poller
  → POST /v1/wechat/inbound
  → Intake normalizeWechatInbound（conversationId / idempotency / RunTrigger）
  → (optional) WeChat Intake 意图路由（`wechat-intake.ts`：dev_session / switch / dev_task / chat）
  → (optional) inline approval: 确认/拒绝 → ScopedGrant + RunEngine.resumeRun（同一 runId）
  → EventBridge append ConversationStarted
  → runButlerLoop → RunEngine.executeInbound（若已有 active main Run 则拒绝另开）
  → PolicyGate.executeThroughBoundary (tools)
  → LLM / tools / delegate
  → HTTP reply
  → iLink sendmessage
  → WeChat phone
```

该路径不经过退役的 v4 gateway。

**Intake（A6）**：`packages/runtime/src/intake/` 负责 conversationId 校验/默认、idempotencyKey、`RunTrigger` 构造；Slack/Telegram 协议解析与 channel allowlist 仍在 `apps/api`。

**WeChat 产品 Intake（2026-08，方案 B）**：`apps/api/src/wechat-intake.ts` 在 slash 命令与 inline 审批之后、`runButlerLoop` 之前做意图分类（规则优先；`BUTLER_V5_INTAKE_LLM=1` 时 Flash 补充分类）。**dev_task / continue_dev** 主 Loop 工具面 = plan + `delegate_to_subagent`（**不含** `write_file` / `run_command`）；exec 仅在 Child Run（subagent worker + `MODEL_EXEC`）内执行。Legacy 直调：`BUTLER_V5_DEV_DIRECT_EXEC=1`。Dev Session Grant 经 `dev-session-grant.ts` → `issuePreconfiguredGrants` 写入 `scoped_grants`（合成 Run anchor，与审批/委派 Grant 同表）。

**Model Router**：`packages/adapters/src/model-router.ts` — 主 Loop 用 `plan`（DeepSeek Flash），子代理 worker 用 `exec`（MiniMax M3，需 `MINIMAX_API_KEY`）。

**Dev 验收（P4）**：`dev-quality-gate.ts` — dev_task / exec 子代理结束后可选自动跑 `BUTLER_V5_DEV_VERIFY_CMD`（默认 `pnpm test`），微信回复结构化摘要；项目 dev 状态 JSON 见 `project-state.ts`（`/状态` 展示）。

### 3.1 Loop

Execution 多轮循环在 `packages/runtime/src/execution/conversation-loop.ts`（`runConversationLoop`）。`apps/api/wechat-inbound-butler` 负责：

- 内联审批、backfill、`RunEngine.executeInbound`；
- 打开 `AgentKernel` Turn、组装历史（relational / event_store compact）；
- 注入 LLM / 工具 ports；
- 调用 `runConversationLoop`（默认最多 5 轮）。

循环内行为：

- 支持原生 tool calls 与 JSON Decision fallback；
- 需确认副作用写入 `waiting_approval` Step，Run 暂停；用户可回复「确认/拒绝」，或 Owner 调 `/v1/owner/approvals/*` / `butler approve`；
- 审批通过后经 `RunEngine.resumeRun` **恢复同一 Run**：执行挂起 capability、写入 capability Step；`run_command` / `write_file` 默认直接返回结果（不再二次 Ask）；其他 capability 可继续只读工具 Loop；
- 对话已有 active main Run（`queued`/`running`/`waiting_approval`）时，普通入站不再另开主 Run（`ActiveMainRunConflict` → 友好提示）；
- `waiting_external` + trusted/owner 入站：自动 resume 同 Run 并继续 Loop；
- 无 LLM、解码失败或工具异常时仍返回非空回复。

### 3.2 工具

父管家当前有 8 个工具：

- `recall_history`
- `get_current_time`
- `greet_with_time`
- `summarize_today`
- `read_file`
- `run_command`
- `send_wechat_file`
- `delegate_to_subagent`

`run_command` 使用 argv 数组和具名白名单，不使用 shell。`send_wechat_file` 只允许 workspace 内路径，不进入子代理能力白名单。

### 3.3 媒体

- 入站图片/文件：CDN host allowlist、AES-128-ECB 解密、workspace 缓存；
- 入站语音：优先 `voice_item.text`；无文本时保存 silk；DashScope 仅处理 wav/mp3；
- 出站图片/文件：getuploadurl、AES-128-ECB、CDN POST、sendmessage type 2/4。

---

## 4. 委派与实时结果

```text
delegate_to_subagent
  → ChildRunCreated + transactional outbox
  → subagent worker claim
  → child LLM tool loop
  → AssistantMessageProduced 写回 parent stream
  → WebSocket pushEventToSubscribers
```

子代理能力由 `ALLOWED_CAPABILITIES` 具名授予，并在 LLM 工具广告和执行时分别检查。`general` 只表示语言任务，不解锁工具。委派时若有 parent `runId`，会创建 `parentRunId` Child Run（`triggerSource=parent_run`），outbox worker 将其推进到终态并写 result Step。

当前限制：

- 子代理默认不可递归委派；
- `send_wechat_file` 不可授予子代理；
- 能力只有工具名范围，尚未具备完整路径、域名、次数、预算和批准指纹租约。

---

## 5. 数据边界

### 5.1 生产 schema

`0001_initial.sql`：event_store / outbox / snapshots / projections。

`0002_target_runtime.sql`（additive）：conversations（含 `project_id` 索引）/ messages / runs / steps / scoped_grants / audit_events。

`0003_scoped_grant_fields.sql`（additive）：`scoped_grants.delegable`（默认 false）、`approval_id`、`sandbox_profile`。

生产在 `NODE_ENV=production` 且有 `DATABASE_URL` 时使用 PostgreSQL（长轮次、多项目、Run 状态持久化所需）。测试与显式本地模式使用 PGlite，执行同一迁移 SQL。

**读模型**：`BUTLER_V5_READ_MODEL` 默认 `relational`——Loop 工作集与 `recall_history` / `summarize_today` 读 0002 `messages`。`event_store` 仍写入（审计/outbox/兼容）；入站时 `backfillConversation` 可将 legacy 事件流一次性投影到 relational。显式 `hybrid` 仅在迁移期需要 event 回退；`event_store` 仅事件流调试。

### 5.2 禁止第二套 schema

`packages/infrastructure/src/persistence/` 的 `events` 等表属未接线脚手架，与生产 `event_store` 不兼容。该包已归档至 `_archive/packages/infrastructure/`，不得被接入生产，也不得作为架构事实。

---

## 6. 治理与权限（生产事实）

当前已接入：

- **PolicyGate + CapabilityRegistry**：`wechat-inbound-butler` 与子代理 worker 的工具执行经 `executeThroughBoundary`，禁止 apps 层直接 `runTool`（architecture test 锁定）；
- **waiting_approval Step**：Policy `Ask` 时持久化待执行 capability（含 args/digest/过期时间），Run 转 `waiting_approval`；
- **ScopedGrant**：Owner approve 或微信内联「确认」后签发 `uses=1` Grant（锁定 capability + path + action digest + **network allow/hosts**）；一等列 `delegable=false`、`approval_id`→审批 Step、`sandbox_profile`（提升隔离时填写，A8 扩面）；WeChat CDN 固定表 + `BUTLER_V5_GRANT_NETWORK_HOSTS` 额外域名；MCP 能力自动合并 `BUTLER_V5_MCP_URL` 主机名；
- **恢复路径**：`resumeApprovedCapability` → `RunEngine.resumeRun`（同一 `runId`）执行挂起 capability + 持久化 capability/result Step；Run 终态由引擎收口为 `succeeded`/`failed`；
- **Owner API**：`GET /v1/owner/conversations?projectId=`（多项目会话列表）+ `GET /v1/owner/conversations/:id/messages`（读 0002 消息，供 recall/运维）+ `POST /v1/owner/schedule/tick`（手动跑一轮 Schedule）+ `GET/POST /v1/owner/approvals*` + …；CLI `butler conversations` / `butler schedule tick`（**loopback only**）；
- **Run 终态**：`cancelRun` / `expireOverdueRuns`（`run-lifecycle.ts`）；`waiting_external` enter/resume；**可信/Owner 入站**在 `executeInbound` 自动 resume 同 Run；
- **微信内联审批**：同对话有待审批 Step 时，用户发送「确认」「拒绝」等短句触发 approve/deny（需为 pending subject 或 `BUTLER_OWNER_WECHAT_ID`）；
- **审计**：子代理 JSONL + `audit_events` 双写；审批/request/grant/execute/cancel/expire 写 `audit_events`；
- workspace 路径约束、`run_command` 白名单、子代理 capability gate、iLink DM allowlist。

仍待完善：

- Project Knowledge MVP（K1 ✅ 2026-08-24）；
- Schedule / Durable Memory / Document ingest / Local tracing / Task·Procedure MVP 已落地；
- Child Run relational（A5）：`delegate` 创建 `parentRunId` + `triggerSource=parent_run`；worker 写 running→终态 + result Step；
- Conversation Loop（A7）：多轮循环在 `runtime/execution`；apps 仅接线。
- 审批 resume 后接完整多轮 `runConversationLoop`；waiting_external 可信入站自动 resume（已落地）。

**RunTrigger（已接入）**：微信 `buildWechatRunTrigger`、Channel `buildChannelRunTrigger`、Owner 审批 `buildApiRunTrigger`、CLI `butler run` → `buildCliRunTrigger`、Schedule `buildScheduleRunTrigger`（opt-in worker）、Task `buildTaskRunTrigger`；元数据在 Run `budget` 或审计事件。

### 6.0 Schedule / Heartbeat（opt-in）

| Env | 说明 |
| --- | --- |
| `BUTLER_V5_SCHEDULE_ENABLED` | 默认关；`1` 启动 API 进程内 tick worker |
| `BUTLER_V5_SCHEDULE_TICK_MS` | 轮询间隔，默认 60000 |
| `BUTLER_V5_SCHEDULE_JOBS_PATH` | JSON 任务文件（默认 `config/schedule-jobs.json`） |
| `BUTLER_V5_SCHEDULE_JOBS` | 内联 JSON（设置时优先于 path） |
| `BUTLER_V5_SCHEDULE_DEFER_WHEN_BUSY` | `1` 时尊重主队列 busy 钩子 |

任务字段：`id` / `everyMs` / `goal` / `cooldownMs` / `maxSteps` / `deadlineMs` / `quietSuccess` / `enabled`。Fire 路径：`evaluateScheduleTick` → `runScheduleJob` → `runButlerLoop`（只读工具白名单）。不建第二套 Run Engine。

### 6.0b Durable Memory（MVP）

| 面 | 说明 |
| --- | --- |
| Schema | `durable_memories`（migration `0004`）：subject/content/source_kind/status/confidence/provenance/expires |
| 写入 | Owner `POST /v1/owner/memories`；CLI `butler memory add\|list\|confirm\|reject\|delete` |
| 召回 | 工具 `recall_durable_memory`（子串）；注入工作集需 `BUTLER_V5_DURABLE_MEMORY=1` |
| 边界 | 非 Transcript；压缩摘要不自动升级；非 Owner 来源默认 `candidate` |

### 6.0c Document ingest（MVP）

| 面 | 说明 |
| --- | --- |
| Schema | `documents`（migration `0005`）：format/mime/byte_size/extracted_text/provenance |
| 格式 | `plaintext` / `markdown` / `pdf`（pdf **必须**预提取文本；无内嵌解析器） |
| 写入 | Owner `POST /v1/owner/documents`；CLI `butler document add\|list\|get\|delete\|promote` |
| 召回 | 工具 `recall_document`（子串）；`promote-memory` → Durable Memory candidate |
| 删除 | 级联 `deleteBySourceDocumentId` |

### 6.0c1 Project Knowledge（MVP，K1 ✅）

| 面 | 说明 |
| --- | --- |
| Schema | `project_knowledge_items`（migration `0010`）：project_id/title/kind/body/byte_size/provenance |
| Kind | `manual_note` / `ingested_document` / `workspace_snapshot` |
| 写入 | Owner `POST /v1/owner/project-knowledge`；Document `POST .../promote-project-knowledge`；workspace `POST .../snapshot` |
| CLI | `butler project-knowledge list\|add\|get\|delete\|promote-doc\|snapshot` |
| 召回 | 工具 `recall_project_knowledge`（子串，project 作用域）；跨 project 读取 Deny |
| 注入 | 工作集 prefix 需 `BUTLER_V5_PROJECT_KNOWLEDGE=1`（默认 `0`） |
| K1.1 watch | `config/project-knowledge-sources.json` + `BUTLER_V5_PROJECT_KNOWLEDGE_WATCH=1`；Owner `POST .../sync` 或 CLI `project-knowledge sync` |
| markitdown chain | sources 中 office/PDF → `mcp_markitdown_convert_to_markdown` → document → `ingested_document` |
| 边界 | 非 Durable Memory / 非 Transcript；无 embedding / 全盘索引 |

### 6.0d Local tracing（MVP）

| Env | 说明 |
| --- | --- |
| `BUTLER_V5_TRACE` | 默认开；`0` 停用 |
| `BUTLER_V5_TRACE_REDACT` | 默认开 |
| `BUTLER_V5_TRACE_MAX_EVENTS` | 环形缓冲上限，默认 500 |
| `BUTLER_V5_OTEL_EXPORTER` | `off`（默认）\| `stdout`（OTLP-ish JSON lines，无 SDK） |

接线：`RunEngine` 记 run start/finish；`executeToolThroughBoundary` 记 policy/capability/approval。Owner `GET /v1/owner/traces`、`POST .../clear`；CLI `butler traces`。

### 6.0e Task / Procedure（MVP）

| 概念 | 说明 |
| --- | --- |
| Procedure | 不可变线性模板（`name`+`version`）；`steps[{key,title,goal,when?}]`；`when` 仅标签 |
| Task | Owner 持久待办；可绑 Procedure + `procedureStepIndex` |
| 执行 | `POST /v1/owner/tasks/:id/run` → `buildTaskRunTrigger` → `runButlerLoop`；成功后默认推进步骤 |
| 表 | `0006_task_procedure.sql`（`procedures` / `tasks`） |
| CLI | `butler task list\|add\|run\|done\|proc-list\|proc-add` |

无 DAG、无并行合并、无 WorkflowRun；不建第二套 Run Engine。

### 6.0f P4 真实路径验收（无真微信）

| 命令 | 说明 |
| --- | --- |
| `pnpm test:p4-acceptance` | 模拟 `POST /v1/wechat/inbound` → Schedule fire → Task/Procedure step → Owner traces |
| `butler verify [--api url]` | 校验迁移清单含 0004–0006、0010；可选 ping `/healthz` |

Harness：`apps/api/src/p4-acceptance.harness.test.ts`（不启 iLink / Web UI）。

**Capability Provider**：`createProductionCapabilityRegistry()` 为生产注册中心；核心 WeChat 工具走 `tools`，MCP 工具经 `mcpCapabilityProvidersFromTools()` 注册为 `extraProviders`（`tool-boundary.makeToolExecutor` 自动拆分 `mcp_*` 前缀能力）。

### 6.2 MCP 传输（opt-in）

`bootstrapMcpTools` 支持三种传输（`BUTLER_V5_MCP_TRANSPORT`）：

| 传输 | 配置 |
|------|------|
| `http`（默认） | `BUTLER_V5_MCP_URL` |
| `sse` | 同上；Accept `text/event-stream` |
| `stdio` | `BUTLER_V5_MCP_COMMAND` + 可选 `BUTLER_V5_MCP_ARGS` |

发现结果注入 `wiring.mcp`；shutdown 时 `mcp.close()` 关闭 stdio 子进程。

客户端在 `tools/list` / `tools/call` 前执行 MCP `initialize` + `notifications/initialized` 握手；HTTP/SSE 传输复用 `Mcp-Session-Id` 响应头并在后续请求中回传（Streamable HTTP 长连接 session）。

**Consent / manifest（opt-in）**：`BUTLER_V5_MCP_REQUIRE_CONSENT=1` 时 bootstrap 仅允许 `BUTLER_V5_MCP_CONSENT` 列出的 server id（默认从 `MCP_URL` hostname 或 `MCP_COMMAND` 推导）。可选 `BUTLER_V5_MCP_MANIFEST_PATH` 指向 manifest JSON；设置后 bootstrap 校验 server id 必须在 manifest 中声明，并可用 manifest 条目提供默认 `transport/url/command`（`BUTLER_V5_MCP_*` env 优先覆盖；token/timeout/args 仍来自 env）。

### 6.3 第二 Channel 接缝（opt-in）

| 入口 | Env | 说明 |
|------|-----|------|
| `POST /v1/channel/inbound` | `BUTLER_V5_CHANNEL_API_ENABLED=1` | 通用 JSON intake |
| `POST /v1/channel/slack/events` | `BUTLER_V5_SLACK_ENABLED=1` | Slack Events API；`BUTLER_V5_SLACK_BOT_TOKEN` 时 `chat.postMessage` 出站 |
| `POST /v1/channel/telegram/webhook` | `BUTLER_V5_TELEGRAM_ENABLED=1` | Telegram Bot webhook；`BUTLER_V5_TELEGRAM_BOT_TOKEN` 时 `sendMessage` 出站 |

三者均复用 `handleChannelInbound` → `runButlerLoop`；默认 conversationId：`c-ch-{channelId}-{subject}`。Webhook 响应含 `delivered: boolean`（有 bot token 且 API 成功时为 true）。

**富媒体入站（opt-in）**：Slack `file_share` / `files[]` 与 Telegram `photo`/`document` 会展开为带 `[slack image …]` / `[telegram image …]` 标记的 content；`BUTLER_V5_TELEGRAM_MEDIA_CACHE=1` 且配置 bot token 时，Telegram 附件会下载到 `BUTLER_V5_TELEGRAM_MEDIA_DIR` 并在 content 追加 `saved to …` 路径。

**富媒体出站（opt-in）**：`BUTLER_V5_CHANNEL_OUTBOUND_MEDIA=1` 时，Loop 回复中的 `[[media:/allowed/path.png]]` 会剥离后上传（Slack `files.upload`、Telegram `sendPhoto`/`sendDocument`）；允许路径限于 workspace / `.butler-v5` / `BUTLER_V5_TELEGRAM_MEDIA_DIR`。Webhook 响应含 `mediaCount`。

### 6.1 bubblewrap 沙箱（opt-in）

`BUTLER_V5_SANDBOX=bubblewrap` 时，本地 argv 副作用经统一入口 `executeArgvInSandbox`（`bubblewrap-runner.ts`）执行；缺 `bwrap` 时 **fail-closed**。

- Provider 默认隔离：`workspace-write-network-deny`（`--unshare-net`）。
- 审批签发：`run_command` / `mcp_*` Grant 写入 `sandboxProfile=workspace-write-network-deny`；Owner `elevateNetwork: true` → `workspace-write-network-allow`（去掉 unshare-net）。
- 执行时 PolicyGate 经 ALS 把 `Grant.sandboxProfile` 传给 sandbox 入口；MCP 远程 I/O 不套 bwrap，profile 作天花板与审计。
- CLI：`butler approve <stepId> --elevate-network`。

`butler-v5-gateway.service` 中已注释 `ExecStartPre=…sandbox-preflight.sh`；启用 bubblewrap 沙箱时取消注释，避免 gateway 在无 `bwrap` 时启动后静默拒绝命令。

环境变量 SSOT：`butler-v5/.env.example`（`BUTLER_V5_SANDBOX`、`BUTLER_V5_WORKSPACE_ROOT`）。

运维 preflight（生产建议在 systemd 启用）：

```bash
# CLI
cd butler-v5 && pnpm exec tsx cli/src/index.ts sandbox-preflight

# 或 cutover 脚本（供 ExecStartPre）
butler-v5/scripts/cutover/butler-v5-sandbox-preflight.sh
```

`butler-v5-gateway.service` 中已注释 `ExecStartPre=…sandbox-preflight.sh`；启用 bubblewrap 沙箱时取消注释，避免 gateway 在无 `bwrap` 时启动后静默拒绝命令。

环境变量 SSOT：`butler-v5/.env.example`（`BUTLER_V5_SANDBOX`、`BUTLER_V5_WORKSPACE_ROOT`）。

---

## 7. 包的处置原则

### 保留并继续演进

- `apps/api`：生产 delivery 与当前编排；
- `packages/runtime`：Core 应用层（AgentKernel、RunEngine、PolicyGate、approval-runtime、Tool Runtime、Delegate Runtime），仅依赖 domain 抽象接口注入；
- `packages/adapters`：LLM、WeChat 与外部协议；
- `packages/persistence`：唯一数据实现；**并承载 EventBridge**（driven adapter，实现 domain `EventStorePort`）；
- `packages/domain`：被生产需求采用的纯策略与类型（含 `RuntimeStore`、`EventStorePort` 等抽象契约）。

### 已归档（2026-08-27，根 `_archive/packages/`）

- `_archive/packages/application`：未接线的 runLoop/delegateTask/runWorkflow/dream；
- `_archive/packages/infrastructure`：未接线 Layer、重复 persistence 和 MCP mock 骨架；
- `_archive/packages/contracts`：未被生产 import 的契约原型。

处置已完成：依赖扫描证明无生产引用后，三包整体迁至根 `_archive/`，从编译/测试/覆盖率白名单剔除；有价值的测试由 `pnpm test:archived`（`vitest.archived.config.ts`）保留运行。

---

## 8. 架构变更规则

- 新能力优先作为具名 Tool、Channel Adapter、MCP Adapter 或 Runtime Service 接入。
- 不把业务判断继续堆进 route；可重放的 Policy 与状态迁移放在 domain/runtime。
- 不为了“层数完整”创建空包或第二套实现。
- 任何新持久化结构必须进入唯一 migration/schema。
- 所有副作用入口必须逐步收敛到统一 Policy → waiting_approval（Ask 时）→ ScopedGrant（需要时）→ Provider Boundary → Audit（需要时）流程。模型调用走独立 Model Port。
