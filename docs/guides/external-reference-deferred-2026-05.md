# 外部对标 — 剩余项分析与落地状态

> 2026-05-25 · 汇总 Hermes / LangChain / Dify / Langflow 四报告 + 阶段 A/B/C  
> **统一索引**：[`../plans/roadmap-backlog-and-boundaries-2026-05.md`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)（§1.3 否决、§3.1–3.2 可选 Backlog）

## 1. 总览

| 类别 | 数量 | 说明 |
|------|------|------|
| 已落地（A/B/C + 本轮） | 大部分 P0/P1 | 见各 `phase-*-external-reference.md` |
| 本轮补做 | 7 项 | 见 §2 |
| 建议不做 | 平台级能力 | 见 §3 |
| 单独立项 | 重安全/重产品 | 见 §4 |

---

## 2. 本轮已补做（原「未做」中有价值的）

| 原编号 | 项 | 模块 | 价值 |
|--------|-----|------|------|
| B9+ | `list_workflows` 工具 | `tools/workflow_tools.py` | Agent 跑 DAG 前先列可用流 |
| C8− | `search_project_knowledge` | `tools/knowledge_search.py` | 项目 MEMORY+语义检索（复用 butler_recall） |
| C9− | `secrets.yaml` 凭证分离 | `config_secrets.py` + `butler secrets` | API key 不进 config.yaml，文件 600 |
| Hermes | Terminal 模式智能批准 | `terminal_pattern_approval.py` + `/批准模式` | 同类危险命令本会话放行 |
| Hermes | `rm -rf` 模式修复 | `terminal_danger.py` | 匹配 `rm -rf /` 等 |
| LangChain | `clear_at_least` 剪枝下限 | `tool_output_prune.py` | `BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST` |
| — | 诊断行扩展 | `openclaw_diagnostics.py` | secrets / 危险模式 / 工具预选 |

---

## 3. 明确不做（四报告共识）

> **四报告专用完整清单**（browser-use / RAGFlow / design-md / autoresearch）：[`../plans/four-reports-out-of-scope-2026-05.md`](../plans/decisions/four-reports-out-of-scope-2026-05.md)

以下为 Hermes / LangChain / Dify / Langflow 阶段对标共识；与四报告清单互补，不重复展开。

| 能力 | 原因 |
|------|------|
| Hermes 单体 Loop / 多平台网关 | 违背 v4 架构 |
| LangChain + LangGraph 替换 agent_loop | 维护与边界 |
| Dify GraphEngine / Celery / plugin_daemon | 非微信管家产品 |
| Langflow 画布 / Flow JSON 一等公民 | 无 Studio |
| workflow 暂停后自动续跑 | 维持显式 `/workflow` |
| SQL 消息库替换 transcript.jsonl | 现有 JSONL + 索引够用 |
| 多租户 SaaS / 计费 | 产品边界 |
| MCP Host / 70+ 工具 / 浏览器自动化 | 范围 |
| LangSmith 默认接入 | 已有 runtime_metrics |

---

## 4. 仍建议单独立项（未在本轮实现）

| 项 | 来源 | 建议 |
|----|------|------|
| **凭证 Fernet 加密** | Dify C9 完整版 | 依赖 `cryptography`（wechat extra 已有）；`secrets.yaml` 明文+600 为过渡 |
| **execute_code 生产开放** | Hermes C7 | 须安全评审 + 审计；默认仍 `BUTLER_EXECUTE_CODE=0` |
| **微信真·流式编辑回复** | Hermes A2 | 依赖 iLink 是否支持消息编辑；现有 progressive_stream 为补充消息 |
| **LLM 工具模拟器** | LangChain P2 | 仅 `BUTLER_TOOL_EMULATE=1` 测试路径，ROI 低 |
| **契约测试基类** | LangChain P2 | 可用现有 `test_phase_*` 覆盖 |
| **OpenAPI 声明式 HTTP 工具** | Dify P2 | `.butler/tools/*.yaml` 需产品定义 |
| **全量 RAG 管道** | Dify C8 | 已有 semantic_index + butler_recall；ingest 管线另立项 |
| **权限 LLM 分类器** | Hermes | 与「无 classifier」原则冲突 |
| **Checkpointer 断点续跑** | LangChain | 单进程微信非刚需 |

---

## 5. 环境变量（本轮新增）

| 变量 | 默认 | 说明 |
|------|------|------|
| `BUTLER_SECRETS_FILE` | 1 | 从 `~/.butler/secrets.yaml` 补全 provider key |
| `BUTLER_SECRETS_PATH` | — | 自定义 secrets 路径 |
| `BUTLER_TERMINAL_SMART_APPROVE` | 1 | 危险模式可按会话批准 |
| `BUTLER_TERMINAL_PATTERN_APPROVE_TTL` | 86400 | 模式批准有效期（秒） |
| `BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST` | — | 向后剪枝最少回收字符（默认同 MINIMUM） |

---

## 6. 验收

```bash
pytest tests/test_phase_a_external.py tests/test_phase_b_external.py \
  tests/test_phase_c_external.py tests/test_deferred_external.py -q
butler secrets status
butler workflow validate --path butler/workflows/builtin/novel-factory-status.yaml
```
