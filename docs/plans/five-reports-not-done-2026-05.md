# 五报告路线图 — 未作清单（2026-05）

> **状态**：P5–P10 **已落地**（2026-05-25）；本文记录**仍未实现**或**明确不做**的项。  
> **已落地速查**：[`../guides/five-reports-capabilities-2026-05.md`](../guides/five-reports-capabilities-2026-05.md)、[`../guides/external-agent-reports-capabilities-2026-05.md`](../guides/external-agent-reports-capabilities-2026-05.md)  
> **路线图核对表**：[`five-reports-improvement-roadmap-2026-05.md`](five-reports-improvement-roadmap-2026-05.md) §9  
> **四报告否决（18 项）**：[`four-reports-out-of-scope-2026-05.md`](four-reports-out-of-scope-2026-05.md) §2（优先于本文）

提新需求前：先查四报告 §2，再查本文 **§1 否决**。

---

## 1. 否决型「不做」（产品边界，勿立项）

来源：五报告路线图 §6（S1–S11）。除非产品边界变更，**不实现**。

| # | 能力 | 来源 | 原因 | Butler 替代 |
|---|------|------|------|-------------|
| S1 | claude-mem **Bun Worker + Chroma MCP** | claude-mem | 运行时/依赖栈不符 | `semantic_index` + `.butler/observations.tsv` |
| S2 | claude-mem **IDE 插件 / Viewer UI** | claude-mem | 入口是微信 | CLI / 微信命令 |
| S3 | CC Switch **Tauri 桌面 + 托盘** | cc-switch | 非服务端产品 | CLI + 微信 `/诊断` |
| S4 | CC Switch **五 CLI live 配置双向同步** | cc-switch | 维护面过大 | `project.yaml` + 原子写 |
| S5 | CC Switch **内置 HTTP 代理全家桶** | cc-switch | 网络中间层越界 | 薄 MCP + 现有 transport |
| S6 | PEG **LangChain Agent / notebook 运行时** | PEG | 教学标本 | 自建 `agent_loop` + prompt |
| S7 | PEG **ToT / APE 全自动 prompt 搜索** | PEG | 成本不可控 | 语料测试 + 人工改 prompt |
| S8 | TradingAgents **LangGraph + 行情 API** | tradingagents | 领域/依赖越界 | `task_orchestrator` + workflow YAML |
| S9 | TradingAgents **SQLite checkpoint 进 core** | tradingagents | 与 transcript 策略冲突 | `session_transcript` + 人工门控 |
| S10 | LobeHub **浏览器 Agent Loop / Chat UI** | lobehub | 产品形态不同 | 微信 Gateway + Butler Loop |
| S11 | LobeHub **全量 MCP Host + OTEL 默认** | lobehub | 重依赖 APM | `BUTLER_MCP_ENABLED` 薄客户端 + `runtime_metrics` |

---

## 2. 路线图 P2 — 仍超出当前子集（勿误判为「未做」）

| 主线 | 项 | 说明 |
|------|-----|------|
| **G** | CC Switch 级 **IDE/托盘** | 已有 `/预设`、`provider apply`、`/模型 preset` |
| **H** | **APE / ToT** 全自动 prompt 搜索 | 已有 pattern + `--llm` + corpus live 子集 |
| **I** | **LangGraph 级** Bull/Bear 图 | 已有可选 `trading-debate` workflow；非默认路径 |
| **I** | **全字段** Pydantic 树覆盖所有 workflow | 已有 `output_schema_registry` + 多轮 repair |
| **J** | **npm 级** MCP Host / OTEL | 见 S11 |
| **J** | Hub **自动升级** lockfile | 已有 `registry verify` + 远程 URL 预扫描 |

---

## 3. 已落地子集（P5–P10 速查）

| 批次 | 能力 |
|------|------|
| P5 | `mcp/skills sync`、ToolsEngine FC、reflexion write、injection 规则分 |
| P6 | `prompt eval`、post_session layered、injection LLM、provider presets |
| P7 | install pre-scan、`mcp scan`、`BUTLER_INJECTION_LLM_GATE` |
| P8 | `provider apply`、`/模型 preset`、`prompt eval --corpus-live` |
| P9 | `--llm`、`--corpus-live-smoke`、`BUTLER_TOOLS_ENGINE_SSOT` |
| P10 | thinking beta 头矩阵、`registry verify`、`--corpus-live-full`、schema 多轮 repair、`trading-debate` workflow、`sessions layered`、`/预设` |

---

## 4. 与外部 Agent 五报告路线图的关系

[`external-agent-reports-improvement-roadmap-2026-05.md`](external-agent-reports-improvement-roadmap-2026-05.md) 中 PR-X 与 P5–P10 重叠项以代码为准。**否决项**仍以本文 §1 与四报告 §2 为准。

---

## 5. 维护义务

- 新否决项：写入 §1。
- 新完成 P2 子集：写入 §3，从 §2 删除或改为「深化边界」说明。

---

## 6. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 初版：S1–S11、P2 未排期 |
| 2026-05-25 | P5–P9 分批落地（见 §3） |
| 2026-05-25 | P10：thinking headers、hub manifest、corpus live full、schema registry/repair、trading-debate、§2 收口 |
| 2026-05-25 | 熵减：`butler-five-reports-gate.sh`、AGENTS/CONTRIBUTING/路线图状态对齐 |
