# Butler v5 目标架构

> **状态**：Accepted target architecture
> **产品定位**：单 Owner、单信任域、自托管、可扩展的个人 AI 管家
> **用途**：定义目标模块、端口、概念、数据、安全、扩展与工程边界；不描述当前代码接线
> **当前实现事实**：[`../docs/architecture/v5-production-architecture-2026-08.md`](../docs/architecture/v5-production-architecture-2026-08.md)
> **产品边界**：[`../docs/plans/decisions/v5-product-boundaries-2026-08.md`](../docs/plans/decisions/v5-product-boundaries-2026-08.md)

---

## 0. 架构裁决（一句话）

Butler v5 采用**六边形（端口-适配器）的模块化单体**，内核按 **Domain 纯规则 → Application 编排 → Ports 端口 → 适配器** 单向分层；不采用强四层框架、CQRS、Event Sourcing 或微服务。

对产品维度的第一性推导：

1. 产品是**单 Owner、自托管、低并发**的个人管家 —— 不需要 CQRS、投影、多读库或事件溯源作为默认；
2. LLM 是**不可信规划器** —— 模型必须是经过 Port 的 driven adapter，不能进入核心规则；
3. 系统首要是 **Owner/AI 维护者可理解、可验证、可演进地保全不变量** —— 依赖方向必须由规则锁死，让核心不陷入具体 I/O；
4. 能力扩展只走**两条接缝**（入站 Trigger、副作用 Capability）—— 恰好等价于六边形的 driving/driven adapter，接缝即端口；
5. 后期要能**并行开发、局部演进** —— 模块化单体 + 端口让每块只对接口编程。

因此六边形是产品画像在工程结构上的自然投影，不是表层套框架。

---

## 1. 架构分层总览

```text
                 Driving Adapters（入站）
   WeChat Trigger · CLI · HTTP/API · Schedule · Owner 控制面
                          │  归一化为 RunTrigger
       ┌───────────────────▼───────────────────┐
       │              CORE                      │
       │                                        │
       │  Domain    纯规则 + 聚合 + 状态机       │
       │  Application  用例编排（RunEngine）    │
       │  Ports      依赖方向向内的接口         │
       └───────────────────┬───────────────────┘
           依 Port 调用，不依赖具体实现
       ┌───────────────────▼───────────────────┐
                 Driven Adapters（出站/资源）
   Persistence · Model Port · Sandbox · MCP · Channel · Clock
                          │
               PostgreSQL · Blob · External APIs
```

逻辑上只有一个内核和两类适配器：

1. **Driving Adapters**：一切入站入口。负责协议级认证、标准化、配对、去重，产生 `RunTrigger`。不包含 Agent 规划、权限判断或业务状态机。
2. **Core**：领域与编排。分三层——
   - **Domain**：纯规则、聚合（状态机）、决策、预算；零 I/O、零副作用。可独立单测。
   - **Application**：编排用例。读入工作集、走 Model Port、收敛 Decision、把副作用提交给 Governance、持久化 Step/审计。
   - **Ports**：Core 依赖的抽象接口（Repository / Model / Capability / Channel / Clock）。依赖方向从适配器向内指到 Ports。
3. **Driven Adapters**：Core 通过 Ports 委托的真实实现。持久化、模型、沙箱、MCP、出站 Channel、时钟、文件/命令能力。

规则：

- 逻辑上**只有一个 Run Engine、一个 Policy Gate、一个副作用出口**；
- 模块间默认直接调用，不使用进程内通用 Event Bus；
- 端口只用于**真正可替换或不可信的边界**（模型、数据库、文件、Channel、MCP、浏览器、时钟）；内部纯函数不为"架构完整"而创建接口；
- 模型调用走**独立 Model Port**，不与副作用 Capability 混为同一咽喉。

### 1.1 实施缝隙：delivery shell

`apps/api` 是 **driving adapter（HTTP / WebSocket / iLink / CLI 入口）+ Core 薄编排层** 的 delivery shell，本身**不是 Core**。因此：

- Core 仅指 `packages/domain` + `packages/runtime` + `packages/ports` 三件；它们严格守 §3 端口依赖硬规则。
- delivery shell 可在 boundary 之内直接引用 driven adapters（`@butler/adapters` 内的 llm-provider / wechat / mcp / bubblewrap 等），但所有副作用须经 `packages/runtime/src/policy-gate.ts` + `capability-boundary.ts` 收口；arch tests（`tests/architecture/*`）锁定 apps/api 不允许 `runTool*` 旁路。

这是**实施缝隙（implementation seam），不是 Core 漂移**。重构为完整 Effect Tag DI 仅在权限 / 数据一致性 / 可测试性出现真实需要时进行；不为兑现架构图而重写已工作的 Loop。权威生产事实见 [`../docs/architecture/v5-production-architecture-2026-08.md`](../docs/architecture/v5-production-architecture-2026-08.md) §1。

---

## 2. 产品身份与非目标

Butler 是个人管家；编码委派只是第一个高价值能力域，不是产品本体。

目标：

- 从微信、CLI、API、本地控制面或定时触发接收意图；
- 通过模型、工具和子 Run 完成受控工作；
- 在重启、审批等待和外部失败后安全恢复；
- 让新 Channel、MCP、浏览器等能力复用同一运行与权限边界；
- 保留清晰的来源、审计和删除路径。

非目标：

- 多租户 SaaS、组织权限、计费或公共插件市场；
- Kubernetes、网络微服务或独立消息集群；
- 通用 IDE、低代码 Agent Studio 或浏览器端第二套 Loop；
- 为未来规模预建通用 Workflow DAG、Temporal、LangGraph 或 ContextGraph；
- 把开发仓库的 Guard、承重文件签名和 Author/Reviewer 流程建模为产品运行时；
- 全面 Event Sourcing、CQRS 读写分离、独立读库投影。

---

## 3. 依赖方向与端口（硬规则）

```text
Driving Adapters → Core.Ports → Core.Domain / Core.Application
Core → Ports（抽象），不 import 具体适配器
Driven Adapters → Ports（实现接口）+ 各自协议 SDK
Persistence → 单一 repository schema
```

硬规则：

- 依赖方向**单向向内核**：Core 只能依赖 Ports 接口，不能 import `persistence`、`adapters` 的具体实现；具体实现由 Composition Root（组合根）注入；
- Intake 不包含 Agent 规划、权限判断或业务状态机；出站格式化和发送属于 Outbound Channel driven adapter，不属于任何入口；
- 模型调用只经 Model Port；模型不能签发/延长/转移 Grant，不能访问凭证、数据库、文件系统或 Channel，不能绕过 Policy Gate；
- Governance 不依赖具体 Channel、工具或 Provider SDK；Provider 不能绕过 Policy Gate 回调核心状态；
- 两个外层（driving/driven）都要通过端口与核心交换，**不存在绕过 Port 的第三类接缝**。
- Delivery shell（`apps/api`，见 §1.1）是 driving adapter + Core 薄编排层的复合体；boundary 之内可直连 driven adapters，所有副作用须经 PolicyGate + CapabilityRegistry 收口（arch tests 锁定边界完整性）。

> **§3 主体实施 audit state**（D33, 2026-08-31）：
>
> - **§3 #1 依赖方向向内核**（D33 case #1 lock）：Core (`packages/domain + packages/runtime`) 0 import `@butler/adapters` / `packages/adapters` / `@butler/persistence` / `packages/persistence`；具体实现由 `apps/api/src/bootstrap-wiring.ts`（composition root）注入。继承 D26A §20 #2 lock。
> - **§3 #2 Intake 不含 Agent 规划**（D33 case #2 lock）：`apps/api/src/wechat-intake.ts` 0 import `PolicyGate` / `CapabilityRegistry` / `decidePermission` / `decidePolicy` / `ActiveMainRunConflict` / `grantMatchesAction`；Intake 保持 parsing/normalization 单一职责，决策逻辑全在 Core.Application。
> - **§3 #3 模型调用只经 Model Port**（D33 case #3 lock）：`apps/api/src/**` 0 直接 fetch upstream LLM endpoints (anthropic / openai / deepseek / dashscope)；继承 D26A §20 #3 lock。
> - **§3 #4 Governance SDK-isolated**（D33 case #4 lock）：`packages/runtime/src/policy-gate.ts` 0 import `@butler/adapters` / `@butler/persistence` / `slack` / `wechat` / `mcp` / `axios` / `node-fetch`；Governance 与 Channel/工具/Provider SDK 完全解耦。
> - **§3 #5 不存在绕过 Port 的第三类接缝**（D33 case #5 lock）：`apps/api/src/**` (排除 `wechat-inbound-butler.ts` canonical entry) 0 调用 `registry.execute*` / `registry.register` / `gate.decide` / `gate.evaluate`；所有副作用必经 canonical runButlerLoop closure。继承 D26A §20 #4 lock。
> - **§3 #6 Delivery shell 不另立第二套 Loop/Policy**（D33 case #6 lock）：`apps/api/src/**` 0 定义第二 `class ... Loop/LoopEngine/ConversationEngine/Orchestrator/PolicyGate/Engine`；继承 D8 §20 #11 lock。
>
> 锁定方式：`tests/architecture/section3-dependency-rules.test.ts`（D33, 6 cases）+ D26A §20 #2+#4 + D8 §20 #11 既有 lock。

