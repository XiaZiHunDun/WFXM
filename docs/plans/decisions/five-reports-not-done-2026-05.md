# 五报告 — 未作与边界索引（2026-05）

> **主入口（推荐）**：[`roadmap-backlog-and-boundaries-2026-05.md`](../decisions/roadmap-backlog-and-boundaries-2026-05.md) — 合并各路线图「不做 / 深化边界 / Backlog」。  
> **已落地**：PR-F1–F6 + P5–P10 → [`../guides/five-reports-capabilities-2026-05.md`](../../guides/five-reports-capabilities-2026-05.md)、[`../guides/external-agent-reports-capabilities-2026-05.md`](../../guides/external-agent-reports-capabilities-2026-05.md)  
> **四报告否决**：[`four-reports-out-of-scope-2026-05.md`](../decisions/four-reports-out-of-scope-2026-05.md)（优先于五报告重叠项）

提新需求前：先读 **主入口 §0 决策流**，再查下表 S1–S11。

---

## S1–S11 否决（勿立项）

| # | 能力 | Butler 替代 |
|---|------|-------------|
| S1 | claude-mem Bun Worker + Chroma MCP | `semantic_index` + observations.tsv |
| S2 | claude-mem IDE / Viewer | CLI / 微信 |
| S3 | CC Switch Tauri 桌面 | CLI + `/诊断` |
| S4 | 五 CLI live 双向同步 | `project.yaml` |
| S5 | CC Switch HTTP 代理全家桶 | 薄 MCP |
| S6 | PEG LangChain Agent 运行时 | 自建 Loop |
| S7 | PEG ToT/APE 全自动搜索 | `prompt eval` |
| S8 | TradingAgents LangGraph + 行情 | workflow YAML |
| S9 | SQLite checkpoint 进 core | transcript + human_gate |
| S10 | LobeHub 浏览器 Loop/UI | 微信 Gateway |
| S11 | 全量 MCP Host + OTEL 默认 | 薄 MCP + metrics |

原因与原文：[`five-reports-improvement-roadmap-2026-05.md`](../roadmaps/five-reports-improvement-roadmap-2026-05.md) §6。

---

## 深化边界（非「未做」）

PR-F1–F6 与 P5–P10 子集已落地；路线上仍可能写的「全量对标」见主入口 **§2.1**。

| 批次 | 能力摘要 |
|------|----------|
| P5 | mcp/skills sync、ToolsEngine、reflexion write |
| P6 | prompt eval、post_session layered、injection LLM、presets |
| P7 | install pre-scan、injection gate |
| P8 | provider apply、`/模型 preset` |
| P9 | LLM rubric、corpus live smoke、ToolsEngine SSOT |
| P10 | thinking beta、`registry verify`、corpus live full、trading-debate |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-25 | 正文合并至 `roadmap-backlog-and-boundaries`；本文保留索引 |
