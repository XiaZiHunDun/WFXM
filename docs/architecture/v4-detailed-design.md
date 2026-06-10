# Butler v4 详细设计方案 — 三支柱管家架构

> 版本 2.2 | 2026-06-07
> 基于 `v4-theoretical-baseline.md` v3.0（10 定理 / 7 公理 / 608+ 验证测试）
> 理论方法：三元张力分解 → 五元组形式化 → LLM 概率预言机 → 十定理证明体系
> 子理论详设：L4 开发引擎见 `v4-dev-engine-theory.md` 第五章；L6 记忆系统见 `v4-memory-theory.md` 第五章
> **可复用** 的现有技术方案标注为 **[复用]**

---

## 1. 系统总架构

### 1.1 五元组到六层映射

理论基线 v3.0 将系统定义为五元组 $(\text{Gateway}, \text{Loop}, \text{Pillars}, \text{Memory}, \text{Authority})$。工程上映射到六层架构：

```
┌─────────────────────────────────────────────────────────┐
│ L1  WeChat 界面层    [Gateway]                          │
│     Adapter · Pipeline · CmdRouter · MsgQueue · Outbox  │
│     ReminderPoll · OutboundBridge · Typing · MediaInbound│
├─────────────────────────────────────────────────────────┤
│ L2  管家智能层       [Loop]                             │
│     AgentLoop · CtxPipeline(5阶段) · IntentRouter       │
│     ToolDispatch · RoleResolver · Guardrail · CostTracker│
├─────────────────────────────────────────────────────────┤
│ L3  PIM 层           [Pillars.PIM]                      │
│     TenantStore · Contacts · Memo · Expense · Habits    │
│     Reminder · PIMSchema · PIMState                     │
├─────────────────────────────────────────────────────────┤
│ L4  开发引擎层       [Pillars.Dev]                      │
│     DelegateEngine · DevEngine(PLAN→EDIT→VERIFY→FIX)    │
│     SubAgentMgr · PermFilter · EditHistory              │
├─────────────────────────────────────────────────────────┤
│ L5  项目管理层       [Pillars.PM]                       │
│     ProjectRegistry · WorkflowDAG · RuntimeJobs         │
│     ProjectTodos · MultiProjectOverview                 │
├─────────────────────────────────────────────────────────┤
│ L6  记忆与安全层     [Memory + Authority]               │
│     MemoryFacade · SemanticIdx · FactExtraction         │
│     PermModel · HumanGate · InjectionGuard · PostSession│
└─────────────────────────────────────────────────────────┘
```

### 1.2 设计原则（源自公理 A1–A7 + 设计原则 P1–P6）

| 公理/原则 | 工程映射 | 验证手段 |
|-----------|----------|----------|
| **A1 Owner 唯一性** | `is_gateway_owner` 一票通过，无 ACL | P5 权限隔离 (17 tests) |
| **A2 WeChat 即产品** | 所有 UX 围绕微信文本/斜杠命令 | 运营巩固轨道 |
| **A3 管家不动手** | L2 不含写工具，写操作经 L4 委派或 DevEngine | T8 管家-委派分离 (14 tests) |
| **A4 权限单调递减** | `allowed_tools ⊆ parent_tools` | P5 (17 tests) |
| **A5 双域隔离** | Tenant 域 `~/.butler/tenants/` vs Project 域 `{ws}/.butler/` | T4 记忆不污染 |
| **A6 记忆分层** | Profile → Experience → Project 三级 | 架构保证 |
| **A7 能力可插拔** | MCP / Runtime / Registry 三扩展口共享安全管线 | P-E1~E3 (22 tests) |
| **P1 架构保证 > LLM 承诺** | 安全性靠代码路径，不靠 prompt | L1/L2 坚实度定理 |
| **P2 显式记忆** | 全部记忆操作可审计 | post-session + fact extraction |
| **P3 容错 > 完美** | at-least-once outbox, doom loop guard | durable_outbox + guardrail |

### 1.3 三元张力模型驱动的架构权衡

v3.0 理论基线识别的核心矛盾：**全能管家承诺** vs **微信单通道约束** vs **LLM 能力上界**。

