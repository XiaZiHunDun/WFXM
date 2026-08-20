# WFXM BlackBoard State

_last_synced: 2026-08-20 21:17_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- MCP：`http` / `sse` / `stdio` 三传输；Slack/Telegram webhook 入站已接。
- 全部 opt-in，默认 off；`main` 直接 push。

## 下一步

- Slack/Telegram 出站回复；MCP 长连接 session 管理。

## 上一班

- stdio/SSE MCP + Slack/Telegram adapters；630 测试全绿。
