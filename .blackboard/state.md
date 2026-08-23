# WFXM BlackBoard State

_last_synced: 2026-08-23 20:47_
_handoff: docs/plans/active/v5-mcp-multi-server-handoff-2026-08.md_
_commit: b59651a2 (github trim + wechat allowlist)_

## 主线

P3 MCP ✅ — Grant 验收通过；github 只读裁剪 + 微信 Loop MCP 白名单已 commit（`b59651a2`）。

## 生产 MCP

- manifest github：26 → 14 只读工具（待 gateway 重启生效）
- 微信白名单：`config/wechat-tool-allowlist.json`（需 env `BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH`）

## 下一步

1. commit + push
2. 生产 env 加 `BUTLER_V5_WECHAT_TOOL_ALLOWLIST_PATH=config/wechat-tool-allowlist.json` 并 restart gateway
3. Project Knowledge — 单独立项

## 不要做

- 浏览器 MCP / Marketplace
- env 里留 `BUTLER_V5_MCP_COMMAND`
- 改 ai_guard 无 `[MANUAL-OVERRIDE]`

## 上一班

- github manifest 只读裁剪；微信 Loop 按 project 过滤 MCP；40 项相关测试通过。
