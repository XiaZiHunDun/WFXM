# Butler v4 — 形式化理论推导文档

> **版本**：2026-06-12（分析包）  
> **SSOT 原文**：[`../v4-theoretical-baseline.md`](../v4-theoretical-baseline.md) v3.1.1 第三–七章 + 附录；[`v4-memory-theory.md`](../v4-memory-theory.md)；[`v4-dev-engine-theory.md`](../v4-dev-engine-theory.md)  
> **差距登记**：[`../../plans/decisions/theory-implementation-gap-register-2026-06.md`](../../plans/decisions/theory-implementation-gap-register-2026-06.md)  
> **读者**：高级模型 — 用于证明链完整性、前提可验证性、诚实边界与 G1–G4 归类审阅

---

## 0. 推导体系总览

### 0.1 定理族谱

```text
父理论（v3.1.1）
├── T1–T10   主定理（上下文、队列、权限、记忆、DAG、门控、PIM、委派、回滚、Dev 终止）
├── OT1–OT2  观测演化（L7）
├── 公理 A1–A7、OA1–OA3
└── 前提 P-*   工程可验证前提

记忆子理论（v1.2）
├── 公理 MA1–MA7
├── 定理 MT1–MT7
└── 基准 MB1–MB7、前提 P-MT*

开发引擎子理论（v1.5）
├── 公理 DA1–DA7（A3→A3''）
├── 定理 DT1–DT7
├── 编码知识：公理 CA1–CA4、定理 CT1–CT5、组件 CD0–CD8
└── 基准 B1–B8（含 B9 LLM 端到端）
```

### 0.2 坚实度分级（附录 A）

| 等级 | 含义 | 代表定理 |
|------|------|----------|
| **L1** | 代码路径静态保证 | T4, T6, T9, OT1 |
| **L2** | 数学/有限常数 | T2, T5, T7, T10, DT2 |
| **L3** | 配置/frozenset 维护 | T3, T8 |
| **L4** | 依赖 LLM/估算假设 | T1 |
| **有条件目标** | 需生产数据 | OT2 |

---

## 1. 形式化定义索引

### 1.1 管家会话状态（定义 3.1）

\[
\mathcal{S} = (\text{SessionKey}, \text{LoopState}, \text{QueueState}, \text{MemoryState}, \text{PIMState}, \text{Role})
\]

- SessionKey = platform × chat_id × project
- LoopState = (H, σ, i, W)
- QueueState = (Q^now, Q^next, Q^later, mode)
- MemoryState = (𝒦_profile, 𝒦_experience, 𝒦_facts, 𝒦_project)
- PIMState = (contacts, expenses, memos, habits, reminders)

### 1.2 通道（定义 3.3–3.5）

\[
\mathcal{C}_{\text{in}} = (\text{Arrive}, \text{Classify}, \text{Admit}, \text{Queue}, \text{Dispatch})
\]

\[
\mathcal{C}_{\text{out}} = (\text{Reply}, \text{Supplementary}, \text{Reminder}, \text{Completion})
\]

**命题 2.2**：同一 session_key 无并发 `loop.run()`（Admission 单飞）。

**命题 2.3**：斜杠命令路由确定性（canonical 单射）。

### 1.3 LLM 预言机（定义 3.6–3.7）

\[
\mathcal{O}_{\text{LLM}}: \text{Messages} \times \text{Tools} \to \text{Dist}(\text{Response})
\]

\[
\epsilon_{\text{route}}(m) = 1 - P(t^* \mid m, \text{sys}, \mathcal{T}),\quad \partial \epsilon_{\text{route}} / \partial |\mathcal{T}| > 0
\]

### 1.4 TenantStore（定义 3.8，不变量 3.1）

\[
\mathcal{I} = \bigcup_{m \in \text{PIM\_MODULES}} \mathcal{I}_m,\quad |\mathcal{I}_m^{\text{active}}| \leq N_m^{\max}
\]

| 模块 | N^max |
|------|-------|
| contacts | 500 |
| expenses | 5000 |
| memos (active) | 200 |
| habits (active) | 30 |
| reminders (active) | 100 |

总存储上界 ≈ 10.8 MB（详设推导）。

### 1.5 扩展点（定义 3.9，不变量 3.2）

\[
|\mathcal{E}_{\text{MCP}}^{\text{servers}}| \leq 20,\quad \sum_s |\text{Tools}(s)| \leq 100
\]

