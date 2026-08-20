# Butler v5 目标架构

> **状态**：Accepted target architecture
> **产品定位**：单 Owner、单信任域、自托管、可扩展的个人 AI 管家
> **用途**：定义目标模块、概念、数据、安全和扩展边界；不描述当前代码接线
> **当前实现事实**：[`../docs/architecture/v5-production-architecture-2026-08.md`](../docs/architecture/v5-production-architecture-2026-08.md)
> **产品边界**：[`../docs/plans/decisions/v5-product-boundaries-2026-08.md`](../docs/plans/decisions/v5-product-boundaries-2026-08.md)

---

## 1. 架构裁决

Butler v5 采用**务实模块化单体**，而不是完整分层框架或分布式 Agent 平台。

核心裁决：

1. 保留函数式核心、ADT、显式副作用和单向依赖原则；
2. 不强制每个调用经过 Domain/Application/Ports/Infrastructure 四层；
3. 不要求所有异步代码、依赖注入和错误处理使用 Effect；
4. 当前状态表是业务事实，关键安全与外发动作另写不可变审计记录；
5. 只保留一个 Run Engine、一个 Policy Gate 和一个副作用出口；
6. 产品模块只有三个：Intake、Execution、Governance；
7. 扩展只能进入 Trigger Adapter 或副作用 Capability Provider 两条接缝；
8. 模型调用走独立 Model Port，不与副作用 Capability 混为同一咽喉；
9. 产品运行时安全与开发 Butler 自身时的 AI Guard 分开设计。

系统的首要成本不是吞吐量，而是 Owner 与 AI 维护者理解、验证和安全演进整套不变量所需的上下文。

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
- 把开发仓库的 Guard、承重文件签名和 Author/Reviewer 流程建模为产品运行时。

---

## 3. 总体架构

```text
Trigger Adapters
  WeChat · CLI · API · Webhook · Schedule · Local UI
                         |
                         v
                       Intake
     identity · pairing · normalize · deduplicate
         Conversation · Message · reply address
                         |
                         v
                    Run Engine
                    Run / Step
                   /         \
          Governance         Model Port
   Policy / Grant / Audit    (planning only)
                   \
                    ActionRequest
                         |
                         v
         Side-effect Capability Providers
   File · Command · MCP · Browser · Outbound Channel
                         |
                         v
              PostgreSQL · Blob Store · External APIs
```

逻辑上只有三个产品模块：

1. **Intake**：承载 Trigger Adapter；负责入口协议、认证、配对、标准化、去重，以及 Conversation、Message 和持久回复地址。
2. **Execution**：Run、Step、模型循环、预算、取消和恢复。
3. **Governance**：Policy、ScopedGrant、Sandbox Profile 和 Audit。审批是 `waiting_approval` Step 的查询视图，不是第四个引擎。

Knowledge 不是第四个领域模块。Transcript 就是 Message。摘要与工具结果压缩是 Run Engine 内部策略。Durable Memory 与 Project Knowledge 按需立项后，作为 Execution 可读的附属存储，不能发送消息或执行外部动作。

Integration 也不是领域模块。它由 Trigger Adapter、Model Port、副作用 Capability Provider 和 Repository 实现组成。

这些是逻辑边界，不要求“一模块一 npm 包”。可以按变化频率和依赖关系放在同一包的不同目录。

---

## 4. 依赖方向

```text
Intake → Execution → Governance
Execution → Model Port
Execution / Governance → side-effect provider contracts
Adapters               → those contracts
Persistence            → repository contracts
```

硬规则：

- Intake 不包含 Agent 规划、权限判断或业务状态机；
- 出站格式化和发送属于 Outbound Channel Capability Provider，不属于 Intake；
- Execution 只能通过 Policy Gate 请求副作用；模型调用不经过 ActionRequest；
- Governance 不依赖具体 Channel、工具或 Provider SDK；
- Provider 不能绕过 Policy Gate 回调核心状态；
- 模块间默认直接调用，不使用进程内通用 Event Bus。

Port 只用于真正可替换或不可信的外部边界，例如模型、数据库、文件、Channel、MCP、浏览器和时钟。内部纯函数不为“架构完整”而创建接口。

---

## 5. 统一概念模型

### 5.1 核心实体

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

### 5.2 Run 状态机

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

### 5.3 Conversation 与 Run 的寿命

- Conversation 无界：同一对话可跨越任意多条 Message 与多次 Run。
- Run 有界：普通入站 Trigger 启动一次新 Run，或恢复该对话中已有的 waiting Run。
- 同一 Conversation 默认最多一条活动主 Run（`queued`、`running` 或 `waiting_*`）。
- 主 Run 进行中的新入站默认排队；Owner 明确取消或取代时先结束当前主 Run，再启动新 Run。
- 审批与 `waiting_external` 的后续可信消息恢复原 Run，不另开一条抢权的主 Run。
- Child Run 不受“每对话一条”限制，但计入父 Run 的深度与预算。

