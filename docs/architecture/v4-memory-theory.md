# Butler v4 — 记忆系统子理论（L6 层完整推导）

> 版本 1.2 | 2026-06-09  
> **沉积层演进**：Experience + 程序性 Skill 合并为 **Skill 沉积层** 的理论草案见 **[`v4-skill-memory-theory.md`](v4-skill-memory-theory.md) v2.0-draft**。本文 **契约层**（Profile / Facts / ProjectMemory、MA7、MB 契约项）在 v2 中 **继续有效**；\(\mathcal{K}_E\) 章节在实现迁移完成后由 v2 取代。  
> 父文档：`v4-theoretical-baseline.md` v3.1（10 定理 + OT1-OT2 / 10 公理含 OA1-OA3 / 608+ 验证测试）
> **v1.2 变更**：修正 §4.1/§4.3 内部矛盾；更新智能遗忘与 L2 度量接线状态；对齐 DevEngine B8 基准计数
> 方法论：需求公理化 → 形式化建模 → 定理证明 → 能力差距分析 → 详细设计映射 → 度量模型 → 工程验证
> 定位：将 L6 层从"分散的公理/命题/定义"升级为"完整记忆子理论"，为管家系统提供可证明、可度量、可演化的记忆能力
> 前提验证：P-MT1a~P-MT7e 共 27 tests 全绿（`test_premise_memory_theory.py`）
> 效果度量：L2 运行时度量 + L3 基准测试 MB1-MB7 共 20 tests 全绿（`test_memory_metrics_benchmark.py`）

---

## 第一章 需求公理化 — 记忆能力的第一性原理

### 1.1 核心矛盾分析

父理论 M3 指出了"个人数据持久 vs 上下文有限"的矛盾：

\[
|\mathcal{K}| \gg W \quad \Rightarrow \quad \text{全量注入不可行，必须检索}
\]

但检索引入了新的根本问题——**信息损失**。全量注入时 LLM 能"看到"所有记忆；检索式注入时，LLM 只能看到检索命中的子集。如果检索遗漏了关键信息，管家的回答质量将显著退化。

父理论 §2.6 给出了四层模型和混合检索公式，但存在以下未解决的根本问题：

1. **完整性**：Owner 说过的重要事情是否一定被记住？
2. **可靠检索**：记住的信息在需要时能否被找到？
3. **时间一致性**：跨会话、跨重启后记忆是否完整？
4. **容量可持续**：记忆持续增长后检索质量是否退化？
5. **遗忘安全**：时间衰减是否会误杀关键记忆？

本子理论将这些问题形式化，并建立可验证的公理-定理体系。

### 1.2 管家记忆 vs 通用 AI 记忆

| 维度 | 通用 AI 记忆（ChatGPT Memory, Claude Memory） | 管家记忆（Butler） |
|------|----------------------------------------------|-------------------|
| **写入模型** | LLM 自主决定记什么 | 结构化四层 + scope 路由 + Owner 审批 |
| **存储模型** | 不透明云存储 | 文件系统透明（JSON/SQLite/Markdown） |
| **检索模型** | 隐式（全量注入或隐式检索） | 显式混合检索（FTS + 向量 + rerank） |
| **隔离模型** | 单用户 | 双域（Tenant + Project）+ 多项目隔离 |
| **遗忘模型** | 用户手动删除 | 时间衰减 + 容量截断 + 显式删除 |
| **审计模型** | 不可审计 | MEMORY.md 可读 + Pending 审批 + 诊断命令 |
| **安全模型** | 平台托管 | 本地存储 + PII 清除 + 注入过滤 |

**核心洞察**：管家记忆不需要追赶通用 AI 的"自主记忆"能力，但必须在**可靠性、可审计性、可控性**上超越它们。管家场景下，Owner 可以容忍"我需要告诉管家记住这件事"（显式写入），但不可容忍"我明明告诉过管家，它却忘了"（检索失败）。

### 1.3 记忆系统公理

以下 7 条公理定义了管家记忆系统的不可动摇基础：

**公理 MA1（写入原子性）**：每次记忆写入操作要么完整成功（数据持久化 + 索引同步），要么完全不应用。不存在"数据写入但索引未更新"的中间态。

\[
\text{Write}(k, v) \implies (\text{Store}(k, v) \land \text{Index}(k, v)) \lor \text{NoOp}
\]

**公理 MA2（检索完备性）**：对于已成功写入的记忆条目，存在至少一种检索策略（精确匹配、FTS、向量）能在有限时间内找到它。