| 张力 | 工程缓解 | 详设节 |
|------|----------|--------|
| M1: 多领域 vs 单通道 | 斜杠命令路由 + 意图分类 + 角色切换 | §2, §3 |
| M2: 结构化 PIM vs 自然语言 | 闭集枚举 + 自由文本长度限制 + 注入防护 | §4 |
| M3: 记忆容量 vs 上下文窗口 | 五阶段上下文管线 + fact extraction + 分级 prune | §3.3 |
| M4: 安全 vs 灵活 | 声明式权限 + human gate + 只读默认 | §7 |
| M5: 路由质量 vs 工具数量 | 系统提示路由表 + 核心工具 pinning + tool_selector | §3.2 |
| M6: 成本 vs 能力 | 成本观测器 + PIM 固定成本量化 + 角色粒度优化 | §3.5 |

---

## 2. L1: WeChat 界面层

### 2.1 模块职责

| 模块 | 职责 | 定理映射 |
|------|------|----------|
| **WeChat Adapter** | iLink 长连接管理、消息收发、媒体下载 | — |
| **Admission Controller** | per-session 单飞锁 + 会话注册 | — |
| **Message Pipeline** | 消息预处理管线（sanitize → inject-guard → rewrite → dispatch） | T6（审批前不执行） |
| **Command Router** | 斜杠命令注册/别名解析/分发 | — |
| **Message Queue** | 三桶优先级队列 + 四种模式（followup/collect/interrupt/steer） | T2（队列收敛） |
| **Durable Outbox** | 出站消息持久化 + at-least-once 投递 | — |
| **Reminder Poller** | 定时提醒轮询 + 出站推送 | P-PIM1（不堆积） |
| **Outbound Bridge** | typing、进度、委派完成的运行时补充回复 | — |
| **Injection Pipeline** | 入站注入风险评估 + 对抗标记 | P-INJ（22 tests） |
| **Media Inbound** | 图片/语音识别管线（VLM + STT） | — |

### 2.2 关键设计决策

**D-L1-1: 统一出站接口** **[复用]**。所有出站路径统一为 `Adapter.send(chat_id, content, kind)` 单一出口。

**D-L1-2: 消息管线阶段化** **[复用]**。保留 `message_pipelines.py` 多阶段设计，将注入防护提升为独立阶段。

**D-L1-3: 队列模式完备性** **[复用]**。四种模式覆盖完整调度语义空间（命题 2.1），已通过 P4 验证 (13 tests)。

**D-L1-4: 入站注入防护三层体系**（v2.0 新增）：
```
Layer 1: _reject_injection() 正则匹配 → 拦截已知 prompt-injection 模式
Layer 2: score_injection_risk() 风险评分 0–100 → 梯度警告
Layer 3: mark_adversarial_user_text() 对抗标记 → LLM 上下文安全提示
```
已通过 P-INJ 验证（22 tests，含 5 种注入 payload + 评分梯度 + 零误报）。

**D-L1-5: 通道中断降级矩阵**（v2.0 新增）：

| 功能 | WeChat 可用 | WeChat 中断 |
|------|-------------|-------------|
| PIM 操作 | ✅ | ❌ 完全不可用 |
| 开发委派 | ✅ | ❌ |
| 提醒推送 | ✅ | ❌ 暂存 outbox |
| Runtime 执行 | ✅ | ✅ 后台执行，结果暂存 |
| 记忆写入 | ✅ | ❌ |

---

## 3. L2: 管家智能层

### 3.1 模块职责

