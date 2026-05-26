# 已落地能力总索引（env / 守门）

> **更新**：2026-05-25 | 详表见各 `*-capabilities` 与路线图 §9/§10  
> **勿从对照报告正文抽待办** — [`roadmap-backlog`](../plans/decisions/roadmap-backlog-and-boundaries-2026-05.md)

| 主线 | 速查文档 | 典型守门 |
|------|----------|----------|
| CC 线束 P0–P4 | [`cc-butler-gap-analysis`](../plans/active/cc-butler-gap-analysis-2026-05.md) | `test_cc_p3_p4_features.py` |
| 四报告 PR1–PR6 | [`four-reports-capabilities`](./four-reports-capabilities-2026-05.md) | `test_ragflow_p0_retrieval` 等 |
| 五报告 PR-F + P5–P10 | [`five-reports-capabilities`](./five-reports-capabilities-2026-05.md) · [`external-agent-reports-capabilities`](./external-agent-reports-capabilities-2026-05.md) | `butler-five-reports-gate.sh` |
| 外部 Agent PR-X | [`external-agent-reports-improvement-roadmap`](../plans/roadmaps/external-agent-reports-improvement-roadmap-2026-05.md) §10 | `test_external_agent_*.py` |
| 外部对标 A/B/C | [`phase-abc-external-reference`](./phase-abc-external-reference.md) | `test_phase_a/b/c_external.py` |
| OpenCode | [`opencode-parity`](./opencode-parity.md) | `test_opencode_*` |
| 运行指标 | [`diagnostic-thresholds`](../ops/diagnostic-thresholds.md) | `test_runtime_metrics.py` |
| MCP 薄客户端 | [`butler-mcp-capability`](../plans/comparisons/butler-mcp-capability-2026-05.md) | `BUTLER_MCP_ENABLED` |

**env 权威列表**：[`config/reference.md`](../config/reference.md) + [`.env.example`](../../.env.example)
