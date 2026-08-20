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

P0–P2 迁移已落地；P1.0–P1.4 治理链路已接入生产：`RunEngine` 收口微信入站 Run；`RuntimeStore` 双写关系表；`PolicyGate` + `CapabilityRegistry` 统一工具执行；`waiting_approval` Step + Owner API/CLI + 微信内联「确认/拒绝」；`ScopedGrant` 一次性扣减；`audit_events` 双写子代理审计；`BUTLER_V5_READ_MODEL` 控制读模型（默认 `event_store`）；`BUTLER_V5_SANDBOX=bubblewrap` 时 `run_command` fail-closed 走 bubblewrap。

当前生产 Loop 是 `apps/api/src/wechat-inbound-butler.ts` 的 async/await 编排。`packages/application` 与部分 `packages/infrastructure` 是重构期脚手架，只有自身测试，不在生产调用链上。

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
4. API 模块同时启动 WebSocket server 和 subagent outbox worker；
5. SIGINT/SIGTERM 关闭 HTTP、WS、poller 与数据库连接。

生产由 `butler-v5-gateway.service` 运行，默认：

- HTTP：`PORT=3000`；
- WebSocket：由 `WS_PORT` 配置；代码默认 3001；
- PostgreSQL 与 wechat mock：Docker Compose；
- 凭证：`~/.config/butler-v5/env`；
- 工作目录：`butler-v5/`。

## 3. 微信主路径

```text
WeChat phone
  → Tencent iLink getupdates
  → apps/api ilink-poller
  → POST /v1/wechat/inbound
  → (optional) inline approval: 确认/拒绝 → ScopedGrant + resume
  → EventBridge append ConversationStarted
  → runButlerLoop → RunEngine.executeInbound
  → PolicyGate.executeThroughBoundary (tools)
  → LLM / tools / delegate
  → HTTP reply
  → iLink sendmessage
  → WeChat phone
```

该路径不经过退役的 v4 gateway。

### 3.1 Loop

`runButlerLoop`：

- 创建 `AgentKernel`，写入 `TurnOpened`；
- 加载同一 conversation stream 的历史；
- 超预算时使用 LLM 摘要，失败回退为抽取压缩；
- 最多执行 5 轮模型/工具交互；
- 支持原生 tool calls 与 JSON Decision fallback；
- 需确认副作用（如 `send_wechat_file`）写入 `waiting_approval` Step，Run 暂停；用户可回复「确认/拒绝」，或 Owner 调 `/v1/owner/approvals/*` / `butler approve`；
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

子代理能力由 `ALLOWED_CAPABILITIES` 具名授予，并在 LLM 工具广告和执行时分别检查。`general` 只表示语言任务，不解锁工具。

当前限制：

- 子代理默认不可递归委派；
- `send_wechat_file` 不可授予子代理；
- 能力只有工具名范围，尚未具备完整路径、域名、次数、预算和批准指纹租约。

---

## 5. 数据边界

### 5.1 生产 schema

`0001_initial.sql`：event_store / outbox / snapshots / projections。

`0002_target_runtime.sql`（additive）：conversations / messages / runs / steps / scoped_grants / audit_events。

生产在 `NODE_ENV=production` 且有 `DATABASE_URL` 时使用 PostgreSQL。测试与显式本地模式使用 PGlite，执行同一迁移 SQL。

### 5.2 禁止第二套 schema

`packages/infrastructure/src/persistence/` 的 `events` 等表属于未接线脚手架，与生产 `event_store` 不兼容。它不得被接入生产，也不得继续作为架构事实。

后续处置：

1. 确认没有生产 import；
2. 将仍有价值的测试或纯 helper 迁移到 `packages/persistence`；
3. 删除或归档重复 adapter/schema；
4. 添加 architecture test，阻止 apps 导入该旧 persistence 实现。

---

## 6. 治理与权限（生产事实）

当前已接入：