| 模块 | 职责 | 定理保证 |
|------|------|----------|
| **Agent Loop** | LLM 调用循环、7 状态机转移、中断处理 | T2（队列收敛） |
| **Context Pipeline** | 五阶段上下文控制（Spill→Prune→Preemptive→Compress→Reactive） | T1（不溢出） |
| **Intent Router** | 系统提示驱动的意图分类（PIM/Dev/PM/Direct） | P-PIM（MiniMax 94%/DeepSeek 90%） |
| **Tool Dispatch** | 统一工具分发 + 权限检查 + 审计 | T3（权限不升级） |
| **Role Resolver** | butler/lead 角色判定 → 工具集选择 | T8（管家-委派分离） |
| **Guardrail Controller** | doom loop 检测、stuck 判定 | — |
| **Cost Tracker** | 会话成本观测（仅观测，不调度） | P-COST（14 tests） |
| **Tool Selector** | LLM 辅助工具子集选择（工具数 > 12 时激活） | — |
| **Fact Extraction** | 压缩前结构化事实提取 + 压缩后重注入 | P6-LIVE（100% 覆盖） |

### 3.2 意图路由设计（v2.0 新增深化）

理论基线 v3.0 引入意图路由概率模型：

$$\epsilon_{\text{route}} = P(\text{LLM selects wrong tool} | \text{user intent}) \quad \text{其中} \quad \frac{\partial \epsilon_{\text{route}}}{\partial |\mathcal{T}|} > 0$$

工程缓解措施（三层路由体系）：

| 层次 | 机制 | 代码位置 |
|------|------|----------|
| **L-R1: 系统提示路由表** | 歧义消歧规则（记一下→memo_add, 提醒我→set_reminder, 记住我→butler_remember） | `butler/prompts/butler_system.md` |
| **L-R2: 核心工具 Pinning** | PIM 写入工具 always visible，不被 tool_selector 裁剪 | `butler/core/tool_selector.py::_CORE_TOOLS` |
| **L-R3: 角色-工具集隔离** | butler 可见 PIM + 委派；lead 不可见 PIM；dev 不可见 PIM + 委派 | `butler/tools/project_tools.py` |

**实测验证**：50 条真实中文指令 × 2 provider，MiniMax 94.0%，DeepSeek 90.0%，均超过 85% 阈值。

### 3.3 五阶段上下文管线 **[复用]**

```
Spill(大结果落盘) → Prune(分级剪枝) → Preemptive(估算路由) → Compress(LLM压缩) → Reactive(413重试)
```

v2.0 增强：
- **Fact Extraction 锚点**：压缩前提取决策/完成/偏好/文件变更事实，压缩后重注入。已验证 100% 覆盖率，91.7% 类型精度。
- **PIM 结果 pii_clearable**：PIM 工具结果 2 轮后清空，不进入 post-session 提取。

### 3.4 角色-工具集绑定

```python
butler_tools = base_tools ∪ ALL_PIM_TOOLS ∪ {delegate_task, memory_tools, runtime_tools}
lead_tools   = base_tools ∪ {delegate_task, memory_tools, runtime_tools}  # 无 PIM
dev_tools    = project_rw_tools  # 无 PIM、无 delegate、无 runtime
```

**完整性保证**：`ALL_PIM_TOOLS` (26 工具) ⊆ `_BUTLER_EXTRA_TOOLS`，已通过 P-PIM 结构性验证。

### 3.5 成本模型（v2.0 新增）

$$\text{Cost}(\text{session}) = \sum_{i=1}^{n} \left[ c_{\text{in}}(i) \cdot p_{\text{in}} + c_{\text{out}}(i) \cdot p_{\text{out}} \right]$$

| 组件 | 代码 | 分类 |
|------|------|------|
| SessionCost 数据类 | `butler/ops/cost_tracker.py` | PIM / Dev / PM / Other 四分类 |
| 工具调用记录 | `butler/core/tool_batch.py::_on_complete` | 自动分类 |
| 用量标准化 | `butler/transport/usage_normalize.py` | 跨 provider 统一 |
| 观测接口 | `/成本` 斜杠命令 | 仅观测，不影响调度 |

已验证：26 种 PIM 工具正确分类，负 token 数拒绝，空工具名归类 other（P-COST 14 tests）。

---

## 4. L3: PIM 层

### 4.1 模块职责

