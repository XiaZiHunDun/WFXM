# ADR：API 消息边界子集（Message ACL）

> **状态**：已采纳（2026-06-30）  
> **边界**：`prepare_messages_for_api` 的 `repair_sanitize` 之后 → LLM transport  
> **关联**：[`memory-acl-adr-2026-07.md`](memory-acl-adr-2026-07.md) · [`compaction-acl-adr-2026-07.md`](compaction-acl-adr-2026-07.md)

## 背景

消息 `content` 可能为 str、多模态 block list、或畸形 dict。全量会话 Pydantic 化成本高；在 **API 发送边界** 用 per-message 视图做可观测校验即可。

## 决策

1. **神圣契约**：`LoopApiMessageView`（`butler/contracts/message_ports.py`）— `role` + 规范化 `content: str`
2. **适配器**：`to_loop_api_message_view()`（`butler/core/message_context_adapter.py`）
3. **opt-in 接线**：`BUTLER_API_MESSAGE_ACL=1` 时 `annotate_api_message_boundary` 仅写 diagnostics，**不**改写 messages
4. **Schema CI**：`schemas/message/loop_api_message_view.v1.json`

## 非目标

- 全量 conversation state Pydantic
- 在 ACL 层删除 tool_calls / thinking blocks

## 验收

- `tests/core/test_message_context_adapter.py` 绿
- 默认 `BUTLER_API_MESSAGE_ACL=0` 行为不变