- **PolicyGate + CapabilityRegistry**：`wechat-inbound-butler` 与子代理 worker 的工具执行经 `executeThroughBoundary`，禁止 apps 层直接 `runTool`（architecture test 锁定）；
- **waiting_approval Step**：Policy `Ask` 时持久化待执行 capability（含 args/digest/过期时间），Run 转 `waiting_approval`；
- **ScopedGrant**：Owner approve 或微信内联「确认」后签发 `uses=1` Grant（锁定 capability + path + action digest + **network allow/hosts**），执行成功后扣减 `remainingUses`；
- **恢复路径**：`resumeApprovedCapability` 在 approve 后立即执行挂起动作；Run 终态 `succeeded`/`failed`；
- **Owner API**：`GET/POST /v1/owner/approvals*` + CLI `butler approvals|approve|deny`（`BUTLER_V5_OWNER_TOKEN`）；
- **微信内联审批**：同对话有待审批 Step 时，用户发送「确认」「拒绝」等短句触发 approve/deny（需为 pending subject 或 `BUTLER_OWNER_WECHAT_ID`）；
- **审计**：子代理 JSONL + `audit_events` 双写；审批/request/grant/execute 写 `audit_events`；
- workspace 路径约束、`run_command` 白名单、子代理 capability gate、iLink DM allowlist。

仍待完善：

- 浏览器/调度等更多 Channel 出站回复（Slack/Telegram 目前仅入站 webhook → loop）；
- Grant 出网域名/端口动态扩展（非 WeChat CDN 固定表）；
- `packages/application` / 旧 infrastructure 脚手架归档（见 [`v5-unwired-packages-inventory-2026-08.md`](../plans/active/v5-unwired-packages-inventory-2026-08.md)）。

### 6.2 MCP 传输（opt-in）

`bootstrapMcpTools` 支持三种传输（`BUTLER_V5_MCP_TRANSPORT`）：

| 传输 | 配置 |
|------|------|
| `http`（默认） | `BUTLER_V5_MCP_URL` |
| `sse` | 同上；Accept `text/event-stream` |
| `stdio` | `BUTLER_V5_MCP_COMMAND` + 可选 `BUTLER_V5_MCP_ARGS` |

发现结果注入 `wiring.mcp`；shutdown 时 `mcp.close()` 关闭 stdio 子进程。

### 6.3 第二 Channel 接缝（opt-in）

| 入口 | Env | 说明 |
|------|-----|------|
| `POST /v1/channel/inbound` | `BUTLER_V5_CHANNEL_API_ENABLED=1` | 通用 JSON intake |
| `POST /v1/channel/slack/events` | `BUTLER_V5_SLACK_ENABLED=1` | Slack Events API（签名校验 + url_verification） |
| `POST /v1/channel/telegram/webhook` | `BUTLER_V5_TELEGRAM_ENABLED=1` | Telegram Bot webhook |

三者均复用 `handleChannelInbound` → `runButlerLoop`；默认 conversationId：`c-ch-{channelId}-{subject}`。

### 6.1 bubblewrap 沙箱（opt-in）

`BUTLER_V5_SANDBOX=bubblewrap` 时，`run_command` 经 `packages/adapters/src/sandbox/bubblewrap-runner.ts` 在 bubblewrap 内执行；未安装 `bwrap` 时 **fail-closed**（拒绝执行）。

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
- `packages/runtime`：AgentKernel、EventBridge、RunEngine、PolicyGate、approval-runtime、Tool Runtime、Delegate Runtime；
- `packages/adapters`：LLM、WeChat 与外部协议；
- `packages/persistence`：唯一数据实现；
- `packages/domain`：被生产需求采用的纯策略与类型。

### 审核后归档或收敛

- `packages/application`：未接线的 runLoop/delegateTask/runWorkflow/dream；
- `packages/infrastructure`：未接线 Layer、重复 persistence 和 MCP mock 骨架；
- 未被生产 import 的 ports/contracts/config 原型。

处置不是一次性删除：先用依赖扫描证明无生产引用，再迁移仍有价值的契约与测试，最后删除重复路径。

---

## 8. 架构变更规则

- 新能力优先作为具名 Tool、Channel Adapter、MCP Adapter 或 Runtime Service 接入。
- 不把业务判断继续堆进 route；可重放的 Policy 与状态迁移放在 domain/runtime。
- 不为了“层数完整”创建空包或第二套实现。
- 任何新持久化结构必须进入唯一 migration/schema。
- 所有副作用入口必须逐步收敛到统一 Policy → waiting_approval（Ask 时）→ ScopedGrant（需要时）→ Provider Boundary → Audit（需要时）流程。模型调用走独立 Model Port。
