# ADR：记忆预取边界防腐层（Memory ACL）

> **状态**：已采纳（2026-06-30）  
> **边界**：记忆检索 / 外部 chunk 形态 → `memory_prefetch` / `pre_llm_transform`  
> **关联**：[`compaction-acl-adr-2026-07.md`](compaction-acl-adr-2026-07.md) · [`v4-context-memory-compaction.md`](../../architecture/v4-context-memory-compaction.md)

## 背景

记忆预取来源可能演进（纯字符串、`{"content"}`、`{"chunks":[]}`、snippet 列表、向量检索 dict）。注入 Loop 前应只依赖 **LoopMemoryView** 不变契约。

## 决策

1. **神圣契约**：`LoopMemoryView`（`butler/contracts/memory_ports.py`）— `content: str` + `schema_version` + `metadata`
2. **适配器**：`to_loop_memory_view()` / `adapt_memory_prefetch_content()`（`butler/core/memory_context_adapter.py`）— 永不向调用方抛异常
3. **单入口接线**：`prefetch_turn_memory` 在缓存写入前经 `_normalize_prefetch_body`；缓存命中经 `_decorate_prefetch_for_turn`（含 Reflection 注入）
4. **Schema CI**：`schemas/memory/loop_memory_view.v1.json` + `check-schema-drift.sh`

## 非目标

- 全量 `messages: list[dict]` Pydantic 化（见 Message ACL 子集）
- 向量索引内部文档 schema 外置

## 验收

- `tests/core/test_memory_context_adapter.py` 绿
- `bash scripts/check-schema-drift.sh` exit 0
