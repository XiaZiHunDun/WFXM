# WFXM BlackBoard State

_last_synced: 2026-08-23 20:10_
_handoff: docs/plans/active/v5-mcp-multi-server-handoff-2026-08.md_
_commit: 80017a8c (feat(v5) multi-server MCP)_

## 主线

P3 MCP 四 server 生产接线 ✅ — 见交接文档。

## 生产 MCP

- `mode: multi`，34 tools（markitdown 1 + firecrawl 3 + github 26 + todoist 4）
- manifest: `butler-v5/config/mcp-manifest.json`
- 验收: `butler mcp status --api http://127.0.0.1:3000`

## 下一步

1. 真调用 + Grant 验收（firecrawl / todoist）
2. Project Knowledge — 单独立项
3. `pnpm test` 全绿后 push

## 不要做

- 浏览器 MCP / Marketplace
- env 里留 `BUTLER_V5_MCP_COMMAND`（会串台）
- 改 ai_guard 无 `[MANUAL-OVERRIDE]`

## 上一班

- multi-server MCP bootstrap 落地；交接文档已写；commit `b8f1b2a5`。