\[
\forall m \in \mathcal{K}_{\text{stored}}: \exists q: m \in \text{Retrieve}(q, \mathcal{K})
\]

**注意**：MA2 保证"存在可检索的查询"，不保证"任意查询都能检索到"。后者是效果问题，由度量系统衡量。

**公理 MA3（域隔离不可旁路）**：Tenant 域（Profile, Experience）和 Project 域（Facts, ProjectMemory）的存储路径物理分离。跨域读写只通过显式的 Facade 接口，不存在直接文件路径交叉。

\[
\text{Path}(\mathcal{K}_{\text{tenant}}) \cap \text{Path}(\mathcal{K}_{\text{project}}) = \emptyset
\]

**公理 MA4（注入透明性）**：记忆注入只通过 `<memory-context>` 围栏标记影响 LLM 输入，不修改 transcript SSOT。LLM 和 Owner 可以区分注入内容和对话内容。

\[
\text{Inject}(H, \text{Hits}) = H' \quad \text{s.t.} \quad H_{\text{transcript}} \text{ 不变}
\]

**公理 MA5（衰减单调性）**：记忆的检索权重随时间单调非递增（除非被显式访问刷新）。更近期的记忆在相同相关性下优先于更早的记忆。

\[
t_1 < t_2 \implies \text{decay}(t_1) \leq \text{decay}(t_2), \quad \text{decay}(t) = 2^{-t/\tau}
\]

**公理 MA6（容量有界）**：每个记忆层有显式的容量上限。超过上限时，写入操作被拒绝或触发淘汰，不产生未定义行为。

\[
\forall L \in \{\text{profile}, \text{experience}, \text{facts}, \text{project}\}: |\mathcal{K}_L| \leq N_L^{\max}
\]

**公理 MA7（安全写入门控）**：含决策语气的记忆写入必须经过 Owner 审批（Pending 队列），不直接进入正式记忆。PIM 工具结果不进入认知记忆（fact 提取跳过 PIM）。

\[
\text{Write}_{\text{decision}}(m) \implies m \in Q_{\text{pending}} \quad \text{直到 Owner 批准}
\]

### 1.4 与父理论的映射

| 父公理/原则 | 子理论扩展 | 说明 |
|------------|-----------|------|
| **A6**（记忆分层不可旁路） | **MA3 + MA7 强化** | MA3 增加路径物理隔离保证；MA7 增加决策门控 |
| **P2**（显式记忆优先于模型记忆） | **MA1 + MA2 具体化** | 显式记忆要求写入原子且可检索 |
| **M3**（个人数据持久 vs 上下文有限） | **MA5 + MA6 解法** | 衰减 + 容量限制解决无限增长问题 |
| **T4**（记忆不污染） | **MA4 继承** | MA4 是 T4 在记忆子理论的局部表述 |

---

## 第二章 形式化建模

### 2.1 记忆状态 MemoryState

**定义 M1（记忆状态）**：

\[
\mathcal{M} = (\mathcal{K}_P, \mathcal{K}_E, \mathcal{K}_F, \mathcal{K}_J, \mathcal{V}, \mathcal{Q}_{\text{pending}})
\]

其中：
- \(\mathcal{K}_P\)（Profile）：Owner 画像条目集合，\(|\mathcal{K}_P| \leq N_P^{\max}\)（默认 2000 字符）
- \(\mathcal{K}_E\)（Experience）：跨项目经验记录集合，每条含 `(id, text, tags, project, category, created_at, access_count)`
- \(\mathcal{K}_F\)（Facts）：项目级机读事实集合，每条含 `(id, type, content, source, timestamp)`
- \(\mathcal{K}_J\)（Project Memory）：MEMORY.md 的章节-条目结构，每条含 `(section, bullet, created_at)`
- \(\mathcal{V}\)（Vector Index）：派生向量索引，\(\mathcal{V} = \text{Embed}(\mathcal{K}_P \cup \mathcal{K}_E \cup \mathcal{K}_J)\)
- \(\mathcal{Q}_{\text{pending}}\)：待审批记忆队列

### 2.2 记忆操作代数

**定义 M2（记忆操作）**：

