# Butler v4 — 开发引擎子理论（L4 层完整推导）

> 版本 1.5 | 2026-06-09  
> **工程层**：**L4 工具与能力**（+ L3 delegate 路径；九层：[`v4-layer-model.md`](v4-layer-model.md)；映射：[`layer-theory-engineering-map.md`](layer-theory-engineering-map.md)）  
> 父文档：`v4-theoretical-baseline.md` v3.1.2（10 定理 + OT1-OT2 / 12 公理含 OA1-OA3 / A12-A13 / 608+ 验证测试）
> 方法论：需求公理化 → 形式化建模 → 定理证明 → 能力差距分析 → 详细设计 → 工程验证
> 定位：将 L4 层从"黑盒委派"升级为"内置开发引擎"，为管家系统提供可控、可观测、可演化的开发能力
> **v1.3 变更**：新增第九章"编码知识层"——定理库 + 经验库 + 七元素分解 + 双重验证门；公理 CA1-CA4、定理 CT1-CT5、前提假设 H1-H12；更新能力边界声明
> **v1.5 变更**：补充 B8（SWE-bench Lite）基准；收窄 CD0/CD6/CD8/CA4 实现成熟度声明；区分「测试级通过」与「生产路径已接」；对齐父理论 L7 观测演化层  
> **v1.4 变更**：第九章全面完善——补充 CD0/CD8（规格/合成器/TC 生成）形式化；拆分 CA3 为入库准确性+实例化保持性；CA4 增加适用范围与终止前提；CA1 正交性精确化；CT1-CT5/CL1 证明链修正（补 H4 桥接、CL1 限定适用范围）；H6/H8/H11 分类修正为有条件理论确认；能力边界精确化；DT6/CD6 验证栈澄清；新增 H0/H13 前提

---

## 第一章 需求公理化 — 开发引擎的第一性原理

### 1.1 核心矛盾分析

父理论 M4' 指出了"开发深度 vs 管家广度"的矛盾，并以委派模型作为解法：

\[
\text{管家}(\text{breadth}) \xrightarrow{\text{delegate}} \text{子Agent}(\text{depth})
\]

但这个解法存在根本缺陷——**它将开发能力的全部语义推给了 LLM 黑盒**。父理论 §1.4 明确声明"管家不动手"（A3'），并在 §4.1 承认"开发质量上限取决于子 Agent LLM"。这意味着：

1. **不可观测**：管家不知道子 Agent 编辑了什么、为什么编辑、编辑是否正确
2. **不可控制**：管家无法指导编辑策略、搜索策略、验证策略
3. **不可替换**：开发能力与特定 LLM 的行为深度耦合
4. **不可演化**：无法在不替换 LLM 的情况下提升开发能力

本子理论将**公理 A3' 从"管家不动手"修正为"管家通过内置开发引擎动手"**——开发引擎是管家自身能力的一部分，而非外部黑盒。

### 1.2 管家开发引擎 vs 独立 IDE Agent

| 维度 | 独立 IDE Agent (Claude Code, Cursor) | 管家内置开发引擎 |
|------|--------------------------------------|-----------------|
| **交互通道** | 本地终端 / IDE 编辑器 | 微信远程 + CLI 调试 |
| **上下文源** | 当前打开文件 + LSP + 终端 | 记忆系统 + 项目知识 + PIM |
| **安全模型** | 本地信任 / sandbox | 远程 Owner 审批 + 权限格 |
| **会话模型** | 即时交互，低延迟 | 异步委派，高延迟可容忍 |
| **目标** | 尽快完成编辑 | 正确完成编辑 + 管家级报告 |
| **状态持久** | 无（每次会话独立） | 跨会话记忆 + 项目知识累积 |

**核心洞察**：管家开发引擎不需要追赶 IDE Agent 的交互速度，但必须在**正确性、可观测性、可审批性**上超越它们。管家场景下的编辑延迟 10 秒无关紧要，但编辑错误和不可回滚是不可接受的。

### 1.3 开发引擎公理

以下 7 条公理定义了管家内置开发引擎的不可动摇基础：

**公理 DA1（编辑原子性）**：所有代码变更可分解为有限个原子编辑操作的有序序列。每个原子操作要么完全成功，要么完全不应用。多文件编辑可组合为事务。

\[
\text{Change} = [e_1, e_2, \ldots, e_n], \quad \forall i: \text{apply}(e_i) \in \{\text{OK}, \text{FAIL}\}
\]

\[
\text{MultiEdit}([e_1, \ldots, e_n]) \implies \forall i: \text{apply}(e_i) = \text{OK} \quad \lor \quad \text{rollback\_all}
\]

**公理 DA2（可验证性）**：每次编辑后，系统状态可通过构建、测试或静态分析验证。验证结果为结构化数据（非文本），可被修复策略解析。

\[
\text{Verify}: \text{WorkspaceState} \to (\text{PASS} \mid \text{FAIL}(\text{Diagnostics}))
\]

**公理 DA3（上下文有界性）**：开发引擎在有限 token 窗口内工作。面对大型代码库，引擎使用搜索-聚焦-编辑策略，而非全量加载。

\[
\text{tokens}(\text{Codebase}) \gg W \implies \text{Locate}(\text{intent}) \to \text{Focus}(\text{files}) \to \text{Edit}(\text{focused})
\]

**公理 DA4（错误可修复性）**：编辑引入的可检测错误可通过有限步修复循环消除。修复循环有步数上限，超限后进入 STUCK 状态而非无限重试。

\[
\forall d \in \text{Diagnostics}: \exists k \leq K_{\max}: \text{Fix}^k(d) = \text{PASS} \quad \lor \quad \text{Fix}^{K_{\max}}(d) = \text{STUCK}
\]

**公理 DA5（管家一体性）**：开发引擎共享管家的记忆系统、审批流、上下文管线和 PIM 上下文。不是独立子系统，而是 AgentLoop 的增强模式。

\[
\text{DevEngine} \subseteq \text{AgentLoop} \quad (\text{模式增强，非独立进程})
\]

**公理 DA6（可观测性）**：开发引擎的每一步操作（搜索、编辑、验证、修复）都产生结构化记录，管家可据此向 Owner 报告进度、解释决策、提供审批依据。

\[
\forall \text{step} \in \text{DevLoop}: \text{step} \to (\text{Result}, \text{Trace}) \quad \text{where Trace is structured}
\]

**公理 DA7（可替换增强）**：外部开发工具（OpenCode、未来产品）通过 A7'（能力可插拔）接入，作为引擎的可选增强源，不是引擎的依赖。核心开发循环不依赖任何外部产品。

\[
\text{DevEngine}_{\text{core}} \cap \text{ExternalTools} = \emptyset \quad (\text{核心不依赖外部})
\]
\[
\text{DevEngine}_{\text{enhanced}} = \text{DevEngine}_{\text{core}} \cup \text{ExternalTools}_{\text{optional}}
\]

### 1.4 与父理论公理的关系

| 父公理 | 修正/扩展 | 说明 |
|--------|-----------|------|
| **A3'（管家不动手）** | **修正为 A3''** | 管家通过内置开发引擎动手。引擎是管家自身能力，不是外部委派 |
| **A4'（权限递减）** | 保持 | 开发引擎操作受权限格约束 |
| **A7'（可插拔）** | **强化** | 外部工具从"核心集成"降级为"可选增强" |
| **M4'（深度 vs 广度）** | **重新解决** | 不再通过外部委派解决，而是通过内置引擎模式切换 |

**修正公理 A3''（管家内置开发引擎）**：

\[
\text{管家主循环}(\text{role=butler}) \xrightarrow{\text{mode\_switch}} \text{开发引擎}(\text{内置增强模式})
\]

管家不再"不动手"，而是**通过内置开发引擎、在完整的记忆/审批/安全管线下动手**。

---

## 第二章 形式化建模 — 开发状态机与操作语义

### 2.1 开发状态 DevState

**定义 D1（开发状态）**：

\[
\text{DevState} = (\mathcal{F}, \mathcal{G}, \mathcal{V}, \mathcal{E}_h, \mathcal{S}_c)
\]

其中：
- \(\mathcal{F}\)（Files）：工作区文件集合 + 版本快照，\(\mathcal{F} = \{(p, c, t) : p \in \text{Path}, c \in \text{Content}, t \in \text{Timestamp}\}\)
- \(\mathcal{G}\)（Diagnostics）：诊断集合，\(\mathcal{G} = \{(p, l, \text{severity}, \text{msg}) : p \in \text{Path}, l \in \mathbb{N}, \text{severity} \in \{\text{error}, \text{warning}, \text{info}\}\}\)
- \(\mathcal{V}\)（VerifyResult）：最近一次验证结果，\(\mathcal{V} \in \{\text{PASS}, \text{FAIL}(\mathcal{G}), \text{UNKNOWN}\}\)
- \(\mathcal{E}_h\)（EditHistory）：本次任务的编辑序列（可回滚），\(\mathcal{E}_h = [(e_1, \text{undo}_1), \ldots, (e_n, \text{undo}_n)]\)
- \(\mathcal{S}_c\)（SearchContext）：已探索的代码区域，\(\mathcal{S}_c = \{(p, r, \text{relevance}) : p \in \text{Path}, r \in \text{Range}\}\)

**不变量 DI1（文件一致性）**：

\[
\forall (p, c, t) \in \mathcal{F}: \quad \text{disk\_content}(p) = c \quad \lor \quad p \text{ has been externally modified}
\]

当外部修改被检测到时（mtime 变化），DevState 进入 CONFLICT 状态。

### 2.2 编辑操作代数

**定义 D2（原子编辑操作）**：

\[
\text{Edit} ::= \text{Write}(p, c) \mid \text{Patch}(p, \text{old}, \text{new}) \mid \text{Delete}(p) \mid \text{Create}(p, c)
\]

**定义 D3（编辑语义）**：

\[
\text{apply}: \text{Edit} \times \mathcal{F} \to \mathcal{F} \cup \{\bot\}
\]