| 模块 | 职责 | 定理保证 | 硬上限 |
|------|------|----------|--------|
| **TenantStore** | 租户级 JSON 文件存储引擎 | T7（有界性） | — |
| **Contacts** | 通讯录 CRUD + 搜索 | T7 | ≤ 500 |
| **Memo** | 备忘 CRUD + 搜索 + 状态流转 | T7 | ≤ 200 active |
| **Expense** | 记账 CRUD + 时段聚合 | T7 | ≤ 5000 |
| **Habits** | 习惯打卡 + 连续天数 + 完成率 | T7 + P-PIM2（幂等） | ≤ 30 active |
| **Reminder** | 提醒设置/取消 + cron 支持 + 轮询 | P-PIM1（不堆积） | 无硬上限* |
| **PIMSchema** | 枚举常量 + 上限定义 + 工具名集合 | P-PIM3（封闭性） | — |
| **PIMState** | 域映射 + 使用追踪 | P-PIM | — |

### 4.2 关键设计决策

**D-L3-1: TenantStore 引擎统一** **[复用]**。所有 PIM 模块通过统一引擎执行 CRUD。

**D-L3-2: PIM 枚举集中** **[复用]**。`pim_schema.py` 为唯一枚举源，工具 schema 的 enum 值与之一致（P1-LIVE 验证通过）。

**D-L3-3: 注入防护三级策略**（v2.0 细化）：

| 防护层 | 目标 | 机制 | 验证 |
|--------|------|------|------|
| **枚举封闭** | category/priority/status/direction/frequency | 非法值 → 默认值 | P-PIM3 (5 tests) + P-INJ (7 tests) |
| **长度截断** | content/name/notes/description | `strip()[:MAX_*]` | P-INJ (3 tests) |
| **Memory 注入拦截** | ProfileStore/ExperienceStore 写入 | `_reject_injection()` 正则 | P-INJ (7 tests) |

> **已知取舍**：PIM 自由文本字段（content/name/message）不调用 `_reject_injection`，仅靠长度截断。避免误拦合法内容（如"忽略之前的备忘"）。

**D-L3-4: PIM 上下文注入策略** **[复用]**。PIM 结果 2 轮后 `pii_clearable` 清空，fact extraction 跳过 PIM 工具结果。

**D-L3-5: 自然语言时间解析** **[复用]**。支持「30分钟后」「明天9点」「每天」「工作日」等模式。

### 4.3 存储上界分析

$$|\text{TenantStore}| \leq 500 \times 3\text{KB} + 5000 \times 1\text{KB} + 200 \times 3\text{KB} + 30 \times 1\text{KB} + 30 \times 365 \times 0.3\text{KB} \approx 10.8 \text{ MB}$$

---

## 5. L4: 开发引擎层

### 5.1 DevEngine 状态机（v2.0 提升为一等设计）

理论基线 v3.0 将 DevEngine 的两个核心定理（T9 编辑可回滚、T10 开发循环终止）提升为主理论。

```
PLAN → LOCATE → EDIT → VERIFY → [PASS] → DONE
                                → [FAIL] → FIX → (k ≤ K_max)
                                              → VERIFY
```

| 状态 | 职责 | 安全保证 |
|------|------|----------|
| PLAN | 分析任务、制定编辑计划 | — |
| LOCATE | 定位目标文件/函数 | read_before_edit |
| EDIT | 执行文件修改 | T9: EditHistory 记录 undo |
| VERIFY | 运行验证命令 | DA3: 验证策略配置 |
| FIX | 修复验证失败 | T10: k ≤ K_max 保证终止 |
| DONE | 任务完成 | — |

### 5.2 关键设计决策

**D-L4-1: 委派-管家分离** **[复用]**。管家不含写工具，DevEngine 在完整安全管线下操作。

**D-L4-2: 编辑可回滚** **[复用]**。每个编辑记录完整 undo 操作，逆序回滚恢复原始状态（T9，91 tests）。

**D-L4-3: 开发循环有界终止**。进度度量 $\mu = I_{\max} - i + K_{\max} - k$ 严格递减，总步数 $\leq I_{\max} \times (1 + K_{\max})$（T10）。

**D-L4-4: OpenCode 扩展点** **[架构预留]**。推荐 MCP 桥接模式。

### 5.3 编码知识层（v2.2 新增）

