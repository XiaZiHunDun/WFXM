# WFXM BlackBoard State

_last_synced: 2026-08-23 20:50_
_handoff: docs/plans/active/v5-mcp-multi-server-handoff-2026-08.md_
_commit: b30466d7_

## 主线

P3 MCP ✅ — github 只读裁剪 + 微信白名单已生产生效（22 tools）。

## 生产 MCP

- `mode: multi`，22 tools（markitdown 1 + firecrawl 3 + github 14 + todoist 4）
- 白名单 env：`BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH=config/wechat-tool-allowlist.json`
- 验收: `butler mcp status --api http://127.0.0.1:3000`

## 下一步

1. Project Knowledge — 单独立项
2. markitdown / github 真调用 Grant 验收（可选）

## 不要做

- 浏览器 MCP / Marketplace
- env 里留 `BUTLER_V5_MCP_COMMAND`
- 改 ai_guard 无 `[MANUAL-OVERRIDE]`

## 上一班

- 生产 env + gateway 重启；MCP 22 tools / github 无写工具；verify 全绿。
