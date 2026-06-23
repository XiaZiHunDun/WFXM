# Butler v4 — 理论基线文档（三支柱管家模型）

> 版本 3.1.1 | 2026-06-09  
> 方法论：概念建模 → 七层细化 → 形式化建模 → 三角色评审 → 定理证明 → 工程验证 → 能力边界声明  
> 基于产品定义：**微信原生个人 AI 管家 — 融合 PIM、开发引擎与项目管理的统一智能体**  
> **子理论**：L4 开发引擎见 [`v4-dev-engine-theory.md`](v4-dev-engine-theory.md)（DA1-DA7 / DT1-DT7 / CA1-CA4）；L6 记忆系统见 [`v4-memory-theory.md`](v4-memory-theory.md) v1.2（MA1-MA7 / MT1-MT7）；L6 检索信任级联见 [`memory-roadmap.md`](memory-roadmap.md#检索信任级联)；L7 观测演化见本章 §2.7  
> **v3.1 变更**：新增 L7 观测演化层（OA1-OA3 / OT1-OT2）；LangFuse 评测闭环纳入理论；修正 Token 估算诚实声明（FINDING-1 已缓解）；子理论交叉引用更新  
> **v3.0 变更**：全新独立推导 → 三元张力框架替代六矛盾平列；LLM 概率预言机显式化；意图路由概率模型、成本框架新增；定理 T9/T10 从子理论提升；三角色评审覆盖 9 盲区

---

## 第一章 概念建模 — 三元张力与三支柱管家

### 1.1 系统定义

Butler v4 是一个**微信原生个人 AI 管家**，通过微信作为唯一产品界面与 Owner 交互，融合个人信息管理（PIM）、AI 开发引擎与项目管理三大能力支柱，辅以分层记忆与单 Owner 安全模型。

形式化定义：

\[
\text{Butler} = (\mathcal{G}, \mathcal{L}, \Pi, \mathcal{M}, \mathcal{A})
\]

其中：
- \(\mathcal{G}\)（Gateway）：通道模型 — 微信入站/出站/队列/斜杠命令体系/OutboundBridge
- \(\mathcal{L}\)（Loop）：Agent 循环模型 — LLM 编排/工具调度/上下文管线/流式预取
- \(\Pi\)（Pillars）：三支柱模型 — \(\Pi = \Pi_I \cup \Pi_D \cup \Pi_P\)
  - \(\Pi_I\)（PIM）：~35 个租户级工具（备忘、通讯录、记账、习惯打卡、提醒推送）
  - \(\Pi_D\)（Dev）：`delegate_task` 委派 + 内置 DevEngine 状态机
  - \(\Pi_P\)（PM）：多项目切换、Workflow DAG、Runtime Jobs、项目待办
- \(\mathcal{M}\)（Memory）：分层记忆 — Profile → Experience → Facts → ProjectMemory → SemanticIndex
- \(\mathcal{A}\)（Authority）：权限模型 — `is_gateway_owner` + `human_gate` + permissions + 信息流等级

**五元组建模决策**：Gateway 和 Loop 是**基础设施层**——它们提供通道和编排能力，本身不产生业务价值。PIM/Dev/PM 是**业务能力层**——它们是管家对 Owner 的直接价值体现。Memory 和 Authority 是**横切关注点层**——它们贯穿所有业务能力。这一分层比旧版六元组（将 WeChat、PIM、Dev、PM、Memory、Identity 平列）更清晰地反映了架构关系。

**输入域**：Owner 通过微信发送的文本、图片、语音、文件消息，以及 60+ 条斜杠命令（覆盖项目管理、对话控制、记忆操作、开发工具、日常生活五大类）。

**输出域**：微信文本回复、补充消息推送、定时提醒推送、工作流进度通知、委派完成报告、PIM 操作确认。

**状态空间**：每个会话 \(s \in \mathcal{S}\) 由以下状态向量描述：

\[
s = (H, \sigma, i, W, P, R, K, \mathcal{I}_s)
\]

其中 \(H\) 是消息历史，\(\sigma\) 是会话运行状态，\(i\) 是当前迭代计数，\(W\) 是上下文窗口大小，\(P\) 是当前项目绑定，\(R \in \{\text{butler}, \text{lead}\}\) 是当前角色，\(K\) 是累积记忆状态，\(\mathcal{I}_s\) 是 PIM 租户数据快照。

**存储双域**：
- **Tenant 域**：`~/.butler/tenants/{tenant_id}/` — 个人数据（PIM 工具存储），跨项目共享
- **Project 域**：`{workspace}/.butler/` — 项目数据（记忆、配置、转录），项目间隔离

### 1.2 核心矛盾 — 三元张力模型

Butler 的根本张力来自三个不可同时完全满足的力：

```
            全能管家承诺
           ╱            ╲
          ╱   三元张力    ╲
    单通道约束 ──────── LLM 能力上界
```

\[
\underbrace{\text{全能管家承诺}}_{\text{PIM} + \text{Dev} + \text{PM}} \times \underbrace{\text{WeChat 单通道}}_{\text{文本/语音/文件}} \times \underbrace{|H| \to \infty}_{\text{会话累积}}
\quad\longrightarrow\quad
\underbrace{W < \infty}_{\text{窗口有限}} \times \underbrace{\epsilon_{\text{LLM}} > 0}_{\text{能力有界}} \times \underbrace{\text{single-process}}_{\text{资源有限}}
\]

从三元张力出发，可推导出六个具体矛盾：

**M1（全能管家 vs 安全边界）**：管家同时管理 PIM 个人数据和项目代码。个人数据的隐私性要求隔离，但管家角色需要跨域关联能力（如："上次和张三讨论的那个项目进度如何？"需要关联通讯录与项目记忆）。

\[
\text{PIM}(\text{private}) \cap \text{Project}(\text{shared}) = \emptyset \quad \text{但} \quad \text{Butler 需要跨域推理}
\]

**M2（WeChat 单通道 vs 多模态需求）**：WeChat 是唯一产品界面，但用户需求跨越文本对话、代码审查、文件操作、定时提醒、数据可视化等多种模态。单通道的局限性：(a) 消息长度受限；(b) 无实时双向流；(c) 富交互受限。

**M3（个人数据持久 vs 上下文有限）**：PIM 数据总量远超上下文窗口。

\[
\text{tokens}(\mathcal{I}) \gg W \quad \Rightarrow \quad \text{需要检索而非全量注入}
\]

**M4（开发深度 vs 管家广度）**：管家覆盖日常生活、项目管理和开发三个领域，但开发任务需要深度上下文和专业知识。解决方案是通过 `delegate_task` 或内置 DevEngine 实现"广度管家 → 深度专家"的切换。

\[
\text{管家}(\text{breadth}) \xrightarrow{\text{delegate / DevEngine}} \text{专家}(\text{depth})
\]

**M5（离线自治 vs Owner 控制）**：定时任务和工作流可自动执行，但不可逆操作需人工确认。分级解法：`readonly` 自动执行，`mutating` 需审批。

**M6（扩展性 vs 架构简洁）**：未来可能接入外部开发工具或 MCP 服务，但扩展不能演变为通用插件平台。受控扩展点：MCP 客户端（MAX_SERVERS=3, MAX_TOOLS=20）、Runtime Jobs、工具注册表。

### 1.3 设计公理

以下 7 条公理是 Butler 三支柱管家模型的不可动摇基础：

**公理 A1（Owner 唯一性）**：系统为单个 Owner 设计。`is_gateway_owner` 是唯一的身份验证函数。安全模型基于 Owner 信任而非多租户隔离。

**公理 A2（WeChat 即产品）**：微信是 Owner 的**唯一产品界面**，不是"接入通道之一"。所有面向 Owner 的交互模式针对微信优化。无 Web UI、IDE 插件等第二产品界面。运维/CI/发版可使用 CLI（`butler gateway`、`runtime run`、`deploy` 等），**不构成 Owner 产品通道**，亦不改变 M2 单通道约束（约束对象是 Owner，不是运维操作员）。

**公理 A3（管家通过引擎动手）**：管家主循环（role=butler/lead）不直接调用项目文件修改工具（`write_file`, `patch` 等不在管家工具集中）。项目修改通过 `delegate_task` 委派给子 Agent（role=dev/content/review），或通过内置 DevEngine（在完整安全管线下）完成。PIM 工具是管家自身能力，不经委派。

**公理 A4（权限单调递减）**：在委派链 \(A_0 \to A_1 \to \ldots \to A_d\) 中，工具权限严格不增：\(\mathcal{T}_{A_{i+1}} \subseteq \mathcal{T}_{A_i}\)。PIM 工具不传递给子 Agent。

**公理 A5（数据分层 Tenant/Project）**：个人数据存储在 Tenant 域 `~/.butler/tenants/{t}/`，项目数据存储在 Project 域 `{workspace}/.butler/`。文件系统层面物理隔离。切换项目不影响 Tenant 数据。

**公理 A6（记忆分层不可旁路）**：记忆系统的四个层级有各自的写入入口和访问模式。`butler_remember` 按 scope 路由到对应层级，不可跨层直接写入。记忆注入通过 `pre_llm_transform` 仅影响 LLM API 输入，不污染 transcript SSOT。

**公理 A7（能力可插拔）**：新能力通过三种受控机制接入：(a) MCP 客户端（`mcp.yaml` 声明式配置）；(b) Runtime Jobs（项目级定时任务）；(c) 工具注册表扩展。三种机制共享同一权限/审计/审批管线。不演变为通用插件平台。

### 1.4 不可动摇的设计原则

从三元张力和公理出发，推导出以下 6 条设计原则：

**原则 P1（架构保证优于 LLM 承诺）**：能通过代码路径静态保证的性质，永远不要依赖 LLM 的行为承诺。例如 PIM 数据有界性通过硬编码上限保证，而非通过 prompt 提示。

**原则 P2（显式记忆优先于模型记忆）**：不依赖 LLM 的隐式记忆，通过结构化的四层记忆系统显式管理知识。

**原则 P3（容错优于完美）**：多重冗余而非单组件完美。上下文管理有五阶段管线，LLM 调用有多 provider failover，出站消息有 durable outbox。

**原则 P4（封闭优于开放）**：PIM 分类枚举封闭、工具集在启动时确定、MCP 上限硬编码。封闭范围内可以提供高可靠性。

**原则 P5（静态优于动态）**：能被配置静态保证的性质（权限格、工具集 frozenset），优于依赖运行时 LLM 判断的性质。

**原则 P6（诚实边界优于虚假承诺）**：明确声明系统不能做什么，比承诺能做什么更重要。

### 1.5 系统边界约束

| 约束 | 说明 | 对理论的影响 |
|------|------|-------------|
| 单 Owner | 不考虑多用户/多租户 | 权限模型简化为 Owner ⊇ Agent；PIM 数据无 ACL |
| 单进程 | 不考虑分布式一致性 | 队列模型为进程内锁；TenantStore 无并发写保护 |
| WeChat 单通道 | 非实时双向流 | 通信模型为异步 request-response；无富交互 |
| LLM 黑盒 | 不建模 LLM 内部 | 将 LLM 行为建模为概率预言机 \(\mathcal{O}_{\text{LLM}}\) |
| 文件存储 | 不考虑事务性存储 | TenantStore 单文件 `atomic_write_text`；无跨记录事务（见 G2-05） |
| 管家通过引擎动手 | 管家不直接写项目文件 | 开发能力取决于委派/DevEngine 质量 |
| PIM 有界 | 每类 PIM 数据有硬上限 | 联系人 ≤ 500、记账 ≤ 5000、备忘 ≤ 200、习惯 ≤ 30 |

---

## 第二章 七层理论细化

### 2.1 L1: WeChat 界面层 — 通道理论

#### 2.1.1 消息到达模型

单 Owner 在会话活跃期以可变速率 \(\lambda(t)\) 发送消息。关键特征是**突发性**——Owner 可能连续发送多条补充指令。

**WeChat 特有约束**：
- 消息到达为异步 push（iLink 长连接）
- 单条文本长度受微信客户端限制（约 4096 字符）
- 图片/文件需额外下载处理时间
- 语音需 STT 转换（当前由微信侧完成）

#### 2.1.2 入站队列模型

定义入站队列状态 \(Q_s\) 为会话 \(s\) 的待处理消息集合，分三个优先级桶：

\[
Q_s = Q_s^{\text{now}} \cup Q_s^{\text{next}} \cup Q_s^{\text{later}}
\]

**入队条件**：当 \(\sigma_s = \text{running}\)（会话忙）且消息非斜杠命令时入队。

**去重机制**：2 秒窗口内相同内容消息被丢弃（`_should_dedupe` 时间戳比对）。

**容量控制**：队列总容量 \(C_q\)（默认 20）。溢出时 `_apply_cap_before_append` 按策略处理（`summarize`/`old`/`new`）。

#### 2.1.3 四种队列模式

| 模式 | 入队行为 | Drain 行为 | 适用场景 |
|------|----------|------------|----------|
| `followup`（默认） | 正常入队 + ACK | 轮次结束逐条 pop | 一般对话 |
| `collect` | 正常入队 | `pop_all_merged` 合并 | 用户连续补充 |
| `interrupt` | 入队前 `loop.interrupt()` | 打断后重新开始 | 紧急指令 |
| `steer` | 不入队，注入运行中 Loop | 实时影响当前轮次 | 运行时指引 |

**命题 2.1（模式完备性）**：消息到达时系统只有两种根本选择——**等还是不等**。等的话，消息之间是**独立还是合并**。不等的话，是**替换当前任务（interrupt）还是修改当前行为（steer）**。四种模式恰好覆盖这棵决策树的四个叶节点。

#### 2.1.4 Admission 单飞

`reply_admission` 使用 per-session 互斥锁实现单飞：

\[
\forall t, \forall s: \quad |\{m \in \text{processing}(s, t)\}| \leq 1
\]

三层串行化保证：Adapter 层 `asyncio.Lock` → Admission 层 `try_admit` → Session Registry 层 `RLock`。

**命题 2.2（无并发轮次）**：同一 `session_key` 不可能有两个并发的 `loop.run()` 调用。

#### 2.1.5 斜杠命令体系

Butler 注册 60+ 条斜杠命令，分布在 9 个命令模块中。命令注册机制：`command_registry.py` 维护 `_REGISTRY` + `_ALIAS_MAP`，`dispatch(ctx)` 解析命令名 → 别名解析 → handler 调用。

**命题 2.3（命令路由确定性）**：每个斜杠命令映射到唯一 handler（或 None fallthrough）。别名解析无歧义（alias→canonical 单射）。

#### 2.1.6 出站可靠性

`durable_outbox` 提供 at-least-once 语义：

\[
\text{write}(m, \text{outbox}) \to \text{send}(m) \to \text{archive}(m, \text{sent})
\]

Crash 后重启可重发 outbox 中未归档的消息。不提供 exactly-once（微信侧可能收到重复）。

**提醒推送**：`reminder.py` 通过 Gateway 轮询循环检查（`BUTLER_REMINDER_POLL_SECONDS`=60s）。到期提醒触发 `outbound_bridge` 推送到微信。一次性提醒 fired 后状态变为 `fired`；周期性提醒自动计算下次触发时间。

**命题 2.4（提醒不丢失）**：在 Gateway 进程持续运行的前提下，所有到期提醒在最多 `POLL_SECONDS` + 处理时间内被发现并推送。

#### 2.1.7 Drain 收敛

**命题 2.5（Drain 终止）**：drain 在最多 `DRAIN_PER_TURN` 步内终止。若 \(\lambda \to 0\)（用户停止发送），队列在有限轮次后清空。

#### 2.1.8 通道中断降级分析（v3.0 新增）

当 iLink 连接中断时，各功能的可用性：

| 功能 | 中断期间 | 恢复后 |
|------|----------|--------|
| 消息收发 | **不可用** | 正常 |
| 定时提醒 | 本地存储不丢失，推送延迟 | 重发未推送的到期提醒 |
| Runtime Job | 继续执行，结果推送延迟 | durable outbox 重放 |
| 进行中 Loop | 正常完成，回复缓存 | 回复通过 outbox 发送 |
| PIM 操作 | 数据写入正常（本地存储） | 正常 |

### 2.2 L2: 管家智能层 — 意图路由理论

#### 2.2.1 LLM 概率预言机模型（v3.0 新增）

将 LLM 显式建模为概率预言机，不假设其内部机制：

\[
\mathcal{O}_{\text{LLM}}: \text{Messages} \times \text{Tools} \to \text{Distribution}(\text{Response})
\]

关键特征：
- **输出非确定性**：相同输入可能产生不同输出
- **能力有界**：存在误差率 \(\epsilon > 0\)，对任意任务 \(\tau\)，\(P(\text{error} | \tau) = \epsilon_\tau > 0\)
- **Schema 遵守度可变**：不同 provider 对 JSON schema 的遵守度 \(\rho \in [0, 1]\) 差异大

#### 2.2.2 意图路由概率模型（v3.0 新增）

用户消息 \(m\) 到工具 \(t\) 的路由建模为条件分布：

\[
P(t | m, \text{sys\_prompt}, \mathcal{T})
\]

路由错误率：

\[
\epsilon_{\text{route}} = 1 - P(t^* | m), \quad t^* = \text{正确工具}
\]

**工具数量对路由质量的影响**：

\[
\frac{\partial \epsilon_{\text{route}}}{\partial |\mathcal{T}|} > 0
\]

工具数量越多，路由错误率越高。这意味着"全能管家"（更多工具）和"可靠路由"（更少选择）之间存在根本张力。

**PIM-Memory 路由歧义分析**：

| 用户指令 | 正确路由 | 常见误路由 | 歧义原因 |
|----------|----------|------------|----------|
| "帮我记一下明天开会" | `memo_add` | `set_reminder` / `butler_remember` | "记"的多义性 |
| "记住我喜欢喝美式" | `butler_remember scope=profile` | `memo_add` | "记住"偏好 vs 备忘 |
| "提醒我明天带伞" | `set_reminder` | `memo_add` | "提醒"有时间触发需求 |

#### 2.2.3 角色模型

管家主循环有两种角色，由 `gateway_loop_role()` 确定：

| 角色 | 触发条件 | 工具集 | 核心行为 |
|------|----------|--------|----------|
| `butler` | 默认 | `_BUTLER_EXTRA_TOOLS`（含 PIM） | 日常管理 + 委派开发 |
| `lead` | `is_lead_project()` 为 True | `_LEAD_EXTRA_TOOLS`（无 PIM） | 项目深度管理 + 厂长模式 |

**命题 2.6（角色确定性）**：对任意项目绑定 \(P\)，`gateway_loop_role(P)` 返回唯一确定的角色。

**命题 2.7（PIM-Dev 分离）**：PIM 操作由管家自身完成，不经委派。开发操作必须经 `delegate_task` 委派或 DevEngine。两条路径在工具注册层面分离。

#### 2.2.4 上下文经济学与 Token 预算

每次 LLM 调用时，上下文窗口 \(W\) 被分配给多个消费者：

\[
W = W_{\text{sys}} + W_{\text{hist}} + W_{\text{tools}} + W_{\text{mem}} + W_{\text{pim}} + W_{\text{reserve}}
\]

**PIM 工具定义的固定成本**（v3.0 量化）：~20 个 PIM 工具的 JSON schema 占用约 2000-4000 tokens。在 128K 窗口中占比 < 3%，为常量成本。当 butler 角色不需要 PIM 能力时（如 lead 角色），这些 token 被释放。

#### 2.2.5 五阶段上下文控制管线

Butler 采用五阶段策略保证上下文不溢出，按「预防-缓解-应急」递进：

**阶段 1 Spill**：大工具结果（超过 `_DEFAULT_SPILL_MIN_CHARS`）落盘，消息内只保留指针。

**阶段 2 Prune**：按工具类型和时间衰减剪枝。`read_file`/`grep` 等可清空旧结果；`patch`/`delegate_task` 保留更长摘要。PIM 工具结果按 `pii_clearable` 策略 2 轮后清空（vs 普通 4 轮）。

**阶段 3 Preemptive Compact**：估算 token 数，按阈值路由到 ok/compact/truncate/overflow_fail。

**阶段 4 Compress**：LLM 辅助压缩，保留头尾消息和关键锚点。压缩后执行 `post_compact_anchors` 重注入（含 MEMORY / 任务 / Skill / AGENTS·DESIGN 节锚点）。

**阶段 5 Reactive Compact**：API 返回 413 后，按轮次粒度丢弃旧对话再压缩重试。

**命题 2.8（五阶段覆盖性）**：五个阶段覆盖从正常到极端的全部上下文压力场景。每一层只处理前一层没有解决的问题。

#### 2.2.6 Agent Loop 状态机

状态集合：

\[
\Sigma = \{\text{RUNNING}, \text{COMPLETED}, \text{TOOL\_LIMIT}, \text{ERROR}, \text{INTERRUPTED}, \text{WAITING\_CONFIRMATION}, \text{STUCK}\}
\]

**命题 2.9（Loop 终止性）**：Agent Loop 在最多 `max_iterations` 步内终止，终态为 \(\Sigma \setminus \{\text{RUNNING}\}\)。

#### 2.2.7 成本模型框架（v3.0 新增）

单次会话的 token 成本：

\[
\text{Cost}(\text{session}) = \sum_{i=1}^{n} \left[ c_{\text{in}}(i) \cdot p_{\text{in}} + c_{\text{out}}(i) \cdot p_{\text{out}} \right]
\]

成本放大因子：
- **PIM 工具定义**：每轮 \(\Delta_{\text{pim}} \approx 3000\) tokens 固定成本
- **委派**：\(n_{\text{delegate}}\) 次委派，每次产生独立的 Loop 成本
- **压缩**：压缩调用消耗辅助模型 token

### 2.3 L3: 个人信息管理层 — PIM 数据理论

#### 2.3.1 TenantStore 模型

PIM 数据存储在 TenantStore 中，路径模式：

```
{BUTLER_HOME}/tenants/{normalize(BUTLER_TENANT)}/{subdir}/{id}.json
```

| PIM 模块 | subdir | 硬上限 | ID 格式 | 环境开关 |
|----------|--------|--------|---------|----------|
| 通讯录 | `contacts` | 500 条 | `uuid4.hex[:10]` | `BUTLER_CONTACTS_ENABLED` |
| 记账 | `expenses` | 5000 条 | `uuid4.hex[:10]` | `BUTLER_EXPENSE_ENABLED` |
| 习惯 | `habits` | 30 条（active） | `uuid4.hex[:10]` | `BUTLER_HABITS_ENABLED` |
| 备忘 | `memos` | 200 条（active） | `uuid4.hex[:10]` | `BUTLER_MEMO_ENABLED` |
| 提醒 | `reminders`* | 100 条（active） | `uuid4.hex[:10]` | — |

*提醒的全局路径迁移至 `{BUTLER_HOME}/tenants/{t}/reminders/`。`MAX_ACTIVE_REMINDERS=100`（`pim_schema.py`）。

#### 2.3.2 PIM 数据有界性分析

每个 PIM 模块的存储量有硬上限：

\[
|\mathcal{I}_{\text{contacts}}| \leq 500, \quad |\mathcal{I}_{\text{expenses}}| \leq 5000, \quad |\mathcal{I}_{\text{memos}}| \leq 200, \quad |\mathcal{I}_{\text{habits}}| \leq 30
\]

单条记录大小约束：联系人备注 ≤ 500 字符、标签 ≤ 10 个；记账描述 ≤ 200 字符；备忘内容 ≤ 2000 字符。

**命题 2.10（TenantStore 有界性）**：TenantStore 总存储量有确定性上界：

\[
|\text{TenantStore}| \leq 500 \times 3\text{KB} + 5000 \times 1\text{KB} + 200 \times 3\text{KB} + 30 \times 1\text{KB} + 30 \times 365 \times 0.3\text{KB} \approx 10.8 \text{ MB}
\]

#### 2.3.3 PIM 分类封闭性

各 PIM 模块有预定义分类枚举。

**命题 2.11（分类封闭性）**：每个 PIM 记录的分类字段受限于预定义枚举集合。非法值回退默认值，无法通过 API 注入自定义分类。

#### 2.3.4 习惯打卡模型

同日重复打卡为累积模式（`count` 递增，`note` 以 `"; "` 连接）。

**命题 2.12（打卡幂等性）**：同一习惯同一天的多次打卡不产生重复记录，而是累积到同一条打卡记录中。

#### 2.3.5 提醒推送模型

| 类型 | 触发后行为 | 状态变迁 |
|------|-----------|----------|
| 一次性 | status → `fired` | 不再触发 |
| 周期性 | `fire_count += 1`，计算下次触发 | 保持 `pending` |

**命题 2.13（周期提醒不堆积）**：周期性提醒每次触发后立即计算下一次触发时间，不会在单次轮询中触发多次。

#### 2.3.6 PIM 隐私泄露路径分析（v3.0 新增）

PIM 数据的隐私泄露路径：

```
PIM 查询 → 结果进入 LLM 上下文 → 可能出现在压缩摘要中
  → 可能被 post-session 提取到 Experience 层
```

**缓解措施**：
1. PIM 工具结果受 Prune `pii_clearable` 策略控制（2 轮后清空，vs 普通 4 轮）
2. `fact_extraction.py` 跳过 PIM 工具结果，防止个人数据进入认知记忆
3. **未解决风险**：压缩摘要中的 PII 残留

### 2.4 L4: 开发引擎层 — 委派与引擎双模型

#### 2.4.1 管家-委派分离原则

委派角色：`dev`（编码/调试）、`content`（文档/文案）、`review`（审查/测试）。

**命题 2.14（管家不写文件）**：管家主循环（role=butler/lead）的运行时工具集不含项目文件修改工具：`_BUTLER_EXTRA_TOOLS` / `_LEAD_EXTRA_TOOLS` 的 frozenset 不含写工具，且 `allowed_tool_names_for_project` 从 `project.yaml` 剥离变异工具（`_BUTLER_BLOCKED_PROJECT_TOOLS`）。管家层对项目文件的修改只能通过 `delegate_task` 间接完成，或通过 DevEngine 在完整安全管线下完成。

#### 2.4.2 委派深度控制

`MAX_DELEGATE_DEPTH = 2`：

\[
\text{Butler}(\text{depth}=0) \to \text{Dev}(\text{depth}=1) \to \text{SubAgent}(\text{depth}=2)
\]

工具集收缩：

\[
\mathcal{T}_{\text{child}} = (\mathcal{T}_{\text{parent}} \cap \mathcal{T}_{\text{allowed}}) \setminus (\mathcal{T}_{\text{blocked}} \cup \mathcal{T}_{\text{deny}})
\]

**命题 2.15（权限单调递减）**：委派链中工具权限严格不增。PIM 工具仅管家主循环拥有。

#### 2.4.3 DevEngine 状态机

开发循环状态集合：

\[
\Sigma_{\text{dev}} = \{\text{PLAN}, \text{LOCATE}, \text{EDIT}, \text{VERIFY}, \text{FIX}, \text{DONE}, \text{STUCK}, \text{REVIEW}\}
\]

FIX→VERIFY 是唯一的循环路径，受 \(K_{\max}\) 限制。STUCK 和 DONE 是终态。完整形式化见 [`v4-dev-engine-theory.md`](v4-dev-engine-theory.md)。

#### 2.4.3b 编码知识层

DevEngine 第九章（v1.4）引入编码知识层，解决"生成的代码为什么是正确的"：

- **定理库 \(\mathcal{T}\)**（T01-T10）：语义层面永恒的编程定理（CA2），每条定理绑定确定性检查器 \(C_\tau\)
- **经验库 \(\mathcal{X}\)**：有时效的最佳实践，入库前必须通过定理验证（CA3a）；Synth 实例化保持性由 H4 保证
- **双重验证门**：定理验证器（结构正确性）+ 测试验证器（功能正确性），严格模式下两者均通过方可输出（CA4）；verify\_skip 路径下 CA4 不适用
- **七元素可组合覆盖**：所有编码任务分解为 DataFlow / ControlFlow / StateManagement / Composition / BoundaryInterface / ErrorHandling / TypeSchema（CA1），元素在触发层面允许重叠
- **规格与合成器**（v1.4 新增）：规格 \(S = (D_S, E_S, C_S)\) 形式化（CD0）；合成器 Synth（CD8）；测试用例生成 GenTC（CD6）
- **组合封闭性**（CL1）：限定于 \(\mathcal{T}_{\text{local}} = \{T05, T06, T08\}\)、单线程、无共享可变状态

核心保证：经验缺失时降级为纯定理推理，定理合规仍保证（CT2，结构正确性，非功能正确）。14 条前提假设（H0-H13），其中 H6/H8/H11 有条件理论确认。详见子理论 §9。

#### 2.4.4 Guardrail 收敛

`tool_guardrails` 检测 doom loop。连续 \(k\) 次相同工具调用且结果相似 → STUCK → Loop 终止。

**命题 2.17（Doom Loop 有界）**：guardrail 在最多 \(k_{\max}\) 次相同失败后终止 Loop。

### 2.5 L5: 项目管理层 — 编排理论

#### 2.5.1 多项目管理

**命题 2.18（项目隔离）**：项目切换改变 \(P\) 和对应的工具集/权限/记忆。Project 域数据项目间隔离。Tenant 域数据（PIM）跨项目共享。

#### 2.5.2 DAG 工作流

`_topological_sort` 使用 Kahn 算法，包含环检测。同层节点可并行（`asyncio.to_thread`）。

**命题 2.19（DAG 终止）**：`execute_graph` 在有限步内完成。

#### 2.5.3 Runtime Jobs

| 属性 | 说明 | 约束 |
|------|------|------|
| `mode` | readonly / mutating | mutating 需审批 |
| `timeout_seconds` | 执行超时 | 默认 900s |
| `schedule` | cron 表达式 | 5 字段标准 cron |
| `approval.expires_hours` | 审批有效期 | 默认 48h |

**命题 2.20（Runtime 安全）**：`mutating` 模式 Job 在未获审批前不执行。审批有 TTL，过期需重新审批。每个 Job 有执行锁，防止并发执行。

### 2.6 L6: 记忆与安全层 — 记忆/权限理论

> 完整记忆子理论（MA1-MA7 公理 / MT1-MT7 定理 / 度量模型）见 [`v4-memory-theory.md`](v4-memory-theory.md)。经验优先 + Skill 兜底检索策略见 [`memory-roadmap.md`](memory-roadmap.md#检索信任级联)（**不改** MA/MT）。

#### 2.6.1 四层记忆模型

\[
\mathcal{K} = \underbrace{\mathcal{K}_{\text{profile}} \cup \mathcal{K}_{\text{experience}}}_{\text{Tenant 域（跨项目）}} \cup \underbrace{\mathcal{K}_{\text{facts}} \cup \mathcal{K}_{\text{project}}}_{\text{Project 域（项目内）}}
\]

| 层 | 域 | 存储 | 写入入口 | 检索方式 |
|----|-----|------|----------|----------|
| Profile | Tenant | JSON | `butler_remember scope=owner_profile` | 精确字段 + 向量 |
| Experience | Tenant | SQLite FTS5 | `butler_remember scope=owner_experience` / post-session | FTS + 向量混合 |
| Facts | Project | JSON | 自动提取 / `butler_remember` | 前缀匹配 |
| Project Memory | Project | MEMORY.md | `butler_remember scope=project_notes` | 章节解析 + 向量 |

#### 2.6.2 混合检索理论

`hybrid_search` 合并 FTS 和向量检索：

\[
\text{score}(d) = \alpha \cdot \text{RRF}_{\text{vector}}(d) + (1 - \alpha) \cdot \text{RRF}_{\text{FTS}}(d)
\]

理论召回率上界：

\[
\text{Recall}_{\text{hybrid}} \leq 1 - (1 - R_{\text{vector}}) \times (1 - R_{\text{FTS}})
\]

#### 2.6.3 记忆注入不污染

**命题 2.22（记忆不污染）**：记忆注入通过 `pre_llm_transform` 回调操作消息副本，不修改 `loop._messages` 或 transcript。这是代码路径的静态保证。

#### 2.6.4 权限模型

**工具权限格**：\((\mathcal{T}, \subseteq)\)，Owner ⊇ 管家 ⊇ 子 Agent。

**PIM 权限隔离**：\(\mathcal{T}_{\text{PIM}} \cap \mathcal{T}_{\text{child}} = \emptyset\)。

**Plan Mode 阻断**：`BUTLER_PLAN_MODE=1` 时阻断所有写操作工具和 mutating MCP 工具。

**命题 2.23（Plan Mode 完备性）**：Plan mode 下，任何修改文件系统或执行外部命令的工具都被阻断。

#### 2.6.5 Read-Before-Edit 一致性

\[
\text{edit}(f) \text{ 成功} \iff \text{mtime}(f) = \text{mtime\_at\_read}(f)
\]

**命题 2.24（编辑冲突检测）**：文件在 `read_file` 和 `patch`/`write_file` 之间被外部修改时，编辑将被拒绝。

### 2.7 L7: 观测演化层 — 评测与反馈理论

> v3.1 新增。LangFuse 与评测体系在工程落地后补入理论；与 L4 DA6（开发步骤 Trace）、L6 度量模型（MB1-MB7）互补，不替代。

#### 2.7.1 训练类比与三层回路

Butler 的长期演化可类比模型训练的三段回路：

| 类比 | Butler 对应 | 实现模块 | 当前成熟度 |
|------|-------------|----------|------------|
| **前向传播** | 理论驱动的代码执行（Loop / DevEngine / 记忆 / 编码知识） | `butler/core/`, `butler/dev_engine/`, `butler/memory/` | ✅ 结构层已落地 |
| **损失计算** | pytest（正确性 SSOT）+ LangFuse（质量趋势 SSOT） | `tests/`, `butler/ops/eval_*` | ✅ CI 基准推送已接；per-turn `eval_turn` 已接 gateway |
| **反向传播** | 评估结果 → 行为/参数调整 | `eval_feedback` / `eval_actions` → `agent_loop`；经验生命周期 | ✅ 软/硬反馈已 opt-in 接入；OT2 收敛待生产验证 |

```
[Owner/微信] → Agent Loop（前向）
                    ↓ traces
              LangFuse（损失观测）
                    ↓ scores
              eval_feedback（软反馈注入）
                    ↓ eval_actions（硬反馈，opt-in）
         经验库 / 衰减参数 / 阈值调优
```

#### 2.7.2 观测演化公理

**公理 OA1（双 SSOT 互补）**：系统质量由两个独立事实源度量，互不替代：
- **pytest**：结构正确性 SSOT（pass/fail，CI 守门）
- **LangFuse**：运行时质量趋势 SSOT（Trace / Score / Dataset，opt-in `BUTLER_LANGFUSE_ENABLED=1`）

\[
\text{Quality} = \text{Correctness}_{\text{pytest}} \times \text{Trend}_{\text{LangFuse}}
\]

两者正交：pytest 保证「不会坏」；LangFuse 观测「是否在变好」。

**公理 OA2（反馈有界性）**：评估反馈不得绕过安全公理：
- 不得修改权限格（A4）、记忆审批门（MA7）、人工门控（T6）
- 软反馈仅通过 `pre_llm_transform` / ephemeral system note 影响当轮 LLM 输入
- 硬反馈（参数调优、经验淘汰）须写入审计日志，阈值可配置

\[
\text{Feedback} \nRightarrow \mathcal{T}_{\text{agent}} \uparrow \quad \land \quad \text{Feedback} \nRightarrow \text{bypass}(Q_{\text{pending}})
\]

**公理 OA3（度量可累积）**：L2 运行时度量（DevEngine `dev_metrics`、Memory `memory_metrics`）与 L3 基准分数（B1–B8、MB1–MB7）构成时间序列，是「靠时间积累变好」的数据前提。

\[
\mathcal{H}_t = \{s_i : t_i \leq t\} \quad \text{where } s_i \in \text{Scores}(\text{LangFuse}) \cup \text{Metrics}(\text{L2})
\]

#### 2.7.3 观测演化定理

**定理 OT1（软反馈有界性）**：`eval_feedback.get_feedback_context()` 注入的文本摘要不改变系统持久状态，仅影响当前 Turn 的 LLM 输入。

**前提**：
- (P-OT1a) 反馈通过 `_turn_ephemeral_system` 注入，不写入 transcript SSOT
- (P-OT1b) 反馈内容来自 LangFuse 只读查询 + 阈值比较，无写操作

**证明**：由 P-OT1a，注入操作与 T4（记忆不污染）同构——操作消息副本/ephemeral 字段，不修改 `_messages` 或 transcript。由 P-OT1b，LangFuse 查询为只读。因此软反馈不改变 \(\mathcal{S}\) 的持久分量。 ∎

**坚实度**：**L1 架构保证**（代码路径静态保证）。

**定理 OT2（硬反馈收敛前提）**：经验生命周期（续期/降权/淘汰）与配置调参（衰减 τ、阈值）在 OA2 约束下构成有界演化，但**收敛性取决于生产数据量**，当前为设计目标而非已证结论。

**前提**：
- (P-OT2a) `ExperienceLibrary.lifecycle_pass()` 每次操作有审计记录
- (P-OT2b) 调参幅度受配置上下界约束（如 τ ∈ [7, 90] 天）
- (P-OT2c) 生产环境 L2 度量接线完整（P_r、R_r、S_f 等）

**状态**：P-OT2a 已实现；P-OT2b/P-OT2c 为 Phase 1–3 实施项。OT2 诚实标注为**有条件理论目标**。

#### 2.7.4 与 DA6 的区分

| 维度 | DA6（L4 开发步骤 Trace） | L7 观测演化 |
|------|-------------------------|-------------|
| 范围 | 单次开发任务的搜索/编辑/验证步骤 | 跨 Turn / 跨会话 / 跨项目的质量趋势 |
| 存储 | DevState 内存 + 结构化 Result | LangFuse + L2 metrics 时间序列 |
| 消费者 | 管家向 Owner 报告进度 | eval_feedback 注入 + CI 回归 + 人工复盘 |
| 反馈类型 | 无（仅观测） | 软反馈（已实现）+ 硬反馈（待实现） |

#### 2.7.5 多项目 LangFuse 共享

LangFuse 实例为**基础设施层共享服务**（`~/gongju/langfuse`，独立于 WFXM），各 Butler 托管项目通过独立 API Key 隔离 Trace：

\[
\text{LangFuse}_{\text{shared}} \xrightarrow{\text{project\_id}} \text{Trace}_{\text{butler-v4}} \cup \text{Trace}_{\text{lingwen}} \cup \cdots
\]

配置存储：`~/.butler/projects/<project_id>/langfuse.json`；tracer 按 `project_id` 动态选择 client。详见 [`langfuse-multi-project.md`](../guides/langfuse-multi-project.md)。

---

## 第三章 形式化建模

### 3.1 管家状态模型 \(\mathcal{S}\)

**定义 3.1（管家会话状态）**：

\[
\mathcal{S} = (\text{SessionKey}, \text{LoopState}, \text{QueueState}, \text{MemoryState}, \text{PIMState}, \text{Role})
\]

其中：
- \(\text{SessionKey} = \text{platform} \times \text{chat\_id} \times \text{project}\)
- \(\text{LoopState} = (H, \sigma, i, W)\)
- \(\text{QueueState} = (Q^{\text{now}}, Q^{\text{next}}, Q^{\text{later}}, \text{mode})\)
- \(\text{MemoryState} = (\mathcal{K}_{\text{profile}}, \mathcal{K}_{\text{experience}}, \mathcal{K}_{\text{facts}}, \mathcal{K}_{\text{project}})\)
- \(\text{PIMState} = (\mathcal{I}_{\text{contacts}}, \mathcal{I}_{\text{expenses}}, \mathcal{I}_{\text{memos}}, \mathcal{I}_{\text{habits}}, \mathcal{I}_{\text{reminders}})\)
- \(\text{Role} \in \{\text{butler}, \text{lead}\}\)

**定义 3.2（LoopStatus 转移函数）**：

\[
\delta: \Sigma \times \text{Event} \to \Sigma
\]

| 当前状态 | 事件 | 目标状态 |
|----------|------|----------|
| RUNNING | tool_call 成功 | RUNNING |
| RUNNING | tool_call → PIM 操作成功 | RUNNING（PIMState 更新） |
| RUNNING | tool_call → waiting | WAITING_CONFIRMATION |
| RUNNING | tool_call → stuck | STUCK |
| RUNNING | text_response 完整 | COMPLETED |
| RUNNING | text_response 截断 | RUNNING（注入续写） |
| RUNNING | interrupt | INTERRUPTED |
| RUNNING | LLM error | ERROR |
| RUNNING | iteration >= max | TOOL_LIMIT |

### 3.2 通道模型 \(\mathcal{C}\)

**定义 3.3（WeChat 通道约束）**：

\[
\mathcal{C}_{\text{wechat}} = (\text{msg\_len\_limit}, \text{media\_types}, \text{serial}, \text{async})
\]

**定义 3.4（入站通道）**：

\[
\mathcal{C}_{\text{in}} = (\text{Arrive}, \text{Classify}, \text{Admit}, \text{Queue}, \text{Dispatch})
\]

\[
\text{Arrive}(m) \to \begin{cases}
\text{slash\_cmd}(m) & \text{if } m \text{ 以 `/` 开头} \\
\text{Dispatch}(m, s) & \text{if } \sigma_s = \text{idle} \wedge \text{Admit}(s) \\
\text{Queue}(m, s, \text{mode}) & \text{if } \sigma_s = \text{running}
\end{cases}
\]

**定义 3.5（出站通道）**：

\[
\mathcal{C}_{\text{out}} = (\text{Reply}, \text{Supplementary}, \text{Reminder}, \text{Completion})
\]

### 3.3 LLM 预言机模型（v3.0 新增）

**定义 3.6（LLM 概率预言机）**：

\[
\mathcal{O}_{\text{LLM}}: \text{Messages} \times \text{Tools} \to \text{Distribution}(\text{Response})
\]

**定义 3.7（意图路由函数）**：

\[
\text{Route}: \text{Message} \times \text{SysPrompt} \times \mathcal{T} \to \text{Distribution}(\mathcal{T})
\]

\[
\epsilon_{\text{route}}(m) = 1 - P(t^* | m, \text{sys}, \mathcal{T}), \quad \frac{\partial \epsilon_{\text{route}}}{\partial |\mathcal{T}|} > 0
\]

### 3.4 TenantStore 模型 \(\mathcal{I}\)

**定义 3.8（TenantStore）**：

\[
\mathcal{I} = \bigcup_{m \in \text{PIM\_MODULES}} \mathcal{I}_m, \quad |\mathcal{I}_m^{\text{active}}| \leq N_m^{\max}
\]

| 模块 \(m\) | \(N_m^{\max}\) | \(S_m^{\max}\) (估计) | 唯一键 |
|-----------|-------------|-------------------|--------|
| contacts | 500 | ~3 KB | `id` (uuid4.hex[:10]) |
| expenses | 5000 | ~1 KB | `id` (uuid4.hex[:10]) |
| memos | 200 (active) | ~3 KB | `id` (uuid4.hex[:10]) |
| habits | 30 (active) | ~1 KB | `id` (uuid4.hex[:10]) |
| reminders | 100 (active)* | ~0.5 KB | `id` (uuid4.hex[:10]) |

**不变量 3.1（PIM 有界性）**：\(\forall m \in \{\text{contacts}, \text{expenses}, \text{memos}, \text{habits}\}: |\mathcal{I}_m^{\text{active}}| \leq N_m^{\max}\)。超限时拒绝新增。

### 3.5 扩展点模型 \(\mathcal{E}\)

**定义 3.9（扩展接口）**：

\[
\mathcal{E} = \mathcal{E}_{\text{MCP}} \cup \mathcal{E}_{\text{Runtime}} \cup \mathcal{E}_{\text{Registry}}
\]

\[
|\mathcal{E}_{\text{MCP}}^{\text{servers}}| \leq 20 \text{ (硬上限)}, \quad \sum_s |\text{Tools}(s)| \leq 100 \text{ (硬上限)}
\]

实际默认限制更紧：`MAX_SERVERS=3`, `MAX_TOOLS=20`。

**不变量 3.2（扩展隔离）**：所有扩展工具共享同一 dispatch/permission/hook/approval 管线，不旁路内建安全管线。

### 3.6 上下文模型 \(\mathcal{X}\)

**定义 3.10（上下文预算）**：

\[
\mathcal{X} = (W, \text{Pack}, \text{Compress}, \text{Spill}, \text{Prune})
\]

**不变量 3.3（上下文不溢出）**：\(\forall \text{api\_call}: \text{tokens}(\text{Pack}(H)) \leq W - W_{\text{reserve}}\)

### 3.7 权限模型 \(\mathcal{P}\)

**定义 3.11（工具权限格）**：\((\mathcal{T}, \subseteq)\)，Owner ⊇ 管家 ⊇ 子 Agent。

**定义 3.12（PIM 权限隔离）**：\(\mathcal{T}_{\text{PIM}} \cap \mathcal{T}_{\text{child}} = \emptyset\)

**定义 3.13（信息流等级）**：\(\text{Level} = \{\text{auto}, \text{gated}\}\)。不存在从 `gated` 到 `auto` 的路径，除非经过 Owner 确认。

### 3.8 记忆模型 \(\mathcal{M}\)

> 完整形式化见 [`v4-memory-theory.md`](v4-memory-theory.md) 第二章（定义 M1-M10）。

**定义 3.14（记忆检索函数）**：

\[
\text{Retrieve}(q, \mathcal{K}) = \text{rerank}(\text{FTS}(q, \mathcal{K}) \cup \text{Vector}(q, \mathcal{K}))
\]

**定义 3.15（记忆注入变换）**：

\[
\text{Inject}: H \times \text{Hits} \to H'
\]

\(\text{Inject}\) 操作 \(H\) 的副本，不修改原始 transcript。

**不变量 3.4（注入幂等性）**：对同一轮次，\(\text{Inject}\) 只执行一次。

### 3.9 成本模型 \(\mathcal{C}_{\$}\)（v3.0 新增）

**定义 3.16（会话成本）**：

\[
\text{Cost}(s) = \sum_{i=1}^{n} \left[ c_{\text{in}}(i) \cdot p_{\text{in}} + c_{\text{out}}(i) \cdot p_{\text{out}} \right] + \sum_{j=1}^{d} \text{Cost}(\text{delegate}_j)
\]

**固定成本分析**：每轮 \(\Delta_{\text{tools}} \approx W_{\text{pim}} + W_{\text{core}}\) tokens 的工具定义是不随对话长度增长的固定成本。

### 3.10 编排模型 \(\mathcal{O}\)

**定义 3.17（工作流 DAG）**：

\[
\mathcal{O} = (G, \text{Schedule}, \text{Spawn}, \text{Approve})
\]

\[
\forall v \in V: \text{can\_execute}(v) \iff \forall (u, v) \in E: \text{completed}(u) \wedge (\neg v.\text{requires\_approval} \vee \text{Approve}(v))
\]

---

## 第四章 三角色评审（v3.0 重构）

### 4.1 架构师视角

**批评 1：意图路由是系统最薄弱环节**

理论中将意图路由简化为 LLM 自行决定，但实际是将用户自然语言映射到 ~64 个工具的分类问题。工具数量增长导致路由质量下降是根本性张力。

**修补**：引入意图路由概率模型（§2.2.2 / 定义 3.7）。承认 \(\partial \epsilon_{\text{route}} / \partial |\mathcal{T}| > 0\)，并将 P-PIM 意图路由准确率列为高优先级待验证前提。

**批评 2：PIM 工具定义的固定成本未量化**

**修补**：§2.2.4 量化 PIM 工具定义 token 占用（~2000-4000 tokens, < 3%）。角色机制（butler vs lead）提供粗粒度优化。

**批评 3：单进程 Job 调度的资源竞争**

**修补**：声明为已知边界（§1.5）。当前单进程下 Runtime Job 使用 `try_acquire_lock` 防止并发执行。

### 4.2 安全研究员视角

**批评 4：PIM 数据存储未加密**

TenantStore 使用明文 JSON。服务器入侵时所有 PIM 数据暴露。

**修补**：在能力边界（§7.1）中声明风险。Backlog 中已有 `secrets.yaml Fernet 加密` 项。

**批评 5：自由文本字段的注入攻击面**

PIM 工具的自由文本字段（通讯录备注、备忘内容）可能被注入恶意 prompt，在后续检索时污染 LLM 上下文。

**修补**：`_reject_injection` 检查记忆内容是否包含 injection 模式。分类枚举封闭性只防止枚举值注入，自由文本字段的消毒覆盖度需要工程验证。列为待验证前提。

**批评 6：durable outbox 重放可能导致 Owner 困惑**

**修补**：at-least-once 的产品影响已在 §2.1.6 声明。"操作确认"类消息的重复发送是已知行为。

### 4.3 产品经理视角

**批评 7：成本模型完全缺失**

**修补**：引入成本模型框架（§2.2.7 / 定义 3.16）。PIM 固定成本、委派放大因子、压缩辅助消耗已建模。具体数值需工程实测。

**批评 8：WeChat 通道中断降级策略**

**修补**：§2.1.8 新增通道中断降级分析，明确各功能在中断期间的可用性。

**批评 9：PIM 数据分析能力未建模**

PIM 聚合查询（"上月餐饮花费"）依赖 `expense_summary` 工具已有实现。复杂趋势分析依赖 LLM 对工具结果的理解能力，属于 LLM 预言机的应用范畴。

### 4.4 评审修补汇总

| # | 批评 | 严重度 | 修补措施 | 状态 |
|---|------|--------|----------|------|
| 1 | 意图路由未建模 | **高** | §2.2.2 引入路由概率模型 | ✅ 已修补 |
| 2 | PIM 工具固定成本 | 中 | §2.2.4 量化 | ✅ 已修补 |
| 3 | 单进程 Job 调度 | 低 | §1.5 声明边界 | ✅ 已修补 |
| 4 | PIM 存储未加密 | 中 | §7.1 风险声明 | ✅ 已修补 |
| 5 | 自由文本注入 | **高** | P-INJ 待验证前提 | ⚠️ 待工程验证 |
| 6 | outbox 重放 | 低 | §2.1.6 声明 | ✅ 已修补 |
| 7 | 成本模型缺失 | 中 | §2.2.7 / 定义 3.16 | ✅ 已修补 |
| 8 | 通道中断降级 | 中 | §2.1.8 可用性矩阵 | ✅ 已修补 |
| 9 | PIM 数据分析 | 低 | 已有 expense_summary 等工具 | ✅ 已有子集 |

---

## 第五章 形式化定理证明

### 定理 T1：上下文不溢出

**陈述**：在五阶段上下文控制管线正常运行的前提下，任何发送给 LLM API 的消息序列的 token 数不超过上下文窗口 \(W\)。

**前提**：
- (P-T1a) token 估算函数 \(\hat{T}\) 的误差有界——英文接近 1:1，中文低估约 50%（FINDING-1）
- (P-T1b) 压缩函数使得 \(T(\text{Compress}(H)) < T(H)\)
- (P-T1c) `overflow_fail` 在估算超限时正确触发
- (P-T1d) PIM 工具定义 token 占用为常量 \(W_{\text{pim}} \leq C_{\text{pim}}\)

**证明**：

1. Spill 保证单工具结果不无限膨胀：\(|r'| \leq \max(\theta_{\text{spill}}, |\text{ptr}|)\)。
2. Prune 只减不增：\(T(\text{Prune}(H)) \leq T(H)\)。
3. Preemptive Compact 三路路由保证要么压缩、要么截断、要么中止。
4. Reactive Compact 作为 API 413 的后备。
5. PIM 工具定义 token 占用为常量，不随对话增长。

**关于 FINDING-1 的影响**：中文内容低估约 50% 意味着纯中文长对话可能延迟触发 preemptive compact。但 `threshold_ratio=0.5` 提供 2x 安全裕度，且 reactive compact 作为最终兜底。

**坚实度**：**L4（LLM 依赖）**。英文场景中等可靠；中文场景依赖安全裕度。 ∎

---

### 定理 T2：队列收敛

**陈述**：在 `followup` 模式下，若用户最终停止发送新消息（\(\lambda \to 0\)），队列中所有消息最终被处理。

**前提**：(P-T2a) Agent Loop 在有限步内终止；(P-T2b) `DRAIN_PER_TURN` > 0；(P-T2c) 处理后不重入队列。

**证明**：\(|Q_{t_{\text{last}} + \lceil|Q_{t_{\text{last}}}|/\text{DRAIN}\rceil}| = 0\)

**坚实度**：**L2（数学保证）**。 ∎

---

### 定理 T3：权限不可提升

**陈述**：在委派链中，子 Agent 的可用工具集是父 Agent 工具集的子集。PIM 工具不传递给任何子 Agent。

**前提**：(P-T3a) `DELEGATE_BLOCKED_TOOLS` 和 `_DEFAULT_SUBAGENT_DENY` 正确维护；(P-T3b) `dispatch_tool` 使用权限检查；(P-T3c) `MAX_DELEGATE_DEPTH = 2`。

**证明**：
1. \(\mathcal{T}_{\text{child}} = (\mathcal{T}_{\text{parent}} \cap \mathcal{T}_{\text{allowed}}) \setminus (\mathcal{T}_{\text{blocked}} \cup \mathcal{T}_{\text{deny}}) \subseteq \mathcal{T}_{\text{parent}}\)
2. PIM 工具在 `_BUTLER_EXTRA_TOOLS` 中。子 Agent 工具集不包含 PIM 工具。
3. 归纳：\(\mathcal{T}_{A_d} \subseteq \ldots \subseteq \mathcal{T}_{A_0}\)，且 \(\forall i \geq 1: \mathcal{T}_{\text{PIM}} \cap \mathcal{T}_{A_i} = \emptyset\)。

**坚实度**：**L3（配置保证）**。已通过 17 项工程测试验证。 ∎

---

### 定理 T4：记忆不污染

**陈述**：记忆注入操作不修改 transcript SSOT，Tenant 域记忆不被 Project 域操作覆盖。

**前提**：(P-T4a) `pre_llm_transform` 操作消息副本；(P-T4b) transcript 写入不经过 `pre_llm_transform`。

**证明**：
1. `prepare_messages_for_api` 返回独立副本。
2. `pre_llm_transform` 操作该副本，不影响 `loop._messages`。
3. Transcript 写入操作 `loop._messages`，不经 `pre_llm_transform`。两条路径在代码中物理分离。
4. Tenant 域路径 `~/.butler/tenants/{t}/` 与 Project 域路径 `{workspace}/.butler/` 不重叠。

**坚实度**：**L1（架构保证）**——代码路径静态保证，不依赖 LLM。 ∎

---

### 定理 T5：DAG 终止

**陈述**：`TaskOrchestrator.execute_graph` 在有限步内完成。

**前提**：(P-T5a) DAG 无环；(P-T5b) 每节点 `max_retries` 有限；(P-T5c) 每次 `spawn_agent` 有限步内返回；(P-T5d) `max_replan` 有限。

**证明**：总步数上界：\(\sum_{v \in V} R_v \times \text{max\_iterations} < \infty\)。

**坚实度**：**L2（数学保证）**。 ∎

---

### 定理 T6：信息流安全

**陈述**：需要审批的工作流步骤和 mutating Runtime Job 在 Owner 确认前不自动执行。

**前提**：(P-T6a) `requires_approval: true` 正确标注；(P-T6b) 审批检查返回 False 时步骤不执行；(P-T6c) 确认仅在 `is_gateway_owner` 时处理；(P-T6d) Runtime Job `mutating` 模式需审批且有 TTL。

**证明**：
1. 工作流：`approved=False` 时 `spawn_agent` 不被调用。
2. Runtime：未审批 `mutating` Job 返回 REJECTED。
3. 只有 Owner 可确认。审批有 `expires_hours` TTL（默认 48h）。

**坚实度**：**L1（架构保证）**。 ∎

---

### 定理 T7：PIM 数据有界性

**陈述**：每个 PIM 模块的活跃记录数不超过其硬编码上限。

**前提**：(P-T7a) `_MAX_*` 常量在创建时检查；(P-T7b) 超限返回错误。

**证明**：各创建函数在写入前检查活跃记录数。\(|\mathcal{I}_m^{\text{active}}| \geq N_m^{\max}\) 时返回错误。内容字段被 `strip()[:limit]` 截断。

总存储上界 ≤ 10.8 MB。提醒上限 `MAX_ACTIVE_REMINDERS=100`（`pim_schema.py`），已纳入 PIM 有界性保证。

**坚实度**：**L2（数学保证 + 代码路径）**。 ∎

---

### 定理 T8：管家-委派分离

**陈述**：管家主循环（role=butler/lead）不直接调用项目文件修改工具。

**前提**：(P-T8a) `_BUTLER_EXTRA_TOOLS` 不含写工具；(P-T8b) 系统提示指示管家不直接动手；(P-T8c) `_LEAD_EXTRA_TOOLS` 同样不含写工具；(P-T8d) `allowed_tool_names_for_project(project, role∈{butler,lead})` 从 `project.yaml` 映射中剔除 `_BUTLER_BLOCKED_PROJECT_TOOLS`（`write_file`/`patch`/`delete_file`/`terminal` 等）。

**证明**：运行时允许集 \(\mathcal{T}_{\text{runtime}} = f(\text{mapped}) \cup \mathcal{T}_{\text{extra}}\)，其中 \(f\) 剔除变异工具，\(\mathcal{T}_{\text{extra}}\) 为角色 extra frozenset 且本身不含写工具。即使 LLM 尝试调用，dispatch 因工具不在 loop 定义集合中而失败。DevEngine 模式下管家通过内置引擎在完整安全管线下操作（`role=dev` 路径不受本条限制）。

**坚实度**：**L3（配置保证 + 提示引导）**。 ∎

---

### 定理 T9：编辑可回滚（v3.0 从子理论提升）

**陈述**：DevEngine 的任意编辑序列可通过 EditHistory 完全撤销，恢复到编辑前的文件状态。

**前提**：(P-T9a) 每个编辑记录 undo 操作；(P-T9b) 原始内容编辑前快照；(P-T9c) 无外部并发修改（单 Owner）。

**证明**：由 undo 定义 \(\text{apply}(\text{undo}(e), \text{apply}(e, \mathcal{F})) = \mathcal{F}\)，逆序回滚恢复原始状态。

**坚实度**：**L1（架构保证）**（单 Owner 无并发时）。 ∎

---

### 定理 T10：开发循环终止（v3.0 从子理论提升）

**陈述**：开发循环在有限步内终止于 DONE、STUCK 或 REVIEW。

**前提**：(P-T10a) 总迭代上限 \(I_{\max}\)；(P-T10b) 修复循环上限 \(K_{\max}\)。

**证明**：进度度量 \(\mu = I_{\max} - i + K_{\max} - k\) 严格递减。总步数 \(\leq I_{\max} \times (1 + K_{\max})\)。

**坚实度**：**L2（数学保证）**。 ∎

---

## 第六章 工程前提验证

### 6.1 已完成的前提验证矩阵

原 166 个测试继承自 v2.1 基线，DevEngine 56 个测试 + 集成 35 个测试，v3.0 新增 77 个结构性前提验证 + 10 个 LLM-in-loop 实测 + 实施方案落地 26 个验证测试 + DevEngine 度量/基准 31 个 + 记忆子理论前提验证 27 个 + 记忆度量/基准 20 个 + 编码知识层前提验证 99 个（v1.4 扩展）。**总计 608+ 个全部通过**。

#### 6.1.1 继承的前提验证（84 tests）

| ID | 前提 | 风险等级 | 状态 | 测试文件 | 结果 |
|----|------|----------|------|----------|------|
| P4 | Queue drain 延迟 ≤ 5s | 低 | **通过** | `test_premise_p4_queue_drain.py` | 13/13 |
| P5 | 权限隔离无漏洞 | 低 | **通过** | `test_premise_p5_permission_isolation.py` | 17/17 |
| P-T1a | Token 估算误差 | 中 | **有条件通过** | `test_premise_pt1a_token_estimation.py` | 18/18 |
| P3 | 记忆检索 Recall | 中 | **通过** | `test_premise_p3_memory_recall.py` | 15/15 |
| P1 | LLM 工具调用（结构） | 高 | **结构通过** | `test_premise_p1_p2_p6_structural.py` | 8/8 |
| P2 | 压缩信息保留（结构） | 中 | **结构通过** | `test_premise_p1_p2_p6_structural.py` | 7/7 |
| P6 | Post-session 提取（结构） | 高 | **结构通过** | `test_premise_p1_p2_p6_structural.py` | 6/6 |

#### 6.1.2 PIM 验证（68 tests）

| ID | 前提 | 状态 | 测试文件 | 结果 |
|----|------|------|----------|------|
| P-T7 | TenantStore 有界性 | **通过** | `test_premise_t7_pim_bounded.py` | 28/28 |
| P-T8 | 管家-委派分离 | **通过** | `test_premise_t8_delegate_separation.py` | 18/18 |
| P-PIM1 | 提醒推送可靠性 | **通过** | `test_premise_pim_reminder.py` | 18/18 |
| P-PIM2 | 打卡幂等性 | **通过** | `test_premise_t7_pim_bounded.py` | 3/3 |
| P-PIM3 | PIM 枚举封闭性 | **通过** | `test_premise_pim_reminder.py` | 5/5 |

#### 6.1.3 扩展点验证（20 tests）

| ID | 前提 | 状态 | 测试文件 | 结果 |
|----|------|------|----------|------|
| P-E1 | MCP dispatch 管线 | **通过** | `test_premise_extension_points.py` | 8/8 |
| P-E2 | MCP 上限生效 | **通过** | `test_premise_extension_points.py` | 9/9 |
| P-E3 | Runtime mutating 审批 | **通过** | `test_premise_extension_points.py` | 3/3 |

#### 6.1.4 DevEngine 验证（91 tests）

| ID | 前提 | 状态 | 测试文件 | 结果 |
|----|------|------|----------|------|
| P-DA1~7 | DevEngine 公理 | **通过** | `test_dev_engine_theory.py` | 56/56 |
| P-DT1~7 | DevEngine 定理 | **通过** | `test_dev_engine_integration.py` | 35/35 |

#### 6.1.5 编码知识层验证（99 tests）

| ID | 前提 | 状态 | 测试文件 | 结果 |
|----|------|------|----------|------|
| P-CA1 | 七元素可组合覆盖性 | **通过** | `test_premise_coding_knowledge.py` | 8/8 |
| P-CA2 | 定理语义不变性（T01-T10） | **通过** | `test_premise_coding_knowledge.py` | 9/9 |
| P-CA3 | 经验入库准确性 + 时效性 | **通过** | `test_premise_coding_knowledge.py` | 6/6 |
| P-CA4 | 双重验证闭合（含空集防护） | **通过** | `test_premise_coding_knowledge.py` | 5/5 |
| P-CT1 | 全定理合规/违规（T01-T10） | **通过** | `test_premise_coding_knowledge.py` | 22/22 |
| P-CL1 | 组合封闭性（含负面测试） | **通过** | `test_premise_coding_knowledge.py` | 5/5 |
| P-CT2 | 经验降级无害性（端到端） | **通过** | `test_premise_coding_knowledge.py` | 4/4 |
| P-CT3 | 经验替换安全性（含入库验证） | **通过** | `test_premise_coding_knowledge.py` | 4/4 |
| P-CT4 | 测试覆盖补充 | **通过** | `test_premise_coding_knowledge.py` | 3/3 |
| P-CT5 | 联合保证 | **通过** | `test_premise_coding_knowledge.py` | 2/2 |
| P-CD5 | 激活函数（归一化+基线注入） | **通过** | `test_premise_coding_knowledge.py` | 8/8 |
| P-CD7 | 知识处理管线（含严格覆盖） | **通过** | `test_premise_coding_knowledge.py` | 5/5 |
| P-H6 | 规格解析确定性（有条件确认） | **通过** | `test_premise_coding_knowledge.py` | 3/3 |
| P-H8 | 组合封闭性（有条件确认） | **通过** | `test_premise_coding_knowledge.py` | 3/3 |
| P-H11 | 测试环境可靠（有条件确认） | **通过** | `test_premise_coding_knowledge.py` | 3/3 |
| P-H13 | 验证器确定性 | **通过** | `test_premise_coding_knowledge.py` | 2/2 |
| 经验库操作 | CRUD + 搜索 + 排序 + 严格过滤 | **通过** | `test_premise_coding_knowledge.py` | 7/7 |


### 6.2 已发现的工程事实

#### FINDING-1: 中文 Token 估算低估（P-T1a）

`_estimate_tokens()` 使用 `len(json.dumps(m, ensure_ascii=False)) // 4`。中文字符低估约 50%。缓解：`threshold_ratio=0.5` + reactive compact。

#### FINDING-2: HashingEmbedder Recall 限制（P3）

HashingEmbedder 是确定性哈希嵌入器，Recall@3 ≈ 50-67%。生产环境应配置 API 嵌入器。

### 6.3 v3.0 新增前提验证（77 结构 + 10 LLM-in-loop = 87 tests）

#### 6.3.1 结构性验证（77 tests，`test_premise_v3_new.py`）

| ID | 前提 | 结构性验证 | 状态 | 测试数 |
|----|------|-----------|------|--------|
| **P-PIM** | PIM 意图路由准确率 | Prompt 路由表完整性 + 允许列表一致性 + 领域映射覆盖 | **通过** | 9/9 |
| **P-INJ** | 自由文本注入防护完备性 | Memory 注入拦截 + PIM 闭集归一化 + Prefetch 过滤 + 评分梯度 + 长度限制 | **通过** | 22/22 |
| P-COST | 成本模型准确性 | 计数器正确性 + 工具分类 + 会话管理 + 非调度性断言 | **通过** | 14/14 |
| P1-LIVE | LLM 工具调用结构性 | Schema 规范性 + 净化管线 + enum 一致性 + PIM happy path | **通过** | 13/13 |
| P6-LIVE | Post-session 提取结构性 | 事实模式提取 + PIM 跳过 + 持久化/去重/锚点 + watermark + 短对话跳过 | **通过** | 19/19 |

#### 6.3.2 LLM-in-loop 实测（10 tests，`test_premise_v3_llm_live.py`，env-gated `live_llm`）

| ID | 前提 | Provider | 测试数据 | 实测结果 | 可证伪标准 | 状态 |
|----|------|----------|----------|----------|-----------|------|
| **P-PIM** | 意图路由准确率 | MiniMax (M2.7) | 50 条指令 | **94.0%** (47/50) | < 85% | **✅ 通过** |
| **P-PIM** | 意图路由准确率 | DeepSeek (chat) | 50 条指令 | **90.0%** (45/50) | < 85% | **✅ 通过** |
| **P1-LIVE** | 工具调用 parse | MiniMax (M2.7) | 20 条指令 | **100.0%** (20/20) | < 90% | **✅ 通过** |
| **P1-LIVE** | 工具调用 parse | DeepSeek (chat) | 20 条指令 | **100.0%** (20/20) | < 90% | **✅ 通过** |
| **P6-LIVE** | Heuristic 事实提取覆盖率 | — | 10 段 transcript | **100.0%** (10/10) | < 80% | **✅ 通过** |
| **P6-LIVE** | Heuristic 事实类型精度 | — | 10 段 transcript | **91.7%** (22/24) | < 80% | **✅ 通过** |
| **P6-LIVE** | PIM 结果跳过 | — | PIM 工具输出 | **100%** 跳过 | 任一泄露 | **✅ 通过** |
| **P6-LIVE** | Post-session LLM 提取 | MiniMax (M2.7) | 1 段 transcript | **可调用** | 崩溃 | **✅ 通过** |
| **P6-LIVE** | Post-session LLM 提取 | DeepSeek (chat) | 1 段 transcript | **可调用** | 崩溃 | **✅ 通过** |

**P-PIM 路由错误分析**（供后续优化参考）：

| Provider | 典型误路由 | 模式 |
|----------|-----------|------|
| MiniMax | "打卡" → 无工具调用 | 省略动作识别不足 |
| 共同 | "memo_update" → `memo_search` | 缺少上下文（无 memo_id）时回退查询 |
| DeepSeek | `habit_stats` → `habit_list` | 同模块工具区分度不够 |
| DeepSeek | `list_reminders` → `reminder_list_active` | 语义近似导致选择变体 |

> **结论**：两个 provider 的路由准确率均超过 85% 阈值（MiniMax 94%、DeepSeek 90%），**无需引入显式分类器**。建议的优化方向：在系统提示中增加更多同模块工具间的消歧示例（如 `habit_checkin` vs `habit_stats`）。

### 6.4 验证方法学守则

1. **GT 独立性**：标注者不应是设计者本人
2. **样本代表性**：测试用例必须反映真实使用场景
3. **多模型交叉验证**：关键前提在至少 2 个 provider 上测试
4. **诚实报告**：实测数据推翻假设时修正理论
5. **方法学优先**：验证方案的设计比验证的执行更重要

---

## 第七章 能力边界与扩展性声明

### 7.1 三支柱能力边界

#### PIM 支柱

| 边界 | 量化估计 | 验证状态 | 缓解 |
|------|----------|----------|------|
| 联系人/记账/备忘/习惯上限 | 500/5000/200/30 | **P-T7 通过** | 超限拒绝 |
| 打卡幂等性 | 同日累积 | **P-PIM2 通过** | count 累加 |
| 提醒推送 | 周期不堆积 | **P-PIM1 通过** | 自动重调度 |
| 枚举封闭性 | 无注入 | **P-PIM3 通过** | 非法值回退默认 |
| PIM 意图路由准确率 | MiniMax 94% / DeepSeek 90% | **全部通过**（结构 9/9 + LLM 2/2） | 系统提示示例引导 |
| PII 泄露风险 | 压缩摘要中可能残留 | 未解决 | Prune 清空 + fact 跳过 |
| PIM 存储加密 | 默认明文 JSON | opt-in 可启用 | `BUTLER_PIM_ENCRYPT=1` + Fernet（D7） |

#### Dev 支柱

| 边界 | 量化估计 | 验证状态 | 缓解 |
|------|----------|----------|------|
| 委派深度 | MAX=2 | P5 通过 | 深度超限拒绝 |
| 管家不写文件 | 运行时 allowlist | **P-T8 通过** | extra frozenset + project.yaml 剥离变异工具 |
| 编辑可回滚 | 完全撤销 | **P-DT5 通过** | EditHistory + undo |
| Dev 循环终止 | I_max × (1+K_max) | **P-DT2 通过** | 有限常数 |
| 开发质量上限 | 取决于 LLM | 未量化 | 验证循环 + failover |

#### PM 支柱

| 边界 | 量化估计 | 验证状态 | 缓解 |
|------|----------|----------|------|
| DAG 终止 | 数学保证 | T5 证明 | 有限节点 × 有限重试 |
| Runtime 审批 TTL | 默认 48h | **P-E3 通过** | 未审批 mutating 拒绝 |
| MCP 上限 | 3/20 (默认), 20/100 (硬上限) | **P-E2 通过** | 硬编码 |

### 7.2 基础设施边界

| 边界 | 量化估计 | 验证状态 | 缓解 |
|------|----------|----------|------|
| 队列 drain 延迟 | < 100ms/10 msgs | P4 通过 | O(1) 桶操作 |
| Token 估算精度 | 英文 ~1.0x；中文 CJK×1.3 启发式（v3.1 修正） | P-T1a 通过 | reactive compact 兜底 |
| 记忆检索 Recall | HashingEmbedder Recall@3 ≈ 50-67% | P3 基线通过 | API 嵌入器 |
| 观测演化闭环 | LangFuse opt-in；软/硬反馈已接 | OT1 通过；OT2 待生产验证 | `butler-deploy.sh langfuse` |
| WeChat 通道中断 | 不可用 | 无备选通道 | durable_outbox 恢复 |
| 单点故障 | 进程崩溃 = 中断 | — | systemd 重启 |
| 成本模型 | 框架 + D4 落盘/汇总 | **结构通过**（P-COST 14/14）；账单 baseline 对照待 A5 | `cost_calibration` + `/成本` |

### 7.3 理论适用条件

本理论基线在以下条件下成立：

1. **单 Owner 部署**：不适用于多用户/多租户
2. **单进程运行**：不适用于分布式部署
3. **LLM 基本可用**：至少一个 provider 可响应
4. **WeChat 通道可用**：iLink 连接正常
5. **文件系统可靠**：本地磁盘不故障
6. **PIM 数据在硬上限内**：未被外部程序直接修改

### 7.4 诚实声明

1. **LLM 行为的前提（P1/P2/P6/P-PIM）已完成结构性验证（77 tests）+ LLM-in-loop 实测（10 tests）**。PIM 路由准确率 MiniMax 94% / DeepSeek 90%，工具调用 parse 率 100%，事实提取覆盖率 100%（精度 91.7%）。两个 provider 均超过可证伪阈值。

2. ~~**Token 估算对中文内容存在已知低估（FINDING-1）**~~ **已缓解（v3.1）**：CJK 估算从 `cjk/1.5` 修正为 `cjk×1.3`，实测 ratio 落入 0.8–2.5 区间。极端长文仍依赖 reactive compact。

3. **HashingEmbedder 基线 Recall 有限（FINDING-2）**。生产环境必须配置 API 嵌入器。

4. **PIM 数据在 LLM 上下文中的隐私风险未完全解决**。Prune `pii_clearable` 策略和 fact 跳过提供缓解，但压缩摘要中的 PII 残留是未解决风险。

5. **管家"全能"承诺受限于 LLM 能力上界和意图路由质量**。工具数量增加会降低路由准确率（\(\partial \epsilon_{\text{route}} / \partial |\mathcal{T}| > 0\)）。

6. **成本模型结构性正确性已验证（14 tests）**；D4 事件落盘与 N 日汇总已接入，**账单 baseline 对照（A5）仍待人工完成**。PIM 固定成本 + 委派放大因子的累计影响需持续观测。

7. **WeChat 通道中断时完全不可用**。无备选交互通道，但 durable outbox 保证恢复后补发。

8. **自由文本字段的注入防护结构性已验证（22 tests）**。Memory 写入注入拦截 + PIM 闭集归一化 + Prefetch 过滤 + 对抗标记 + 长度限制均通过。但 PIM content/notes 自由文本字段未做 `_reject_injection` 调用，仅靠长度截断防护——这是已知设计取舍（避免误拦合法内容）。

9. ~~提醒无硬上限~~ **已修复**：`MAX_ACTIVE_REMINDERS=100`（`pim_schema.py`），`tool_set_reminder` 在写入前检查活跃数，超限拒绝。提醒已纳入 PIM 有界性不变量。

10. **观测演化层（L7）软/硬反馈已 opt-in 接入（v3.1.1 对齐）**。`eval_feedback` 注入 agent loop（OT1）；`eval_turn` per-turn 评分经 gateway `locked_phases` 推送 LangFuse；`eval_actions.apply_hard_feedback` 可调记忆半衰期/经验降权（`BUTLER_EVAL_HARD_FEEDBACK`）。L2 度量（`memory_metrics` prefetch/fact 接线）已生产路径采集。**OT2 收敛性仍为有条件目标**，须长期生产数据验证。LangFuse 默认 opt-in，生产须显式启用。

11. **「靠时间变好」的前提部分满足（v3.1.1 对齐）**。持续积累路径：(a) 成功 `delegate` → `extract_experience_candidate` → `coding_experiences.json`；(b) `delegate_phases` → `process_task` / `format_coding_guidance_block`（Synth/GenTC 约束注入）；(c) `/经验挖掘` 或 CLI 手动挖掘（**无自动调度**）；(d) `eval_actions` 硬反馈调参。缺口：经验挖掘 cron、OT2 收敛证明。

---

## 附录 A：定理坚实度分级

| 等级 | 定义 | 本文定理 |
|------|------|----------|
| **L1 架构保证** | 代码路径静态保证，不依赖 LLM | T4（记忆不污染）、T6（信息流安全）、T9（编辑可回滚） |
| **L2 数学保证** | 仅依赖有限常数和数学性质 | T2（队列收敛）、T5（DAG 终止）、T7（PIM 有界）、T10（Dev 终止） |
| **L3 配置保证** | 依赖配置文件/工具集的正确维护 | T3（权限不升级）、T8（管家-委派分离） |
| **L4 LLM 依赖** | 依赖未验证的 LLM 能力假设 | T1（上下文不溢出） |
| **L1 架构保证（观测）** | 软反馈不改变持久状态 | OT1（软反馈有界性） |
| **有条件目标** | 需生产数据验证 | OT2（硬反馈收敛前提） |

## 附录 B：符号表

| 符号 | 含义 |
|------|------|
| \(\mathcal{G}, \mathcal{L}, \Pi, \mathcal{M}, \mathcal{A}\) | Gateway、Loop、Pillars（三支柱）、Memory、Authority |
| \(\Pi_I, \Pi_D, \Pi_P\) | PIM 支柱、Dev 支柱、PM 支柱 |
| \(\mathcal{O}_{\text{LLM}}\) | LLM 概率预言机 |
| \(H\) | 消息历史（transcript） |
| \(W\) | 上下文窗口大小（tokens） |
| \(\sigma\) | 会话运行状态 |
| \(R\) | 当前角色（butler/lead） |
| \(Q_s\) | 会话 \(s\) 的入站队列 |
| \(\lambda\) | 消息到达率 |
| \(\epsilon_{\text{route}}\) | 意图路由错误率 |
| \(\theta_{\text{spill}}\) | Spill 阈值 |
| \(\mathcal{T}_{\text{PIM}}\) | PIM 工具集（管家专有） |
| \(\mathcal{T}_{\text{blocked}}\) | 委派阻断工具集 |
| \(\text{MAX\_DELEGATE\_DEPTH}\) | 最大委派深度（= 2） |
| \(N_m^{\max}\) | PIM 模块 \(m\) 的最大记录数 |
| \(S_m^{\max}\) | PIM 模块 \(m\) 的单条记录最大大小 |
| \(\mathcal{E}\) | 扩展接口集合 |
| \(K_{\max}\) | DevEngine 修复循环上限 |
| \(I_{\max}\) | DevEngine 总迭代上限 |
| \(\mathcal{C}_{\$}\) | 成本模型 |

## 附录 C：版本变更记录

### C.1 v3.1 → v3.1.1（2026-06-09，实现同步补丁）

| 变更项 | v3.1 | v3.1.1 | 变更原因 |
|--------|------|--------|----------|
| 公理 A2 | 「无 CLI」 | Owner 微信 vs 运维 CLI 二分 | 与 `butler.main` 运维路径对齐；不改变 M2 |
| 定理 T8 | 前提 P-T8a–c | 增 P-T8d runtime allowlist | `project_tools._butler_allowed_tools` 工程落地 |
| §2.7.1 成熟度 | 硬反馈/per-turn 待接 | 已 opt-in 接入 | L7 工程状态同步 |
| §7.4 #10–#11 | L7/积累路径未接 | 部分满足 + 缺口明示 | 与 Phase O/D 路线图一致 |
| 附录 D | — | L7/D4/经验挖掘映射 | 代码-理论映射补全 |

> **证明链不变**：公理 A1–A7、定理 T1–T10、OA1–OA3 证明正文未改；仅前提补全（P-T8d）与陈述性成熟度更新。

### C.2 v3.0 → v3.1（2026-06-09）

| 变更项 | v3.0 | v3.1 | 变更原因 |
|--------|------|------|----------|
| 理论层数 | 六层（L1–L6） | 七层（L1–L7） | LangFuse 评测闭环需形式化 |
| 观测演化 | 未建模 | OA1-OA3 + OT1-OT2 | 补齐「损失计算 / 反向传播」理论 |
| FINDING-1 | 中文 Token 低估 | CJK×1.3 已缓解 | `context_compressor.py` 修正 |
| 诚实声明 | 9 条 | 11 条（+L7 状态、积累前提） | 与实现对齐 |
| 子理论引用 | L4/L6 | L4/L6/L7 | 编码知识层 + 观测层交叉引用 |

### C.3 v2.1 → v3.0

| 变更项 | v2.1 | v3.0 | 变更原因 |
|--------|------|------|----------|
| 系统定义 | 六元组 \((\mathcal{W}, \mathcal{I}, \mathcal{D}, \mathcal{P}, \mathcal{M}, \mathcal{A})\) | 五元组 \((\mathcal{G}, \mathcal{L}, \Pi, \mathcal{M}, \mathcal{A})\) | 区分基础设施/业务/横切层 |
| 核心矛盾 | M1'-M6' 六矛盾平列 | 三元张力 → 推导六矛盾 | 更本质的理论框架 |
| LLM 建模 | 隐式假设 | 概率预言机 \(\mathcal{O}_{\text{LLM}}\) | 显式化 LLM 依赖 |
| 意图路由 | 未建模 | 路由概率模型 + 工具数量影响分析 | 评审发现最薄弱环节 |
| 成本模型 | 缺失 | 定义 3.16 会话成本框架 | 评审发现缺失 |
| 通道中断 | 仅声明不可用 | §2.1.8 降级分析矩阵 | 评审要求明确各功能可用性 |
| 定理数量 | 8 条（T1'-T8'） | 10 条（T1-T10） | T9/T10 从子理论提升 |
| L1+L2 保证 | 5 条 | 7 条 | 更多核心性质有强保证 |
| 评审方法 | 单一自审 | 三角色模拟评审 | 覆盖更多维度 |
| 发现盲区 | 5 个 | 9 个 | 架构师/安全/产品三视角 |
| PII 缓解 | Prune 清空旧结果 | + pii_clearable 策略 + fact 跳过 | Sprint 3 工程落地 |
| 会话状态 | 六维 | 八维（增加 \(i\), \(R\)） | 更完整的状态描述 |
| 待验证前提 | 0 条新增 | 5 条新增（P-PIM/P-INJ/P-COST/P1-LIVE/P6-LIVE） | 推导暴露的验证缺口 |

## 附录 D：代码-理论映射表

| 理论概念 | 代码路径 |
|----------|----------|
| 管家角色路由 | `butler/project/lead.py` → `gateway_loop_role()` |
| PIM 工具注册 | `butler/tools/builtin_register.py` → 各 `register_*_tools` |
| TenantStore | `butler/tools/contacts.py`, `expense.py`, `habits.py`, `memo.py` |
| PIM Schema 集中 | `butler/tools/pim_schema.py` |
| 提醒推送 | `butler/tools/reminder.py` + gateway poll loop |
| 委派分离（提示） | `butler/prompts/butler_system.md` §任务委派规则 |
| 委派分离（工具集） | `butler/tools/project_tools.py` → `_BUTLER_EXTRA_TOOLS` + `_butler_allowed_tools()` |
| L7 per-turn 评分 | `butler/ops/eval_turn.py` → `butler/gateway/locked_phases.py` |
| L7 硬反馈 | `butler/ops/eval_actions.py` → `butler/core/agent_loop_phases.py` |
| 经验挖掘 | `butler/memory/experience_mining.py` + `/经验挖掘` |
| D4 成本标定 | `butler/ops/cost_calibration.py` + `/成本` |
| MCP 扩展点 | `butler/mcp/config.py`, `registry_hook.py`, `manager.py` |
| MCP 安全 | `butler/mcp/security.py` |
| Runtime Jobs | `butler/runtime/schema.py`, `service.py`, `runner.py` |
| Tenant/Project 分层 | `~/.butler/tenants/{t}/` vs `{workspace}/.butler/` |
| Agent Loop 状态机 | `butler/core/agent_loop.py` |
| 上下文管线 | `butler/core/context_pipeline.py` |
| 消息队列 | `butler/gateway/message_queue.py` |
| 斜杠命令体系 | `butler/gateway/command_registry.py` + `commands/*.py` |
| 记忆预取 | `butler/session/memory_prefetch.py` |
| 混合检索 | `butler/memory/semantic_index.py` |
| 委派策略 | `butler/delegate/policy.py` |
| DAG 编排 | `butler/task_orchestrator.py` |
| 人工门控 | `butler/human_gate.py` |
| Durable Outbox | `butler/gateway/durable_outbox.py` |
| 成本追踪 | `butler/ops/cost_tracker.py` |
| PII 缓解 | `butler/core/tool_prune_policy.py` (`pii_clearable`) |
| Fact 提取 PIM 跳过 | `butler/core/fact_extraction.py` |
| DevEngine 状态机 | `butler/dev_engine/dev_loop.py` |
| 编辑操作代数 | `butler/dev_engine/edit_ops.py` |
| 分层验证 | `butler/dev_engine/verify.py` |
| OpenCode 扩展点 | `butler/extensions/opencode.py` |
| **工程前提验证** | |
| P4 队列收敛 | `tests/test_premise_p4_queue_drain.py` (13 tests) |
| P5 权限隔离 | `tests/test_premise_p5_permission_isolation.py` (17 tests) |
| P-T1a Token 估算 | `tests/test_premise_pt1a_token_estimation.py` (18 tests) |
| P3 记忆检索 | `tests/test_premise_p3_memory_recall.py` (15 tests) |
| P1/P2/P6 结构性 | `tests/test_premise_p1_p2_p6_structural.py` (21 tests) |
| P-T7 PIM 有界性 | `tests/test_premise_t7_pim_bounded.py` (28 tests) |
| P-T8 管家-委派分离 | `tests/test_premise_t8_delegate_separation.py` (18 tests) |
| P-PIM 提醒/枚举封闭 | `tests/test_premise_pim_reminder.py` (18 tests) |
| **v3.0 结构性前提** | `tests/test_premise_v3_new.py` (77 tests) |
| **v3.0 LLM-in-loop** | `tests/test_premise_v3_llm_live.py` (10 tests, `live_llm` gate) |
| P-E 扩展点安全 | `tests/test_premise_extension_points.py` (22 tests) |
| P-DA/DT DevEngine | `tests/dev_engine/test_dev_engine_theory.py` (56 tests) |
| P-DT 集成 | `tests/dev_engine/test_dev_engine_integration.py` (35 tests) |
| V4 详设回归 | `tests/test_v4_design_regression.py` (17 tests) |
| P-CA/CT 编码知识层 | `tests/test_premise_coding_knowledge.py` (99 tests) |
| **L7 观测演化** | |
| LangFuse Tracer | `butler/ops/langfuse_tracer.py` |
| Eval Bridge | `butler/ops/eval_bridge.py` |
| Eval Feedback | `butler/ops/eval_feedback.py` |
| Eval Scoring | `butler/ops/eval_scoring.py` |
| 软反馈注入 | `butler/core/agent_loop_phases.py` |
| CI 基准推送 | `.github/workflows/ci.yml` (eval-push job) |
| 多项目 LangFuse | `butler/config.py::get_project_langfuse_config` |
| LangFuse 栈 | `~/gongju/langfuse/ops.sh`；Butler 客户端 `langfuse_tracer.py` |
| 观测指南 | `docs/guides/evaluation-guide.md`, `langfuse-multi-project.md` |