默认更紧：MAX_SERVERS=3, MAX_TOOLS=20。扩展不得旁路安全管线。

### 1.6 上下文（定义 3.10，不变量 3.3）

\[
\mathcal{X} = (W, \text{Pack}, \text{Compress}, \text{Spill}, \text{Prune})
\]

\[
\forall \text{api\_call}:\ \text{tokens}(\text{Pack}(H)) \leq W - W_{\text{reserve}}
\]

五阶段：Spill → Prune → Preemptive → Compress → Reactive(413)。

### 1.7 权限（定义 3.11–3.13）

- 工具格 (𝒯, ⊆)，Owner ⊇ Butler ⊇ Child
- 𝒯_PIM ∩ 𝒯_child = ∅
- Level ∈ {auto, gated}，gated→auto 仅经 Owner

### 1.8 记忆（定义 3.14–3.15，不变量 3.4）

\[
\text{Retrieve}(q, \mathcal{K}) = \text{rerank}(\text{FTS}(q,\mathcal{K}) \cup \text{Vector}(q,\mathcal{K}))
\]

\[
\text{Inject}: H \times \text{Hits} \to H',\quad H_{\text{transcript}}\ \text{不变}
\]

### 1.9 成本（定义 3.16）

\[
\text{Cost}(s) = \sum_i [c_{\text{in}}(i)p_{\text{in}} + c_{\text{out}}(i)p_{\text{out}}] + \sum_j \text{Cost}(\text{delegate}_j)
\]

PIM 工具 schema 为固定 token 成本，不随对话长度增长。

### 1.10 编排（定义 3.17）

\[
\forall v \in V:\ \text{can\_execute}(v) \iff \text{preds done} \land (\neg v.\text{requires\_approval} \vee \text{Approve}(v))
\]

---

## 2. 主定理 T1–T10（陈述 · 前提 · 坚实度）

### T1 上下文不溢出

**陈述**：五阶段管线正常时，API 消息 token ≤ W。

**前提**：P-T1a 估算有界（中文 CJK×1.3 启发式）；P-T1b 压缩减 token；P-T1c overflow_fail；P-T1d PIM schema 常量占用。

**证明要点**：Spill 限单结果；Prune 单调减；Preemptive 三路；Reactive 413 兜底。

**坚实度**：**L4**。中文场景依赖 threshold_ratio 裕度。

**工程**：`context_pipeline.py`, `context_compressor.py`, `reactive_compact.py` — FINDING-1 已缓解。

---

### T2 队列收敛

**陈述**：followup 模式下，λ→0 时队列最终被 drain 空。

**前提**：P-T2a Loop 有限步终止；P-T2b DRAIN_PER_TURN>0；P-T2c 处理后不重入。

**坚实度**：**L2**。

**工程**：`message_queue.py`, `message_handler.py` — 13+ tests。

---

### T3 权限不可提升

**陈述**：委派链上 𝒯_child ⊂ 𝒯_parent；PIM ∉ 子 Agent。

**前提**：P-T3a blocked/deny 集；P-T3b dispatch 检查；P-T3c MAX_DELEGATE_DEPTH=2。

**坚实度**：**L3** — 17 tests。

**工程**：`delegate/policy.py`, `project_tools.py`, `permissions/`。

---

### T4 记忆不污染

**陈述**：Inject 不改 transcript；Tenant 路径不被 Project 操作覆盖。

**前提**：P-T4a pre_llm_transform 操作副本；P-T4b transcript 不经 transform。

**坚实度**：**L1**。

**工程**：`memory_prefetch.py`, `session_transcript.py`。

---

### T5 DAG 终止

**陈述**：TaskOrchestrator 有限步完成。

**前提**：无环；有限 max_retries；spawn 有限步；max_replan 有限。

**坚实度**：**L2**。

**工程**：`task_orchestrator.py`。

---

### T6 信息流安全

**陈述**：requires_approval 步骤与 mutating Runtime Job 未经 Owner 确认不执行。

**前提**：P-T6a–d 标注与 TTL。

**坚实度**：**L1**。

**工程**：`human_gate.py`, `runtime/builtin_handlers.py`。

---

### T7 PIM 数据有界性

**陈述**：各 PIM 模块 active 记录 ≤ N^max。

**前提**：创建前检查；超限错误；字段 strip 截断。

**坚实度**：**L2**。

