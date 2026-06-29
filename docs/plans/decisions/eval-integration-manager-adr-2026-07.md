# ADR：Eval 统一接入管理器（EvalIntegrationManager）

> **状态**：已采纳（2026-06-29）· **Phase 1 落地**  
> **理论**：[`v4.5-modular-eval-context-theory.md`](../../architecture/v4.5-modular-eval-context-theory.md)

## 背景

Eval 分散在 ~15 个 shell、`eval_bridge`、TCR、`agent_eval_weekly`；两套 KPI（LangFuse 四维 vs TCR）无统一调度与报告 schema。

## 决策

1. 新增 `butler/eval_integration/`，实现 **EvalIntegrationManager**
2. **多后端并列 SSOT**：LangFuse / junit / audit 各自存储；`EvalReport v1` 仅索引 + 聚合
3. CLI：`butler eval list|run|report|sync`
4. 现有 shell **保留薄包装** 至少一个版本周期

## Suite 首版

| ID | Layer | Sinks |
|----|-------|-------|
| `tcr` | L-B | junit, audit |
| `agent_weekly` | L-D | audit |
| `capability` | L-D | audit（季度三件套） |

## 非目标

- 不替换 LangFuse 为唯一 SSOT
- Phase 1 不接入 DeepEval/RAGAS（Phase 4 opt-in）

## 验收

- `butler eval run --preset release --no-langfuse` exit 0
- `tests/eval_integration/test_manager.py` 绿
