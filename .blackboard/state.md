# WFXM BlackBoard State

_last_synced: 2026-08-20 21:13_
_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md

## 当前主线

- Butler v5 / `main`：MCP HTTP bootstrap + 第二 Channel intake 接缝已落地。
- 生产：微信 iLink opt-in；MCP/Channel 均默认 off。

## 下一步

- Slack/Telegram 等专用 Channel 适配（立项后）。
- D1：2026-09-18 前不删除 `~/.butler/`。

## 不要做

- 不把黑板迁进 v5 Run / Task。

## 上一班

- MCP JSON-RPC HTTP + `POST /v1/channel/inbound`；619 测试全绿。