> 理论来源：`v4-dev-engine-theory.md` 第九章（CA1-CA4 / CT1-CT5）

编码知识层回答"生成的代码**为什么**是正确的"，与 §5.1 的引擎机械层（"引擎如何安全运行"）互补。

**核心组件**：

| 组件 | 模块 | 理论映射 |
|------|------|---------|
| 七元素分解器 | `coding_knowledge.decompose_task` | CA1 + CD1 |
| 定理库（T01-T10） | `coding_knowledge.TheoremLibrary` | CA2 + CD2/CD3 |
| 经验库 | `coding_knowledge.ExperienceLibrary` | CA3 + CD4 |
| 激活函数 | `coding_knowledge.TheoremLibrary.activate` | CD5 |
| 双重验证门 | `coding_knowledge.dual_verify` | CA4 + CD6 |
| 知识处理管线 | `coding_knowledge.process_task` | CD7 |

**设计决策**：

**D-L4-5: 定理库为永恒知识** **[新增]**。T01-T10 由人类专家形式化，跨语言/框架恒久成立。定理约束在代码生成后由独立验证器检查（CT1），不依赖 LLM 推理能力。

**D-L4-6: 经验为可进化最佳实践** **[新增]**。经验有有效期和定理基础（$B_x$），入库前必须通过定理验证器全量检查（CT3）。经验缺失时系统降级为纯定理推理，仍保证逻辑正确（CT2）。

**D-L4-7: 双重验证门** **[新增]**。程序输出必须同时通过定理验证（结构正确性）和测试验证（功能正确性，复用 V1-V5）。定理保证骨架，测试填充血肉。

**D-L4-8: 知识层嵌入 DevLoop** **[新增]**。PLAN 阶段激活定理 + 检索经验；EDIT 阶段使用经验模板；VERIFY 阶段扩展为双重验证门；FIX 阶段区分定理违规（结构修复）和测试失败（功能修复）。

---

## 6. L5: 项目管理层

**D-L5-1: 多项目注册协议** **[复用]**。支持本地路径和 Git URL。

**D-L5-2: Runtime 安全模型** **[复用]**。mutating Job 需 Owner 审批（T6 信息流安全）。

**D-L5-3: Workflow DAG 有限常数**。最大节点数 ≤ 50，最大并行度 ≤ 5（T5 DAG 终止）。

**D-L5-4: 项目级持久待办** **[复用]**。Session-scoped todos + 项目级 todos。

---

## 7. L6: 记忆与安全层

> 子理论详设：[`v4-memory-theory.md`](v4-memory-theory.md) 第五章

### 7.1 模块职责

| 模块 | 职责 | 定理保证 | 子理论映射 |
|------|------|----------|-----------|
| **MemoryFacade** | 统一记忆入口（Profile/Experience/Project 三层） | T4（记忆不污染） | MA1+MT1（写入原子性） |
| **SemanticIdx** | 向量检索（HashingEmbedder / API Embedder） | — | MA2+MT2（检索完备性） |
| **RetrievalRanking** | 衰减 + 访问加权 rerank | — | MA5+MT5（衰减单调性） |
| **RecallLayers** | 多层渐进式召回（index→timeline→fetch） | — | M4（多层检索模型） |
| **FactExtraction** | 压缩前事实提取（决策/完成/偏好/文件变更） | P6-LIVE（100%/91.7%） | M10（事实提取模型） |
| **PostSession** | 会话结束双通道提取（记忆 + 技能） | P6-LIVE | M10 |
| **InjectionGuard** | 三层注入防护（正则 + 评分 + 对抗标记） | P-INJ（22 tests） | MA4+MT4（注入透明性） |
| **MemoryCaps** | 分层容量上限 + 截断 | — | MA6+MT6（容量有界性） |
| **Reindex** | 从 Store 重建向量索引 | — | MT1+MT7（原子性+持久化） |
| **PermModel** | 声明式权限 + 只读默认 | T3（权限不升级） | — |
| **HumanGate** | Owner 审批门控 | T6（信息流安全） | MA7（安全写入门控） |
| **MemoryMetrics** | 运行时效果度量采集 | — | §6 度量模型 |