\[
\text{MemOp} ::= \text{Append}(L, m) \mid \text{Remove}(L, id) \mid \text{Replace}(L, id, m') \mid \text{Approve}(id) \mid \text{Reject}(id)
\]

其中 \(L \in \{\text{Profile}, \text{Experience}, \text{Facts}, \text{ProjectMem}\}\) 是目标层。

**操作语义**：

| 操作 | 前置条件 | 后置条件 | 失败模式 |
|------|---------|---------|---------|
| \(\text{Append}(L, m)\) | \(|\mathcal{K}_L| < N_L^{\max}\) | \(m \in \mathcal{K}_L \land \text{Embed}(m) \in \mathcal{V}\) | 容量超限拒绝 |
| \(\text{Remove}(L, id)\) | \(id \in \mathcal{K}_L\) | \(id \notin \mathcal{K}_L \land \text{Invalidate}(id, \mathcal{V})\) | id 不存在忽略 |
| \(\text{Replace}(L, id, m')\) | \(id \in \mathcal{K}_L\) | \(\mathcal{K}_L[id] = m' \land \text{Re-embed}(id, \mathcal{V})\) | id 不存在退化为 Append |
| \(\text{Approve}(id)\) | \(id \in \mathcal{Q}_{\text{pending}}\) | \(id \in \mathcal{K}_J \land id \notin \mathcal{Q}_{\text{pending}}\) | id 不在队列忽略 |
| \(\text{Reject}(id)\) | \(id \in \mathcal{Q}_{\text{pending}}\) | \(id \notin \mathcal{Q}_{\text{pending}} \land \text{Invalidate}(id, \mathcal{V})\) | id 不在队列忽略 |

**定义 M3（操作原子性约束）**：

\[
\text{Append}(L, m) = \text{Store}(L, m) \otimes \text{IndexSync}(m, \mathcal{V})
\]

\(\otimes\) 表示"同步成功"：如果 Store 成功但 IndexSync 失败，下次 `reindex` 时修复。这是**最终一致性**而非严格事务，但通过 reindex 机制保证收敛。

### 2.3 检索模型

**定义 M4（多层检索函数）**：

\[
\text{Retrieve}(q, \mathcal{M}) = \text{Rerank}\left(\bigcup_{L \in \text{ActiveLayers}} \text{Search}_L(q, \mathcal{K}_L)\right)
\]

其中 \(\text{ActiveLayers} \subseteq \{P, E, F, J\}\) 由 `BUTLER_MEMORY_RECALL_LAYERS` 配置。

**定义 M5（混合检索函数）**：

\[
\text{Search}_E(q, \mathcal{K}_E) = \text{FTS}(q, \mathcal{K}_E) \cup_{\text{RRF}} \text{Vector}(q, \mathcal{V}_E)
\]

\[
\text{score}_{\text{hybrid}}(d) = \alpha \cdot \text{RRF}_{\text{vector}}(d) + (1-\alpha) \cdot \text{RRF}_{\text{FTS}}(d)
\]

默认 \(\alpha = 0.7\)（`BUTLER_VECTOR_HYBRID_WEIGHT`）。

**定义 M6（衰减-加权 Rerank）**：

\[
\text{RankScore}(d) = \text{RelevanceScore}(d) \times \text{decay}(\Delta t_d) \times (1 + \beta \cdot \log(1 + \text{access\_count}(d)))
\]

其中：
- \(\text{decay}(\Delta t) = 2^{-\Delta t / \tau}\)，\(\tau\) = `BUTLER_MEMORY_HALF_LIFE_DAYS`（默认 30）
- \(\beta\) = `BUTLER_MEMORY_ACCESS_BOOST`（默认 0.12）
- \(\Delta t_d\) = 当前时间 − 记忆创建时间（天）

### 2.4 注入模型

**定义 M7（预取注入变换）**：

\[
\text{Prefetch}(q, \mathcal{M}) = \text{Truncate}(\text{Filter}_{\text{inj}}(\text{Retrieve}(q, \mathcal{M})), C_{\max})
\]

\[
\text{Inject}(H, \text{Prefetch}(q, \mathcal{M})) = H[:-1] \oplus \text{Fence}(H[-1], \text{Prefetch}) \oplus []
\]

其中：
- \(\text{Filter}_{\text{inj}}\)：行级 prompt-injection 过滤
- \(\text{Truncate}(\cdot, C_{\max})\)：截断到 `BUTLER_PREFETCH_TOTAL_MAX_CHARS`
- \(\text{Fence}\)：用 `<memory-context>` 围栏包裹，附加到最后一条 user 消息

### 2.5 持久化模型

**定义 M8（存储拓扑）**：

\[
\text{Storage} = \begin{cases}
\text{Tenant 域}: & \texttt{\textasciitilde/.butler/tenants/\{t\}/memory/} \\
  & \quad \texttt{profile.json} \quad (\mathcal{K}_P) \\
  & \quad \texttt{experience.db} \quad (\mathcal{K}_E, \text{FTS5}) \\
  & \quad \texttt{memory\_vectors.db} \quad (\mathcal{V}_{\text{tenant}}) \\[4pt]
\text{Project 域}: & \texttt{\{workspace\}/.butler/} \\
  & \quad \texttt{memory/MEMORY.md} \quad (\mathcal{K}_J) \\
  & \quad \texttt{facts.json} \quad (\mathcal{K}_F) \\
  & \quad \texttt{memory/memory\_vectors.db} \quad (\mathcal{V}_{\text{project}})
\end{cases}
\]

**定义 M9（持久化不变量）**：

\[
\text{Restart}(\text{Process}) \implies \text{Load}(\text{Storage}) = \mathcal{M}_{\text{pre-shutdown}} \setminus \mathcal{V}
\]

向量索引 \(\mathcal{V}\) 是派生数据，可通过 `reindex` 从 \(\mathcal{K}\) 重建：

\[
\text{Reindex}(\mathcal{K}) \to \mathcal{V}' \quad \text{s.t.} \quad \forall m \in \mathcal{K}: \text{Embed}(m) \in \mathcal{V}'
\]

### 2.6 事实提取模型

**定义 M10（会话事实提取）**：

\[
\text{ExtractFacts}(H_{\text{middle}}) = \{(t, c) \mid t \in \{\text{decision}, \text{completion}, \text{preference}, \text{file\_change}\}, c = \text{match}(H_{\text{middle}}, R_t)\}
\]

其中 \(R_t\) 是类型 \(t\) 的启发式正则模式。提取的事实用于压缩后锚点重注入，防止上下文压缩导致关键决策丢失。

\[
|\text{ExtractFacts}(H)| \leq 50, \quad \text{PIM 工具结果排除在外}
\]

---

## 第三章 定理证明

### 定理 MT1：记忆写入原子性

**陈述**：每次 `butler_remember` 操作在存储层和索引层保持最终一致性。即使 IndexSync 失败，`reindex` 操作可恢复一致。

**前提**：
- (P-MT1a) `ButlerMemoryService._remember()` 先写 Store 再调 IndexSync
- (P-MT1b) `reindex_semantic_memory()` 扫描 Store 重建全量索引
- (P-MT1c) IndexSync 失败不回滚 Store 写入（最终一致性设计）

**证明**：

设操作 \(\text{Append}(L, m)\) 分两步：\(S = \text{Store}(L, m)\)，\(I = \text{IndexSync}(m, \mathcal{V})\)。

情况 1：\(S\) 成功，\(I\) 成功 → 即时一致。
情况 2：\(S\) 成功，\(I\) 失败 → \(m \in \mathcal{K}_L\) 但 \(\text{Embed}(m) \notin \mathcal{V}\)。FTS 路径仍可检索到 \(m\)（Experience 层）或精确匹配可达（Profile/Facts 层）。下次 `reindex` 执行后 \(\text{Embed}(m) \in \mathcal{V}\)，恢复完全一致。
情况 3：\(S\) 失败 → 操作整体失败，NoOp。

**收敛时间**：设 reindex 周期为 \(T_r\)，最大不一致窗口为 \(T_r\)。

**坚实度**：**L2 机制保证**——依赖 reindex 周期性执行。 ∎

---

### 定理 MT2：检索完备性

**陈述**：对于已成功写入的记忆条目 \(m\)，存在查询 \(q\) 使得 \(m \in \text{Retrieve}(q, \mathcal{M})\)，前提是 \(m\) 未被衰减淘汰且未超容量截断。

**前提**：
- (P-MT2a) FTS5 对精确子串匹配保证召回
- (P-MT2b) 向量索引对 \(\text{Embed}(m)\) 的自查询保证最高相似度
- (P-MT2c) Profile 层精确字段匹配保证完全召回

**证明**：

对各层分别证明：
1. **Profile**：精确字段匹配，查询 = 字段名 → \(\text{Recall} = 1\)。
2. **Experience**：\(q = m.\text{text}\) 时 FTS 精确匹配命中；\(q = m.\text{text}\) 时向量自查询 \(\cos(\text{Embed}(q), \text{Embed}(m)) = 1\)。
3. **Facts**：前缀匹配，\(q = m.\text{type}\) 时命中。
4. **ProjectMemory**：章节解析 + 向量，\(q = m.\text{bullet}\) 时命中。

以上均为存在性证明：存在使检索成功的查询。**不保证**任意用户查询都能命中——这是检索质量问题，由度量系统衡量。

**坚实度**：**L1 架构保证**（精确匹配）+ **L2 机制保证**（向量检索依赖嵌入质量）。 ∎

---

### 定理 MT3：域隔离安全

**陈述**：Tenant 域的记忆操作不会修改 Project 域的存储，反之亦然。不同项目的 Project 域存储互不影响。

**前提**：
- (P-MT3a) Tenant 域路径 `~/.butler/tenants/{t}/` 与 Project 域路径 `{workspace}/.butler/` 不重叠
- (P-MT3b) `butler_remember` 的 scope 参数决定写入路径，不存在跨域 scope
- (P-MT3c) 项目切换改变 `workspace`，但不改变 tenant 路径

**证明**：

1. 路径不重叠由文件系统结构保证：`~/.butler/` 在用户 home，`{workspace}/.butler/` 在项目目录。
2. `_remember()` 方法中，scope 映射到固定路径前缀：
   - `owner_profile` → `tenant_path/memory/profile.json`
   - `owner_experience` → `tenant_path/memory/experience.db`
   - `project_notes` → `workspace_path/.butler/memory/MEMORY.md`
3. 不存在接受任意路径的 scope 值。

**坚实度**：**L1 架构保证**——文件系统路径静态保证。 ∎

---

### 定理 MT4：注入不污染（继承 T4）

**陈述**：记忆注入操作不修改 transcript SSOT。注入内容通过围栏标记可区分。

**前提**：继承 T4 的 P-T4a 和 P-T4b。

**证明**：直接继承父理论 T4 的证明。额外强化：`<memory-context>` 围栏使 LLM 可以区分注入的记忆与用户消息，避免记忆内容被误认为 Owner 指令。

**坚实度**：**L1 架构保证**。 ∎

---

### 定理 MT5：衰减单调性与安全遗忘

**陈述**：衰减函数 \(\text{decay}(t)\) 关于时间 \(t\) 单调递减，且 \(\text{decay}(0) = 1\)，\(\lim_{t \to \infty} \text{decay}(t) = 0\)。被显式访问的记忆通过 `access_boost` 提升排名，但不重置衰减。

**前提**：
- (P-MT5a) `decay_factor()` 实现 \(2^{-\Delta t / \tau}\)
- (P-MT5b) `access_boost` 是加法加权 \((1 + \beta \cdot \log(1 + n))\)，不修改时间戳

**证明**：

\[
\text{decay}(t) = e^{-\ln 2 \cdot t / \tau} = 2^{-t/\tau}
\]

\[
\frac{d}{dt} \text{decay}(t) = -\frac{\ln 2}{\tau} \cdot e^{-\ln 2 \cdot t / \tau} < 0 \quad \forall t \geq 0
\]

单调递减得证。\(\text{decay}(0) = e^0 = 1\)，\(\lim_{t \to \infty} \text{decay}(t) = 0\)。

**安全遗忘分析**：衰减不删除数据——只降低检索排名。低排名记忆仍存在于存储层，可通过 `butler_recall` 显式查询或 `reindex` 后重新检索。因此衰减是**软遗忘**而非**硬删除**。

**风险声明**：当 \(\text{decay}(\Delta t)\) 很小且没有 `access_boost` 时，关键但长期未被引用的记忆可能无法在自动 prefetch 中被召回。这是设计取舍：优先最近相关性。

**坚实度**：**L1 数学保证**（函数性质）+ **L3 配置保证**（τ 可调）。 ∎

---

### 定理 MT6：容量有界性

**陈述**：每个记忆层的存储大小有显式上限，超限时操作被安全拒绝或触发截断。

**前提**：
- (P-MT6a) ProfileStore：2000 字符硬上限
- (P-MT6b) MEMORY.md：`BUTLER_MEMORY_MAX_LINES`（200）× `BUTLER_MEMORY_MAX_BYTES`（25KB）
- (P-MT6c) 会话事实：50 条/会话
- (P-MT6d) Prefetch 注入：`BUTLER_PREFETCH_TOTAL_MAX_CHARS`（3500）

**证明**：

各层分别证明：

1. **Profile**：`ProfileStore.add()` 在写入前检查 `len(content) > 2000` 并拒绝。
2. **ProjectMemory**：`truncate_memory_text()` 在读取时截断超限内容。
3. **Facts**：`extract_pre_compact_facts()` 在 `len(facts) >= 50` 时停止提取。
4. **Prefetch**：`prefetch_turn_memory()` 累计字符数超 `PREFETCH_TOTAL_MAX_CHARS` 时截断。

Experience 层无硬上限（SQLite 可无限增长），但通过 FTS5 索引保证检索性能 \(O(\log n)\)，且 prune 机制（`BUTLER_EXPERIENCE_PRUNE_DAYS`）定期清理。

**坚实度**：**L2 机制保证**。 ∎

---

### 定理 MT7：持久化一致性

**陈述**：进程重启后，从持久化存储加载的记忆状态等于重启前的状态（向量索引除外，可通过 reindex 恢复）。

**前提**：
- (P-MT7a) Profile：JSON 文件，每次写入完整覆盖
- (P-MT7b) Experience：SQLite WAL 模式，写入即持久
- (P-MT7c) MEMORY.md：文本文件，每次写入完整覆盖
- (P-MT7d) Facts：JSON 文件
- (P-MT7e) Vector Index：SQLite 存储 embedding，可从 Store 重建

**证明**：

JSON 和 SQLite 文件在 `write()` / `commit()` 后持久化到文件系统。进程重启后 `open()` / `connect()` 读取相同文件。向量索引的 `memory_vectors.db` 也是 SQLite 文件，正常情况下持久。异常丢失时，`reindex` 可从源数据完全重建。

\[
\text{Load}(\text{Storage}) = \mathcal{K}_P \cup \mathcal{K}_E \cup \mathcal{K}_F \cup \mathcal{K}_J
\]
\[
\text{Reindex}(\mathcal{K}) \to \mathcal{V}' = \mathcal{V}_{\text{pre-shutdown}}
\]

**坚实度**：**L2 机制保证**——依赖文件系统持久化和 SQLite 事务保证。 ∎

---

## 第四章 能力差距分析 — 对照跨会话记忆系统

### 4.1 核心能力矩阵

| 能力维度 | Butler 当前 | ChatGPT Memory | Claude Memory | 目标状态 |
|----------|------------|----------------|---------------|---------|
| **写入模型** | scope 路由 + Pending 审批 | LLM 自主决定 | LLM 自主决定 | **优势项**：可控写入 |
| **存储透明** | 文件系统可审计 | 不可见 | 不可见 | **优势项**：MEMORY.md 人类可读 |
| **检索模型** | FTS + 向量 hybrid | 隐式全量注入 | 隐式注入 | 合格，需提升嵌入质量 |
| **嵌入质量** | HashingEmbedder（低） | OpenAI Embedding | Claude Embedding | **劣势**：需升级嵌入器 |
| **衰减模型** | 艾宾浩斯 + 访问加权 | 无 | 无 | **优势项**：主动遗忘 |
| **跨会话** | 四层持久化 | 平台托管 | 平台托管 | 合格 |
| **多项目** | 双域隔离 | 单空间 | 单空间 | **优势项**：项目隔离 |
| **安全** | PII 清除 + 注入过滤 + Pending | 平台策略 | 平台策略 | **优势项**：本地可控 |
| **效果度量** | L2 `memory_metrics` + L3 MB1-MB7（20 tests） | 无 | 无 | **Butler 优势项**（竞品无公开度量） |
| **容量管理** | 分层上限 + 截断 | 不透明 | 不透明 | 合格 |

### 4.2 Butler 记忆的差异化优势

1. **写入可控**：Owner 明确知道什么被记住了（MEMORY.md 可读）
2. **双域隔离**：个人 Profile 跨项目共享，项目知识项目内隔离
3. **审批门控**：决策类记忆需要 Owner 确认才正式生效
4. **主动遗忘**：时间衰减避免过时信息干扰
5. **本地存储**：数据不离开 Owner 设备

### 4.3 必须补齐的能力

1. **嵌入质量升级**：HashingEmbedder Recall@3 ≈ 50-67%，需支持 API 嵌入器（已有代码但默认未启用）
2. **L2 度量生产接线**：`memory_metrics.py` 已实现；`on_retrieval()`（P_r/R_r）已接 `memory_prefetch`；`on_fact_anchor_survival()`（S_f 锚点）已接 `post_compact_cleanup` + `/诊断`；P_r 的 LLM 引用闭环仍为 Backlog（见 [`v4-context-memory-compaction.md`](v4-context-memory-compaction.md) §7）
3. ~~**智能遗忘**~~：✅ 已实现 `retrieval_ranking.py::type_adjusted_half_life()`，按记忆类型差异化半衰期（如 profile/decision 衰减更慢）。全局 τ 仍可通过 `BUTLER_MEMORY_HALF_LIFE_DAYS` 调整

### 4.4 暂不追赶的能力

1. **LLM 自主记忆**：管家场景下显式记忆更可控
2. **云端同步**：本地存储是安全优势
3. **多模态记忆**：图片/语音记忆待微信媒体接入后再考虑

---

## 第五章 详细设计映射 — 公理/定理到代码的映射

### 5.1 模块映射表

| 公理/定理 | 关键模块 | 验证点 |
|----------|---------|--------|
| MA1（写入原子性） | `facade.py::_remember()`, `semantic_index.py::index_experience_row()` | Store 后 IndexSync；reindex 兜底 |
| MA2（检索完备性） | `semantic_index.py::hybrid_experience_search()`, `recall_layers.py` | FTS + 向量双路径 |
| MA3（域隔离） | `butler_memory.py`, `project_memory.py` | 路径前缀分离 |
| MA4（注入透明性） | `session/memory_prefetch.py`, `injection_guard.py` | 围栏标记 + 过滤 |
| MA5（衰减单调性） | `retrieval_ranking.py::decay_factor()` | 指数衰减函数 |
| MA6（容量有界） | `butler_memory.py::ProfileStore`, `memory_caps.py`, `fact_extraction.py` | 各层上限检查 |
| MA7（安全写入） | `project_memory.py::_auto_classify()`, `facade.py::_remember()` | 决策→Pending |
| MT1（写入原子性） | `facade.py`, `reindex.py` | 最终一致性 |
| MT2（检索完备性） | `semantic_index.py`, `recall_layers.py`, `query_decompose.py` | 多策略检索 |
| MT3（域隔离） | 文件系统路径 | 静态保证 |
| MT4（注入不污染） | `context_pipeline.py::pre_llm_transform` | 操作副本 |
| MT5（衰减安全） | `retrieval_ranking.py` | 数学性质 |
| MT6（容量有界） | 各层 Store | 上限检查 |
| MT7（持久化一致性） | SQLite + JSON + MEMORY.md | 文件系统 + reindex |

### 5.2 记忆生命周期与模块职责

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

---

## 第六章 度量模型 — 记忆效果的形式化量化

### 6.1 核心指标定义

| 指标 | 公式 | 含义 |
|------|------|------|
| 检索精度 \(P_r\) | \(\frac{|\text{Prefetch} \cap \text{LLM\_used}|}{|\text{Prefetch}|}\) | 注入的记忆中被 LLM 实际引用的比例 |
| 检索召回 \(R_r\) | \(\frac{|\text{Prefetch} \cap \text{Relevant}|}{|\text{Relevant}|}\) | 相关记忆被成功检索的比例 |
| 写入存活率 \(S_w\) | \(\frac{|\{m : \text{Write}(m) \to \text{Recall}(m) \text{ 成功}\}|}{|\text{Write}|}\) | 写入的记忆在后续能被召回的比例 |
| Fact 存活率 \(S_f\) | \(\frac{|\text{FactsPostCompact}|}{|\text{FactsPreCompact}|}\) | 压缩后事实锚点保留比例 |
| 衰减误杀率 \(E_d\) | \(\frac{|\{m : \text{important}(m) \land \text{RankScore}(m) < \theta\}|}{|\{m : \text{important}(m)\}|}\) | 重要记忆因衰减降到阈值以下的比例 |
| 首轮命中率 \(H_1\) | \(\frac{|\{t : \text{Prefetch}_1(t) \cap \text{Relevant}(t) \neq \emptyset\}|}{|\text{Turns}|}\) | 第一次 prefetch 就命中的轮次比例 |

### 6.2 基准任务设计

| 编号 | 类别 | 描述 | 测量指标 |
|------|------|------|---------|
| MB1 | 精确召回 | 写入 profile → 用原文查询 | \(S_w, R_r\) |
| MB2 | 语义召回 | 写入 experience → 用改写查询 | \(R_r\)（语义匹配） |
| MB3 | 跨会话持久 | 写入 → 模拟重启 → 查询 | \(S_w\)（持久化后） |
| MB4 | 衰减行为 | 写入 → 模拟 60 天 → 查询排序 | \(E_d\)（衰减是否合理） |
| MB5 | 容量压力 | 写入大量条目 → 查询最早条目 | \(R_r\)（容量下的检索） |
| MB6 | Fact 压缩 | 提取事实 → 模拟压缩 → 锚点 | \(S_f\) |
| MB7 | 注入安全 | 包含 injection 模式的记忆 | 过滤成功率 |

### 6.3 与 DevEngine 度量体系的对齐

| 对比维度 | DevEngine 度量 | Memory 度量 |
|----------|---------------|-------------|
| 核心"做到"指标 | 任务完成率 | 检索召回率 |
| 核心"做好"指标 | 编辑精度 | 检索精度 |
| 核心"安全"指标 | STUCK 终止率 | 注入过滤率 |
| 核心"效率"指标 | 平均迭代次数 | 首轮命中率 |
| 基准任务数 | 8 项（含 B8 SWE-bench Lite） | 7 项 |

---

## 第七章 能力边界与诚实声明

### 7.1 记忆系统能力边界

| 边界 | 量化估计 | 缓解 |
|------|----------|------|
| 检索召回率 | HashingEmbedder: Recall@3 ≈ 50-67%；API Embedder: 更高 | 多策略降级 + 嵌入器可配 |
| 嵌入质量 | 取决于嵌入模型选择 | `BUTLER_EMBEDDING_PROVIDER` 可切换 |
| 衰减参数 | 基础半衰期 + 类型调整（`type_adjusted_half_life`） | `BUTLER_MEMORY_HALF_LIFE_DAYS` 可调 |
| Profile 容量 | 2000 字符硬上限 | 精炼化存储 |
| 压缩信息损失 | fact 提取为正则启发式，非 LLM | 锚点重注入缓解 |
| 并发安全 | SQLite WAL 模式；进程内读写锁 | 单进程设计下足够 |

### 7.2 诚实声明

1. **检索不等于理解**。即使记忆被成功检索并注入 LLM 上下文，LLM 是否正确使用该记忆取决于 LLM 自身能力。

2. **衰减不保证安全遗忘**。时间衰减只降低排名，不删除数据。如需真正遗忘（如 GDPR 要求），需显式 `remove` 操作。

3. **Fact 提取是启发式的**。正则模式无法捕获所有类型的重要决策。压缩过程仍可能丢失无法被正则匹配的关键信息。

4. **嵌入器是瓶颈**。默认 HashingEmbedder 是确定性哈希，语义理解有限。向量检索的上限由嵌入器质量决定。

5. **最终一致性有窗口**。写入成功到索引更新之间存在不一致窗口，期间向量检索可能找不到刚写入的内容。

6. **L2 度量接线不完整（v1.2 新增）**。S_w、H_1、E_d 已接入生产路径；P_r、R_r、S_f 的 `on_*` 钩子仅测试调用。在 Phase 1 接线完成前，§6.1 的部分指标无法支撑 OT2 硬反馈。

7. **MB 基准与理论定义的差距**。MB2 使用关键词匹配而非完整语义改写；MB4 在 rerank 层模拟衰减而非全存储路径；MB6 测试 fact 提取上限而非完整压缩存活。基准通过表示**机械层合格**，不完全等价于理论 §6.2 的形式化定义。

---

## 附录 A：记忆系统符号表

| 符号 | 含义 |
|------|------|
| \(\mathcal{M}\) | 记忆系统完整状态 |
| \(\mathcal{K}_P\) | Profile 层（Owner 画像） |
| \(\mathcal{K}_E\) | Experience 层（跨项目经验） |
| \(\mathcal{K}_F\) | Facts 层（项目机读事实） |
| \(\mathcal{K}_J\) | ProjectMemory 层（MEMORY.md） |
| \(\mathcal{V}\) | 派生向量索引 |
| \(\mathcal{Q}_{\text{pending}}\) | 待审批记忆队列 |
| \(\alpha\) | 向量在混合检索中的权重 |
| \(\tau\) | 衰减半衰期（天） |
| \(\beta\) | 访问频次加权系数 |
| \(C_{\max}\) | Prefetch 总字符上限 |
| MA1-MA7 | 记忆系统公理 |
| MT1-MT7 | 记忆系统定理 |
| MB1-MB7 | 记忆基准任务 |
| \(P_r, R_r, S_w, S_f, E_d, H_1\) | 效果度量指标 |

## 附录 B：与父理论映射

| 父理论概念 | 子理论扩展 |
|------------|-----------|
| A6（记忆分层不可旁路） | **MA3 + MA7 强化**：增加路径隔离保证和决策门控 |
| P2（显式记忆优先于模型记忆） | **MA1 + MA2 具体化**：写入原子性和检索完备性 |
| M3（个人数据持久 vs 上下文有限） | **MA5 + MA6 解法**：衰减 + 容量限制 |
| T4（记忆不污染） | **MT4 继承**：增加围栏可区分性保证 |
| 定义 3.14（检索函数） | **M4 + M5 细化**：多层 + 混合 + rerank |
| 定义 3.15（注入变换） | **M7 细化**：过滤 + 截断 + 围栏 |
| 不变量 3.4（注入幂等性） | **保持**：同轮次 Inject 一次 |
| 命题 2.18（项目隔离） | **MT3 强化**：路径不重叠的形式化证明 |
| 命题 2.22（记忆不污染） | **MT4 继承并强化** |