\[
\text{apply}(\text{Write}(p, c), \mathcal{F}) = \begin{cases}
\mathcal{F}[p \mapsto (p, c, \text{now})] & \text{if } p \in \text{dom}(\mathcal{F}) \wedge \text{mtime\_check}(p) \\
\bot & \text{otherwise}
\end{cases}
\]

\[
\text{apply}(\text{Patch}(p, \text{old}, \text{new}), \mathcal{F}) = \begin{cases}
\mathcal{F}[p \mapsto (p, c', \text{now})] & \text{if } \text{old} \in c_p \wedge |\text{matches}| = 1 \\
\bot & \text{otherwise}
\end{cases}
\]

其中 \(c' = c_p.\text{replace}(\text{old}, \text{new})\)

**定义 D4（事务性多文件编辑）**：

\[
\text{MultiEdit}([e_1, \ldots, e_n]) = \begin{cases}
\text{apply}(e_n, \ldots \text{apply}(e_1, \mathcal{F})) & \text{if } \forall i: \text{apply}(e_i, \cdot) \neq \bot \\
\mathcal{F} \quad (\text{rollback}) & \text{otherwise}
\end{cases}
\]

**定义 D5（撤销操作）**：

\[
\text{undo}: \text{Edit} \to \text{Edit}
\]

\[
\text{undo}(\text{Write}(p, c)) = \text{Write}(p, c_{\text{original}})
\]
\[
\text{undo}(\text{Patch}(p, \text{old}, \text{new})) = \text{Patch}(p, \text{new}, \text{old})
\]
\[
\text{undo}(\text{Create}(p, c)) = \text{Delete}(p)
\]
\[
\text{undo}(\text{Delete}(p)) = \text{Create}(p, c_{\text{original}})
\]

### 2.3 开发循环状态机

**定义 D6（开发循环状态）**：

\[
\Sigma_{\text{dev}} = \{\text{PLAN}, \text{LOCATE}, \text{EDIT}, \text{VERIFY}, \text{FIX}, \text{DONE}, \text{STUCK}, \text{REVIEW}\}
\]

**定义 D7（状态转移函数）**：

\[
\delta_{\text{dev}}: \Sigma_{\text{dev}} \times \text{Event}_{\text{dev}} \to \Sigma_{\text{dev}}
\]

| 当前状态 | 事件 | 目标状态 | 语义 |
|----------|------|----------|------|
| PLAN | plan\_complete | LOCATE | 方案确定，开始定位编辑点 |
| PLAN | plan\_trivial | EDIT | 简单任务，跳过搜索直接编辑 |
| LOCATE | files\_found | EDIT | 找到目标文件和编辑范围 |
| LOCATE | not\_found | PLAN | 需要修正搜索策略 |
| LOCATE | locate\_timeout | STUCK | 搜索超时 |
| EDIT | edit\_success | VERIFY | 编辑完成，进入验证 |
| EDIT | edit\_conflict | LOCATE | 文件冲突，重新定位 |
| EDIT | edit\_fail | FIX | 编辑操作失败（如 patch 无匹配） |
| VERIFY | verify\_pass | DONE | 验证通过，任务完成 |
| VERIFY | verify\_fail(diags) | FIX | 验证失败，进入修复循环 |
| VERIFY | verify\_skip | REVIEW | 无验证手段，人工审查 |
| FIX | fix\_applied | VERIFY | 修复已应用，重新验证 |
| FIX | fix\_count >= K_max | STUCK | 修复次数耗尽 |
| FIX | fix\_rollback | PLAN | 回滚所有编辑，重新规划 |
| REVIEW | owner\_approve | DONE | Owner 审批通过 |
| REVIEW | owner\_reject | PLAN | Owner 要求重做 |
| STUCK | — | terminal | 终态，报告失败原因 |
| DONE | — | terminal | 终态，报告成功结果 |

**命题 DP1（开发循环非环性）**：FIX→VERIFY 构成唯一的循环路径，且受 \(K_{\max}\) 限制。PLAN→LOCATE→PLAN 和 EDIT→LOCATE 为回退路径，不形成无限循环（受总迭代数 \(I_{\max}\) 约束）。

### 2.4 搜索策略形式化

**定义 D8（代码搜索函数）**：

\[
\text{Locate}: \text{Intent} \times \mathcal{F} \to [(\text{Path}, \text{Range}, \text{Relevance})]
\]

搜索策略分层：

1. **结构搜索**（最快）：文件名 glob、目录遍历
   \(\text{cost} = O(|\text{files}|), \quad \text{precision} = \text{low}\)

2. **文本搜索**（精确）：正则表达式匹配（rg）
   \(\text{cost} = O(|\text{codebase}|), \quad \text{precision} = \text{high for exact patterns}\)

3. **符号搜索**（语义级）：函数/类/变量定义与引用
   \(\text{cost} = O(|\text{AST nodes}|), \quad \text{precision} = \text{high}\)

4. **语义搜索**（模糊匹配）：嵌入向量相似度
   \(\text{cost} = O(|\text{chunks}| \times d), \quad \text{precision} = \text{medium}\)

**搜索策略选择规则**：

\[
\text{strategy}(\text{intent}) = \begin{cases}
\text{structural} & \text{if intent specifies filename/path} \\
\text{textual} & \text{if intent contains exact string/pattern} \\
\text{symbolic} & \text{if intent references function/class name} \\
\text{semantic} & \text{if intent is natural language description}
\end{cases}
\]

### 2.5 验证模型

**定义 D9（验证函数）**：

\[
\text{Verify}: \text{WorkspaceState} \times \text{VerifyConfig} \to \text{VerifyResult}
\]

\[
\text{VerifyResult} = \text{PASS} \mid \text{FAIL}(\text{Diagnostics}) \mid \text{TIMEOUT} \mid \text{SKIP}
\]

验证手段层次：

| 层次 | 手段 | 速度 | 覆盖度 | 前提 |
|------|------|------|--------|------|
| V1 | 语法检查（lint/format） | 秒级 | 表面错误 | 语言工具链已安装 |
| V2 | 类型检查（mypy/tsc） | 秒-分钟 | 类型错误 | 类型检查器已配置 |
| V3 | 单元测试（pytest/jest） | 分钟级 | 功能回归 | 测试套件存在 |
| V4 | 集成测试 | 分钟-小时 | 系统行为 | 测试环境就绪 |
| V5 | 构建验证（build） | 分钟级 | 编译/链接 | 构建系统已配置 |

**验证策略选择**：

\[
\text{verify\_level}(\text{edit}) = \begin{cases}
\text{V1} & \text{if edit is format-only} \\
\text{V1+V2} & \text{if edit changes signatures/types} \\
\text{V1+V2+V3} & \text{if edit changes behavior} \\
\text{V1+V5} & \text{if edit changes build config}
\end{cases}
\]

### 2.6 修复策略形式化

**定义 D10（修复函数）**：

\[
\text{Fix}: \text{Diagnostics} \times \text{DevState} \to [\text{Edit}]
\]

修复策略分级：

1. **直接修复**：诊断信息直接指示修复方案
   - 例：`unused import X` → `Delete import X`
   - 例：`missing semicolon at line 42` → `Patch(file, line42, line42+';')`

2. **上下文修复**：需要理解周围代码的修复
   - 例：`type error: expected int, got str` → 需要追溯赋值源

3. **结构修复**：需要重新规划编辑策略
   - 例：`test_foo failed: assert expected != actual` → 回到 PLAN 重新理解需求

4. **回滚修复**：多次修复失败，回滚所有编辑重新开始
   - 触发条件：\(\text{fix\_count} \geq K_{\max} / 2\) 且进展停滞

---

## 第三章 定理证明 — 开发引擎关键性质

### 定理 DT1：编辑安全（Edit Safety）

**陈述**：在 read-before-edit + atomic write 机制下，开发引擎的编辑操作不会丢失文件数据。并发外部修改被检测并拒绝。

**前提**：
- (P-DT1a) `read_state.py` 正确记录 mtime
- (P-DT1b) `atomic_write_text` 使用 temp + rename
- (P-DT1c) 编辑操作在 apply 前检查 mtime

**证明**：

1. **无并发丢失**：`read_file(p)` 记录 `(p, mtime_0, content_hash_0)`。后续 `write_file(p, c')` 在写入前检查 `mtime(p) == mtime_0`。若外部程序在此期间修改了 `p`，`mtime(p) > mtime_0`，写入被拒绝并返回错误。
2. **原子写入**：`atomic_write_text` 先写临时文件 `p.tmp`，再 `os.replace(p.tmp, p)`。`os.replace` 在 POSIX 系统上是原子操作。即使进程在写入过程中崩溃，`p` 仍保持原内容（`p.tmp` 为残留文件）。
3. **MultiEdit 回滚**：事务性编辑维护 undo 栈。若第 \(i\) 个编辑失败，逆序执行 \(\text{undo}(e_{i-1}), \ldots, \text{undo}(e_1)\)。

**坚实度**：**L1 架构保证**。atomic write + mtime check 是代码路径静态保证。 ∎

---

### 定理 DT2：开发循环终止（Dev Loop Termination）

**陈述**：开发循环在有限步内终止于 DONE、STUCK 或 REVIEW。

**前提**：
- (P-DT2a) 总迭代上限 \(I_{\max}\)（默认 24）
- (P-DT2b) 修复循环上限 \(K_{\max}\)（默认 3）
- (P-DT2c) 搜索超时上限（15s/次）
- (P-DT2d) 验证超时上限（配置化，默认 300s）

**证明**：

定义进度度量函数 \(\mu: \Sigma_{\text{dev}} \to \mathbb{N}\)：

\[
\mu(\text{state}) = I_{\max} - i + K_{\max} - k
\]

其中 \(i\) 为当前迭代数，\(k\) 为当前修复次数。

每个状态转移至少消耗一个单位的 \(\mu\)：
- PLAN→LOCATE, LOCATE→EDIT, EDIT→VERIFY, VERIFY→DONE: \(i \gets i + 1\)
- FIX→VERIFY: \(k \gets k + 1\)
- FIX(k >= K_max)→STUCK: 终止
- 任何状态且 \(i \geq I_{\max}\)→STUCK: 终止

因此 \(\mu\) 严格递减，且 \(\mu = 0\) 时必然进入终态。

\[
\text{steps} \leq I_{\max} \times (1 + K_{\max}) < \infty
\]

**坚实度**：**L2 数学保证**。仅依赖有限常数。 ∎

---

### 定理 DT3：权限保持（Permission Preservation）

**陈述**：开发引擎执行的所有操作是当前 AgentLoop 权限集的子集。开发引擎不引入权限提升。

**前提**：
- (P-DT3a) 开发引擎使用的工具全部来自 AgentLoop 的工具注册表
- (P-DT3b) 开发引擎不直接调用系统 API，而是通过工具 dispatch

**证明**：

开发引擎的所有操作映射为工具调用：

\[
\text{DevOp} \to \text{ToolCall} \subseteq \mathcal{T}_{\text{current\_role}}
\]

| 开发操作 | 映射工具 | 权限要求 |
|----------|----------|----------|
| 读文件 | `read_file` | 项目只读 |
| 写文件 | `write_file` | 项目写入 |
| 补丁 | `patch` | 项目写入 |
| 搜索 | `search_files` | 项目只读 |
| 终端 | `terminal` | 终端权限 |
| 删除 | `delete_file` | 项目写入 |

所有工具调用经过 `dispatch_tool` → `check_project_permission_block` → 权限检查。开发引擎不旁路此管线。

结合父定理 T3'（权限不可提升）：\(\mathcal{T}_{\text{dev\_engine}} \subseteq \mathcal{T}_{\text{role}}\)。

**坚实度**：**L3 配置保证**。依赖工具注册表的正确维护。 ∎

---

### 定理 DT4：上下文有界（Context Bounded）

**陈述**：开发循环的上下文消耗有上界。搜索-聚焦-编辑策略保证不因代码库规模而溢出上下文窗口。

**前提**：
- (P-DT4a) 搜索结果有截断上限（50 matches）
- (P-DT4b) 文件读取有大小限制（1MB / 1000 行）
- (P-DT4c) 五阶段上下文管线正常运行（T1'）

**证明**：

开发循环每步注入上下文的量有上界：

\[
W_{\text{step}} \leq \underbrace{W_{\text{search}}}_{\leq 50 \times 200 \text{chars}} + \underbrace{W_{\text{read}}}_{\leq 1000 \text{lines} \times 100 \text{chars/line}} + \underbrace{W_{\text{diag}}}_{\leq 100 \text{entries} \times 200 \text{chars}}
\]

\[
W_{\text{step}} \leq 10\text{K} + 100\text{K} + 20\text{K} = 130\text{K chars} \approx 32.5\text{K tokens (heuristic)}
\]

这在典型上下文窗口（128K-200K tokens）内。多步累积由 L2 五阶段管线（Spill→Prune→Compact）控制，旧步骤的工具结果被剪枝。

**坚实度**：**L2 数学保证 + L4 LLM 依赖**（剪枝时机依赖 token 估算）。 ∎

---

### 定理 DT5：回滚安全（Rollback Safety）

**陈述**：开发引擎的任意编辑序列可通过 EditHistory 完全撤销，恢复到编辑前的文件状态。

**前提**：
- (P-DT5a) 每个编辑操作记录其 undo 操作
- (P-DT5b) 原始文件内容在编辑前被快照
- (P-DT5c) 无外部并发修改（单 Owner 假设）

**证明**：

设编辑历史为 \(\mathcal{E}_h = [(e_1, u_1), (e_2, u_2), \ldots, (e_n, u_n)]\)，其中 \(u_i = \text{undo}(e_i)\)。

回滚操作定义为逆序执行 undo 序列：

\[
\text{Rollback}(\mathcal{E}_h, \mathcal{F}_n) = \text{apply}(u_1, \text{apply}(u_2, \ldots \text{apply}(u_n, \mathcal{F}_n)))
\]

由 D5 的 undo 定义：\(\text{apply}(\text{undo}(e), \text{apply}(e, \mathcal{F})) = \mathcal{F}\)

因此 \(\text{Rollback}(\mathcal{E}_h, \mathcal{F}_n) = \mathcal{F}_0\)（编辑前状态）。

**前提 P-DT5c 的必要性**：若有外部并发修改，mtime 检查会导致 undo 操作失败。此时回滚为部分回滚（best-effort），需人工干预。

**坚实度**：**L1 架构保证**（单 Owner 无并发时）。 ∎

---

### 定理 DT6：诊断完备（Diagnostic Completeness）

**陈述**：如果编辑引入了验证工具可检测的错误，Verify 步骤一定能发现。

**前提**：
- (P-DT6a) 验证工具链已安装且可执行
- (P-DT6b) 验证命令的输出可被解析为结构化诊断
- (P-DT6c) 验证步骤涵盖编辑涉及的文件

**证明**：

设编辑 \(e\) 引入错误集 \(E = \{e_1, \ldots, e_m\}\)。Verify 执行验证命令 \(v\)，输出 \(\text{diag}(v)\)。

\[
\forall e_i \in E: \quad e_i \in \text{detectable}(v) \implies e_i \in \text{diag}(v)
\]

完备性受限于验证工具的能力——V1（lint）检测格式错误，V2（type check）检测类型错误，V3（test）检测行为回归。但逻辑错误（功能正确但不符合需求）不在验证工具的检测范围内。

**坚实度**：**L3 配置保证**。完备性以验证工具链的安装和正确配置为前提。 ∎

---

### 定理 DT7：外部工具可替换（External Tool Substitutability）

**陈述**：核心开发循环不依赖任何特定外部工具（OpenCode 等）。外部工具的移除或替换不影响核心引擎功能。

**前提**：
- (P-DT7a) 核心操作（编辑、搜索、验证）完全由内置工具实现
- (P-DT7b) 外部工具通过 A7' 扩展接口接入，与核心操作无强依赖

**证明**：

核心开发循环的操作集：

\[
\text{CoreOps} = \{\text{read\_file}, \text{write\_file}, \text{patch}, \text{search\_files}, \text{list\_directory}, \text{terminal}\}
\]

所有 CoreOps 在 Butler 内置工具注册表中，不依赖 MCP 或外部进程。

外部工具（如 `opencode_task`）在 `_BUTLER_EXTRA_TOOLS` 中的条件添加：

\[
\text{BUTLER\_OPENCODE\_ENABLED} = 0 \implies \text{opencode\_task} \notin \mathcal{T}
\]

移除外部工具后，核心循环 PLAN→LOCATE→EDIT→VERIFY→FIX 仍可完整执行。

**坚实度**：**L1 架构保证**。工具注册表的条件加载是代码路径保证。 ∎

---

## 第四章 能力差距分析 — 对照顶级 Coding Agent

### 4.1 核心能力矩阵

| 能力维度 | Butler 当前 | Claude Code | Cursor Agent | 目标状态 |
|----------|------------|-------------|--------------|----------|
| **编辑模型** | search-replace only | multi-strategy | search-replace + apply | 统一 diff + multi-hunk + MultiEdit 事务 |
| **搜索模型** | rg 正则 only | rg + exploration | semantic + grep | rg + glob + ctags/treesitter + 语义搜索 |
| **验证模型** | 无自动化 | 自主 TDD | linter loop | 分层验证 V1-V5 + 自动触发 |
| **修复模型** | corrective recall | stderr → retry | problem matcher | 结构化诊断 → 分级修复策略 |
| **上下文模型** | 通用压缩 | @files + compaction | @codebase + symbols | 代码感知聚焦 + 相关性评分 |
| **终端模型** | 严格白名单 | 完全自由 | sandbox | 开发 profile 自适应 + 审批 |
| **Git 模型** | 基础 read + guarded write | 完整 | 完整 + PR | 完整 git 操作 + 安全审批 |
| **记忆/知识** | 会话压缩 | 无跨会话 | 无跨会话 | **优势项**：跨会话记忆 + 项目知识 |
| **安全模型** | Owner 审批 + 权限格 | 本地信任 | sandbox | **优势项**：远程可控 + 分级审批 |
| **多项目** | 项目切换 + 隔离 | 单目录 | workspace | **优势项**：多项目编排 |

### 4.2 Butler 的差异化优势（不放弃）

1. **跨会话记忆**：记住项目架构、个人偏好、历史决策
2. **远程安全控制**：Owner 通过微信审批关键操作
3. **多项目编排**：同时管理多个项目，跨项目知识迁移
4. **PIM 集成**：开发任务与个人日程、联系人、提醒联动
5. **结构化报告**：向非技术 Owner 解释开发进展

### 4.3 必须补齐的能力（高优先级）

1. **编辑能力升级**：统一 diff 解析 + multi-hunk apply + MultiEdit 事务
2. **自动验证循环**：编辑后自动运行 lint/test/build + 结构化诊断解析
3. **代码导航增强**：ctags/treesitter 符号索引 + 语义搜索
4. **修复闭环**：诊断 → 定位 → 修复 → 重验证的自动化循环
5. **开发 profile 终端**：为 dev 角色自动放宽终端白名单

### 4.4 暂不追赶的能力（低优先级）

1. **IDE 集成**：不需要 — 管家的 UI 是微信/CLI
2. **实时流式编辑**：不需要 — 异步模型可接受
3. **无限制 shell**：不需要 — 安全模型要求可控终端

---

## 第五章 详细设计 — 开发引擎架构

### 5.1 模块总览

```
butler/dev_engine/
├── __init__.py           # 包入口 + 工厂
├── dev_state.py          # DevState 数据结构 + 编辑历史
├── dev_loop.py           # 开发循环状态机 (PLAN→LOCATE→EDIT→VERIFY→FIX)
├── edit_ops.py           # 编辑操作代数（atomic write, diff apply, multi-edit）
├── diagnostics.py        # 诊断收集器（terminal output → structured diagnostics）
├── code_search.py        # 多策略代码搜索（rg + glob + ctags + semantic）
├── verify.py             # 分层验证（lint/typecheck/test/build）
├── fix_strategy.py       # 修复策略选择器（diagnostic → fix plan）
├── dev_context.py        # 代码感知上下文管理（relevance scoring）
└── dev_tools.py          # 开发引擎专用工具注册（verify, rollback, dev_status）
```

### 5.2 与 AgentLoop 的集成方式

开发引擎**不是独立进程**，而是 AgentLoop 的增强模式。集成点：

1. **工具注入**：当 `role=dev` 时，注册 `dev_verify`、`dev_rollback`、`dev_status` 等增强工具
2. **系统提示增强**：注入开发循环指导（PLAN→LOCATE→EDIT→VERIFY）
3. **后置钩子**：edit 工具完成后触发 DevState 更新和自动验证
4. **上下文增强**：将 DevState（当前诊断、编辑历史）注入上下文

```
AgentLoop
  ├── 标准模式（butler/lead）
  │     └── 使用标准工具集
  └── 开发模式（dev）       ← 增强
        ├── 标准工具集
        ├── + DevState 跟踪
        ├── + 自动验证触发
        ├── + 诊断注入上下文
        └── + dev_verify / dev_rollback / dev_status 工具
```

### 5.3 关键设计决策

**DD1: 开发循环作为系统提示指导**

开发循环状态机（PLAN→LOCATE→EDIT→VERIFY→FIX）**不是硬编码的控制流**，而是通过系统提示和增强工具引导 LLM 遵循的工作流。这保持了 LLM 的灵活性，同时通过 DevState 跟踪和自动验证提供结构化框架。

**DD2: 验证自动触发**

当 `write_file` 或 `patch` 完成后，自动运行与编辑文件类型匹配的验证命令。验证结果作为结构化诊断注入下一轮 LLM 上下文。

\[
\text{post\_edit\_hook}(e) \to \text{Verify}(\text{affected\_files}(e)) \to \text{inject\_diagnostics}(\text{context})
\]

**DD3: 诊断结构化**

将终端输出（pytest/ruff/tsc/gcc 等）解析为结构化诊断：

```python
@dataclass
class Diagnostic:
    file: str
    line: int
    column: int
    severity: str  # error | warning | info
    message: str
    source: str    # pytest | ruff | tsc | gcc | ...
    rule: str      # E501 | unused-import | ...
```

**DD4: 编辑历史作为 DevState 组件**

每次 `write_file`/`patch`/`delete_file` 完成后，记录到 `DevState.edit_history` 中。提供 `dev_rollback` 工具允许 LLM 撤销最近的编辑。

**DD5: 外部工具降级为增强源**

OpenCode 等外部工具通过 `opencode_task` 工具可选接入。核心循环不依赖它们。外部工具的使用场景：
- 需要特定语言的深度 LSP 分析时
- 需要执行 Butler 终端白名单外的命令时
- 需要并行处理多个子任务时

### 5.4 新增工具定义

| 工具 | 描述 | 触发条件 |
|------|------|----------|
| `dev_verify` | 运行分层验证（lint/test/build）并返回结构化诊断 | 手动调用或 post-edit 自动触发 |
| `dev_rollback` | 回滚最近 N 次编辑操作 | LLM 判断编辑方向错误时 |
| `dev_status` | 查看当前 DevState（编辑历史、诊断状态、搜索上下文） | 开发循环任意阶段 |
| `dev_search_symbols` | 搜索函数/类/变量定义和引用 | LOCATE 阶段 |

### 5.5 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `BUTLER_DEV_ENGINE` | `1` | 启用开发引擎增强 |
| `BUTLER_DEV_AUTO_VERIFY` | `1` | 编辑后自动验证 |
| `BUTLER_DEV_VERIFY_TIMEOUT` | `300` | 验证超时秒数 |
| `BUTLER_DEV_MAX_FIX_ROUNDS` | `3` | 最大修复轮数 K_max |
| `BUTLER_DEV_ROLLBACK_ENABLED` | `1` | 启用编辑回滚 |
| `BUTLER_DEV_DIAGNOSTICS_INJECT` | `1` | 诊断自动注入上下文 |

---

## 第六章 工程前提验证矩阵

### 6.1 公理验证

| ID | 公理 | 验证方法 | 状态 |
|----|------|----------|------|
| P-DA1 | 编辑原子性 | atomic_write_text 崩溃安全测试 + MultiEdit 回滚测试 | **通过** (10/10) |
| P-DA2 | 可验证性 | 验证命令可执行 + 输出可解析 | **通过** (6/6) |
| P-DA3 | 上下文有界 | 搜索结果截断 + 文件读取限制 | **通过** (3/3) |
| P-DA4 | 错误可修复 | 修复循环终止 + 诊断→修复映射 | **通过** (3/3) |
| P-DA5 | 管家一体性 | DevEngine 使用 AgentLoop 工具注册表 | **通过** (2/2) |
| P-DA6 | 可观测性 | 每步产生结构化 Trace | **通过** (3/3) |
| P-DA7 | 可替换增强 | 移除 opencode_task 后核心循环完整 | **通过** (2/2) |

### 6.2 定理验证

| ID | 定理 | 验证方法 | 依赖前提 | 状态 |
|----|------|----------|----------|------|
| P-DT1 | 编辑安全 | mtime 并发修改检测 + atomic write 崩溃测试 | P-DT1a/b/c | **通过** (3/3) |
| P-DT2 | 循环终止 | I_max 和 K_max 倒计时测试 | P-DT2a/b/c/d | **通过** (5/5) |
| P-DT3 | 权限保持 | dev 工具集 ⊆ 注册表 | P-DT3a/b | **通过** (2/2) |
| P-DT4 | 上下文有界 | 搜索/读取/诊断结果大小上界 | P-DT4a/b/c | **通过** (3/3) |
| P-DT5 | 回滚安全 | 编辑→回滚→验证原始状态 | P-DT5a/b/c | **通过** (4/4) |
| P-DT6 | 诊断完备 | 注入已知错误→验证检出 | P-DT6a/b/c | **通过** (2/2) |
| P-DT7 | 外部可替换 | OPENCODE_ENABLED=0 时核心循环完整 | P-DT7a/b | **通过** (2/2) |

---

## 第七章 能力边界与诚实声明

### 7.1 开发引擎能力边界

| 边界 | 量化估计 | 缓解 |
|------|----------|------|
| 编辑正确性 | 取决于 LLM 生成质量 | 验证循环 + 回滚机制 |
| 验证覆盖度 | 取决于项目测试套件完备度 | 多层验证（V1-V5）|
| 搜索精度 | 符号搜索取决于语言工具链 | 多策略降级 |
| 修复成功率 | 取决于诊断信息质量 + LLM 理解 | K_max 限制 + 回滚 |
| 终端命令范围 | 受白名单约束 | dev profile 自动放宽 |
| 大文件编辑 | 受上下文窗口限制 | 搜索-聚焦策略 |

### 7.2 诚实声明

1. **开发引擎不替代人类开发者**。它是 LLM 驱动的自动化工具，能力上限受 LLM 质量和项目测试覆盖度约束。

2. **验证不等于正确**。V1-V5 验证检测的是可检测错误。逻辑错误（代码运行但不符合需求）超出自动验证范围。

3. **修复循环不保证收敛到正确解**。K_max 保证终止，但不保证修复成功。STUCK 是合法终态。

4. **符号搜索依赖语言工具链**。对没有 LSP/ctags 支持的语言，退化为文本搜索。

5. **管家一体性引入耦合**。开发引擎与 AgentLoop 共享上下文管线，意味着 PIM 上下文可能与代码上下文竞争窗口空间。

---

## 第八章 效果度量与对比基准

> 新增于 v1.2（2026-06-07）。填补第七章 §7.1 中"量化估计 → 取决于 LLM"的空白。

### 8.1 三层度量体系

| 层次 | 度量内容 | 实现 | 状态 |
|------|---------|------|------|
| **L1: 结构正确性** | 状态机转移合法、回滚成功、终止有界 | `tests/dev_engine/test_dev_engine_theory.py` (120+ tests) | ✅ |
| **L2: 运行时效果** | 任务完成率、编辑精度、修复收敛率、首次通过率 | `butler/dev_engine/dev_metrics.py` | ✅ |
| **L3: 对比基准** | 标准化任务集上的端到端表现 | `butler/dev_engine/dev_benchmark.py` | ✅ |

### 8.2 Layer 2 — 运行时效果指标

每次 `create_dev_state()` 创建任务时自动注册到全局 `MetricsCollector`。每次 `transition()` 自动发射度量事件。

**核心指标定义**：

| 指标 | 公式 | 含义 |
|------|------|------|
| 完成率 \(R_c\) | \(\frac{\|\{t : \text{outcome}(t) = \text{DONE}\}\|}{\|\{t : \text{outcome}(t) \in \{\text{DONE}, \text{STUCK}, \text{ABANDONED}\}\}\|}\) | 成功完成的任务比例 |
| STUCK 率 \(R_s\) | \(\frac{\|\{t : \text{outcome}(t) = \text{STUCK}\}\|}{\text{finished}}\) | 耗尽重试进入终态的比例 |
| 编辑精度 \(P_e\) | \(\frac{\text{verify\_passes}}{\text{total\_edits}}\) | 编辑后首次验证通过比例 |
| 首次通过率 \(R_{fp}\) | \(\frac{\|\{t : \text{DONE} \land \neg \text{entered\_fix}\}\|}{\|\{t : \text{DONE}\}\|}\) | 无需修复循环直接完成的比例 |
| 修复收敛率 \(C_f\) | \(\frac{\text{fix\_exits\_to\_verify}}{\text{fix\_entries}}\) | 修复循环成功收敛的比例 |
| 平均迭代 \(\bar{I}\) | \(\frac{\sum_{t \in \text{DONE}} I(t)}{\|\text{DONE}\|}\) | 成功任务的平均状态转移次数 |

**工具接口**：`dev_metrics` 工具提供 `summary`（聚合）、`full`（含任务列表）、`task`（单任务详情）三种详细级别。

### 8.3 Layer 3 — 对比基准框架

8 项内置基准任务覆盖开发引擎的关键能力维度：

| 编号 | 类别 | 描述 | 预期结局 | 测试维度 |
|------|------|------|---------|---------|
| B1 | 语法修复 | 修复 Python 缺少冒号 | DONE (首次通过) | 直接编辑能力 |
| B2 | 逻辑 Bug | 修复 off-by-one 错误 | DONE (经 FIX) | 定位 + 修复循环 |
| B3 | 新增函数 | 创建 fibonacci 函数 | DONE (首次通过) | 代码生成能力 |
| B4 | 重构重命名 | 跨文件 rename | DONE (首次通过) | 多文件编辑 |
| B5 | 修复测试 | 修改代码使测试通过 | DONE (经 FIX) | 测试驱动修复 |
| B6 | 不可能修复 | 持续失败的类型错误 | STUCK | 终止能力（DT2） |
| B7 | 回滚恢复 | 编辑失败→回滚→重编辑 | DONE | 回滚恢复能力（DT5） |
| B8 | SWE-bench Lite | 15 实例 oracle patch + pytest 验证 | DONE | 真实仓库修复能力（扩展基准） |

**当前基线结果**（v1.2，B1–B7）：

```
完成率:       85.7%  (6/7 — B6 设计为 STUCK)
首次通过率:   50.0%  (3/6 DONE 任务)
编辑精度:     78.6%
修复收敛率:   75.0%
平均迭代:     4.7 次/任务
平均编辑:     1.2 次/任务
```

**注意**：以上为**引擎机械能力**的基线（使用预定义的 oracle 编辑序列），不是 LLM 端到端效果。LLM 端到端效果需要在生产环境中收集 L2 指标后获得。

### 8.4 能力量化的局限性

1. **L3 基准使用 oracle 编辑**：基准任务的编辑序列是预定义的正确操作，不经过 LLM 决策。这测量的是引擎的状态管理和度量收集能力，不是 LLM 的编码能力。

2. **L2 指标需要生产数据积累**：首次部署时 L2 指标为空。需要实际运行开发任务后才能获得有意义的效果数据。

3. ~~**缺少跨系统对比基准**~~ **部分缓解（v1.5）**：B8 接入 SWE-bench Lite 15 实例（`swebench_lite.py`），使用 oracle patch 验证引擎机械层。仍为 oracle 模式，非 LLM 端到端；与 Claude Code / Cursor 的直接对比仍不可行。

4. **B8 未纳入发版回归门（v1.5 新增）**：B8 可在本地/CI 运行，但尚未绑定 `butler-deploy.sh update` 自动回归。Phase 3 实施项。

### 8.5 编码知识层实现成熟度（v1.5 新增）

理论第九章（CA1-CA4 / CD0-CD8 / CT1-CT5）按**实现成熟度**分为三级，避免「测试通过 ≡ 生产生效」的过度承诺：

| 级别 | 含义 | 组件 |
|------|------|------|
| **T1 测试级** | 模块存在 + pytest 通过，未接入生产路径 | CD0 Parse/Spec、`synthesize()`、`generate_test_cases()` |
| **T2 检测级** | 接入 post-edit / delegate 初始化，起 advisory 作用 | `dual_verify()`、T01–T10 AST checkers、`process_task()`、`load_seed_if_empty()` |
| **T3 阻断级** | 违反时阻止输出或中断流程 | CA4 严格模式（`BUTLER_CODING_STRICT=1`）——**已 opt-in 实证**（2026-07-13，pilot report 见 `docs/plans/pilot-reports/pilot-report-G2-08-2026-07-13.md`） |

**关键收窄声明**：

| 理论组件 | 理论描述 | 实际实现 | 成熟度 |
|----------|----------|----------|--------|
| CD0（规格解析） | 任务 → 结构化规格 \(S\) | 关键词启发式 `process_task()`，无 `parse_spec()` | T1 |
| CD6（GenTC） | 等价类测试生成 + 执行 | 静态 `_THEOREM_TEST_PATTERNS`，未在 DevLoop 执行 | T1 |
| CD8（Synth） | 定理约束下的程序合成 | `synthesize()` 函数存在，未注入 delegate prompt | T1 |
| CA4（严格模式） | 双重验证失败则 STUCK 不输出 | `apply_coding_strict_pilot_gate` 已接 4-gate 链；首次 pilot 真跑 2026-07-14（verdict NO_VIOLATIONS，捕获率 0.0000）：`docs/plans/pilot-reports/pilot-report-G2-08-2026-07-14.md` | T2（advisory）/ T3（opt-in + 真跑实证） |
| T02/T07 checkers | 组合性 / 幂等性形式化验证 | AST 启发式，覆盖窄于完整形式化陈述 | T2 |
| 经验库 | 跨任务知识积累 | 种子 15 条 + 成功 delegate 提取；挖掘未触发 | T2 |

---

## 附录 E-bis：实现一致性修复记录（2026-06-07）

| 编号 | 缺陷 | 修复 | 影响定理 |
|------|------|------|---------|
| DE-1 | `tool_batch._dev_engine_post_edit` 对 patch/delete 未保存 `original_content`，导致回滚 undo 失败 | 统一从 `_fetch_pre_edit_snapshot` 获取快照并写入所有编辑类型的 `EditRecord.original_content` | DT1/DT5（编辑安全/回滚） |
| DE-2 | `_run_auto_verify` 验证失败后未触发 `fix_applied` 事件，`fix_count` 始终为 0，K_max 限制无效 | 验证失败且状态进入 FIX 后自动触发 `fix_applied` 递增 `fix_count` | DT2（循环终止） |
| DE-3 | 状态进入 STUCK/DONE 后 `AgentLoop` 无法感知终态，继续调用编辑工具 | `DevEnginePlugin.before_model` 在终态注入强制终止提示 | DT2（循环终止） |
| DE-4 | `auto-verify` 使用被编辑文件的父目录作为 workspace，lint 上下文不完整 | 改用 `get_tool_safe_root()` 获取项目根目录 | DA4/DT6（验证完整性） |

## 附录 E：开发引擎符号表

| 符号 | 含义 |
|------|------|
| \(\mathcal{F}\) | 工作区文件集合 |
| \(\mathcal{G}\) | 诊断集合 |
| \(\mathcal{V}\) | 验证结果 |
| \(\mathcal{E}_h\) | 编辑历史 |
| \(\mathcal{S}_c\) | 搜索上下文 |
| \(\Sigma_{\text{dev}}\) | 开发循环状态集 |
| \(\delta_{\text{dev}}\) | 开发循环转移函数 |
| \(K_{\max}\) | 修复循环上限 |
| \(I_{\max}\) | 总迭代上限 |
| DA1-DA7 | 开发引擎公理 |
| DT1-DT7 | 开发引擎定理 |
| DD1-DD5 | 详细设计决策 |
| V1-V5 | 验证层次 |

## 附录 F：与父理论映射

| 父理论概念 | 子理论扩展 |
|------------|------------|
| A3'（管家不动手） | **修正为 A3''**（管家通过内置引擎动手） |
| A7'（可插拔） | **强化**：外部工具降级为可选增强 |
| M4'（深度 vs 广度） | **重新解决**：内置引擎替代外部委派 |
| \(\mathcal{D}\)（Dev 支柱） | 从委派模型升级为 DevState + DevLoop + 操作代数 |
| T3'（权限不升级） | DT3 保持一致 |
| T1'（上下文不溢出） | DT4 在代码域特化 |
| 命题 2.14（管家不写文件） | **修正**：管家通过 DevEngine 写文件，但在完整安全管线下 |
| 命题 2.17（Doom Loop） | DT2 在开发域特化（FIX 循环 K_max） |

---

## 第九章 编码知识层 — 定理与经验驱动的代码正确性

> 新增于 v1.3（2026-06-07）；v1.4 全面完善（2026-06-08）。
> 动机：第一至八章解决了"引擎如何安全运行"（编辑安全、循环终止、权限保持），但未回答"生成的代码为什么是正确的"。
> 第七章 §7.2 诚实声明承认"编辑正确性取决于 LLM 生成质量"——本章将此从黑盒依赖提升为结构化的知识驱动保证。

### 9.1 核心矛盾与解法

**矛盾**：莱斯定理指出两个程序功能等价不可判定——纯测试永远只是采样，无法穷举证明正确性。同时，当前 LLM 缺乏顶级数学推理能力，不能依赖"涌现"来保证代码质量。

**解法**：将代码正确性保证从"LLM 黑盒生成 + 测试碰运气"重构为三层知识驱动体系：

1. **定理层（永恒知识）**：编程世界的不变法则，由人类专家一次性形式化
2. **经验层（动态实践）**：当前技术环境下经过验证的最佳实践，有时效性
3. **验证层（双重门控）**：定理验证器（静态结构检查）+ 测试验证器（动态行为检查）

**核心洞察**：大模型的角色从"创造性推理者"下移为"模式匹配与约束执行器"——推理的深度由定理库保证，实现的最优性由经验库保证，正确性由验证器把关。系统的上限由**人类定义的定理库完备性**决定，而非模型的涌现能力。

**隐含系统外假设**：
- **H0（规格忠实性）**：规格 \(S\) 准确反映用户意图。这是用户/上游责任，系统不验证需求本身的正确性。
- **H13（验证器确定性）**：\(\text{Verify}_{\text{thm}}\) 和 \(\text{Verify}_{\text{test}}\) 的执行结果不依赖 LLM 的随机性——验证器为确定性程序。

### 9.2 编码知识公理

以下公理定义编码知识层的理论基础，与 DA1-DA7（引擎机械公理）互补。

**公理 CA1（编码元素可组合覆盖性）**：所有编码任务可分解为七种基础元素的有限组合。这七种元素构成编码世界的最小生成集——每种元素有独立的语义职责和验证属性维度，但同一代码片段可涉及多种元素（如 `filter` 同时涉及 DataFlow 和 ControlFlow）。

\[
\text{CodingTask} = \text{Compose}(E_1, E_2, \ldots, E_k), \quad E_i \in \mathcal{E}_7
\]

\[
\mathcal{E}_7 = \{\text{DataFlow}, \text{ControlFlow}, \text{StateManagement}, \text{Composition}, \text{BoundaryInterface}, \text{ErrorHandling}, \text{TypeSchema}\}
\]

注："可组合覆盖"而非"正交"——元素在触发层面允许重叠，但在验证属性维度上互不包含（每种元素拥有其他元素不检查的属性集）。

**公理 CA2（定理语义不变性）**：编程世界存在一组语义层面永恒不变的结构性约束——**定理库** \(\mathcal{T}\)。定理由人类专家从计算理论、类型论、编程语言语义中提炼。定理的语义陈述（如"资源必须释放"）恒久成立；其实例化形式（如具体 API 调用方式）可能随技术栈变化。

\[
\forall \tau \in \mathcal{T}, \forall t \in \text{Time}: \quad \text{semantic}(C_\tau) \text{ 在 } t \text{ 时成立}
\]

注：T09（契约遵守）的"契约"指逻辑层面的前置/后置/不变量，而非特定 API 版本的文档。具体 API 版本映射属于经验层。

**公理 CA3a（经验入库准确性）**：经验入库时其模板 \(\text{pattern}(x)\) 满足其宣称的定理基础 \(B_x\)。

\[
\forall x \in \mathcal{X}_{\text{admitted}}: \forall \tau \in B_x: C_\tau(\text{pattern}(x)) = \text{true}
\]

**公理 CA3b（经验时效性）**：经验有有效期 \(\text{validity}(x) = [t_s, t_e]\)，过期经验不参与推理选择。

**注**：入库准确性保证 pattern 自身满足定理，但 Synth 实例化后的程序是否仍满足，由 H4（合成器定理保持性）保证，而非 CA3 直接断言。

**公理 CA4（双重验证闭合——严格模式）**：在严格模式（`BUTLER_CODING_STRICT=1`）下，程序输出当且仅当同时通过定理验证和测试验证。验证失败触发修复循环（受 DT2 的 \(K_{\max}\) 约束），循环未收敛则终止于 STUCK（不输出）。

\[
\text{Output}_{\text{strict}}(P) \iff \text{Verify}_{\text{thm}}(P, \mathcal{T}_S) = \text{pass} \;\land\; \text{Verify}_{\text{test}}(P, S) = \text{pass}
\]

\[
\text{修复未收敛} \implies \text{STUCK}(\text{不输出}) \quad \text{（引用 DT2 的 } K_{\max} \text{）}
\]

**适用范围**：DevLoop 的 `verify_skip → REVIEW` 路径绕过自动验证，此时 CA4 不成立，能力边界相应收缩至引擎机械层保证。

### 9.3 形式化定义

**定义 CD0（规格与解析）**（v1.4 新增）：

规格 \(S\) 是三元组 \((D_S, E_S, C_S)\)：
- \(D_S\)：元素组合声明——任务涉及的编码元素子集
- \(E_S\)：输入-输出示例与边界约束
- \(C_S\)：触发关键词集合

\[
\text{Parse}: \text{Input} \to \text{Spec} = (D_S, E_S, C_S)
\]

**定义 CD1（七基础编码元素）**：

| 元素 | 职责 | 标准模式 | 静态验证属性 |
|------|------|---------|-------------|
| **DataFlow** | 数据变换，无副作用 | map, filter, reduce, flatMap, pipeline | 无状态修改；输入不可变；管道方向一致 |
| **ControlFlow** | 执行路径控制 | if/else, switch, for/while, 递归, 提前返回 | 终止性（度量函数单调递减）；分支完备；无死代码 |
| **StateManagement** | 可变状态创建/读取/更新 | 局部变量, 闭包状态, 对象字段 | 作用域最小化；变更可预测；无意外共享 |
| **Composition** | 函数/组件串联 | 嵌套 f(g(x)), 管道, 装饰器 | 类型兼容；效应顺序正确；无循环依赖 |
| **BoundaryInterface** | 外部系统交互 | 网络调用, I/O, 第三方库 | 契约覆盖（所有响应状态）；资源释放；输入校验 |
| **ErrorHandling** | 异常与降级 | 错误值/Maybe/Either, try/catch, 默认值 | 异常覆盖；错误不丢失；恢复一致性 |
| **TypeSchema** | 数据形状与约束 | 类型标注, 自定义类型, 验证守卫 | 类型闭合；模式匹配完整；约束符合性 |

元素→定理固定映射（CD5 使用）：DataFlow → T01, Composition → T02, TypeSchema → T03, ControlFlow → T04, StateManagement → {T05, T07}, ErrorHandling → T06, BoundaryInterface → {T08, T09, T10}。

**定义 CD2（定理）**：定理 \(\tau\) 是三元组 \((\text{id}, \text{triggers}, C_\tau)\)，其中 \(C_\tau: \mathbb{P} \to \{\text{true}, \text{false}\}\) 是**确定性**可计算的结构/逻辑谓词（H13）。

**定义 CD3（定理库与分层）**：

| 层 | 定理 | 陈述 |
|----|------|------|
| **计算基础** | T01 确定性 | \(\forall f: A \to B, x \in A: f(x) = f(x)\)。纯函数同一输入同一输出 |
| | T02 组合性 | 若 \(f: A \to B\) 正确且 \(g: B \to C\) 正确，则 \(g \circ f: A \to C\) 正确 |
| | T03 类型安全 | \(\forall e: T\)，若 \(e\) 被当作类型 \(U\) 使用，则必须 \(T <: U\) 或存在合法转换 |
| | T04 终止性义务 | \(\forall\) 循环/递归，必须存在单调递减的度量函数，保证有限步终止 |
| **效应与状态** | T05 状态隔离 | 可变状态作用域最小化；模块内部创建且不传递引用的状态不影响外部 |
| | T06 异常安全（强保证） | 操作要么成功并产生全部副作用，要么失败且不产生任何副作用 |
| | T07 幂等性 | 若操作 \(op\) 是幂等的，则 \(\forall s: op(op(s)) = op(s)\) |
| **资源与边界** | T08 资源生命周期 | 每个 \(\text{acquire}()\) 必须与唯一的 \(\text{release}()\) 配对，在所有退出路径上可达 |
| | T09 契约遵守 | 与外部接口交互时，逻辑层面的前置/后置条件、不变量必须被满足 |
| | T10 信任边界 | 来自外部的数据不可信，使用前必须校验类型、范围、格式 |

**定义 CD4（经验）**：经验 \(x\) 是元组 \((\text{pattern}, B_x, \text{context}, \text{benchmarks}, \text{validity})\)：
- `pattern`：程序模板（可实例化的 AST 骨架）
- \(B_x \subseteq \mathcal{T}\)：定理基础（该经验满足的定理子集）
- `context`：适用上下文
- `benchmarks`：客观基准数据
- `validity`：有效期 \([t_{\text{start}}, t_{\text{end}}]\)

**定义 CD5（激活函数）**：

\[
\text{Activate}(S) = \{\tau \in \mathcal{T} \mid \text{triggers}(\tau) \cap \text{normalize}(C_S) \neq \varnothing\} \cup \text{ElementTriggered}(D_S)
\]

其中 \(\text{normalize}\) 将关键词统一为小写词干，\(C_S\) 为规格关键词集合，\(D_S\) 为元素组合声明。ElementTriggered 基于 CD1 固定映射。

空激活集保护：若 \(\mathcal{T}_S = \varnothing\)，强制注入基线定理集 \(\{T03, T10\}\)（类型安全 + 信任边界），确保不出现空验证（vacuous pass）。

**定义 CD5b（经验选择）**（v1.4 新增）：

\[
\text{Select}(S) = \arg\max_{x \in \mathcal{X}_{\text{valid}}} \text{Score}(x) \quad \text{s.t.} \quad \mathcal{T}_S \subseteq B_x
\]

其中 \(\mathcal{X}_{\text{valid}} = \{x \in \mathcal{X} \mid t \in \text{validity}(x)\}\)。若无候选满足 \(\mathcal{T}_S \subseteq B_x\)，则 \(e^* = \text{None}\)（降级为 theorem\_only 模式）。

**定义 CD6（双重验证门）**：

\[
\text{Verify}_{\text{thm}}(P, \mathcal{T}_S) = \begin{cases} \text{pass} & \forall \tau \in \mathcal{T}_S: C_\tau(P) = \text{true} \\ \text{fail}(\tau_{\text{violated}}) & \text{otherwise} \end{cases}
\]

\[
\text{Verify}_{\text{test}}(P, S) = \begin{cases} \text{pass} & \forall tc \in \text{GenTC}(E_S): \text{exec}(P, tc) = \text{expected}(tc) \\ \text{fail}(tc_{\text{failed}}) & \text{otherwise} \end{cases}
\]

其中 \(\text{GenTC}: E_S \to \mathcal{P}(\text{TestCase})\) 从规格的输入-输出示例和边界约束自动生成测试用例集（H10 约束其充分性）。

**验证栈层次关系**：

```
┌─────────────────────────────────────────────┐
│ 知识层: Verify_thm (CA4 / CD6)              │
│   基于 C_τ 谓词的结构/语义检查              │
│   （独立于 V1-V5，不替代也不包含）           │
├─────────────────────────────────────────────┤
│ 工具层: V1-V5 (DT6)                         │
│   V1 Lint ⊂ V2 Type ⊂ V3 Unit ⊂ V4 Int ⊂ V5│
│   作为 Verify_test 的执行基础设施            │
├─────────────────────────────────────────────┤
│ 运行时: OS + 语言运行时 (H11)               │
└─────────────────────────────────────────────┘
```

两层正交：Verify\_thm 检查定理谓词（结构正确性），V1-V5 作为 Verify\_test 的执行基础设施提供功能测试。DT6（可检测错误被诊断）覆盖 V1-V5 范围内的错误；Verify\_thm 检查 DT6 未覆盖的结构性约束。

**定义 CD7（与引擎循环的集成）**：编码知识层嵌入 DevLoop 的 PLAN 和 VERIFY 阶段：

| DevLoop 阶段 | 知识层介入 |
|-------------|-----------|
| PLAN | Parse(Input) → Spec → 元素组合声明 + Activate(S) + Select(S) |
| EDIT | Synth(\(D_S, e^*, \mathcal{T}_S\)) → EditPlan → DA1 原子编辑序列 |
| VERIFY | Verify\_thm → Verify\_test（V1-V5），两者均 pass 方可 DONE |
| FIX | 定理违规：结构修复（重新 Synth）；测试失败：功能修复。每次修复后 **重过两道门**（修复不变式）。消耗 DT2 的 \(K_{\max}\) |

**定义 CD8（合成器）**（v1.4 新增）：

\[
\text{Synth}(D_S, e^*, \mathcal{T}_S) \to P
\]

- 若 \(e^* \neq \text{None}\)（experience\_guided）：以 \(e^*.\text{pattern}\) 为骨架，填充任务参数
- 若 \(e^* = \text{None}\)（theorem\_only）：基于元素原语组合（CL1），在 \(\mathcal{T}_S\) 约束下生成

H4 约束：Synth 实例化不破坏 \(C_\tau\) 满足性。

### 9.4 定理证明 — 编码知识层关键性质

**坚实度层级**（统一标准）：
- **L1**：代码路径保证——架构强制，只要实现正确即成立
- **L2**：数学保证——可通过数学证明论证
- **L3**：配置保证——依赖工程参数设置
- **L4**：外部依赖——依赖 LLM 或外部服务质量

#### 定理 CT1：验证器可靠性推论（Verified Program Compliance）

**陈述**：在定理验证器正确的前提下，通过双重验证门输出的程序满足所有激活定理。

**前提**：
- (P-CT1a) 激活定理集 \(\mathcal{T}_S\) 准确覆盖任务所需的结构性定理（H5）
- (P-CT1b) 定理验证器 \(\text{Verify}_{\text{thm}}\) 对每个 \(C_\tau\) 的检查无误报/漏报（H2）
- (P-CT1c) 程序 \(P\) 通过双重验证门

**证明**：由 P-CT1c，\(\text{Verify}_{\text{thm}}(P, \mathcal{T}_S) = \text{pass}\)。由定义 CD6，这意味着 \(\forall \tau \in \mathcal{T}_S: C_\tau(P) = \text{true}\)。由 P-CT1b，该检查逻辑正确。因此结论成立。

**坚实度**：**L1 架构保证**。本定理是验证器正确性（H2）的直接推论——正确性重担完全转移至验证器实现和定理库设计。CT1 本身不保证 Synth 能生成通过验证的程序，仅保证**通过验证的程序满足定理**。 ∎

#### 引理 CL1：元素原语的定理保持与组合封闭性（限定范围）

**陈述**：在当前局部结构性定理子集 \(\mathcal{T}_{\text{local}} = \{T05, T06, T08\}\) 下，且组合片段间无共享可变状态、执行环境为单线程，七元素生成原语各自产出的代码片段满足其相关定理，且通过顺序拼接或嵌套的组合操作不破坏定理满足性。

**前提**：
- (P-CL1a) 每个元素原语内置遵守其对应定理的构造（如 ErrorHandling 原语禁止写入状态）
- (P-CL1b) 组合方式限于顺序拼接、嵌套和安全扩展点插入；**组合片段间无共享可变引用**
- (P-CL1c) 执行环境为单线程（无并发竞争）
- (P-CL1d) 定理满足性为**局部结构性约束**——可通过仅检查代码片段内部结构判定

**证明草图**：
- 状态隔离（T05）：闭包作用域独立，P-CL1b 保证拼接不共享可变引用 → 拼接后各片段内部的 \(C_{T05}\) 不受外部片段影响
- 异常安全（T06）：成功路径与失败路径的写入操作分离，P-CL1b 保证无交叉污染 → 嵌套 try/catch 结构各自独立满足 \(C_{T06}\)
- 资源生命周期（T08）：每对 acquire/release 在 finally 块中配对，拼接后各对关系不被破坏
- 通过对 AST 的结构归纳可严格论证（P-CL1d 保证可判定性）

**适用边界**：CL1 目前 **不覆盖** T01-T04、T07、T09、T10 的组合封闭性。其中 T02（组合性）本身即为组合性质故自然成立；T01（确定性）在无共享可变状态下保持；T03/T04/T07/T09/T10 的组合封闭性需后续扩展论证。

**坚实度**：**L2 数学保证**（仅限 \(\mathcal{T}_{\text{local}}\) 与上述前提条件下）。 ∎

#### 定理 CT2：经验降级无害性（Graceful Degradation）

**陈述**：经验缺失或过期时，系统降级为纯定理推理模式。若降级后 Synth 仍能生成完整程序（P-CT2a），且该程序通过双重验证门，则仍满足所有激活定理。

**前提**：
- (P-CT2a) 元素原语在无经验模板时仍能基于定理约束生成完整程序（H4 + H7）
- (P-CT2b) 引理 CL1 的前提条件成立（限定范围内）
- (P-CT2c) 存在程序 \(P\) 使得 \(\text{Verify}_{\text{thm}}(P, \mathcal{T}_S) = \text{pass}\)

**证明**：降级后 \(e^* = \text{None}\)，Synth 仅依赖元素原语。由 P-CT2a，Synth 能生成候选程序。由 P-CT2c，若候选程序通过 Verify\_thm，则由 CT1 得证。若未通过，进入 FIX 循环（CD7），受 DT2 约束终止。

**关键区分**：CT2 保证的是**定理合规**（结构正确性），**不保证功能正确**。功能正确仍需 Verify\_test（CT4）补充。"鲁棒降级"指定理层面安全，生成质量（最优性、可读性）可能下降。

**坚实度**：**L2 数学保证**（条件于 P-CT2a/c 成立时），降为 **L3** 若 Synth 生成能力依赖 LLM。 ∎

#### 定理 CT3：经验替换安全性（Experience Update Safety）

**陈述**：新经验 \(x_{\text{new}}\) 替换旧经验 \(x_{\text{old}}\) 时，若 \(x_{\text{new}}\) 已通过定理验证器确认其模板满足 \(B_{x_{\text{new}}}\)，且 Synth 实例化保持定理满足性（H4），则采用新经验生成的程序通过验证后仍满足所有激活定理。

**前提**：
- (P-CT3a) 新经验入库前通过定理验证器全量检查：\(\forall \tau \in B_{x_{\text{new}}}: C_\tau(\text{pattern}(x_{\text{new}})) = \text{true}\)
- (P-CT3b) \(B_{x_{\text{new}}}\) 覆盖任务激活的定理集：\(\mathcal{T}_S \subseteq B_{x_{\text{new}}}\)
- (P-CT3c) Synth 实例化保持性（H4）

**证明**：由 P-CT3a，新经验模板满足 CA3a。由 P-CT3c（H4），实例化后的程序保持定理满足性。由 P-CT3b，激活定理被覆盖。最终程序通过 Verify\_thm，由 CT1 得证。 ∎

**坚实度**：**L1 架构保证**（入库验证流程为代码路径强制）+ **L3 配置保证**（H4 的 Synth 质量）。 ∎

#### 定理 CT4：测试覆盖补充（Test Coverage Supplement）

**陈述**：在定理覆盖范围之外，测试验证器为规格中明确声明的行为维度提供工程置信度——即在 \(\text{GenTC}(E_S)\) 所表征的**行为子空间**内，程序行为与规格一致。

**前提**：
- (P-CT4a) \(\text{GenTC}(E_S)\) 覆盖了 \(E_S\) 中声明的关键等价类（H10）
- (P-CT4b) 测试执行环境在确定性子集（纯函数单元测试）内可靠（H11）
- (P-CT4c) 程序通过 \(\text{Verify}_{\text{test}}(P, S)\)

**证明**：由 P-CT4c，\(\forall tc \in \text{GenTC}(E_S): \text{exec}(P, tc) = \text{expected}(tc)\)。由 P-CT4a，\(\text{GenTC}(E_S)\) 覆盖了 \(E_S\) 的关键等价类。因此 \(P\) 在 \(E_S\) 定义的行为子空间内与规格一致。

注：这是**工程置信而非逻辑必然**（莱斯定理仍在）。测试通过不等于功能穷尽——未声明的行为和 \(\text{GenTC}\) 未覆盖的输入仍无保证。

**坚实度**：**L3 配置保证 + L4 LLM 依赖**（测试生成质量影响覆盖度）。 ∎

#### 定理 CT5：双重验证的联合保证（Joint Guarantee）

**陈述**：若程序 \(P\) 在严格模式下同时通过 \(\text{Verify}_{\text{thm}}\) 和 \(\text{Verify}_{\text{test}}\)，则：

\[
\text{Guarantee}(P) = \underbrace{\left(\bigwedge_{\tau \in \mathcal{T}_S} C_\tau(P)\right)}_{\text{定理覆盖：结构合规}} \;\land\; \underbrace{\left(\bigwedge_{tc \in \text{GenTC}(E_S)} \text{pass}(P, tc)\right)}_{\text{测试覆盖：行为子空间内工程置信}}
\]

**前提**：CT1-CT4 的所有前提 + **修复循环不变式**：每次 FIX 修复后，重过两道验证门（CD7），确保测试修复不引入定理违规。

**证明**：第一部分由 CT1 得；第二部分由 CT4 得。修复不变式保证 FIX 循环中两道门始终联合检查。 ∎

**明确不保证的**：
- 未激活定理对应的性质（H5 遗漏风险）
- \(\mathcal{T}\) 中未形式化为定理的正确性维度（定理盲区）
- 不在 \(\text{GenTC}(E_S)\) 覆盖范围的输入
- 需求本身的业务误解（H0）
- 非功能性指标（除非已纳入定理或测试）
- `verify_skip → REVIEW` 路径下的程序（CA4 不适用）

### 9.5 前提假设汇总与分类

本章引入 14 条前提假设（H0-H13），分为四类。

#### 系统外假设（不验证）

| 编号 | 假设 | 说明 |
|------|------|------|
| **H0** | 规格忠实性：\(S\) 准确反映用户意图 | 用户/上游责任 |

#### 有条件理论确认

以下假设在**限定条件下**可理论确认，超出条件则需工程验证。

| 编号 | 假设 | 理论确认条件 | 超出范围（需工程验证） |
|------|------|-------------|---------------------|
| **H6** | 规格解析确定性 | 输入为严格 DSL/CFG 时，由形式语言理论保证 | 受控自然语言输入需翻译器准确性验证 |
| **H8** | 组合封闭性 | \(\mathcal{T}_{\text{local}} = \{T05, T06, T08\}\)、单线程、无共享可变状态下成立 | 并发、全局性能约束、T01-T04/T07/T09/T10 需扩展论证 |
| **H11** | 测试环境可靠 | 确定性子集（纯函数单元测试）由 OS/运行时保证 | 异步代码、时序依赖、flaky test 需工程处理 |

#### 设计期可验证

| 编号 | 假设 | 验证方式 |
|------|------|---------|
| **H5** | 激活定理集准确性 | 审查触发映射表 + 基准任务库回归 |
| **H13** | 验证器确定性 | 验证器实现不含 LLM 调用（代码审查） |

#### 需完整工程验证

| 编号 | 假设 | 验证方式 |
|------|------|---------|
| **H1** | 定理库相对完备性 | 大量编码任务审计 + 从失败案例反向提取新定理 |
| **H2** | 定理验证器正确性 | 每定理 ≥3 合规/违规样本 + 变异测试 |
| **H3** | 经验入库准确性 | 入库前定理验证器全量检查 + 多变体实例化测试 |
| **H4** | 合成器的定理保持性 | 元素原语输出随机测试 + Synth 实例化后定理验证通过率 |
| **H7** | 七元素原语覆盖性 | 多样化任务基准集 + 失败案例分析 |
| **H9** | 修复循环有效性 | \(K_{\max}\) 内收敛或安全 STUCK（与 DT2 统一） |
| **H10** | 测试生成充分性 | 等价类覆盖审查 + 变异测试得分 |
| **H12** | 修复循环对测试反馈有效性 | 功能缺陷修复成功率基准 |

### 9.6 更新的能力边界声明

整合第七章 §7.1 和本章分析，更新后的能力边界为：

**保证范围**（严格模式）：

| 保证维度 | 具体能力 | 来源 | 条件 |
|----------|----------|------|------|
| 引擎安全 | 编辑原子性、循环终止、权限保持、回滚安全 | DT1-DT7 | — |
| 定理合规 | 通过验证的代码满足所有激活定理 | CT1 + H2 | 验证器正确 |
| 元素覆盖（条件） | 元素覆盖验证 + 测试通过前提下，结构元素与规格声明一致 | CA1 + CD1 + CT4 | H7 + H10 |
| 经验优选（条件） | 兼容候选中 benchmark 评分最高 | CA3a + CD5b | 经验有效 + 激活覆盖 |
| 定理层鲁棒降级 | 经验缺失时，定理合规仍保证（结构正确） | CT2 | P-CT2a/c |
| 安全进化 | 经验替换经入库验证后不引入定理违规 | CT3 | H4 + P-CT3a |
| 行为子空间置信 | GenTC(E\_S) 覆盖的行为子空间内与规格一致 | CT4 | H10 + H11 |

**不保证范围**：

| 边界 | 原因 | 缓解 |
|------|------|------|
| 未激活定理对应性质 | H5 遗漏风险 | 扩展触发映射 + 基线定理集 |
| 定理盲区性质 | 未形式化为定理的维度 | 测试补充（缩小盲区，非消除）+ 持续扩充定理库 |
| GenTC 未覆盖的输入 | 测试采样本质 | 变异测试 + 等价类审查 |
| 业务逻辑误解 | H0——规格正确性是用户责任 | 上游需求澄清 Agent |
| 非功能性绝对满足 | 性能/可读性等软指标 | 纳入定理/测试或经验评分 |
| 无限规模组合 | CL1 限定范围外的涌现性问题 | 限定组合方式 + 扩展 CL1 适用范围 |
| verify\_skip 路径下的代码 | CA4 不适用 | 人工 REVIEW 补充 |
| CD0/CD6/CD8 合成管线 | 仅测试级（§8.5 T1） | 待 Phase 2 接入 delegate |
| CA4 生产阻断 | env 存在但零生产调用 | `BUTLER_CODING_STRICT=1` opt-in |

### 9.7 与引擎机械层的协同关系

```
引擎机械层 (DA1-DA7 / DT1-DT7)     编码知识层 (CA1-CA4 / CT1-CT5)
├── 编辑安全 (DT1)                   ├── 定理合规 (CT1)
├── 循环终止 (DT2) ────────────┐     ├── 经验降级安全 (CT2)
├── 权限保持 (DT3)              │     ├── 经验替换安全 (CT3)
├── 上下文有界 (DT4)             │     ├── 测试覆盖补充 (CT4)
├── 回滚安全 (DT5)              │     └── 联合保证 (CT5)
├── 诊断完备 (DT6: V1-V5) ──┐  │
└── 外部可替换 (DT7)         │  │
                              │  │
     ┌────────────────────────┘  │
     │  Verify_test 使用 V1-V5   │  FIX 消耗 K_max
     │  作为执行基础设施          │
     ▼                           ▼
┌───────────┐  ┌─────────────────────┐
│Verify_test│  │ CA4: 修复 ≤ K_max   │
│(功能正确) │  │ 后 STUCK 不输出      │
└───────────┘  └─────────────────────┘
```

**两层正交互补**：

| 维度 | 引擎机械层 | 编码知识层 |
|------|-----------|-----------|
| **保证什么** | 操作安全（编辑可回滚、循环终止） | 生成质量（定理合规、行为置信） |
| **不保证什么** | 生成代码语义正确 | 编辑原子性、权限保持 |
| **交互点** | DT2 的 \(K_{\max}\) 约束 FIX 循环；DA1 保证 Synth 输出的原子写入；DT6 的 V1-V5 作为 Verify\_test 执行基础 | |
| **模式开关** | verify\_skip → REVIEW（人工审查） | CA4 仅在严格模式生效 |

### 9.8 工程前提验证矩阵（编码知识层）

| ID | 前提 | 验证方法 | 状态 |
|----|------|----------|------|
| P-H0 | 规格忠实性 | 系统外假设（不验证） | — |
| P-CA1 | 七元素覆盖编码任务 | 多样化任务集分解测试 (5 tests) | **通过** |
| P-CA2 | 定理语义不变性（T01-T10） | AST checker 合规/违规样本 + regex fallback (56 tests) | **通过** |
| P-CA3a | 经验入库准确性 | 入库自动验证 + 替换安全 + 候选提取 (8 tests) | **通过** |
| P-CA4 | 双重验证门闭合（严格模式） | `BUTLER_CODING_STRICT` env gate + auto_verify 定理门 (4 tests) | **测试通过**（生产默认 advisory，见 §8.5 T3） |
| P-CT1a | 激活定理集准确 | 触发映射表覆盖率 + 基准任务回归 (8 tests) | **通过** |
| P-CT1b | 验证器无误报/漏报 | 每定理 ≥3 合规/违规样本 + AST 直测 (30+ tests) | **通过** |
| P-CT2a | 无经验时定理模式可用 | 纯定理模式端到端测试 (4 tests) | **通过** |
| P-CT3a | 新经验入库前验证 | 入库流程强制检查 + 违规拒绝 (3 tests) | **通过** |
| P-CT4a | 测试生成覆盖等价类 | 等价类审查 + 变异测试得分（`gentc_mutation.evaluate_pct4a`） | **通过**（7 tests） |
| P-H6 | 规格解析确定性 | DSL 路径：理论确认 (3 tests) | **有条件确认** |
| P-H8 | 组合封闭性 | T\_local + 单线程 + 无共享可变：理论确认 (5 tests) | **有条件确认** |
| P-H11 | 测试环境可靠 | 确定性子集：理论确认 (3 tests) | **有条件确认** |
| P-H13 | 验证器确定性 | 代码审查确认（无 LLM 调用）(2 tests) | **设计期确认** |

## 附录 G：编码知识层符号表

| 符号 | 含义 |
|------|------|
| \(\mathcal{E}_7\) | 七基础编码元素集合 |
| \(\mathcal{T}\)（知识层） | 编码定理库（T01-T10，区别于父理论工具集 \(\mathcal{T}\)） |
| \(\mathcal{T}_{\text{local}}\) | CL1 适用的局部结构性定理子集（当前 \(\{T05, T06, T08\}\)） |
| \(\mathcal{X}\) | 经验库 |
| \(\mathcal{T}_S\) | 任务 S 激活的定理子集 |
| \(C_\tau\) | 定理 τ 的确定性可计算检查谓词 |
| \(B_x\) | 经验 x 的定理基础 |
| \(S = (D_S, E_S, C_S)\) | 规格三元组（元素声明、I/O 示例/边界、触发关键词） |
| \(\text{Parse}\) | 规格解析器 |
| \(\text{Activate}(S)\) | 激活函数 |
| \(\text{Select}(S)\) | 经验选择函数 |
| \(\text{Synth}\) | 代码合成器 |
| \(\text{GenTC}(E_S)\) | 测试用例生成函数 |
| \(\text{Verify}_{\text{thm}}\) | 定理验证器 |
| \(\text{Verify}_{\text{test}}\) | 测试验证器 |
| CA1-CA4 | 编码知识公理（CA3 拆为 CA3a/CA3b） |
| CT1-CT5 | 编码知识定理 |
| CD0-CD8 | 编码知识定义 |
| CL1 | 组合封闭性引理（限定范围） |
| H0-H13 | 编码知识层前提假设（14 条） |