## 4. 统一概念模型

### 4.1 核心实体

默认内核只有五个聚合：

- **Conversation**：长期交互容器，管理参与者、Channel 映射和消息顺序。
- **Message**：不可变的用户输入、系统通知或管家输出。
- **Run**：一次由 Trigger 启动的执行，是唯一工作单元。
- **Step**：Run 内一次模型调用、能力调用、审批等待或结果生成。
- **ScopedGrant**：允许某主体在有限范围和期限内调用某副作用能力。

以下不是独立聚合：

- **Turn**：Message 与 Run 的展示视图；
- **Child Run**：带 `parentRunId`、角色和收窄权限的普通 Run；
- **Subagent**：执行 Child Run 时采用的角色配置；
- **Session**：Conversation 或运行连接的临时视图；
- **Job**：由 Schedule 触发的 Run；
- **Approval**：`waiting_approval` Step 的查询视图；
- **Task**：Owner 待办的延后产品面，在独立任务板出现前可由 Conversation/Run 表达；
- **Procedure**：延后的不可变步骤模板；出现前由普通 Run/Step 顺序表达；
- **WorkflowRun**：不存在；即使以后引入 Procedure，仍是引用模板版本的普通 Run。

### 4.2 Run 状态机

```text
queued
  → running
      ├─→ waiting_approval → running
      ├─→ waiting_external → running
      ├─→ succeeded
      ├─→ failed
      ├─→ cancelled
      └─→ expired
```

规则：

- 每个 Run 有明确 trigger、subject、goal、budget、deadline 和 idempotency key；
- Child Run 不继承父 Run 的全部 Grant，只接受显式收窄后的集合；
- 重试发生在 Step/Provider 边界，不复制整个 Run；
- waiting 状态必须持久化恢复条件；`waiting_approval` Step 保存动作摘要、过期时间和允许的响应主体；
- Run 进入终态后不能创建新的 ActionRequest；终态前已提交的 Outbox 项仍可完成发送并记录结果。

### 4.3 Conversation 与 Run 的寿命

- Conversation 无界：同一对话可跨越任意多条 Message 与多次 Run。
- Run 有界：普通入站 Trigger 启动一次新 Run，或恢复该对话中已有的 waiting Run。
- 同一 Conversation 默认最多一条活动主 Run（`queued`、`running` 或 `waiting_*`）。
- 主 Run 进行中的新入站默认排队；Owner 明确取消或取代时先结束当前主 Run，再启动新 Run。
- 审批与 `waiting_external` 的后续可信消息恢复原 Run，不另开一条抢权的主 Run。
- Child Run 不受"每对话一条"限制，但计入父 Run 的深度与预算。

---

## 5. Domain（纯规则层）

Domain 只做**纯判断与状态迁移**，零 I/O、零时钟、零随机，可确定性单测：

- 聚合类型与状态机（Run、Step、ScopedGrant 的合法迁移）；
- 工作集预算与截断策略；
- ActionRequest 构造与参数摘要（digest）；
- 可重放的确定性决策（Policy 规则）。

Domain 不访问网络、文件、数据库、Channel，也不直接调用 LLM。它只产出**被 Application 消费的纯结果**。

> **Pure-with-impure-fallback pattern**（D25 audit, 2026-08-31）：Domain pure 函数对外暴露的 input 接受 `nowMs?` / `id?` 字段，函数体 `input.nowMs ?? Date.now()` / `input.id ?? crypto.randomUUID()` 提供默认值。这是 §5 "零时钟、零随机" 文字与"caller 注入时钟做 deterministic 单测"实际模式之间的边界豁免：测试 caller 传固定 `nowMs` / `id` 时函数 100% pure；不传 caller 走 fallback 是 single-process 内的 deterministic-but-impure 调用（非 I/O，不打破 §5 line 183 限制）。
>
> **§5 范围路径 audit 状态**（D25）：
>
> | 范围 | 实际路径 | 状态 |
> |---|---|---|
> | 聚合类型与状态机 | `packages/domain/src/{knowledge,conversation,projects}/` | ✅ |
> | 工作集预算与截断策略 | `packages/runtime/src/working-set.ts`（runtime 层调用，§5 业务规则归属 Domain） | ✅ |
> | ActionRequest 构造与参数摘要（digest） | `packages/runtime/src/capability-boundary.ts`（digest 计算） | ✅ |
> | 可重放的确定性决策（Policy 规则） | `packages/domain/src/{permissions,guards,memory,tools,projects}/pure.ts` | ✅ |
>
> 锁定方式：`tests/architecture/section5-domain-pure.test.ts`（D25，8 cases）+ `tests/architecture/domain-zero-io.test.ts`（D17 pre-existing）。

---

## 6. Application（编排层）

Application 是唯一执行协调器（Run Engine），承担：

1. 读取 trigger、Conversation，构造有预算的工作集；
2. 经 Model Port 调用模型；
3. 把模型输出规范化为受限 Decision；
4. 将副作用转换为 ActionRequest；
5. 经 Policy Gate 后调用副作用 Capability（由 driven adapter 实现）；
6. 持久化 Step、状态和必要审计；
7. 在预算、截止时间、取消或完成条件触发时结束。

它不再拆成并列的 AgentKernel、Orchestrator、SessionSupervisor 和 WorkflowRunner。

Context 压缩、Decision Decoder、Model Router 是 Application 内部策略或纯函数，只有在存在独立替换需求时才形成组件。

### 6.1 工作集

每次模型调用的输入是有预算的工作集，不是完整历史：

```text
working set =
  recent messages
  + optional rolling summary
  + this Run's relevant uncompressed steps
  + selected Durable Memory / Project Knowledge when those exist
```

规则：

- 工作集有 token 或字符预算；超预算只压缩或截断工作集，不删除 Transcript；
- 跨 Run 连续性靠工作集，不把历史 Run 的全部 Step 带入下一次模型调用；
- 滚动摘要是 Conversation 上可重建、可过期的压缩产物，不是 Durable Memory，也不自动成为事实；
- 大工具结果和媒体只存引用；默认不把全文回放进下一轮工作集；
- 完整 Message 历史只在存储层完整。

### 6.2 Model Port 与 Decision 边界

模型调用是规划，不是副作用。Model Port 负责协议适配、超时、fallback 和用量记账；不签发权限，不访问凭证、文件系统或 Channel。

不同模型协议统一成：

```text
Respond(content)
CallCapability(name, arguments, callId)
StartChildRun(role, objective, grants)
WaitForApproval(actionRequest)
Finish(reason)
```

模型只能提出 Decision。模型不能：

- 自行判定风险等级；
- 签发、延长或转移 Grant；
- 直接访问凭证、数据库、文件系统或 Channel；
- 绕过 Policy Gate；
- 把外部内容声明为可信指令。

Provider 原生 tool call 和文本 JSON 只是 Decoder 输入格式，不构成两套运行模型。

**Decoder 失败的处理（Phase D B-08/10 扩面）**：decoder 仍然 fail-quiet（不抛 throw；契约不变），但当 Decision 解析失败时，conversation-loop 在 message 队列注入一条 `[system] decision-decode-fail: <reason>` user-message 并继续下一轮 LLM 调用，让模型有机会 self-correct。最大重试次数 `BUTLER_V5_MAX_DECODE_RETRIES`（默认 1）；超过上限落到 owner-可见的 `Respond`，内容要么是模型最后一轮的原文，要么是合成说明（包含具体 parse error 与原始 raw 前 200 字符）。这一扩展保留了"decoders 不抛错"的 §6.2 主线，只在 conversation-loop 增加 retry + 反馈窗口。