**工程**：`tenant.py`, `pim_schema.py`, 各 PIM tools。

---

### T8 管家-委派分离

**陈述**：butler/lead 不直接调用项目文件修改工具。

**前提**：P-T8a–d extra 不含写工具；project.yaml 映射剔除 blocked；dispatch 拒绝未注册工具。

**坚实度**：**L3** — 14 tests。**G4-01 已修**：butler 从 project.yaml 继承写工具冲突已关闭。

**工程**：`project_tools._butler_allowed_tools`, `agent_profiles.py`。

---

### T9 编辑可回滚（自 Dev 子理论提升）

**陈述**：EditHistory 可完全撤销至编辑前文件状态。

**前提**：每编辑有 undo；编辑前快照；单 Owner 无并发写。

**坚实度**：**L1**（无并发时）。

**工程**：`dev_engine/edit_ops.py`, EditHistory。

---

### T10 开发循环终止（自 Dev 子理论提升）

**陈述**：Dev 循环有限步终止于 DONE/STUCK/REVIEW。

**前提**：I_max, K_max 有限；进度度量 μ 严格递减。

**坚实度**：**L2**。

**工程**：`dev_engine/dev_loop.py`。

---

## 3. 观测演化定理 OT1–OT2

### 公理 OA1–OA3

- **OA1**：pytest（结构 SSOT）⊥ LangFuse（趋势 SSOT）
- **OA2**：反馈不得提升权限格、 bypass MA7/T6
- **OA3**：L2 metrics + L3 基准构成可累积时间序列

### OT1 软反馈有界性

**陈述**：`eval_feedback` 注入不改变持久状态，仅影响当轮 LLM 输入。

**前提**：P-OT1a ephemeral 注入；P-OT1b LangFuse 只读。

**坚实度**：**L1** — 与 T4 同构。

**工程**：`ops/eval_feedback.py`, `agent_loop_phases.py` — ✅ 已接 gateway。

### OT2 硬反馈收敛前提

**陈述**：经验生命周期 + 调参在 OA2 下有界演化；**收敛性依赖生产数据**。

**前提**：P-OT2a 审计；P-OT2b 参数上下界；P-OT2c L2 接线完整。

**状态**：**有条件目标** — **G1-04 观测中**（`eval_feedback.jsonl` 窗内积累，06-23 可结案）。

**工程**：`eval_actions.py`, `ExperienceLibrary.lifecycle_pass()` — 硬反馈 opt-in `BUTLER_EVAL_HARD_FEEDBACK`。

---

## 4. 记忆子理论 MA / MT

### 4.1 公理 MA1–MA7（摘要）

| 公理 | 陈述要点 |
|------|----------|
| MA1 | Write 原子：Store∧Index 或 NoOp |
| MA2 | 存在查询 q 可检索已存条目（非任意 q） |
| MA3 | Tenant/Project 路径不交 |
| MA4 | Inject 不改 transcript |
| MA5 | decay(t) 单调非增；访问可刷新 |
| MA6 | 每层容量有界 |
| MA7 | 决策语气写入 → Pending；PIM 不进 fact |

### 4.2 定理 MT1–MT7（摘要）

| 定理 | 陈述 | 坚实度 | 测试 |
|------|------|--------|------|
| MT1 | 写入原子性 | L1/L2 | P-MT1* |
| MT2 | 检索完备性（存在 q） | L3+度量 | P-MT2* |
| MT3 | 域隔离 | L1 | P-MT3* |
| MT4 | 注入不污染（≈T4） | L1 | — |
| MT5 | 衰减单调与安全遗忘 | L2 | type_adjusted_half_life ✅ |
| MT6 | 容量有界 | L2 | — |
| MT7 | 持久化与索引最终一致 | 诚实边界 G2-09 | reindex 兜底 |

**度量**：MB1–MB7 基准；L2 `memory_metrics`（S_w, H_1, E_d 等）— 47+20 tests。

**混合检索**：

\[
\text{Recall}_{\text{hybrid}} \leq 1 - (1-R_v)(1-R_{\text{FTS}})
\]

**FINDING-2**：HashingEmbedder Recall@3 有限；生产需 fastembed/API（O3 ✅）。

---

## 5. 开发引擎子理论 DA / DT

### 5.1 公理 DA1–DA7（摘要）

