# WFXM Butler · 4 页版 Cheat Sheet

> **用途**：4 页版 PPT 配套，半页纸，**只保留 4 页会用到的东西**。
> **打印建议**：A4 横向 / 字号 10pt / 单栏。
> **何时用**：HR 面 / 投递简历后第一轮 / 大会 lightning / 30 秒电梯。

---

## 🎯 灵魂标签（必须记住）

**"跨进程工具路由 + 多源记忆治理"**

> 前者 = Agent 在多权限域里安全调度工具；后者 = Agent 在长会话里不丢上下文。

---

## 📊 4 页 × 4 数字速查

| 数字 | 含义 | 出处 |
|------|------|------|
| **1254** | `butler/` Py 文件数 | `find butler -name '*.py' \| wc -l` |
| **2 层 15 道门** | 入站 9 + 工具链 6 | `permission-gate-stack.md` |
| **7** | runtime jobs（cron） | `runtime/jobs.yaml` |
| **3 层** | Owner / 项目 / 会话，SSOT 文件 | `butler/memory/` |

---

## 🐛 1 个真实 Bug（4 页版只讲这个）

**`transcript_fts.py` PRIMARY KEY 多余 `)`**（commit `323862e`）

- 现象：FTS 索引重建失败，所有 INSERT 静默失败
- 根因：SQLite 早期版本静默吞语法错
- 修法：去掉多余 `)` + 加显式 health check
- 教训：**第三方容错是双刃剑**

---

## ⚖️ Baseline（4 页版只讲这个）

**vs 直接 LLM（无 Agent）**：

| 维度 | 直接 LLM | WFXM Butler |
|------|---------|-------------|
| 跨会话记忆 | 0 | ∞（3 层 SSOT）|
| 多项目切换 | 无 | N 倍（独立 MEMORY）|
| 微信接入 | 无 | ∞（原生网关）|

→ "直接 LLM 适合聊天，不适合远程多项目管理"

---

## 🧠 1 个认知颠覆（4 页版只讲这个）

> **LLM 没有真正的"规划"——是高级模式匹配**
> 子代理前 3 步准确，第 5 步开始漂移
> 真正突破需要"工作记忆 + 长期记忆 + 元认知"工程化，**不是更大模型**

---

## 🗣 4 页口播速查（按 STAR+L 顺序）

### P1 · 封面 + 痛点 + Why Agent（45s）

> "我做的是 **WFXM Butler**——自托管的多项目 AI 管家，**核心标签是'跨进程工具路由 + 多源记忆治理'**。痛点 3 个：远程管理多项目时微信最方便但工具都在电脑端；现成方案五不贴（ChatGPT 没工具、Cursor 要开电脑、LangChain 是框架不是产品）；工具过 10 个后单 Agent 调不动。为什么必须 Agent？意图模糊 + 工具组合 + 跨会话 + 权限分级——传统脚本解决不了。"

### P2 · 架构 + 双挑战 + 关键代码（60s）

> "架构是 **Multi-Agent + Plan-then-Execute 混合**——Lead / Butler / Plan 三角色 + `delegate_task` 委派。两挑战：**一是跨进程工具路由**——100+ 工具横跨 Owner / dev 子代理 / MCP，用 **2 层 15 道门**防御（口播 5 道），3 道回退：**二是多源记忆治理**——3 层架构，SSOT 是文件，压缩前抽 fact 写回 MEMORY。关键代码 4 个：`agent_loop` / `vector_store` / `message_handler` / `registry`——白盒可断点。"

### P3 · 量化 + 真实 Bug + Baseline（60s）

> "硬数据：**1254 个 Py 文件，core/ 232，gateway/ 176，测试覆盖 80%**，Recall@3 ≥ 0.8（实测阈值），7 个 runtime jobs，权限门控 **2 层 15 道**。讲 1 个最戏剧化的 bug：`transcript_fts.py` PRIMARY KEY 多余 `)`，**SQLite 早期版本静默吞语法错**，FTS 重建失败但代码以为成功——所有 INSERT 静默失败。加 health check 才暴露。教训：第三方容错是双刃剑。vs 直接 LLM：跨会话记忆从 0 到 ∞，多项目切换从无到 N 倍。"

### P4 · 认知颠覆 + 标签回锚（30s）

> "最后 1 个认知：**LLM 没有真正的'规划'，是高级模式匹配**——子代理前 3 步准确，第 5 步开始漂移。真正的 Agent 突破需要'工作记忆 + 长期记忆 + 元认知'工程化，不是更大模型。总结：**跨进程工具路由 + 多源记忆治理**——1254 Py、2 层 15 道门、7 个 jobs。Q&A。"

---

## 🔥 高频追问（TOP 5）

| 问题 | 一句话 |
|------|--------|
| 为什么不用 LangGraph？ | 单租户自托管 + 微信原生 + 极致可控的场景下，框架自带能力是负债 |
| 为什么不用 Postgres？ | 文件 SSOT 可 `git diff` 审计；SQLite 索引可 `reindex` 重建 |
| 为什么不用 Claude Code？ | Claude Code 没微信入口 + 多项目切换 + 分层记忆 |
| Agent 幻觉怎么解决？ | 5 道核心防线（口播）/ 2 层 15 道门（追问展开） |
| 怎么看 Agent 未来？ | 当前 LLM ≈ 高级模式匹配 + 短程规划 + 工具调用；真正突破需要工程化记忆 |

---

## ⚠ 遇到不会的问题的 3 个救命句

- "这个问题我能从两个角度回答，您是想听架构层面还是实现层面？"
- "这个我没有实测数据，但我可以从设计意图讲——可以吗？"
- "我可以现场画一下这个架构图，30 秒——可以吗？"

---

<!--
打印 CSS（pandoc 转 PDF 时使用）：
pandoc cheat-sheet-4p.md -o cheat-sheet-4p.pdf --pdf-engine=xelatex -V geometry:margin=1cm -V fontsize=10pt -V mainfont="DejaVu Sans" -V CJKmainfont="Noto Sans CJK SC"

vs cheat-sheet.md 的区别：
- cheat-sheet.md = A4 1 页（17 页版用）
- cheat-sheet-4p.md = A4 半页（4 页版用）
- 4p 版只保留 4 页会用到的：1 bug / 1 baseline / 1 认知
-->