# ADR：压缩边界防腐层（Compaction ACL）

> **状态**：已采纳（2026-06-29）  
> **边界**：Compaction / 压缩模块 → Agent Loop（`ContextPipeline` / `compaction_task`）  
> **关联**：[`v4-context-memory-compaction.md`](../../architecture/v4-context-memory-compaction.md) · ENG-6 contracts

## 背景

会话压缩输出形态可能演进（纯字符串、`{"raw"}`、`{"summary","tags"}`、PostCompact hook `additionalContext`）。Agent Loop 与 `ContextPipeline` 应只依赖**不变内部契约**，外部变种在适配器层消化。

## 决策

1. **神圣契约**：`LoopCompactionView`（`butler/contracts/compaction_ports.py`）— `content: str` + `schema_version` + `metadata`
2. **适配器**：`to_loop_compaction_view()`（`butler/core/compaction_context_adapter.py`）— 永不向调用方抛异常；失败降级空 `content` + `compaction_acl_degraded`
3. **单入口接线**：
   - `ContextPipeline.compress_context` — `compress_messages` 的 `summary` 经适配器
   - `compaction_task.run_compaction_turn` — PostCompact hook 上下文经适配器写入 `diagnostics`
4. **Schema CI**：`schemas/compaction/loop_compaction_view.v1.json` + `scripts/check-schema-drift.sh`

## 外部变种登记

| 形态 | 示例 | 适配结果 |
|------|------|----------|
| v0 str | `"摘要文本"` | `content=strip()` |
| v1 raw | `{"raw": "..."}` | `content=raw` |
| v2 summary+tags | `{"summary": "...", "tags": ["a"]}` | `content=summary [标签: a]` |
| hook / 未知 | dict 无已知键 | `content=str(...)` + `metadata.acl_warn` |

## 非目标

- 全量 `messages: list[dict]` Pydantic 化
- LangGraph 替换 Loop

## ACL 剩余项（2026-06-29 结案）

| 项 | 状态 | 落点 |
|----|------|------|
| DevEngine `PLAN→FIX` 快照 ACL | ✅ | [`dev-engine-acl-adr`](dev-engine-acl-adr-2026-07.md) `LoopDevStateView` |
| 双 EventsSink 合并 | ✅ | [`events-sink-unification-adr`](events-sink-unification-adr-2026-07.md) |
| Memory/Message ACL | ✅ | `ef834e5` — `LoopMemoryView` / `LoopApiMessageView` |

## 扩展（ACL-5～6，2026-06-29）

- **pre_compact** `additionalContext` → `hook_context_adapter` → `compaction_pre_hook_context`
- **checkpoint restore** 摘要 preview 再过 `to_loop_compaction_view`
- **UserPromptSubmit / Stop** hooks → `HookContextView`（[`hook_context_ports.py`](../../butler/contracts/hook_context_ports.py)）

## 验收

- `tests/core/test_compaction_context_adapter.py` ≥12 cases
- `tests/core/test_context_pipeline_acl.py` mock v2 summary 绿
- `bash scripts/check-schema-drift.sh` exit 0（契约未变时）