| 公理 | 要点 |
|------|------|
| DA1 | 编辑原子；MultiEdit 全成功或 rollback |
| DA2 | Verify → PASS \| FAIL(Diagnostics) 结构化 |
| DA3 | tokens(codebase)≫W → Locate→Focus→Edit |
| DA4 | Fix 循环 ≤ K_max → STUCK |
| DA5 | DevEngine ⊆ AgentLoop（非独立进程） |
| DA6 | 每步 (Result, Trace) 结构化 |
| DA7 | 核心不依赖 ExternalTools |

### 5.2 定理 DT1–DT7（摘要）

| 定理 | 陈述 | 映射 |
|------|------|------|
| DT1 | Edit Safety（read-before-edit） | read_state.py |
| DT2 | Dev Loop Termination | ≡ T10 |
| DT3 | Permission Preservation | ≡ T3 在 dev 路径 |
| DT4 | Context Bounded | ≡ T1 在 dev 聚焦 |
| DT5 | Rollback Safety | ≡ T9 |
| DT6 | Diagnostic Completeness | dev trace |
| DT7 | External Tool Substitutability | extensions/opencode MCP |

**Dev FSM 进度度量**：

\[
\mu = I_{\max} - i + K_{\max} - k \quad \text{严格递减}
\]

---

## 6. 编码知识层 CA / CT / CD

### 6.1 公理 CA1–CA4

| 公理 | 含义 |
|------|------|
| CA1 | 任务可分解为七元素（规格/定理/经验/…） |
| CA2 | 定理库为永恒结构性知识 |
| CA3 | 经验可进化但须过定理门 |
| CA4 | 双重验证：定理验证 + 测试验证 |

### 6.2 定理 CT1–CT5（摘要）

| 定理 | 陈述 |
|------|------|
| CT1 | 定理验证器可检结构违规 |
| CT2 | 无经验时纯定理推理仍保逻辑骨架 |
| CT3 | 经验入库须全量定理检查 |
| CT4 | 激活函数选择相关定理子集 |
| CT5 | dual_verify 门控输出 |

### 6.3 组件成熟度（v1.5 §8.5，2026-06 登记）

| 组件 | 理论 | 实现成熟度 | 备注 |
|------|------|------------|------|
| CD7 process_task | T2 | **T2 生产** | delegate 路径已接 |
| CD6 dual_verify | CA4 | T2 诊断注入 | strict 硬阻断 ⏸️ G2-08 |
| CD0/CD6/CD8 | 规格/Synth/GenTC | **T1 测试级** | FP-6 自动化编码仍提示级 |
| CA4 strict | CT5 | advisory 默认 | `BUTLER_CODING_STRICT=0` 零生产调用 |

**定理 T01–T10 库**：8/10 有真实 checker；**T02/T07 stub**（闭环规划 FP-1/FP-2）。

---

## 7. 前提验证矩阵（第六章摘要）

| 前提族 | 内容 | 状态 | 测试入口 |
|--------|------|------|----------|
| P-T1* | 上下文/token | ✅ CJK 修正 | test_env_parse, context tests |
| P-T2* | 队列 | ✅ | test_message_queue |
| P-T3/T8/P5 | 权限/委派 | ✅ | test_premise_p5, delegate tests |
| P-T4/P6 | 记忆/门控 | ✅ | test_premise_p3, p4 |
| P-T7/P-PIM* | PIM 有界/路由 | ✅ 结构+LLM | test_premise_v3_llm_live |
| P-INJ | 注入防护 | ✅ 22 tests | test_premise_injection |
| P-COST | 成本分类 | ✅ 结构；数值 baseline ⏸️ G1-02 | test_premise_cost |
| P-PIM live | 路由 ε | ✅ 94%/92% ≥85% | G2-03 |
| P6-LIVE | fact 提取 | ✅ 100%/91.7% | fact extraction tests |
| P-MT* | 记忆前提 | ✅ 27 | test_premise_memory_theory |
| P-MT benchmarks | MB1–MB7 | ✅ | test_memory_metrics_benchmark |
| CA/CT/H* | 编码知识 | ✅ 99+ | test_premise_coding_knowledge |
| B9 LIVE | LLM delegate E2E | ✅ Tier-1 门控 | test_b9_*, llm_delegate_benchmark |

**规模参考**：post-consolidation ~5040 pytest（2026-06-09 基线）。

---

## 8. 能力边界与诚实声明（§7.4 索引）

