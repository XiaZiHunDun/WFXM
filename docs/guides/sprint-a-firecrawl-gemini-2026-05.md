# Sprint A：网关稳定 + 上下文 G-P0（2026-05）

> 来源：[`firecrawl-butler-comparison-2026-05.md`](../plans/comparisons/firecrawl-butler-comparison-2026-05.md) P0 + [`gemini-cli-butler-comparison-report-2026-05.md`](../plans/comparisons/gemini-cli-butler-comparison-report-2026-05.md) G-P0-1～3

## 已落地

| 项 | 模块 | 说明 |
|----|------|------|
| 入站幂等 | `butler/gateway/inbound_idempotency.py` | `external_id` 去重；`BUTLER_GATEWAY_EXTERNAL_ID_DEDUPE=1` |
| 委派 stale | `butler/runtime/task_store.py` | `BUTLER_TASK_STALE_MINUTES`；`/任务`、`/诊断` |
| 恢复分桶 | `butler/ops/retry_buckets.py` | `recovery_event{reason=...}`；schema/failover/guardrail 等 |
| Tool masking | `butler/core/tool_output_masking.py` | `context_pipeline` 在 backward prune 之后 |
| 压缩前截断 | `context_compressor.truncate_tool_responses_to_budget` | `BUTLER_COMPRESS_TOOL_RESPONSE_BUDGET` |
| 压缩状态 | `butler/core/compaction_status.py` | `/诊断` 显示 truncated / inflated_fail 等 |

## 验收

```bash
PYTHONPATH=. pytest tests/test_sprint_a_gateway.py tests/gateway/test_message_queue.py -q
```

## 后续 Sprint（已落地）

- Sprint B–D 见 [sprint-roadmap-2026-05.md](./sprint-roadmap-2026-05.md) 与 [sprint-bcd-agency-awesome-2026-05.md](./sprint-bcd-agency-awesome-2026-05.md)
- 含：`web_fetch`（可选）、`group_id`、委派并发、`dev-qa-loop`、MCP profiles、纠错召回等

## 仍 defer

- Firecrawl 全量 MCP / Playwright 农场
- Gemini G-P1+ 整包 ContextManager