---

## 6. Run Engine

Run Engine 是唯一执行协调器，承担：

1. 读取 trigger、Conversation，并构造有预算的工作集；
2. 调用 Model Port；
3. 把模型输出规范化为受限 Decision；
4. 将副作用转换为 ActionRequest；
5. 经 Policy Gate 后调用副作用 Capability Provider；
6. 持久化 Step、状态和必要审计；
7. 在预算、截止时间、取消或完成条件触发时结束。

它不再拆成并列的 AgentKernel、Orchestrator、SessionSupervisor 和 WorkflowRunner。

Context 压缩、Decision Decoder、Model Router 是 Run Engine 内部策略或纯函数，只有在存在独立替换需求时才形成组件。它们不是 Knowledge 域。

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

百轮对话成立的前提是 Conversation 无界、Run 有界、工作集有预算。不为此预建 ContextGraph、向量库或独立 Session 聚合。

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

---

## 7. Governance 与副作用咽喉

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

### 7.1 Policy

Policy 是确定性规则，不是 LLM：

- 输入 subject、能力、资源、Channel 信任级别、当前 Grant、Owner 在线状态和运行上下文；
- 输出 `Allow`、`Deny(reason)` 或 `Ask(actionDigest, prompt)`；
- 规则以数据和纯函数表达，不建设通用规则引擎；
- 所有入口与父/子 Run 共用一个 Policy Gate。

### 7.2 Approval

Approval 是 Run 中的等待 Step，不是独立执行引擎，也没有独立生命周期表：

- `waiting_approval` Step 持久化待确认动作摘要、原始 Run/Step、过期时间和允许的响应主体；
- 待审批列表是对该类 Step 的查询；
- 后续可信入站消息恢复原 Run；
- 批准后按风险类生成 ScopedGrant，拒绝或过期则结束该 Step；
- 重启后可以恢复，但不能重新解释已批准参数；
- 凭证、完整敏感参数和原始 secret 不进入审批记录。

微信可承担低风险、低摩擦确认。不可逆动作、凭证操作和首次访问新外部域名应由 loopback 本地控制面确认。

### 7.3 ScopedGrant

最小字段：

- `subject`
- `capability`
- `scope`
- `expiresAt`
- `usesRemaining`
- `approvalId?`：交互审批生成时指向对应 Step；Owner 预配置 Grant 可为空
- `delegable`，默认 `false`
- `sandboxProfile?`：仅在授权提升 Provider 默认隔离等级时填写

动作摘要、策略版本、预算和决策原因属于 Step、Run 或 Audit 元数据，不重复放入 Grant。

授权模型不使用 Lease。并发资源锁（例如独占 workspace）在出现真实冲突前不建设；立项后也不得与 ScopedGrant 混名。

### 7.4 Sandbox

Sandbox Profile 默认属于副作用 Capability Provider 的执行配置：

- Grant 决定“业务上是否允许”；
- Sandbox 决定“技术上最多能做什么”；
- 提升默认 sandbox profile 必须写入短期、不可委派的 ScopedGrant；
- 即使 Policy 错误放行，Sandbox 仍限制路径、网络、进程、输出和资源；
- 即使 Sandbox 允许，高风险业务动作仍可能需要 Approval。

---

## 8. 混合数据模型

Butler 不采用全面 Event Sourcing。当前状态表是业务事实；不可变记录用于消息和必要审计。

默认逻辑数据集：

- `conversations`, `messages`
- `runs`, `steps`
- `scoped_grants`
- `outbox`
- `audit_events`

不默认建设：`tasks`、`procedures`、独立 `approvals` 表、`memory_records`、`documents`。审批字段存在 `waiting_approval` Step 上。

### 8.1 Current State

Conversation、Run、Step、Grant 直接保存当前状态：

- 普通查询不依赖事件重放；
- 写入通过明确事务更新；
- 入站去重键由 Message 或 Run 上的 `(triggerSource, idempotencyKey)` 唯一约束承载；
- 并发控制使用版本号或条件更新；
- 状态迁移仍由纯函数验证合法性。

### 8.2 Append-only Records

以下记录不可变：

- Message；
- Grant 签发、使用和撤销；
- 对外发送；
- Run 开始、终止和人工取消；
- 安全拒绝、越界尝试和 Always-confirm 执行。

成功的低风险工具结果只写入 Step，不双写 `audit_events`。`audit_events` 用于解释和追责，不是重建全部业务状态的唯一来源。

### 8.3 Outbox

Outbox 保留，因为它解决状态提交与异步副作用之间的一致性。

只用于：

- 外部 Channel 发送；
- Child Run 派发；
- 必须在事务提交后执行的外部通知。

