# 外部对标统一路线图（Hermes / LangChain / Dify / Langflow）

> 2026-05-25 · **唯一 backlog 索引**（阶段 A/B/C + 补做 + defer）  
> 原则：零新增 pip（`cryptography` 仅 wechat extra）、不替换 `agent_loop`、微信单平台

## 落地文档（按阶段）

| 阶段 | 文档 | 验收测试 |
|------|------|----------|
| A — 微信体验与网关 | [phase-abc-external-reference.md](./phase-abc-external-reference.md) §A | `tests/test_phase_a_external.py` |
| B — 安全 / 工作流 / 工具纪律 | [phase-abc-external-reference.md](./phase-abc-external-reference.md) §B | `tests/test_phase_b_external.py` |
| C — 规模与工程化 | [phase-abc-external-reference.md](./phase-abc-external-reference.md) §C | `tests/test_phase_c_external.py` |
| 补做 + defer 分析 | [external-reference-deferred-2026-05.md](./external-reference-deferred-2026-05.md) | `tests/test_deferred_external.py` |

```bash
pytest tests/test_phase_a_external.py tests/test_phase_b_external.py \
  tests/test_phase_c_external.py tests/test_deferred_external.py -q
```

## 对照报告（设计来源）

| 报告 | 路径 |
|------|------|
| Hermes | [../architecture/hermes-butler-comparison-2026-05.md](../architecture/hermes-butler-comparison-2026-05.md) |
| LangChain | [../plans/langchain-butler-comparison-2026-05.md](../plans/langchain-butler-comparison-2026-05.md) |
| Dify | [../plans/dify-butler-comparison-2026-05.md](../plans/dify-butler-comparison-2026-05.md) |
| Langflow | [../plans/langflow-butler-comparison-2026-05.md](../plans/langflow-butler-comparison-2026-05.md) |

与 **OpenCode / CC 线束** 正交：见 [opencode-parity.md](./opencode-parity.md)、[../plans/cc-butler-gap-analysis-2026-05.md](../plans/cc-butler-gap-analysis-2026-05.md)。

**四报告 Sprint（Firecrawl / agency / Gemini / awesome）** 另见 [sprint-roadmap-2026-05.md](./sprint-roadmap-2026-05.md)（A–D 已落地，与上表阶段 A/B/C 独立）。

## 状态摘要（2026-05-25）

| 阶段 | 状态 |
|------|------|
| A | ✅ 已落地 |
| B | ✅ 已落地 |
| C | ✅ 已落地 |
| 补做（secrets、list_workflows、search_project_knowledge、smart approve 等） | ✅ 已落地 |
| defer（Fernet、execute_code 生产、iLink 真流式、全量 RAG ingest） | 📋 单独立项 |

## 关键 CLI

```bash
butler workflow validate --path .butler/workflows/foo.yaml
butler secrets status
butler secrets set minimax <api-key>   # 写入 ~/.butler/secrets.yaml，勿提交 git
```

## 配置索引

- 环境变量：[../config/reference.md](../config/reference.md)
- 权限模板：[../templates/permissions.yaml.example](../templates/permissions.yaml.example)（含 `tool_policies`）
