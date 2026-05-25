# Sprint B–D（agency + awesome + Firecrawl 子集）

> 总索引：[sprint-roadmap-2026-05.md](./sprint-roadmap-2026-05.md)

对标四份报告的 **可落地子集**，不引入新 pip 依赖。

## Sprint B

| 能力 | 文件 | 开关 |
|------|------|------|
| Handoff 结构化块 | `butler/core/handoff.py` | `delegate_task` / `nexus-*` category 自动注入 |
| dev-qa-loop 工作流 | `butler/workflows/builtin/dev-qa-loop.yaml` | `run_workflow` |
| `max_retries` 透传 | `butler/workflows/schema.py` → `TaskNode` | YAML `max_retries` |
| 证据优先 review | `butler/agent_profiles.py` | review / `nexus-micro` |
| MCP profiles | `butler/mcp/profiles.py` | `BUTLER_MCP_PROFILES=1`，`~/.butler/mcp.yaml` 内 `profiles` / `mcp_profile_routing` |
| 入站 I/O guardrail | `butler/core/io_guardrail.py` | `BUTLER_IO_GUARDRAIL=1`，`BUTLER_IO_GUARDRAIL_BLOCK=1` 拦截 |

### MCP profiles 示例（`~/.butler/mcp.yaml`）

```yaml
profiles:
  default: [filesystem, fetch]
  browser: [playwright]
mcp_profile_routing:
  browser: [浏览器, 截图, playwright]
  fetch: [抓取, 网页, firecrawl]
```

## Sprint C

| 能力 | 文件 | 开关 |
|------|------|------|
| 纠错召回 | `butler/memory/corrective_recall.py` | `BUTLER_CORRECTIVE_RECALL=1`（委派子 loop 工具失败时追加检索块） |
| 多语料库路由 | `butler/memory/corpus_router.py` | `BUTLER_CORPUS_ROUTING=1`，`search_project_knowledge` |
| RAG `/诊断` 行 | `butler/ops/rag_diagnostics.py` | 随 `/诊断` 输出 |

## Sprint D

| 能力 | 文件 | 开关 |
|------|------|------|
| `web_fetch` | `butler/tools/web_fetch.py` | `BUTLER_ENABLE_WEB_FETCH=1` |
| 委派并发上限 | `butler/core/delegate_semaphore.py` | `BUTLER_DELEGATE_MAX_CONCURRENT=2` |
| `group_id` | `butler/runtime/task_store.py` | 任务 JSON 字段 `group_id` |
| ops-checklist 配方 | `butler/workflows/builtin/ops-checklist.yaml` | 内置工作流 |

## 测试

```bash
pytest tests/test_sprint_bcd.py -q
```

## 明确不做

Redis/RabbitMQ、Playwright 农场、189 Agent 包、Agno/LangGraph 运行时、整包 Gemini ContextManager。