> **§6 Application orchestrator 实施 audit state**（D34, 2026-08-31）：
>
> - **§6 主体 Application 7 职责**（D34 实施确认）：`packages/runtime/src/run-engine.ts` (RunEngine) 实现 7 职责 — read trigger (executeInbound) / Model Port (conversation-loop) / Decision (kernel.applyDecision) / ActionRequest (capability-boundary actionRequestFromTool) / Policy Gate + Capability (executeThroughBoundary) / Step 持久化 (runtimeStore.createStep) / 预算结束 (runBudgetWithTrigger + transitionRunStatus)。D18 §6 lock 3 cases + D34 case #6 验证 RunEngine class declaration。
> - **§6.1 工作集**（D34 case #5 lock）：`packages/runtime/src/working-set.ts` 是 pure transform — 0 DB-write (insert/update/delete-from) + 0 message delete/truncate API。D14 §20 #14 re-locked。`listMessages` 由 caller (run-engine.ts) 传入 working-set，不在 working-set 内调。
> - **§6.2 ModelDecision ADT 5 tag**（D34 case #4 lock）：`packages/domain/src/runtime/decision.ts` 含 5 `_tag` — `Respond` / `CallCapability` / `StartChildRun` / `WaitForApproval` / `Finish`。模型调用只经 Model Port（继承 D26A §20 #3 + D33 §3 #3 lock）。

---

## 7. Ports（端口，依赖方向向内的接口）

Ports 是 Core 对外的**抽象依赖**，由 driven adapters 实现、Composition Root 注入。只有真正可替换或不可信的边界才设立 Port：

| Port | 职责示例 | 典型 adapter 实现 |
| --- | --- | --- |
| Repository | Conversation / Run / Step / Grant / Audit / Outbox 的读写 | persistence runtime-store、event-store、outbox |
| Model Port | 统一模型协议、fallback、记账 | model-router、各 LLM provider |
| Capability | 副作用能力的注册与执行边界 | 工具 executor、MCP provider、沙箱 runner |
| Channel | 出站回复与富媒体发送 | WeChat iLink、Slack、Telegram |
| Clock | 时间与调度（可注入以便测确定性） | 系统时钟 / 测试假时钟 |

规则：

- Core **只依赖 Ports**；依赖注入只解决替换、测试或生命周期问题；
- 未设 Port 的内部函数不为"架构完整"创建接口；
- 新的副作用能力必须实现 Capability 契约；新入口必须实现 Trigger 契约。