### 7.2 关键设计决策

**D-L6-1: 记忆注入不污染 SSOT** **[复用]**。`pre_llm_transform` 操作消息副本，不影响 transcript（T4 + MT4）。

**D-L6-2: Post-session 双通道提取** **[复用]**。

| 通道 | 提取内容 | 存储目标 |
|------|----------|----------|
| 记忆通道 | 用户偏好 → ProfileStore；项目事实 → ProjectMemory；经验 → ExperienceStore | 三层记忆 |
| 技能通道 | 可复用工作流 | SkillManager |

**D-L6-3: Fact Extraction 锚点体系**（v2.0 新增）：

| 事实类型 | 提取模式 | 存活验证 |
|----------|----------|----------|
| 决策 | `决定/结论/确认：...` 正则 | 10/10 transcripts |
| 完成 | `已完成/完成了/已修复...` 正则 | 10/10 transcripts |
| 用户偏好 | `不要/我想/我希望...` 正则 | 10/10 transcripts |
| 文件变更 | tool result `{ok: true, path: ...}` | 10/10 transcripts |

去重：value 集合判定。上限：单 session ≤ 50 条（MA6/P-MT6c）。PIM 工具结果跳过。

**D-L6-4: PII 泄露缓解**。PIM 结果 `pii_clearable` 2 轮清空 + fact extraction 排除 PIM 工具结果。

**D-L6-5: 记忆生命周期** **[v3.0 新增]**。

```
写入路径                             检索路径                          维护路径
─────────                           ─────────                        ─────────
butler_remember                     prefetch_turn_memory              reindex
  → facade._remember()                → recall_layers.dispatch()        → reindex.py
    → scope 路由                        → hybrid_experience_search()   post_session
      → ProfileStore.add()              → search_project_memory()       → LLM 提炼
      → ExperienceStore.add()           → prefix_match_facts()          → _persist_*
      → MarkdownMemory.append()       → retrieval_ranking.rerank()    fact_extraction
    → IndexSync                       → injection_guard.filter()       → 压缩前提取
      → index_experience_row()        → Truncate(C_max)               → 压缩后锚点
      → sync_project_append()         → Fence(<memory-context>)
```

**D-L6-6: 分层容量上限**（MT6 工程映射）：

| 层 | 上限 | 配置项 | 超限行为 |
|----|------|--------|----------|
| Profile | 2000 字符 | `ProfileStore.char_limit` | 拒绝写入 |
| MEMORY.md | 200 行 / 25KB | `BUTLER_MEMORY_MAX_LINES/BYTES` | 截断 + WARNING |
| Session Facts | 50 条 | `_MAX_FACTS_PER_SESSION` | 停止提取 |
| Prefetch 注入 | 3500 字符 | `BUTLER_PREFETCH_TOTAL_MAX_CHARS` | 截断 |
| Experience | 无硬上限 | SQLite FTS5 | prune 机制定期清理 |

**D-L6-7: 效果度量系统**（v3.0 新增）：

| 度量 | 公式 | 采集点 |
|------|------|--------|
| 检索精度 $P_r$ | $\frac{|\text{Prefetch} \cap \text{LLM\_used}|}{|\text{Prefetch}|}$ | `prefetch_turn_memory` + LLM 回复分析 |
| 检索召回 $R_r$ | $\frac{|\text{Prefetch} \cap \text{Relevant}|}{|\text{Relevant}|}$ | `butler_recall` 反馈 |
| 写入存活率 $S_w$ | $\frac{|\text{Write→Recall 成功}|}{|\text{Write}|}$ | `butler_remember` + `butler_recall` |
| Fact 存活率 $S_f$ | $\frac{|\text{FactsPostCompact}|}{|\text{FactsPreCompact}|}$ | `fact_extraction` 前后对比 |
| 衰减误杀率 $E_d$ | 重要记忆因衰减降至阈值以下的比例 | `rerank_memory_hits` |
| 首轮命中率 $H_1$ | 第一次 prefetch 就命中的轮次比例 | `prefetch_turn_memory` |