| # | 诚实声明 | 缓解 | 登记状态 |
|---|----------|------|----------|
| 1 | LLM 路由/parse 有 ε | 消歧 prompt、pinning | P-PIM 已验 |
| 2 | Token 中文估算 | CJK×1.3 + reactive | FINDING-1 已缓解 |
| 3 | Hashing Recall 低 | fastembed semantic | G2-06 边界接受 |
| 4 | PII 压缩残留 | PII_EXCLUSION, pii_clearable | G2-01 边界接受 |
| 5 | 工具数↑ → ε_route↑ | 角色隔离、selector | 设计取舍 |
| 6 | 成本数值未对标账单 | D4 结构+落盘 | G1-02 搁置 |
| 7 | WeChat 中断 | durable outbox | G2-02 已验 2026-06-10 |
| 8 | PIM 自由文本仅截断 | max length | G2-04 边界接受 |
| 9 | reminders 上限 | MAX_ACTIVE=100 | ✅ 已修复 |
| 10 | L7 反馈 | eval 已接 | OT1 ✅；OT2 观测中 |
| 11 | 靠时间变好 | 经验挖掘 weekly job | G1-03 ✅；OT2 开放 |

---

## 9. 理论—实现差距登记（G1–G4，2026-06-09 快照）

### 9.1 分类定义

| 类 | 含义 | 动作 |
|----|------|------|
| G1 | 漏实现 | Backlog 立项 |
| G2 | 诚实边界+缓解 | 验证或接受 |
| G3 | 实现更优 | 同步文档 |
| G4 | 与公理冲突 | 优先修代码或收窄定理 |

### 9.2 当前开放/搁置

| ID | 类 | 项 | 状态 |
|----|-----|-----|------|
| G1-04 | G1 | OT2 生产 eval 证据 | **观测中** — 窗 2026-06-09→06-23 |
| G1-02 | G1 | 账单 baseline | **搁置** |
| G1-08 | G1 | 灵文新书态探针 | **搁置** |
| G2-08 | G2 | CA4 strict 生产硬阻断 | **保持现状** |
| G4-* | — | 无开放 G4 | 全收口 ✅ |

其余 G1/G2/G3 项见登记册 §0 已收口表。

---

## 10. 三角色评审要点（第四章摘要，供批判）

父理论 v3.0 三角色（架构师 / 安全 / 产品）覆盖 9 盲区，包括：

- LLM 作为概率组件时的定理解释力
- 单通道下的 mutating 审批 UX
- 「全能管家」承诺与 ε_route 的可证阈值
- DevEngine prompt-guided FSM vs 硬编码 FSM（FP-5 设计选择）
- B7 oracle 基准 vs B9 LIVE 基准的测量对象差异

**审阅建议**：对每条 L4/有条件目标定理，显式列出**可 falsify 的实验**（如 B9 Tier-1 通过率、P-PIM live 路由、MB Recall@3）。

---

## 11. 符号表（核心）

| 符号 | 含义 |
|------|------|
| 𝒢, ℒ, Π, ℳ, 𝒜 | Gateway, Loop, Pillars, Memory, Authority |
| 𝒪_LLM | LLM 概率预言机 |
| H, W, σ | 历史、窗口、运行状态 |
| Q_s | 会话队列 |
| ε_route | 路由错误率 |
| 𝒯_PIM | PIM 工具集 |
| I_max, K_max | Dev 迭代/修复上限 |
| 𝒦_P, 𝒦_E, 𝒦_F, 𝒦_J | Profile/Experience/Facts/ProjectMemory |

完整表见 [`v4-theoretical-baseline.md`](../v4-theoretical-baseline.md) 附录 B。

---

## 12. 供高级模型的审阅清单

1. **T1+T10+DT2** 在中文长会话与 Dev 嵌套 delegate 下的组合是否需联合定理？  
2. **T8 vs A3''** DevEngine role=dev 路径与 butler 路径的形式化分离是否完整？  
3. **OT2** 在 OA2 下是否可加强为收敛定理，需哪些额外公理？  
4. **MA2 vs 效果**：检索完备性「存在 q」是否足够支撑产品「不应遗忘」承诺？  
5. **CA4 advisory**：定理 CT5 与生产 `_run_auto_verify` 行为是否等价？  
6. **子理论合并**：Experience→Skill 沉积 v2 草案对 MA/MT 契约的影响范围？

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-06-12 | 初版：主/子理论定理与差距登记摘要 |