> **§7 主体实施 audit state**（D31, 2026-08-31）：
>
> - **Thin barrel**（D31 case #1 lock）：`packages/ports/src/index.ts` 仅 `export * from "./core/*.js"`（per-file re-export）+ R2 shim re-export；**0 class** / **0 impl** / **0 IO**（无 fetch / drizzle / pgTable / node:fs）。
> - **Interface-only core/**（D31 case #2 lock）：`packages/ports/src/core/{outbox,channel,clock,model-port,projection,event-store,credential-provider,snapshot}.ts` 8 文件全部 interface-only — 0 class impl / 0 fetch / 0 pgTable / 0 drizzle / 0 node:fs / 0 DB connection。
> - **依赖方向向内**（D31 case #3+5 lock）：`packages/ports/src/**` 0 import `@butler/adapters` / `packages/adapters`；0 import `packages/runtime` / `packages/persistence` / `apps`（仅自身 `./core/*` + archived R2 shim 的 type-only 引用）。
> - **Port snapshot 完整**（D31 case #4 lock + D44 加 Model Port）：`ports/core/` 包含 Model Port `model-port.ts` + 7 port — `channel.ts` / `clock.ts` / `credential-provider.ts` / `event-store.ts` / `outbox.ts` / `projection.ts` / `snapshot.ts`（Repository + Capability 不在 ports/core，按 §7 line 279 "未设 Port 的内部函数不为架构完整创建接口" 与 D26B §20 #6 / D29 §9 已 lock）。
> - **R2 Effect Tag shim**：D12 (commit `33af1722`) 归档 14 个 Tag 类（LLMService / ToolExecutor / EventStoreService 等）— `r2-shim.ts` 仅 archived `pnpm test:archived` 引用，生产 delivery shell 走 async/await + 直调 `@butler/persistence`。
>
> 锁定方式：`tests/architecture/section7-ports-main.test.ts`（D31, 5 cases）+ `tests/architecture/section17-3-orphan-package.test.ts`（D18/D19 §17.3 port 路径继承）+ D11 §7.1 port snapshot lock + D26A §20 #2 Core 不 import adapters + D26B §20 #6 Repository 在 persistence 而非 ports + D29 §9 Capability 在 runtime 而非 ports。

### §7.1 已实施 Port 状态（2026-08-31 snapshot）

| Port | 状态 | File | 实装 / 备注 |
| --- | --- | --- | --- |
| Clock | ✅ 已实施 | `packages/ports/src/core/clock.ts` | `systemClock`/`fixedClock`；注入 RunEngine（R10 P5） |
| Credential Provider | ✅ 已实施 | `packages/ports/src/core/credential-provider.ts` | `createHostCredentialProvider`；fail-closed（R10 P2） |
| Event Store | ✅ 已实施（窄接口） | `packages/ports/src/core/event-store.ts` | `packages/persistence/src/event-bridge.ts` 实装；旧 `EventStoreService`（R2 宽 Tag）已归档（commit `33af1722` 2026-08-28），prod runtime 不经 Tag 注入面 |
| Outbox | ✅ 已实施（窄接口） | `packages/ports/src/core/outbox.ts` | prod runtime 直调 `@butler/persistence/outbox.js`；新 Port 为未来替换/隔离触发的接缝（与 `port-catalog.md` §1 同步） |
| Snapshot | ✅ 已实施（窄接口） | `packages/ports/src/core/snapshot.ts` | prod runtime 直调 `@butler/persistence/snapshot.js`；新 Port 为未来替换/隔离触发的接缝 |
| Projection | ✅ 已实施（窄接口） | `packages/ports/src/core/projection.ts` | prod runtime 直调 `@butler/persistence/projections.js`；新 Port 为未来替换/隔离触发的接缝 |
| Channel | 🟡 接口已实装，adapter 待触发出线 | `packages/ports/src/core/channel.ts` 接口；`packages/adapters/src/wechat/channel-port.ts` iLink impl（线上）；Composition Root 注入 `wiring.channels` | WeChat 上线；Slack adapter skeleton 就位（`packages/adapters/src/slack/`，5 文件）等真接生产触发（DESIGN §18 条件准入）；Telegram 未触发 |
| Capability 契约 | 🟡 实现即接口 | `packages/runtime/src/capability-boundary.ts` | 不另立接口（DESIGN §7 + AGENTS.md §0 三层事实） |
| Repository | ⚪ 隐性承载（YAGNI） | `runtime-store.ts` 直接函数调用 | 等第二持久化实现或独立 mock 需求 |
| Model | ✅ 已实施（D44 P5 Model Port） | `packages/ports/src/core/model-port.ts` | `resolveModelForRole(env, role)` 返回中性 `{provider, model}` 单一真相源；adapters 构建 `LLMAdapter` + apps `llm-pricing` 记账统一消费（§6.2），2 consumers |
| v5 Ports 总入口 (thin barrel + R2 shim) | ✅ thin barrel + fixture shim | `packages/ports/src/index.ts`（顶部 deprecation 注释 + thin barrel）；`packages/ports/src/r2-shim.ts`（fixture-only） | `/core/*` 7 个 v5 物化 Core Port + R2 shim（14 个 Tag 类，仅 `pnpm test:archived` 使用，prod v5 code 不得引；invariant 16 由 `package-membership.test.ts` 锁） |

> "ports-stable × real-need driven" 是 §7 实施准则：不预先为"架构完整"造休眠接口。新增 / 迁移 Port 时同步更新本表与 `port-catalog.md`。

---

## 8. Driving Adapters（入站/Trigger 接缝）

所有入口都归一化为 Run Trigger：

```text
RunTrigger
  subject
  source
  conversationRef?
  payload
  trustLevel
  idempotencyKey
```

`source` 至少包括 `channel`、`cli`、`api`、`webhook`、`schedule` 和 `parent_run`。不存在绕过 Trigger 模型的 Run 创建路径。`task` 仅在独立 Task 产品面立项后启用，仍复用同一 schema。

实现包括：

- WeChat、CLI、HTTP/API；
- Webhook；
- Schedule/Cron；
- 本地控制面；
- 外部系统通知。

Channel Adapter 是可收发 Channel 的 Trigger Adapter 子类，负责解析协议级身份、附件和回复地址；Intake 持久化规范化后的 Channel/Conversation 映射与回复引用。

Schedule 只负责按时产生 Trigger，不拥有另一套 Workflow、Policy 或执行引擎。

外部 Trigger 由 Intake 受理。`parent_run`（以及未来的 `task`）是 Run Engine 写入内部运行队列的 Trigger，复用同一 schema 和去重规则，不反向调用 Intake。Child Run 的 `conversationRef` 可为空；需要继承对话上下文时显式引用父 Conversation。

**边界**：Driving Adapter 不做意图决策；意图分类（如微信 dev_task / 聊天）属于 Core.Application 的用例编排，Adapter 只完成协议适配与 `RunTrigger` 构造。

> **§8 实施 audit state**（D29, 2026-08-31）：`TriggerSource` union (`packages/domain/src/runtime/types.ts:8`) 覆盖 7 source — `channel` / `cli` / `api` / `webhook` / `schedule` / `parent_run` / `task`（§8 line 313 "至少包括 6 项" superset）。6 个 `build*RunTrigger` builders（wechat/channel/api/cli/task + schedule）按 §8 source literal 配对；`parent_run` 由 `delegate-runtime.ts` 直接 set `triggerSource: "parent_run"` on child Run record（§8 line 327 不反向调 Intake）。Schedule (`apps/api/src/schedule-run.ts`) 仅 build trigger + dispatch runButlerLoop，不另立 Workflow/Policy/engine（§8 line 325）。
>
>  锁定方式：`tests/architecture/section8-9-adapters-boundary.test.ts`（D29 §8 段 3 cases）+ D26A §20 #4 RunTrigger 入口归一化 + D26A §20 #1 RunEngine 唯一。

---

## 9. Driven Adapters（出站/副作用 Capability 接缝）

所有副作用能力通过 Provider 注册：

```text
CapabilityDefinition
  name
  inputSchema
  outputSchema
  riskClass
  defaultSandboxProfile
  timeout
  idempotency
  auditPolicy
```

Provider 类型包括：

- 文件、命令和本地工具；
- MCP 工具；
- 浏览器动作；
- 出站 Channel；
- 外部 API。

模型不在此注册表中。MCP 是注册远程副作用 Capability 的适配器，浏览器是一组共享隔离会话的 Capability，出站发送也是 Capability。它们不能形成旁路。

> **§9 实施 audit state**（D29, 2026-08-31）：`CapabilityDefinition` (`packages/runtime/src/policy-gate.ts:11`) 实际 4 顶层字段 — `name` / `kind` / `risk` / `declared?`；§9 text 8 字段重构为 `CapabilityProviderMetadata` (option 子接口) — 含 `inputSchema?` / `outputSchema?` / `sandboxProfile?` (was `defaultSandboxProfile`) / `timeoutMs?` (was `timeout`) / `idempotent?` (was `idempotency`) / `auditPolicy?` (full/summary/none)。**text-vs-impl drift 承认**：riskClass → kind+risk；defaultSandboxProfile → sandboxProfile；timeout → timeoutMs；idempotency → idempotent；8 字段语义保留但分层到顶层 4 + declared 6 optional。
>
>  `CapabilityRegistry.register` (`policy-gate.ts:86`) 是 sync void 唯一 register site；`capabilityDefinitionFromTool` (`capability-boundary.ts:57`) 是 ToolDefinition → CapabilityDefinition canonical adapter。LLM + Channel Port 不进 `registry.register(...)`（§9 line 357 模型不在注册表；Channel Port 走 `wiring.channels` composition root，D2.4 step 1 锁）。
>
>  锁定方式：`tests/architecture/section8-9-adapters-boundary.test.ts`（D29 §9 段 3 cases）+ D10 §20 #10 register sync + D26A §20 #1 CapabilityRegistry 唯一 + D2.4 §7.1 Channel Port + D23/D24 LLM 边界。

---

## 10. Governance 与副作用咽喉

所有副作用先规范化为：

```text
ActionRequest
  actor
  capability
  resource
  argumentsDigest
  context
```

统一执行流程：

```text
ActionRequest
  → Policy: Allow | Deny | Ask
  → waiting_approval Step when Ask
  → ScopedGrant when required
  → Provider Execution Boundary
  → Audit when required
```

模型调用不走这条链。

### 10.1 Policy

Policy 是确定性规则，不是 LLM：

- 输入 subject、能力、资源、Channel 信任级别、当前 Grant、Owner 在线状态和运行上下文；
- 输出 `Allow`、`Deny(reason)` 或 `Ask(actionDigest, prompt)`；
- 规则以数据和纯函数表达，不建设通用规则引擎；
- 所有入口与父/子 Run 共用一个 Policy Gate。

### 10.2 Approval

Approval 是 Run 中的等待 Step，不是独立执行引擎，也没有独立生命周期表：

- `waiting_approval` Step 持久化待确认动作摘要、原始 Run/Step、过期时间和允许的响应主体；
- 待审批列表是对该类 Step 的查询；
- 后续可信入站消息恢复原 Run；
- 批准后按风险类生成 ScopedGrant，拒绝或过期则结束该 Step；
- 重启后可以恢复，但不能重新解释已批准参数；
- 凭证、完整敏感参数和原始 secret 不进入审批记录。

微信可承担低风险、低摩擦确认。不可逆动作、凭证操作和首次访问新外部域名应由 loopback 本地控制面确认。

### 10.3 ScopedGrant

最小字段：

- `subject`
- `capability`（D2.2 first-class column，与 `scope.capabilities` 镜像；`grantMatchesAction` + `findActiveGrant` SQL 以此为准）
- `scope`
- `expiresAt`（实现为 epoch ms；语义描述按字段名）
- `remainingUses`：null 表示无限次；Always-confirm 每次签发 `remainingUses = 1`
- `approvalId?`：交互审批生成时指向对应 Step；Owner 预配置 Grant 可为空
- `delegable`，默认 `false`
- `sandboxProfile?`：仅在授权提升 Provider 默认隔离等级时填写
- `networkAllowlist?`（P2b）：`host:port` 列表，仅 workspace write 类 Grant 填充，约束 Provider 跨网络出口

动作摘要、策略版本、预算和决策原因属于 Step、Run 或 Audit 元数据，不重复放入 Grant。

授权模型不使用 Lease。并发资源锁（例如独占 workspace）在出现真实冲突前不建设；立项后也不得与 ScopedGrant 混名。

### 10.4 Sandbox

Sandbox Profile 默认属于副作用 Capability Provider 的执行配置：

- Grant 决定"业务上是否允许"；
- Sandbox 决定"技术上最多能做什么"；
- 提升默认 sandbox profile 必须写入短期、不可委派的 ScopedGrant；
- 即使 Policy 错误放行，Sandbox 仍限制路径、网络、进程、输出和资源；
- 即使 Sandbox 允许，高风险业务动作仍可能需要 Approval。

> **§10.4 实施 audit state**（D34, 2026-08-31）：
>
> - **Sandbox profile 是 Provider metadata，不是独立 boundary**：text §10.4 暗示"Sandbox Profile 默认属于副作用 Capability Provider 的执行配置" + "Sandbox 决定技术上最多能做什么"（boundary 暗示）；impl 中 sandbox profile 是 `mcpProvider.defaultSandboxProfile` (capability-boundary.ts:283) + `CapabilityProviderMetadata.sandboxProfile?` (policy-gate.ts:24) + `sandboxProfileForApprovedCapability` (sandbox/profiles.ts)。**drift 承认**：text 用 "边界" 语言，impl 把 sandbox 视为 Provider metadata + 工具默认配置。**0 独立 `packages/sandbox/` 目录**（D34 case #1 lock）。
> - **Grant.sandboxProfile + delegable 字段**（D34 case #2 lock）：`ScopedGrantRecord` (`governance/types.ts:65-69`) 含 `readonly delegable: boolean` + `readonly sandboxProfile: string | null`。**drift 承认**：text §10.3 line 448 "默认 false" 在 impl 层面无 interface default（构造时 default 或 runtime check 处理）；text line 449 `sandboxProfile?` 隐含 optional + non-null，但 impl 是 `string | null`（nullable + optional 同义）。
> - **CapabilityProviderMetadata 含 sandboxProfile?**（D34 case #3 lock）：`policy-gate.ts:21-28` 6 optional metadata 字段含 `sandboxProfile?: string`。

> **§10 实施审计状态**（D27, 2026-08-31）：
>
> | §10 字段（设计文字） | 实施字段（TypeScript ADT） | 状态 |
> |---|---|---|
> | ActionRequest `actor` | `subject` | 字段重命名（语义对齐 §10.3 ScopedGrant.subject） |
> | ActionRequest `argumentsDigest` | `digest` | 字段重命名（短化） |
> | ActionRequest `context` | `payload` | 字段重命名 |
> | ActionRequest (无 kind/risk) | `kind` (`ActionKind`: read/write/command/delegate/outbound/model) + `risk` (`RiskLevel`: low/medium/high) | 实施扩面（D2.x 引入 kind/risk 用于 capability 路由 + risk-aware Policy） |
> | ScopedGrant 9 字段（id/runId/createdAtMs 隐式） | ScopedGrantRecord 12 字段 = 9 显式 + 3 DB 必需 (`id` / `runId` / `createdAtMs`) | 实施扩面（D2.2 capability first-class column 独立于 scope.capabilities） |
> | PolicyDecision `Allow` / `Deny(reason)` / `Ask(actionDigest, prompt)` | `Allow` / `Deny(reason)` / `Ask(question, expiresAtMs)` | `Ask` payload 字段调整：`question` + `expiresAtMs` 替代原 `actionDigest + prompt` |
> | waiting_approval 是 Step status | `waiting_approval` 是 Step status + run.status（**不是**独立表） | 实施与设计一致 |
> | ScopedGrant 字段集合 | 12 字段（含 D2.2 first-class `capability` column） | 实施与设计一致 |
> | Sandbox 解析 | `sandboxProfileForApprovedCapability` (runtime/sandbox/profiles.ts) | 实施与设计一致 |
> | 模型调用不走 §10 chain | LLMAdapter 不 import PolicyGate，不构造 ActionRequest | 实施与设计一致（§20 #3 配套 lock） |
>
> 锁定方式：`tests/architecture/section10-governance-arch-guard.test.ts`（D27, 9 cases）+ §20 #1/#3/#7/#10 既有 lock。

---

## 11. 混合数据模型

Butler 不采用全面 Event Sourcing。当前状态表是业务事实；不可变记录用于消息和必要审计。

默认逻辑数据集：

- `conversations`, `messages`
- `runs`, `steps`
- `scoped_grants`
- `outbox`
- `audit_events`

不默认建设（trigger-conditioned，§11.4 line 484 同款："只有出现实测需求时才建"）：`tasks`、`procedures`、独立 `approvals` 表、`memory_records`、`documents`。"不默认"= 默认情况下不建，但有真实触发需求时可建。

> **当前 trigger 状态（D22 audit, 2026-08-31）**：
>
> - **已 trigger**（P0-P4 capability 真需求，commit `f60de759` v5 大爆炸引入）：`tasks`、`procedures`、`documents` — schema.ts 各有 pgTable；persistence 层有 `TaskStore` / `ProcedureStore` / `DocumentStore`；`apps/api` 12 个 owner HTTP endpoints（6 documents + 2 procedures + 4 tasks）接 production；wechat slash commands 入口含 tasks。arch guard `tests/architecture/section11-deferred-triggered.test.ts` 锁住。
> - **未 trigger**：独立 `approvals` 表（审批字段存在 `waiting_approval` Step 上，§6.1 Step status 字段承载）；`memory_records` 走 §12 `durable_memories` 路径满足 MVP；独立 `memory_records` 表待 §18 row 3 G3+ 触发（D39 2026-09-01 G3 batch UI 已实证 MVP 通过 §12 路径跑通）。
>
> **撤销 / 收回流程**：若 owner 收回已 trigger 项需求（取消 `/待办` 命令、关闭文档命令等），按 D19 orphan cleanup 模式：删表 / Store / routes + 更新本段 + 改写 arch guard。

### 11.1 Current State

Conversation、Run、Step、Grant 直接保存当前状态：

- 普通查询不依赖事件重放；
- 写入通过明确事务更新；
- 入站去重键由 Message 或 Run 上的 `(triggerSource, idempotencyKey)` 唯一约束承载；
- 并发控制使用版本号或条件更新；
- 状态迁移仍由 Domain 纯函数验证合法性。

### 11.2 Append-only Records

以下记录不可变：

- Message；
- Grant 签发、使用和撤销；
- 对外发送；
- Run 开始、终止和人工取消；
- 安全拒绝、越界尝试和 Always-confirm 执行。

成功的低风险工具结果只写入 Step，不双写 `audit_events`。`audit_events` 用于解释和追责，不是重建全部业务状态的唯一来源。

### 11.3 Outbox

Outbox 保留，因为它解决状态提交与异步副作用之间的一致性。

只用于：

- 外部 Channel 发送；
- Child Run 派发；
- 必须在事务提交后执行的外部通知。

> **§11.1/§11.2/§11.3 实施审计状态**（D28, 2026-08-31）：
>
> - **§11.1 Current State**：schema.ts 实现 5 表 `messages` / `runs` / `steps` / `scoped_grants` / `audit_events` 都直接保存；`messages.idempotencyKey` + `runs.idempotencyKey` 唯一约束（text 说 `(triggerSource, idempotencyKey)` 联合 key；impl 用 `idempotencyKey` 单独 — D28 承认 drift，narrow key 仍防 duplicate-inbound，多 channel 扩展时再补联合 key）；`runs.version: integer().default(1)` 版本号并发控制（`transitionRunStatus(runId, version, ...)` 模式）；`store.withTransaction(fn)` canonical 事务包装（runtime-store.ts:479 + run-lifecycle.ts ≥ 4 处使用）。`普通查询不依赖事件重放` 由 D26B §20 #6 lock。
> - **§11.2 Append-only Records**：`messages` 表 0 update API（runtime-store 仅暴露 `appendMessage`）；`audit_events` 表 + `appendEventAndEnqueueOutbox` 函数（event-store.ts:146）提供 immutable audit log；capability 成功路径只写 Step tracer.record，**不双写 audit_events**（§11.2 line 497 audit 用于解释追责不重建业务状态）。
> - **§11.3 Outbox**：`outbox` pgTable + `appendEventAndEnqueueOutbox` 单点入队（§20 #8 D7 已 lock 事务原子性）。
>
> 锁定方式：`tests/architecture/section11-1-2-3-current-state-immutable.test.ts`（D28, 7 cases）+ `tests/architecture/section17-3-orphan-package.test.ts`（D18 + D19 表存在性）+ §20 #6/#7/#8/#16 既有 lock。

Outbox 不作为通用领域事件总线。系统内部默认直接函数调用。

同步 Capability Provider 调用使用 ActionRequest idempotency key 与 Step 结果记录防止重复；只有事务后异步外发使用 Outbox。

### 11.4 不默认建设

- 全量 Projection 与独立读库；
- Snapshot 和 DeltaChannel；
- Command Bus / Query Bus；
- 通用 Event Bus；
- Kafka、Redis Stream 或独立 Broker。

只有出现实测性能、隔离或查询需求时，才为具体读模型增加局部 Projection。

---

## 12. 知识层与记忆

记忆只有三层，且后两层按需立项：

1. **Transcript**：原始 Message；默认内核已包含；不可变，受保留策略约束。
2. **Durable Memory**：Owner 偏好、事实和经验；带来源、置信度、有效期和确认状态。
3. **Project Knowledge**：项目文档、结构化资料和可选索引；不等同于个人记忆。

Run 内部的摘要、截断、滚动摘要和工具结果压缩是可重建、可过期的执行产物，不是知识层，也不自动升级为 Durable Memory。

规则：

- 模型生成的记忆默认是 candidate，不是事实；
- Durable Memory 必须能追溯到 Message、Document 或 Owner 明确输入；
- 删除原始数据时同步处理派生内容；
- 向量索引只是可重建检索实现，不是事实源；
- 默认先用结构化字段、全文搜索和显式召回，实测不足后再启用 embedding。

当前不建设：

- Dream 两阶段自动巩固；
- ContextGraph；
- 自动全盘索引；
- 无来源的"经验沉积"；
- 独立 RAG Studio。

> **§12 实施 audit state**（D30, 2026-08-31）：
>
> - **3 层独立**（D9 §20 #9 已 lock cross-import = 0 + D30 延伸）：`messages` 表 (Transcript=原始 Message) / `durable_memories` 表 (Durable Memory) / `project_knowledge_items` 表 (Project Knowledge)。3 个独立 domain 模块 (`packages/domain/src/knowledge/{durable-memory,project-knowledge,document-ingest}.ts`) + 1 个 pure module (`memory/pure.ts`) + `conversation` (transcript)。
> - **DurableMemoryRecord** (`packages/domain/src/knowledge/durable-memory.ts:23`) 4 字段 = `sourceKind` / `confidence` / `expiresAt` / `status` (candidate/confirmed)。**sourceKind 3 source**：`owner` / `message` / `document`（§12 line 556 可追溯 Message/Document/Owner 明确输入）。
> - **Project Knowledge ≠ Durable Memory**（D30 case #4 lock）：`ProjectKnowledgeRecord` 不含 `sourceKind` / `confidence` / `expiresAt` 字段（§12 line 549 不等同个人记忆）。
> - **5 项 not-built 缺席**（D30 case #5 lock）：`DreamPhase` 在 `domain/src/memory/types.ts` 有 type-only 占位（dev stage reservation），但 active runtime / apps/api 0 invoke；`ContextGraph` / `RAG Studio` / `auto-index` 0 调用。符合 §12 trigger-conditioned "默认不建设" stance。
> - **默认不启用 embedding**（D30 case #6 lock）：`durable_memories` 表无 `embedding` column；`memory/pure.ts` recall 走结构化字段 (`scoreImportance` 等) 不用 `.embedding`。
> - **G3 batch candidate UI**（2026-09-01 D39）：owner 撞 "candidate 多到处理不动" 痛点，本轮实施：
>   - Owner routes: `GET /v1/owner/memories?status=candidate&limit&offset`（返 `items` + `total` + `hasMore`）+ `POST /v1/owner/memories/confirm-batch` + `POST /v1/owner/memories/reject-batch`
>   - Wechat: 新增 `/记忆候选` 命令；扩 `/确认记忆` 支持 `id,id,id` 逗号分隔 batch（兼容旧用法）
>   - 复用 `confirmDurableMemory`/`rejectDurableMemory` 单记录纯函数（domain 0 改）
>   - Persistence: `listBySubject` 加 `offset`；新 `countBySubject({subject, status?})` 方法
>   - Subject mismatch / not found / already confirmed / DB error 一律进 `failed[]`（partial-failure 语义，整体仍 200）
>   - 不引入新 first-class event；不引入新 Core Port；不动 §11.4 不默认建设项
> - **G1 candidate expires cleanup** (2026-09-01 D40 ship)：owner 撞 "candidate 多到处理不动" 后 stale candidate 7d 自动软删除（status='expired'）。Owner-routes 加 expired 409 guard；`apps/api/src/candidate-expires-sweeper.ts` opt-in 同进程 sweeper（复用 schedule-worker 模式）；不引入新 Core Port / 不引入新 first-class event / 不建独立 worker 进程（§20 #11 + §18 #11 lock 保持）。Persistence 加 `listExpiredCandidates` + `markExpired` 2 能力；domain 加 `expireOldCandidates` 纯函数。
> - **G2 candidate dedup** (2026-09-01 D41 ship)：trigram Jaccard 检测新 candidate vs 已存在记忆 (confirmed + candidate + rejected) 相似度；>= 0.85 返回 409 with existingMemoryId + similarity；owner 可 `force=true` bypass。Domain 加 `trigramJaccard` + `findSimilarMemories` 纯函数；persistence 加 `findCandidatesForDedup` 1 能力；owner-routes + wechat `/记住` 3 调用点集成。Embed-free（§12 line 593 + D30 case #6 lock 保持）；不引入新 Core Port / 不引入新 first-class event / 0 新 LLM 调用。
> - **G4 candidate auto-promote** (2026-09-01 D42 ship)：owner 撞的下一阶段痛点是 "candidate 长期滞留要 owner 逐条 confirm"，G4 闭环 §12 知识层 4 治理链路 (G3 + G1 + G2 + **G4**)。Candidate 3d 自动 promote 到 confirmed；owner 7d 撤销窗口 + POST `/v1/owner/memories/:memoryId/rollback-auto-promote` API + audit log 3 层 safety net。**违反 §12 line 599 默认不建设 + §12 line 589 模型生成默认 candidate**；spec 显式承认。Domain 加 `autoPromoteOldCandidates` + `rollbackAutoPromotedCandidate` 2 纯函数；persistence 加 `findAutoPromoteCandidates` + `markAutoPromoted` + `rollbackAutoPromoted` 3 能力 + 5 column migration (`promoted_by` / `promoted_at` / `rolled_back_by` / `rolled_back_at` / `rollback_reason`) + 1 partial index；apps/api 加 `auto-promote-config.ts` (env parser) + `auto-promote-sweeper.ts` opt-in (与 G1 expiry sweeper 同模式) + owner-routes 1 route。Embed-free (§12 line 593 + D30 case #6 lock 保持); 不引入新 Core Port / 不引入新 first-class event / 0 新 LLM 调用。
> - **G5 跨 project PK recall** (2026-09-02 D43 ship)：owner 真撞 "其它 project 的项目知识 recall 目前只能查当前 project" 痛点，闭环 §12 recall gap。`recall_project_knowledge` 语义从 "deny cross-project" 改为 "默认当前 project + 显式跨 project 召回"——不传 `projectId`/`projects` 时仍只召回当前对话 project（向后兼容）；`projectId` 可指向任意 project；新增 `projects` 参数（逗号分隔列表 / `"*"` 全量），跨 project 结果带 `[projectId]` 标签。Persistence 加 `listAllProjects` + `listByProjects` 2 能力；domain 加 `expandRecallProjectIds` + `formatCrossProjectRecall` 2 纯函数。沿用 substring recall（§12 line 593 + D30 case #6 lock 保持，embed-free）；0 新 Core Port / 0 新 first-class event / 0 migration。
> - **§12 全部治理链路闭环**：G3 batch UI（D39）+ G1 expires cleanup（D40）+ G2 dedup（D41）+ G4 auto-promote（D42）+ **G5 跨 project recall（D43）** 全 ship，无留待下轮项。
>
> 锁定方式：`tests/architecture/section12-knowledge-memory.test.ts`（D30, 6 cases）+ `tests/architecture/three-memory-separation.test.ts`（D9 §20 #9 cross-import lock）+ `tests/architecture/section11-deferred-triggered.test.ts`（D22, durable_memories 表属 §12 not §11 list）。
>
> Run 内部摘要 / 截断 / 工具结果压缩：可重建 / 可过期的执行产物，**不是知识层**（§12 line 551），**不自动升级为 Durable Memory**。`working-set.ts` (D14 §20 #14 lock) + `extractDevHistory` (filterDevHistoryNoise) 是相关 surface，未自动 promote 到 `durable_memories`。

## 13. 风险与自治

只保留三类运行规则：

1. **自动**：只读或工作区沙箱内低风险动作；
2. **Grant-required**：修改、外发、受限网络和可恢复副作用；
3. **Always-confirm**：不可逆动作、凭证、付款、权限变更和首次访问新外部域名。

"自动审查"是 Policy 规则，"无人值守"是带预批准 Grant、预算和截止时间的 Run，不需要单独自治等级。

Policy 返回 `Allow` 时直接执行且不物化 ScopedGrant；Grant-required 和 Always-confirm 动作必须出示 Grant。Always-confirm 每次只签发 `remainingUses = 1` 的 Grant。

ScopedGrant 的 `subject` 是**不透明 principal 标识符**（"谁在执行"），不是受限词表。代码侧不强制 4-pattern 词表；policy-gate 用 `request.subject === policy.ownerSubject` 直接字符串相等比较，约束由调用方自管理。常见实际值（illustrative，非穷举）：

- 配置的 owner subject（由 `resolveOwnerSubject(env, conversationId)` 解析；具体字符串由 Owner 配置决定，例如 `"owner-1"`、`"wxid_abc"`）；
- 内部 Trigger 来源：`system:scheduler`（`packages/domain/src/runtime/schedule.ts:10`）等 `system:*` 前缀；
- Owner 控制面动作的简单 `"owner"` literal（用于 project-knowledge-sync 等后台路径）。

> **不强制** §13 旧版列的 `owner / principal:<id> / system:<id> / run:<runId>` 4-pattern 词表：impl 用 opaque 字符串语义；`runId` 在 `ScopedGrantRecord` 里有独立字段，不在 subject 前缀里。审计（D18, 2026-08-30）确认所有 ScopedGrant caller 的 subject 实测值都是 opaque principal string。

Schedule 不是长期授权主体；它以 `system:scheduler` 创建 Run，能力授予具体 Run（`ScopedGrant.runId` 字段）。Subagent 是 Child Run 的角色配置，不是独立 subject。

每个 Run 还必须有：

- 模型、工具调用、费用和时间预算；
- 取消入口与 kill switch；
- deadline 和 quiet-success 行为；
- 最大 Child Run 深度；
- 网络与 workspace 边界；
- 可解释的终止原因。

> **§13 风险与自治 实施 audit state**（D34, 2026-08-31）：
>
> - **3 类 trigger text-vs-impl drift 承认**（D34 case #7 lock）：text §13 line 602-606 列 3 类 trigger（自动 / Grant-required / Always-confirm）；impl 用 `PermissionPolicy` (`packages/domain/src/permissions/types.ts:46-53`) 3 列表 — `allowed` / `denied` / `requireApproval`。**drift 承认**：text 描述"3 类"按风险分类，impl 把"Grant-required + Always-confirm"合并到 `requireApproval` 列表（per-tool approver），不再区分两类。`PolicyDecision` ADT (line 55-58) 实际是 `Allow` / `Deny` / `RequireApproval(approver)` — 不是 text §10.1 line 392 的 `Allow` / `Deny` / `Ask`。
> - **Always-confirm remainingUses = 1**（D34 case #8 lock）：`packages/runtime/src/approval-runtime.ts:231` literal `remainingUses: 1` — Always-confirm 路径签发单次 Grant。text §13 line 610 "Always-confirm 每次只签发 `remainingUses = 1` 的 Grant" 实施一致。
> - **ScopedGrant.subject opaque principal**（D34 case #9 lock）：`ScopedGrantRecord.subject: string`（无 4-pattern 词汇表 enforced）— 继承 D20 §13 lock + D33 §3 #4 Governance SDK-isolated。
> - **Schedule `system:scheduler` source**（D34 case #10 lock）：`buildScheduleRunTrigger` (`packages/domain/src/runtime/schedule.ts:76`) 写 `source: "schedule"` — 与 text §13 line 615 `system:scheduler` semantics 对齐。

> **锁定方式**：`tests/architecture/section10-4-6-13-deep-audit.test.ts`（D34, 10 cases）+ `tests/architecture/section13-subject-doc-2026-08-30.md`（D20）+ `tests/architecture/section10-governance-arch-guard.test.ts`（D27）。

## 14. 可靠性与可观测

最小可靠性模型：

- 请求、Run、Step 和 ActionRequest 都有 idempotency key；
- Provider 重试必须有上限，并区分可重试与永久失败；
- 同步 Provider 调用通过 ActionRequest idempotency key 和 Step 结果记录防止重复；
- 异步 Channel 发送、Child Run 派发和事务后通知通过 Outbox 防止丢失与重复；
- Child Run、waiting approval 和 waiting external 可以在重启后恢复；
- 进程关闭停止接收 Trigger，等待或取消活跃 Step，并释放资源；
- 大结果和媒体只存引用，不进入审计正文。

本地可观测字段：

- `conversationId`, `runId`, `stepId`, `parentRunId`
- `subject`, `triggerSource`
- `modelProvider`, `capability`
- `policyDecision`, `grantId`（审批等待时另记 `waitingStepId`）
- latency、token、cost、retry 和终止原因

> **字段捕获状态**（D21/D23/D24 audit, 2026-08-30 + 2026-08-31）：
>
> - **first-class 顶层捕获**（13/14）：`conversationId` / `runId` / `stepId` / `parentRunId` / `subject` / `triggerSource` / `capability` / `policyDecision` / `grantId` / `waitingStepId` / `durationMs`（=latency）/ `token`（D23，adapter 暴露 `usage` 后透传）/ `costUsd`（D24，env-driven pricing 实时填写；缺 pricing = `null`，与 `token` 字段"未知"语义对齐）。
> - **detail Record workaround**（3/14）：`modelProvider` / `retry` / `终止原因`（仅缺 §14 字段在结构上不便单独建模的部分；走 `TraceEvent.detail`）。
> - **未捕获**（0/14）：D21 标记的 `token` / `cost` 缺口已被 D23（token 路径）+ D24（cost 路径）双双闭环。
>
> **LLM pricing env vars**（D24，`apps/api/src/llm-pricing.ts` 解析）：
>
> | Env var | 含义 | 默认 |
> |---|---|---|
> | `BUTLER_V5_PRICING_<MODEL>_INPUT_PER_MTOK` | 模型输入价格 USD / 百万 token | 无即 costUsd=null |
> | `BUTLER_V5_PRICING_<MODEL>_OUTPUT_PER_MTOK` | 模型输出价格 USD / 百万 token | 无即 costUsd=null |
>
> `<MODEL>` = 模型标识大写 + `-` 替 `_`（e.g. `claude-sonnet-4-20250514` → `BUTLER_V5_PRICING_CLAUDE_SONNET_4_20250514_INPUT_PER_MTOK`）。当前模型选择由 Model Port `packages/ports/src/core/model-port.ts:resolveModelForRole(env, "plan")` 统一解析（D44 P5 Model Port；Anthropic / DeepSeek / DashScope / MiniMax）；active model 由 `resolveCurrentLlmModel(env)` 解析。缺 env = 缺定价，trace costUsd = `null`（非 0 / 非 throw）。
>
> 锁定方式：`tests/architecture/section14-observability-fields.test.ts`（D21 + D23 更新）+ `tests/architecture/section14-token-cost.test.ts`（D23，9 cases）+ `tests/architecture/section14-costusd.test.ts`（D24，7 cases）+ `apps/api/src/llm-pricing.test.ts`（D24，15 单元）。

默认使用结构化日志和本地诊断。OpenTelemetry exporter 是可选适配器，不是运行依赖。

---

## 15. Effect 与工程范式

Effect-TS 是可选实现工具，不是架构层级。

适合使用 Effect 的位置：

- 有生命周期的资源；
- 并发、取消、超时和重试；
- 多 Provider fallback；
- 需要组合的流或结构化并发。

不强制使用 Effect 的位置：

- 简单纯函数；
- 单次数据库查询；
- 无组合需求的 request handler；
- 为内部函数创建 Tag/Layer；
- 仅为满足包依赖图而包装 Promise。

统一原则：

- 领域规则优先纯函数；
- 边界输入必须运行时校验；
- 错误在模块公共边界结构化，模块内部不禁止合理的异常捕获；
- 依赖注入只解决替换、测试或生命周期问题；
- 不因"未来可能拆服务"提前创建网络协议或独立包；
- 生产 delivery shell 使用 async/await + wiring 组合根；Effect 只在有生命周期/并发/cancel 语义处使用。

---

## 16. 部署与进程边界

默认部署是单机自托管**模块化单体**：

- 一个主服务接收入站、运行短 Run 和提供本地 API；
- 同一 PostgreSQL 保存当前状态、Outbox、Audit 和后续知识表；
- Outbox worker 可同进程运行；
- 浏览器、沙箱或资源密集任务可按安全需求放入隔离子进程/容器；
- 只有出现故障隔离或资源隔离需求时才拆独立 worker。

进程拆分不改变模块、端口和权限边界，也不引入第二套 Run Engine。

---

## 17. 仓库管理与工程形态（monorepo）

### 17.1 包归属与依赖方向

采用 **pnpm workspace + turbo** 的 TS monorepo。包按"适配器 / 内核 / 端口"三条带聚类，依赖方向必须与运行时架构一致：

| 包带 | 组成 | 依赖方向 |
| --- | --- | --- |
| **Driving 适配器（delivery）** | `apps/*`、`cli` | → Core.Ports → Core |
| **Core 内核** | `runtime`（Application）、`domain`（Domain） | → ports 接口；不得 import persist/adapters 具体实现 |
| **Ports** | 端口接口（如 `ports`） | 只依赖 domain 类型 |
| **Driven 适配器** | `adapters`（模型/Channel/沙箱/MCP）、`persistence`（唯一 schema+repo）、`migration` | → ports + domain + 各自协议 SDK |
| **配置/共享（可选瘦身）** | `config`、`shared` | 精简后的零依赖纯工具 |

目标：**monorepo 里只保留生产调用链 + 明确的端口与驱动适配器**，未接线脚手架迁移/归档，降低认知负载。

### 17.2 并行开发边界

端口接口确立后，三条带可并行开发：

- 改微信/调度/Owner 控制面 → 只动 **driving adapter** + 对应 `RunTrigger`/`Channel` 端口；
- 改模型/持久化/沙箱 → 只动 **driven adapter** + 对应 Port 实现；
- 改 RunEngine/策略/布会 → 只动 **runtime / domain**。

约束：

- schema 变更被 Repository/DAO 端口隔在 core 之外；
- 任何新入口必须实现 Trigger 契约，任何新副作用必须实现 Capability 契约，否则无法接入（架构测试锁定）。

> **§17.1+§17.2 实施 audit state**（D32, 2026-08-31）：
>
> - **workspace 3 glob**（D32 case #1 lock）：`pnpm-workspace.yaml` 列出 3 glob — `packages/*` / `apps/*` / `cli`（driving CLI 在根目录；D19 §17.3 后精简 5 active packages）。
> - **5 active packages**（D32 case #3 lock）：`packages/{adapters,domain,persistence,ports,runtime}/` 完全对应 §17.1 表的 5 条带（Core 内核 `runtime + domain` / Ports `ports` / Driven `adapters + persistence`）；Driving `apps/* + cli` 在 workspace glob；配置/共享 0 active（D19 已 archive）。
> - **turbo.json**（D32 case #2 lock）：workspace root 存在；build/test pipeline orchestrator。
> - **Core 不 import adapters**（D32 case #4 lock）：`runtime + domain` 0 import `@butler/adapters` / `packages/adapters`（§17.1 依赖方向 + §17.2 "Core 不被反向依赖" — 与 D26A §20 #2 互补）。
> - **并行开发 3 条带**（§17.2）：driving (apps/api + cli) 只动 RunTrigger/Channel 端口（apps/api 6 entry points 都 import runButlerLoop，D26A #4 lock）；driven (adapters + persistence) 只动 Port 实现（D26A §20 #1 lock 三唯一 + D19 §17.3 lock workspace = 5 active）；Core (runtime + domain) 只动 RunEngine/策略/布会（D26A §20 #16 lock 单一 schema）。
> - **§17.3 _archive 隔离**（D32 case #5 lock）：`vitest.config.ts`（prod test runner）显式 exclude `_archive/**`；archived tests 走 `vitest.archived.config.ts` 独立 runner（22 files / 101 tests，D19 baseline）。
>
> 锁定方式：`tests/architecture/section17-1-2-monorepo-management.test.ts`（D32, 5 cases）+ `tests/architecture/section17-3-orphan-package.test.ts`（D18/D19）+ D26A §20 #2 + §20 #16 + D31 §7 5 cases 既有 lock。

### 17.3 脚手架修剪与卫生

- 未接入生产调用链的 `package`（脚手架/归档）移入 `_archive/` 或删除，不在编译与测试白名单中；
- 只保留一套 schema/migration（进入单一 `persistence`）；`migration` 包与 `persistence/migrations` 二选一收敛；
- delivery 层不直接访问具体持久化 schema；跨层 import 由架构测试阻止；
- 单文件大小、死代码、测试与依赖方向由工程门禁守护。

---

## 18. 延后项与触发条件

- **独立 Task 聚合**：Owner 需要跨对话的任务板，且 Conversation/Run 查询无法表达待办生命周期；
- **Procedure 模板**：至少两个已批准场景无法由普通线性/条件 Step 表达；通用 DAG、并行合并与 Channel reducer 仍更后；
- **Durable Memory / Project Knowledge 表**：真实召回或资料管理需求出现，且 Transcript 不够 — 🟡 ship 全闭环 + G3 batch UI（2026-09-01 D39）+ G1 expires cleanup（2026-09-01 D40）+ G2 candidate dedup（2026-09-01 D41）+ G4 candidate auto-promote（2026-09-01 D42）+ **G5 跨 project recall（2026-09-02 D43）**；
- **并发资源锁**：出现必须独占的 workspace 或设备冲突；
- **局部 Projection**：具体查询无法在目标延迟内完成；
- **Snapshot**：运行历史加载 p95 超过预算且无法通过普通索引解决；
- **向量检索**：结构化/全文检索在真实语料上召回不足；
- **浏览器能力**：Policy Gate、Grant 和网络沙箱已经稳定；
- **第二 Channel**：微信被证明是场景瓶颈；
- **外部 OTEL**：本地 trace 无法定位生产问题；
- **独立 Worker/Broker**：单进程资源或故障隔离实测不足。

没有触发证据时，不进入路线图。

---

## 19. 文档与治理边界

- 本文是**目标架构 SSOT**；
- 产品硬边界由 [`../docs/plans/decisions/v5-product-boundaries-2026-08.md`](../docs/plans/decisions/v5-product-boundaries-2026-08.md) 裁决；
- 当前生产事实由 [`../docs/architecture/v5-production-architecture-2026-08.md`](../docs/architecture/v5-production-architecture-2026-08.md) 描述；
- 路线和实施顺序由 active roadmap 描述；
- 旧完整函数式设计只作历史，不再约束新实现。

以下内容属于工程治理，不属于产品运行时架构：

- AGENTS、Cursor rules 和 hooks；
- 受保护文件与人工 override；
- Author/Reviewer 分离；
- AI 修改代码的证据门禁；
- 文件大小、死代码和测试门禁；
- 仓库内异构 Agent 交接。

工程治理可以保护本架构，但不能在产品数据库、运行状态机或 API 中复制一套 Guard 或黑板产品。

跨会话交接的默认载体是一份短 `state.md`（当前主线、下一步、不要做、上一班一句）。班次卡可选；claims、第二套 backlog 和 `log.md` 双写冻结。细则见 [`../docs/plans/decisions/v5-engineering-handoff-2026-08.md`](../docs/plans/decisions/v5-engineering-handoff-2026-08.md)。

---

## 20. 架构不变量

任何新设计必须满足：

1. 一个 Run Engine、一个 Policy Gate、一个副作用出口；
2. Core 只依赖 Ports，不 import 具体适配器；具体实现由 Composition Root 注入；
3. 所有副作用通过 Capability Provider；模型调用走独立 Model Port；
4. 所有入口归一化为 Run Trigger（driving adapter）；
5. Child Run 权限不宽于父 Run；
6. 当前状态可直接读取，不依赖全量事件重放；
7. 关键安全与外发动作可审计、可关联、可撤销或明确不可撤销；
8. Outbox 只用于事务后的异步副作用；
9. Transcript、Durable Memory 和 Project Knowledge 不互相冒充；压缩产物不是知识；
10. 新能力不自动扩大授权面；
11. UI、MCP、浏览器、Schedule 不创建第二套 Loop 或 Policy，也不能绕过 Ports；
12. 没有真实触发证据，不引入 Task、Procedure、新的框架、进程或持久化模型；
13. Conversation 无界，Run 有界；同一 Conversation 默认最多一条活动主 Run；
14. 模型输入是有预算的工作集；超预算只压缩工作集，不删除历史；
15. 工程交接（短 `state.md`）不是产品能力，禁止映射为 Run、Task 或 Conversation；
16. monorepo 中只保留生产调用链 + 端口 + 单一 schema；未接线脚手架归档。