# Butler v5 生产架构事实（2026-08）

> **状态**：Current  
> **用途**：描述正在接收真实流量的实现，不描述未接线的目标架构  
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
        runtime AgentKernel / EventBridge
             │                  │
             ▼                  ▼
       LLM / WeChat adapters   persistence
                                  │
                                  ▼
                         PostgreSQL Event Store
```

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
  → EventBridge append ConversationStarted
  → runButlerLoop
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

### 5.1 唯一生产 schema

`packages/persistence/src/migrations/0001_initial.sql` 是唯一生产 schema，包含：

- `event_store`
- `outbox`
- `snapshots`
- `projections`

生产在 `NODE_ENV=production` 且有 `DATABASE_URL` 时使用 PostgreSQL。测试与显式本地模式使用 PGlite，但执行同一迁移 SQL。

### 5.2 禁止第二套 schema

`packages/infrastructure/src/persistence/` 的 `events` 等表属于未接线脚手架，与生产 `event_store` 不兼容。它不得被接入生产，也不得继续作为架构事实。

后续处置：

1. 确认没有生产 import；
2. 将仍有价值的测试或纯 helper 迁移到 `packages/persistence`；
3. 删除或归档重复 adapter/schema；
4. 添加 architecture test，阻止 apps 导入该旧 persistence 实现。

---

## 6. 权限事实与缺口

当前已有：

- workspace 路径约束与 symlink 逃逸检查；
- `run_command` 具名白名单；
- 子代理工具名 capability gate；
- AskApproval Decision 状态；
- 审计日志和事件 actor；
- iLink DM allowlist、CDN host allowlist。

当前未形成统一生产权限内核：

- `AskApproval` 只把问题作为回复返回，未持久化 ApprovalRequest，也不能在 Owner 回复后恢复原动作；
- Domain 的 Policy/Capability 类型未接入 `runButlerLoop`；
- 父管家工具没有统一经过同一 Policy；
- Capability 只有 `{tool, expiresAt}` 等不完整形态；
- `GuardService` 与 Effect Application 用例没有进入生产路径。

在接入浏览器、MCP、定时自治或更多写工具前，必须先完成新版边界路线图的 P1/P2。

---

## 7. 包的处置原则

### 保留并继续演进

- `apps/api`：生产 delivery 与当前编排；
- `packages/runtime`：AgentKernel、EventBridge、Decision、Tool Runtime、Delegate Runtime；
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
- 所有副作用入口必须逐步收敛到统一 Policy → Approval → Lease → Sandbox → Audit 流程。