### 7.3 与子理论的映射验证

| 子理论定理 | 详设保证点 | 坚实度 | 前提验证 |
|-----------|-----------|--------|---------|
| MT1（写入原子性） | D-L6-5 写入路径 + reindex 兜底 | L2 | P-MT1a/b/c（3 tests） |
| MT2（检索完备性） | D-L6-5 检索路径 多策略 | L1+L2 | P-MT2a/b/c（4 tests） |
| MT3（域隔离） | 文件系统路径 + scope 路由 | L1 | P-MT3a/b/c（3 tests） |
| MT4（注入不污染） | D-L6-1 副本操作 + 围栏 | L1 | 继承 T4 |
| MT5（衰减安全） | RetrievalRanking 指数衰减 | L1 | P-MT5a/b（5 tests） |
| MT6（容量有界） | D-L6-6 分层上限 | L2 | P-MT6a/b/c/d（7 tests） |
| MT7（持久化一致性） | JSON + SQLite WAL + reindex | L2 | P-MT7a/b/c/d/e（5 tests） |

---

## 8. 跨层关注点

### 8.1 可观测性

| 命令 | 职责 | 数据源 |
|------|------|--------|
| `/诊断` | 运行时指标 + 系统健康 | `butler/ops/health_report.py` |
| `/成本` | 会话成本概览 | `butler/ops/cost_tracker.py` |
| `/pim` | PIM 数据使用率 | 各 PIM 模块 |
| `/health` | 格式化诊断 | `health_report.py` |

### 8.2 部署模型 **[复用]**

```
[单进程] butler gateway
  ├── WeChat Adapter (asyncio event loop)
  ├── Agent Loop Pool (per-session, LRU 驱逐, max=128)
  ├── Reminder Poller (background task, 60s interval)
  ├── Runtime Scheduler (background task)
  └── MCP Manager (optional, session-scoped, max 3 servers)

存储:
  ~/.butler/                    ← Tenant 域 (PIM + 全局配置 + session facts)
  {workspace}/.butler/          ← Project 域 (记忆 + 权限 + 转录)
  ~/.butler/tenants/{t}/        ← PIM 数据 (contacts/memos/expenses/habits/reminders)
  ~/.butler/session_facts/{s}/  ← 事实锚点 (per-session JSON)
```

### 8.3 LLM 概率预言机约束

v3.0 显式将 LLM 建模为概率预言机 $\mathcal{O}_{\text{LLM}}$。工程含义：

| 约束 | 工程策略 | 已验证 |
|------|----------|--------|
| 工具调用可能失败 | dispatch 兜底 + 结构化错误 | P1-LIVE（100% parse） |
| 意图路由非确定性 | 三层路由体系 + 核心工具 pinning | P-PIM（90-94%） |
| 压缩有损 | fact extraction 锚点 + 多阶段保护 | P6-LIVE（100% 覆盖） |
| Token 估算有偏差 | 安全裕度 + reactive compact | P-T1a（18 tests） |

---

## 9. 与理论基线的映射验证

| 定理 | 架构保证点 | 坚实度 | 验证机制 |
|------|-----------|--------|----------|
| T1 上下文不溢出 | L2 CtxPipeline 五阶段 | L3 | P-T1a (18 tests) |
| T2 队列收敛 | L1 MsgQueue drain | L2 | P4 (13 tests) |
| T3 权限不升级 | L4 PermFilter + L6 PermModel | L1 | P5 (17 tests) + P-T8 (14 tests) |
| T4 记忆不污染 | L6 MemoryPrefetch + transcript 分离 | L1 | 架构保证 |
| T5 DAG 终止 | L5 WorkflowDAG 有限常数 | L2 | 数学保证 |
| T6 信息流安全 | L5 ApprovalStore + L6 HumanGate | L1 | P-E3 (3 tests) |
| T7 PIM 有界性 | L3 TenantStore 硬编码上限 | L2 | P-T7 (28 tests) |
| T8 管家-委派分离 | L2 RoleResolver + L4 工具集分离 | L3 | P-T8 (14 tests) |
| **T9 编辑可回滚** | L4 EditHistory + undo 代数 | L1 | P-DA/DT (91 tests) |
| **T10 开发循环终止** | L4 DevEngine $\mu$ 递减 | L2 | P-DA/DT (91 tests) |
| **MT1-MT7 记忆子理论** | L6 MemoryFacade + SemanticIdx + Ranking | L1-L2 | P-MT (27 tests) |
| **CA1-CA4 / CT1-CT5 编码知识层** | L4 TheoremLibrary + ExperienceLibrary + DualVerify | L1-L2 | P-CA/CT (99 tests) |

