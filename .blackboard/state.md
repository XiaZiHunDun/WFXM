# WFXM BlackBoard State

_last_synced: 2026-08-21 08:40_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- MCP：`http` / `sse` / `stdio`；Slack/Telegram 入站 + 出站（bot token 自动投递）。
- 全部 opt-in，默认 off；`main` 直接 push。

## 下一步

- MCP 长连接 session 管理；Grant 动态 network hosts。

## 上一班

- Slack `chat.postMessage` + Telegram `sendMessage` 出站；633 测试全绿。