Outbox 不作为通用领域事件总线。系统内部默认直接函数调用。

同步 Capability Provider 调用使用 ActionRequest idempotency key 与 Step 结果记录防止重复；只有事务后异步外发使用 Outbox。

### 8.4 不默认建设

- 全量 Projection 与独立读库；
- Snapshot 和 DeltaChannel；
- Command Bus / Query Bus；
- 通用 Event Bus；
- Kafka、Redis Stream 或独立 Broker。

只有出现实测性能、隔离或查询需求时，才为具体读模型增加局部 Projection。

---

## 9. Knowledge 与记忆

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
- 无来源的“经验沉积”；
- 独立 RAG Studio。

---

## 10. 两条扩展接缝

### 10.1 Trigger Adapter

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

### 10.2 副作用 Capability Provider

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

---

## 11. 风险与自治

只保留三类运行规则：

1. **自动**：只读或工作区沙箱内低风险动作；
2. **Grant-required**：修改、外发、受限网络和可恢复副作用；
3. **Always-confirm**：不可逆动作、凭证、付款、权限变更和首次访问新外部域名。

“自动审查”是 Policy 规则，“无人值守”是带预批准 Grant、预算和截止时间的 Run，不需要单独自治等级。

Policy 返回 `Allow` 时直接执行且不物化 ScopedGrant；Grant-required 和 Always-confirm 动作必须出示 Grant。Always-confirm 每次只签发 `usesRemaining = 1` 的 Grant。

ScopedGrant 的 subject 取值限定为：

- `owner`：Owner 本人直接执行的控制面动作；
- `principal:<id>`：已配对 Channel peer 或本地设备；
- `system:<id>`：受配置约束的内部 Trigger 来源，例如 `system:scheduler`；
- `run:<runId>`：普通 Run 或 Child Run。

Schedule 不是长期授权主体；它以 `system:scheduler` 创建 Run，能力仍授予具体 `run:<runId>`。Subagent 是 Child Run 的角色配置，不是独立 subject。

每个 Run 还必须有：

- 模型、工具调用、费用和时间预算；
- 取消入口与 kill switch；
- deadline 和 quiet-success 行为；
- 最大 Child Run 深度；
- 网络与 workspace 边界；
- 可解释的终止原因。

---

## 12. 可靠性与可观测

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

默认使用结构化日志和本地诊断。OpenTelemetry exporter 是可选适配器，不是运行依赖。

---

## 13. Effect 与工程范式

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
- 不因“未来可能拆服务”提前创建网络协议或独立包。

---

## 14. 部署与进程边界

默认部署是单机自托管模块化单体：

- 一个主服务接收入站、运行短 Run 和提供本地 API；
- 同一 PostgreSQL 保存当前状态、Outbox、Audit 和后续知识表；
- Outbox worker 可同进程运行；
- 浏览器、沙箱或资源密集任务可按安全需求放入隔离子进程/容器；
- 只有出现故障隔离或资源隔离需求时才拆独立 worker。

进程拆分不改变模块和权限边界，也不引入第二套 Run Engine。

---

## 15. 延后项与触发条件

- **独立 Task 聚合**：Owner 需要跨对话的任务板，且 Conversation/Run 查询无法表达待办生命周期；
- **Procedure 模板**：至少两个已批准场景无法由普通线性/条件 Step 表达；通用 DAG、并行合并与 Channel reducer 仍更后；
- **Durable Memory / Project Knowledge 表**：真实召回或资料管理需求出现，且 Transcript 不够；
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

## 16. 文档与治理边界

- 本文是**目标架构 SSOT**；
- 产品硬边界由 `v5-product-boundaries-2026-08.md` 裁决；
- 当前生产事实由 `v5-production-architecture-2026-08.md` 描述；
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

## 17. 架构不变量

任何新设计必须满足：

1. 一个 Run Engine；
2. 一个 Policy Gate；
3. 所有副作用通过 Capability Provider；模型调用走独立 Model Port；
4. 所有入口归一化为 Run Trigger；
5. Child Run 权限不宽于父 Run；
6. 当前状态可直接读取，不依赖全量事件重放；
7. 关键安全与外发动作可审计、可关联、可撤销或明确不可撤销；
8. Outbox 只用于事务后的异步副作用；
9. Transcript、Durable Memory 和 Project Knowledge 不互相冒充；压缩产物不是知识；
10. 新能力不自动扩大授权面；
11. UI、MCP、浏览器、Schedule 不创建第二套 Loop 或 Policy；
12. 没有真实触发证据，不引入 Task、Procedure、新的框架、进程或持久化模型；
13. Conversation 无界，Run 有界；同一 Conversation 默认最多一条活动主 Run；
14. 模型输入是有预算的工作集；超预算只压缩工作集，不删除历史。
