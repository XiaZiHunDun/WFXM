# Butler v4 — Skill 沉积层与记忆契约层子理论（L6 v2 草案）

> 版本：**2.0-draft** | 2026-06-09  
> **状态：已搁置（superseded）** — 产品改为 **经验优先 + Skill 兜底** 双轨信任策略，见 [`memory-roadmap.md` §检索信任级联](memory-roadmap.md#检索信任级联)。**不合并** \(\mathcal{K}_E\) 与 Skill；[`v4-memory-theory.md`](v4-memory-theory.md) v1.2 **继续有效**。  
> 父文档：[`v4-theoretical-baseline.md`](v4-theoretical-baseline.md) v3.1  
> 本文仅作历史备选，**勿按此实现 Store 迁移**。

---

## 0. 文档目的与核心命题

### 0.1 核心命题

1. **沉积知识（原 Experience + 程序性 Skill）在认识论上是同一类对象**，统一为 **Skill 沉积库** \(\mathcal{K}_S\)。  
2. **契约记忆（Profile / Facts / ProjectMemory）与规范（Rules）不是 Skill**，分层与 MA7 门控 **不变**。  
3. **Butler Skill ≠ 业界「丢目录即用」的 Agent Skill**；个人助手场景下，外部 Skill 必须经过 **隔离、扫描、待审、去重合并** 才能进入活性库。  
4. 融合目标不是「多一个 skills 目录」，而是 **单 Store、单检索、单注入、分 kind 治理**。

### 0.2 与 v1.2 的关系

| v1.2 (`v4-memory-theory`) | v2（本文） |
|---------------------------|------------|
| \(\mathcal{K}_E\) Experience 层 | \(\mathcal{K}_S\) Skill 沉积层（**语义超集**） |
| `experience.db` + 可选 `skills/*.md` 双轨 | **SkillStore SSOT**（sqlite+FTS；md 为视图/导入格式） |
| `hybrid_experience_search` + `SkillRouter` 双通道 | **`hybrid_skill_search` 单通道**（目标态） |
| 无 Skill 导入门控公理 | **MS2–MS4** 导入门控与去重 |
| MB1–MB7 | SB1–SB7（沉积层基准；契约层 MB 子集保留） |

### 0.3 术语：三种「Skill」

| 术语 | 含义 | 是否自动生效 |
|------|------|----------------|
| **Market Skill Bundle** | 外部生态（Claude Code / Cursor / Hub）发布的包 | 否 |
| **Skill Candidate** | 过 quarantine + guard 后进入 \(Q_{skill}\) 的候选 | 否 |
| **Butler Skill（活性）** | \( \mathcal{K}_S^{active} \) 中可被检索注入的条目 | 是（受 Router 与 cap 约束） |

---

## 第一章 需求公理化 — 三类知识的第一性原理

### 1.1 核心矛盾（继承父理论 M3）

\[
|\mathcal{K}| \gg W \quad \Rightarrow \quad \text{全量注入不可行，必须检索}
\]

管家记忆的额外矛盾（v1 已述）：**检索式注入引入信息损失**；v2 追加：

\[
|\mathcal{K}_S^{import}| \gg |\mathcal{K}_S^{active}| \quad \Rightarrow \quad \text{无门控则 Skill 冗余爆炸}
\]

### 1.2 认识论三分（v2 基础划分）

| 类 | 符号 | 回答的问题 | 写错代价 | 典型载体 |
|----|------|------------|----------|----------|
| **契约型记忆** | \(\mathcal{K}_{contract} = \mathcal{K}_P \cup \mathcal{K}_F \cup \mathcal{K}_J\) | 「是谁 / 项目约定是什么」 | 最高 | profile.json、MEMORY.md、facts.json |
| **沉积型 Skill** | \(\mathcal{K}_S\) | 「怎么做 / 曾学到什么 / 可复用流程」 | 中（可合并、可衰减） | SkillStore（演进自 experience.db） |
| **规范型 Rules** | \(\mathcal{R}\)（**不在** \(\mathcal{M}\) 内） | 「在何路径下必须/禁止」 | 违规即架构失信 | `.butler/rules`、read 触发的 AGENTS.md |

**推导结论**：

- 将 \(\mathcal{K}_E\) 迁入 \(\mathcal{K}_S\)：**不触动** 契约三分界。  
- 将 Rules 并入 Skill：**拒绝**（规范不应被 MA5 衰减或 post_session 改写）。  
- 将 Project 决策 Pending（\(Q_{memory}\)）并入 Skill Pending：**拒绝**（MA7 仅约束契约写入）。

### 1.3 管家 vs 业界 Agent Skill

| 维度 | 业界 Agent Skill（典型） | Butler Skill（v2） |
|------|-------------------------|-------------------|
| 安装 | 用户/IDE 放入目录即生效 | quarantine → guard → **\(Q_{skill}\)** → Owner 批准 |
| 信任模型 | 用户自负 | **默认不信任**外部正文 |
| 冗余 | 用户手动整理 | **MS3 去重合并**为默认路径 |
| 与记忆关系 | 常并列两套系统 | **沉积层合一** |
| 产品定位 | 开发者扩能力 | **个人助手可控知识库** |

### 1.4 契约层公理（自 v1.2 **原样继承**）

以下公理 **编号与含义不变**，仅上下文从「四层记忆」改为「契约三层 + Skill 沉积层」：

- **MA1** 写入原子性（Store ⊗ IndexSync，最终一致 + reindex）  
- **MA2** 检索完备性（存在性可检索，非任意 query）  
- **MA3** 域隔离（Tenant / Project 路径不交）  
- **MA4** 注入透明性（围栏、不改 transcript SSOT）  
- **MA5** 衰减单调性（**仅适用于** \(\mathcal{K}_S^{sediment}\) 等可衰减 kind，见 MS4）  
- **MA6** 容量有界（Profile / MEMORY / Facts / Prefetch；Skill 活性上限见 MS1）  
- **MA7** 契约安全写入（**仅** \(\mathcal{K}_J\) 决策类 → \(Q_{memory}\)）

### 1.5 Skill 沉积层公理（v2 新增 MS1–MS7）

**公理 MS1（活性上限）**：可参与路由的 Skill 数量有界。

\[
|\mathcal{K}_S^{active}| \leq N_S^{\max}
\]

超限时的操作序：**Consolidate → Archive → 拒绝 Append**，不得静默丢弃已批准条目。

**公理 MS2（导入门控）**：外部 Market Bundle 不得直接进入 \(\mathcal{K}_S^{active}\)。

\[
\text{Import}(bundle) \implies bundle \in Q_{skill} \quad \text{直至 Owner 批准}
\]

扫描失败（guard block）则 **Reject**，不入 \(Q_{skill}\)。

**公理 MS3（去重优先）**：相似度超过阈值时合并，禁止平行重复。

\[
\text{similar}(s, \mathcal{K}_S) > \theta \implies \text{Merge}(s, s^*) \quad \text{而非 } \text{Append}(s)
\]

\(\theta\) 与合并策略由 `SkillSimilarity` + `SkillConsolidator` 实现（与代码对齐）。

**公理 MS4（分 kind 衰减）**：衰减仅作用于沉积型，不作用于已批准 SOP / 外部已批准导入。

\[
\text{decay}(s) = \begin{cases}
2^{-\Delta t / \tau_{kind}} & kind \in \{\text{sediment}, \text{session\_echo}\} \\
1 \text{ 或 } 2^{-\Delta t / \tau_{proc}},\ \tau_{proc} \gg \tau_{sediment} & kind \in \{\text{approved}, \text{imported\_approved}\}
\end{cases}
\]

**公理 MS5（单轨检索）**：同一 query 对沉积层 **只有一个** Retrieve 入口（目标态）。

\[
\text{Retrieve}_S(q) = \text{Rerank}(\text{Hybrid}_S(q, \mathcal{K}_S^{active}))
\]

禁止并行 `SkillRouter` 全文注入 + `prefetch_turn_memory` experience 块 **双通道重复**（迁移期允许临时双轨，须在阶段 C 前收口）。

**公理 MS6（单轨注入）**：沉积层注入统一围栏（可保留 `<memory-context>` 标签名，语义改为 skill-context）。

\[
\text{Inject}(H, q) = \text{Fence}(\text{Prefetch}_S(q))
\]

**公理 MS7（session_echo 隔离）**：会话回声仅存档，不参与活性检索与向量索引。

\[
kind = \text{session\_echo} \implies s \notin \text{Retrieve}_S,\ s \notin \mathcal{V}
\]

（继承 v1 `conversation` 类别语义。）

### 1.6 与父理论映射

| 父公理/原则 | v2 扩展 |
|------------|---------|
| **A6** 记忆分层不可旁路 | 契约三层仍旁路不可混；沉积层统一为 SkillStore；**减少** experience/skill 双旁路 |
| **P2** 显式记忆优先 | MA1/MA2 + MS2/MS3 强化「显式 + 门控 + 去重」 |
| **P5** 静态优于动态 | MS2 Owner 批准为静态门；外部 Skill 不得仅靠 LLM 自律 |
| **M3** 上下文有限 | MS1 活性上限防爆炸 |
| **T4** 不污染 | MA4 + MS6 单轨围栏 |

---

## 第二章 形式化建模

### 2.1 系统状态 \(\mathcal{M}\)（v2）

**定义 SM1（记忆 + Skill 状态）**：

\[
\mathcal{M} = (\mathcal{K}_P,\ \mathcal{K}_S,\ \mathcal{K}_F,\ \mathcal{K}_J,\ \mathcal{V},\ Q_{memory},\ Q_{skill})
\]

| 分量 | 含义 |
|------|------|
| \(\mathcal{K}_P\) | Owner 画像（契约） |
| \(\mathcal{K}_S\) | Skill 沉积库（**原** \(\mathcal{K}_E\) **+** 程序性 Skill） |
| \(\mathcal{K}_F\) | 项目机读事实（契约） |
| \(\mathcal{K}_J\) | MEMORY.md（契约） |
| \(\mathcal{V}\) | 派生向量索引 \(\text{Embed}(\mathcal{K}_P \cup \mathcal{K}_S^{indexed} \cup \mathcal{K}_J)\) |
| \(Q_{memory}\) | 项目决策 Pending（**仅契约**） |
| \(Q_{skill}\) | 外部/合并待审 Skill Pending（**仅沉积**） |

**规范层** \(\mathcal{R}\) **不包含在** \(\mathcal{M}\) 中；通过 `read_file` → instruction walkup 叠加。

### 2.2 Skill kind 划分

**定义 SM2（Skill 条目）**：

\[
s = (id,\ text,\ kind,\ project,\ tags,\ triggers,\ meta,\ t_{create},\ n_{access})
\]

\[
kind \in \{\text{approved},\ \text{imported},\ \text{sediment},\ \text{session\_echo}\}
\]

| kind | 来源 | 路由 | 向量 | 衰减 |
|------|------|------|------|------|
| `approved` | Owner 手写 / 正式 SOP | ✅ | ✅ | MS4 弱/无 |
| `imported` | Market Bundle 批准后 | ✅ | ✅ | MS4 弱/无 |
| `sediment` | post_session、委派、显式记住 | ✅ | ✅ | MA5 标准 τ |
| `session_echo` | 会话同步（可选） | ❌ | ❌ | 仅 prune |

**状态机（导入）**：

```text
Market Bundle → quarantine → guard → Normalize → Q_skill
    → Owner Approve → similar? → Merge | Append → K_S^{active}
    → Owner Reject → discard
```

### 2.3 操作代数

**定义 SM3（契约操作 MemOp）** — 与 v1 M2 **相同**：

\[
\text{MemOp} ::= \text{Append}(L,m) \mid \text{Remove} \mid \text{Replace} \mid \text{Approve}_{memory} \mid \text{Reject}_{memory}
\]

\(L \in \{\text{Profile},\ \text{Facts},\ \text{ProjectMem}\}\)（**不再含 Experience**）

**定义 SM4（Skill 操作 SkillOp）**：

\[
\text{SkillOp} ::= \text{Upsert}(s) \mid \text{Archive}(id) \mid \text{Merge}(s_1,s_2) \mid \text{Approve}_{skill}(id) \mid \text{Reject}_{skill}(id) \mid \text{Import}(bundle)
\]

**原子性（继承 MA1）**：

\[
\text{Upsert}(s) = \text{Store}_S(s) \otimes \text{IndexSync}(s, \mathcal{V})
\]

### 2.4 检索模型

**定义 SM5（沉积层检索）**：

\[
\text{Retrieve}_S(q) = \text{Rerank}\left( \text{Hybrid}_S(q,\ \mathcal{K}_S^{active}) \right)
\]

\[
\text{Hybrid}_S = \text{FTS} \cup_{\text{RRF}} \text{Vector} \cup_{\text{optional}} \text{TriggerMatch}(triggers)
\]

契约层检索 **不变**：

\[
\text{Retrieve}_{contract}(q) = \text{Retrieve}_P \cup \text{Retrieve}_F \cup \text{Retrieve}_J
\]

**定义 SM6（全量预取）**：

\[
\text{Prefetch}(q) = \text{Truncate}\left( \text{Retrieve}_{contract}(q) \oplus \text{Retrieve}_S(q),\ C_{max} \right)
\]

目标态：**取消** 独立的 `inject_skill_context` 第二全文通道；`preferred_tools` 从 \(s.meta\) 读出，供 L4 `tool_selector` 使用。

### 2.5 存储拓扑（目标态）

**定义 SM7（Storage）**：

```text
Tenant 域 ~/.butler/tenants/{t}/
  memory/profile.json          → K_P
  memory/skill_store.db        → K_S (+ FTS5)     # 演进自 experience.db
  memory/memory_vectors.db     → V_tenant
  skills/_quarantine/          → 导入隔离（非 SSOT）
  skills/_pending.json         → Q_skill 索引（或等价）
  skills/*.md                  → 可选导出/兼容视图（非 SSOT）

Project 域 {workspace}/.butler/
  memory/MEMORY.md             → K_J
  facts.json                   → K_F
  memory/memory_vectors.db     → V_project
```

**不变量**：Skill 活性 SSOT 在 **SkillStore**；散落 md **不得**作为唯一真源（避免双轨复发）。

### 2.6 Market Bundle 规范化

**定义 SM8（Normalize）**：

\[
\text{Normalize}: \text{Bundle} \to \text{Candidate} = (name,\ description,\ triggers,\ content,\ provenance,\ trust=untrusted)
\]

要求：

1. 过 `scan_skill_text`（继承现有 guard）  
2. frontmatter 强制 `skill_kind=imported`  
3. 禁止保留「ignore previous instructions」类逃逸（已有 pattern）  
4. 安装记录写入 registry audit（已有 `append_audit`）

---

## 第三章 定理（继承 + 修订）

v2 **不重编号** MA/MT；沉积层定理表述替换 \(\mathcal{K}_E \to \mathcal{K}_S\)。

| 定理 | v2 修订要点 |
|------|-------------|
| **MT1** 写入原子性 | `Upsert`/`SkillStore` + IndexSync；reindex 收敛 |
| **MT2** 检索完备性 | 对 \(s \in \mathcal{K}_S^{active}\)，\(q=s.text\) 可命中；**排除** session_echo |
| **MT3** 域隔离 | 不变；项目 Skill 用 `project` 字段过滤，Store 仍在 Tenant |
| **MT4** 注入不污染 | MS6 单轨围栏 |
| **MT5** 衰减安全 | 仅对 `sediment`/`session_echo` 适用完整 MA5；`approved` 用 MS4 |
| **MT6** 容量有界 | MA6 + MS1 联合 |
| **MT7** 持久化一致 | SkillStore sqlite WAL；向量可 reindex |

**新定理候选（草案）MT-S1（导入门控安全）**：

\[
\text{Import}(b) \land \neg \text{Approved}(b) \implies b \notin \mathcal{K}_S^{active}
\]

**坚实度**：L1 路径 + L2 quarantine 实现。

**新定理候选 MT-S2（去重收敛）**：

在相似度度量满足等价关系近似时，重复 Import 在 MS3 下 **事件ual** 合并为单条目，\(|\mathcal{K}_S|\) 不随重复导入线性增长。

**坚实度**：L2（依赖 Consolidator 质量，LLM 不可用时走 deterministic fallback）。

---

## 第四章 与 Rules 的边界（防混）

| 维度 | \(\mathcal{K}_S\) | \(\mathcal{R}\) |
|------|-----------------|-----------------|
| 触发 | 用户 query 语义/触发词 | `read_file` 路径 glob |
| 内容 | 怎么做、事实沉积 | 必须/禁止 |
| 写入 | SkillOp / post_session | 人维护规则文件 |
| 衰减 | kind 依赖 | **无** |
| Pending | \(Q_{skill}\) | 无（不自动提炼） |
| 注入围栏 | MS6 | walkup 标题区分 |

**禁止**：将 `.butler/rules` 自动导入为 Skill 条目（会把规范变成可衰减沉积）。

---

## 第五章 实现映射 — 现状 vs 目标态

### 5.1 模块映射（目标态）

| 公理/定理 | 目标模块 | 现状（迁移前） |
|----------|----------|----------------|
| MA1/MT1 | `SkillStore.upsert` + `index_skill_row` | `add_experience` + `index_experience_row` |
| MS2 | `registry/skill_install` + **`Q_skill` 产品面** | quarantine ✅；**微信/CLI 待审 Skill ❌** |
| MS3 | `skills/similarity` + `consolidator` | 仅 **create** 路径；未接 post_session |
| MS5/MS6 | `prefetch_turn_skill` 单轨 | `prefetch_turn_memory` + `inject_skill_context` **双轨** |
| MS7 | `kind=session_echo` 过滤 | `category=conversation` ✅ |
| MA7 | `project_memory` Pending | ✅ 不变 |
| MS4 | `retrieval_ranking::type_adjusted_half_life` 扩展 kind | 按 category 部分存在 |

### 5.2 生命周期（目标态单图）

```text
写入（沉积）
  post_session / 显式记住 / butler_remember(scope=skill)
    → SkillOp.Upsert(kind=sediment)
    → MS3 相似则 Merge
    → Store_S ⊗ IndexSync

写入（导入）
  registry install / hub
    → quarantine → guard → Q_skill
    → Owner Approve → MS3 Merge → K_S^{active}

写入（契约）  [不变]
  butler_remember(scope=project_notes) → MA7 Pending → K_J

检索（每轮）
  q → Prefetch(q) = contract Retrieve ⊕ Retrieve_S
    → Fence → pre_llm_transform

规范（读文件后）
  read_file → rules_engine + AGENTS walkup  [不变]
```

### 5.3 API / scope 迁移表

| 现状 | 目标 | 兼容期 |
|------|------|--------|
| `butler_remember scope=owner_experience` | `scope=skill` 或 `skill_sediment` | alias 1 版本 |
| `ExperienceStore` | `SkillStore` | 表名 `experiences` 可保留 |
| `hybrid_experience_search` | `hybrid_skill_search` | 函数别名 |
| `skills_list` / `skill_view` | 读 SkillStore 元数据/正文 | 保留工具名 |
| `owner_experience` 诊断行 | `skill_sediment` 计数 | 诊断合并展示 |

---

## 第六章 度量模型 — SB 基准（沉积层）

### 6.1 指标（继承 + 扩展）

| 指标 | 公式 | v2 说明 |
|------|------|---------|
| \(S_w\) | 写入后召回成功比 | 沉积写入改指 \(\mathcal{K}_S\) |
| \(R_r, P_r, H_1\) | 同 v1 | 单轨 Prefetch 后更有意义 |
| \(E_d\) | 衰减误杀率 | 分 kind 报告 |
| **\(D_s\)**（新） | 重复导入合并率 | MS3 有效性 |
| **\(G_s\)**（新） | guard block 率 | 安全扫描 |
| **\(A_s\)**（新） | \(Q_{skill}\) 平均批准时延 | 运营指标 |

### 6.2 基准任务 SB1–SB7

| 编号 | 描述 | 继承 |
|------|------|------|
| SB1 | Profile 精确召回 | = MB1 |
| SB2 | 沉积 paraphrase 召回 | = MB2（写入 \(\mathcal{K}_S^{sediment}\)） |
| SB3 | 重启持久 | = MB3 |
| SB4 | sediment 衰减排序 | = MB4 |
| SB5 | 活性上限压力 | = MB5 + MS1 |
| SB6 | Fact 压缩锚点 | = MB6（契约层） |
| SB7 | 注入过滤 | = MB7 |
| **SB8** | 导入 Pending：未批准不可路由 | MS2 |
| **SB9** | 相似导入合并：两次导入同一 bundle 不增活性计数 | MS3 |

### 6.3 前提验证（测试规划）

| 编号 | 内容 | 继承 |
|------|------|------|
| P-MT1a–e | Store/IndexSync/reindex | 改名 SkillStore |
| P-MS1 | 活性超限拒绝或 consolidate | 新增 |
| P-MS2 | 未批准 imported 不在 Router 结果 | 新增 |
| P-MS3 | similar 触发 merge 而非第二行 | 新增 |
| P-MS4 | approved 条目 decay ≥ sediment | 新增 |

---

## 第七章 迁移阶段（实现路线图）

| 阶段 | 内容 | 理论守门 |
|------|------|----------|
| **T0** | 本文档评审冻结 SM1–SM8、MS1–MS7 | 契约层公理不变声明 |
| **T1** | 文档同步：`v4-theoretical-baseline` §2.6、`memory-roadmap` 沉积章节 | 双文档并存标注 |
| **T2** | SkillStore = experience.db 别名；`skill_kind` 列/标签；`conversation`→`session_echo` | P-MT 全绿 |
| **T3** | `butler_remember` scope 别名；post_session 写 `sediment` | SB2/SB3 |
| **T4** | \(Q_{skill}\) + 微信 `/技能待审`；接 registry install | SB8、MS2 |
| **T5** | 检索并轨：废弃独立 `inject_skill_context` 全文通道 | MS5/MS6、SB2 |
| **T6** | `skills/*.md` 降格为导出视图；活性仅 SkillStore | SM7 不变量 |
| **T7** | 删除 experience 对外术语；`v4-memory-theory` 归档 | 全 SB + 原 MB 契约子集 |

**回滚**：T2 起可保留 `experience.db` 文件名直至 T7；向量 reindex 不变。

---

## 第八章 能力边界与诚实声明

1. **MS3 合并质量依赖 Consolidator**；LLM 不可用时 deterministic merge 可能损失细节——须记录 `fallback_used`（代码已有）。  
2. **Market Skill 语义与 Butler kind 不完全同构**；Normalize 必损失信息，需 Owner 批准补偿。  
3. **单轨检索后**，`preferred_tools` 必须从 Store meta 读取；丢失 meta 则工具链退化。  
4. **契约层仍可能双通道**：system 快照 `build_memory_context` + Prefetch；v2 建议契约快照 **缩短**，沉积 **只走 Prefetch**（实现优化，非公理）。  
5. **Rules 仍不在 \(\mathcal{M}\)**；勿期待 Skill 融合解决编码规范问题。  
6. **本草案未改变 OT2 / G1-04 观测**；度量接线仍按 v1.2 诚实声明执行。

---

## 附录 A：符号表

| 符号 | 含义 |
|------|------|
| \(\mathcal{K}_S\) | Skill 沉积库（原 \(\mathcal{K}_E\) 超集） |
| \(\mathcal{K}_{contract}\) | \(\mathcal{K}_P \cup \mathcal{K}_F \cup \mathcal{K}_J\) |
| \(Q_{skill}\) | Skill 导入/合并待审队列 |
| \(Q_{memory}\) | 项目决策 Pending（契约） |
| \(\mathcal{R}\) | 规范层（Rules + walkup） |
| MA1–MA7 | 契约 + 通用记忆公理（继承） |
| MS1–MS7 | Skill 沉积层公理（v2 新增） |
| MT1–MT7 | 定理（沉积层表述替换 E→S） |
| SB1–SB9 | Skill 沉积层基准 |

## 附录 B：kind 与 v1 category 对照

| v1 `experience.category` | v2 `skill_kind` | 备注 |
|--------------------------|-----------------|------|
| `conversation` | `session_echo` | MS7 |
| `experience`, `note`, `delegation_note` | `sediment` | 默认迁移 |
| `preference` | `sediment` 或 promoted `approved` | 运营策略 |
| （无） | `approved` | 原 `skills/*.md` 正式 SOP |
| （无） | `imported` | 市场导入批准后 |

## 附录 C：开放问题（评审待决）

| # | 问题 | 选项 |
|---|------|------|
| C1 | 活性上限 \(N_S^{max}\) 默认 | 50 / 100 / 按 tenant 配置 |
| C2 | sediment 是否默认进 Router top-k | 与 approved 同池 / 分池配额 |
| C3 | \(Q_{skill}\) 与 \(Q_{memory}\) 微信命令 | 合并 `/待审` 分页 vs 独立 `/技能待审` |
| C4 | SkillStore 表名 | 保留 `experiences` vs 迁移 `skills` |
| C5 | 围栏标签 | 保留 `<memory-context>` vs 改 `<skill-context>` |

---

## 附录 D：文档维护

| 变更类型 | 同步义务 |
|----------|----------|
| 冻结 MS 公理 | `v4-theoretical-baseline` §2.6、`memory-roadmap`、`CONTRIBUTING.md` 记忆段 |
| 实现 T2+ | `v4-architecture.md`、`config/reference.md`、`.env.example` |
| 新增 `BUTLER_*` | 同上 + `butler-memory-phase-*.sh` 守门 |

**索引**：[`docs/README.md`](../README.md) · 运维：[`guides/memory-ops.md`](../guides/memory-ops.md)