---

## 10. 与现有实现的复用/重构判定

| 模块 | 判定 | 理由 | 验证状态 |
|------|------|------|----------|
| Agent Loop 状态机 | **复用** | 7 状态完整 | ✅ |
| 五阶段上下文管线 | **复用** | 全部 5 阶段工作 | ✅ P-T1a |
| 工具注册/分发 | **复用** | registry + dispatch + audit | ✅ P1-LIVE |
| 消息队列 | **复用** | 4 模式 + 3 桶实现 | ✅ P4 |
| TenantStore | **复用** | 各模块已统一 | ✅ P-T7 |
| PIM 工具注册 | **复用** | 26 工具完整暴露 | ✅ P-PIM |
| 提醒系统 | **复用** | Tenant 域 + 推送 API 统一 | ✅ P-PIM1 |
| 系统提示路由表 | **复用** | 路由规则完整 | ✅ P-PIM (94%/90%) |
| Durable Outbox | **复用** | 字段已修复 | ✅ |
| 记忆预取 | **复用** | 端到端工作 | ✅ |
| 注入防护 | **复用** | 三层体系完整 | ✅ P-INJ (22 tests) |
| 成本追踪 | **复用** | 分类正确 + 非调度 | ✅ P-COST (14 tests) |
| Fact Extraction | **复用** | 四类事实提取 | ✅ P6-LIVE |
| Post-session 提取 | **复用** | 双通道 + watermark | ✅ P6-LIVE |
| 委派引擎 | **复用** | 分阶段管线完整 | ✅ |
| DevEngine | **复用** | PLAN→EDIT→VERIFY→FIX | ✅ T9/T10 (91 tests) |
| Runtime Jobs | **复用** | 生产就绪 | ✅ |
| MCP 薄客户端 | **复用** | 设计范围内完整 | ✅ P-E1~E3 |

---

## 附录 A: 验证测试矩阵

| 验证域 | 测试文件 | 测试数 |
|--------|----------|--------|
| P4 队列收敛 | `test_premise_p4_queue_drain.py` | 13 |
| P5 权限隔离 | `test_premise_p5_permission_isolation.py` | 17 |
| P-T1a Token 估算 | `test_premise_pt1a_token_estimation.py` | 18 |
| P3 记忆检索 | `test_premise_p3_memory_recall.py` | 15 |
| P1/P2/P6 结构性 | `test_premise_p1_p2_p6_structural.py` | 21 |
| P-T7 PIM 有界性 | `test_premise_t7_pim_bounded.py` | 28 |
| P-T8 管家-委派分离 | `test_premise_t8_delegate_separation.py` | 14 |
| P-PIM 提醒/枚举 | `test_premise_pim_reminder.py` | 18 |
| **v3.0 结构性前提 + 实施落地** | `test_premise_v3_new.py` | **103** |
| **v3.0 LLM-in-loop** | `test_premise_v3_llm_live.py` | **10** |
| P-E 扩展点安全 | `test_premise_extension_points.py` | 22 |
| DevEngine 公理 | `test_dev_engine_theory.py` | 56 |
| DevEngine 集成 | `test_dev_engine_integration.py` | 35 |
| 编排改进 | `test_orchestration_improvements.py` | 24 |
| V4 详设回归 | `test_v4_design_regression.py` | 17 |
| **记忆子理论前提** | `test_premise_memory_theory.py` | **27** |
| **编码知识层前提** | `test_premise_coding_knowledge.py` | **99** |
| **合计** | | **527+** |
