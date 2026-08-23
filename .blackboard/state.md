# WFXM BlackBoard State

_last_synced: 2026-08-23 20:53_
_handoff: docs/plans/active/v5-mcp-multi-server-handoff-2026-08.md_
_commit: 9229fff5_

## 主线

P3 MCP 全链路验收完成 — 四 server 真调用 + Grant 均已通过。

## 生产 MCP

- `mode: multi`，22 tools（github 14 只读）
- 白名单：`BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH=config/wechat-tool-allowlist.json`
- 已验 Grant：firecrawl / todoist / github(search) / markitdown

## 下一步

1. **Project Knowledge** — 单独立项（Owner 确认场景）
2. 无其他 P3 MCP 阻塞项

## 不要做

- 浏览器 MCP / Marketplace
- env 里留 `BUTLER_V5_MCP_COMMAND`
- 改 ai_guard 无 `[MANUAL-OVERRIDE]`

## 上一班

- github + markitdown Grant 真调用验收通过；黑板已 push `9229fff5`。
