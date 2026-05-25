# 四报告 Sprint 路线图（A–D）

> 2026-05-25 · 来源：Firecrawl、agency-agents、Gemini CLI、awesome-llm-apps 对照报告  
> 原则：**零新增 pip**、单进程微信网关、只提炼模式不粘贴泄露 prompt

## 总览

| Sprint | 指南 | 测试 | 状态 |
|--------|------|------|------|
| **A** 网关 + G-P0 | [sprint-a-firecrawl-gemini-2026-05.md](./sprint-a-firecrawl-gemini-2026-05.md) | `tests/test_sprint_a_gateway.py` | ✅ 已落地 |
| **B** NEXUS + MCP + I/O | [sprint-bcd-agency-awesome-2026-05.md](./sprint-bcd-agency-awesome-2026-05.md) §B | `tests/test_sprint_bcd.py` | ✅ 已落地 |
| **C** RAG / 语料路由 | 同上 §C | 同上 | ✅ 已落地 |
| **D** web_fetch + 并发 + 配方 | 同上 §D | 同上 | ✅ 已落地 |

```bash
PYTHONPATH=. pytest tests/test_sprint_a_gateway.py tests/test_sprint_bcd.py -q
```

## 对照报告（设计来源）

| 报告 | 路径 |
|------|------|
| Firecrawl | [../plans/firecrawl-butler-comparison-2026-05.md](../plans/firecrawl-butler-comparison-2026-05.md) |
| agency-agents | [../plans/agency-agents-extraction-analysis-2026-05.md](../plans/agency-agents-extraction-analysis-2026-05.md) |
| Gemini CLI | [../plans/gemini-cli-butler-comparison-report-2026-05.md](../plans/gemini-cli-butler-comparison-report-2026-05.md) |
| awesome-llm-apps | [../plans/awesome-llm-apps-butler-comparison-report-2026-05.md](../plans/awesome-llm-apps-butler-comparison-report-2026-05.md) |

与 [external-reference-roadmap-2026-05.md](./external-reference-roadmap-2026-05.md)（Hermes/LangChain/Dify/Langflow 阶段 A/B/C）、[phase-d-prompt-corpus.md](./phase-d-prompt-corpus.md)（Prompt Corpus D/E）**正交**，可并行阅读。

## 内置工作流（Sprint B/D）

| 名称 | 用途 |
|------|------|
| `dev-qa-loop` | 开发实现 → 证据优先审查（`max_retries` 透传） |
| `ops-checklist` | 发版前只读巡检 + 摘要写入 `docs/workflow-output.md` |

微信：`/运行 dev-qa-loop <目标>` 或项目配置的 `run_workflow`。

## 委派 category（Sprint B）

`~/.butler/delegate_categories.yaml` 内置扩展：

- `nexus-sprint` — 实现 + Handoff
- `nexus-micro` — 只读证据审查

## 关键环境变量

见 [../config/reference.md](../config/reference.md)（Sprint A–D 段）与 `.env.example` 注释块 `Sprint A` / `Sprint B–D`。

## 明确不做

Redis/RabbitMQ、Playwright 农场、189 Agent 包、Agno/LangGraph 运行时、整包 Gemini ContextManager、Firecrawl 全量 SDK 内嵌。
