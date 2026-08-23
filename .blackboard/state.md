# WFXM BlackBoard State

_last_synced: 2026-08-23 20:38_
_handoff: docs/plans/active/v5-mcp-multi-server-handoff-2026-08.md_
_commit: 4fa64f24 (fix MCP approval resume)_

## 主线

P3 MCP 四 server 生产接线 ✅ — Grant 真调用验收通过（firecrawl + todoist）。

## 生产 MCP

- `mode: multi`，34 tools（markitdown 1 + firecrawl 3 + github 26 + todoist 4）
- manifest: `butler-v5/config/mcp-manifest.json`
- 验收: `butler mcp status --api http://127.0.0.1:3000`

## 下一步

1. `git push`（main 超前 origin 4 commits）
2. Project Knowledge — 单独立项
3. github 工具裁剪 / 微信 Loop MCP 白名单（可选）

## 不要做

- 浏览器 MCP / Marketplace
- env 里留 `BUTLER_V5_MCP_COMMAND`（会串台）
- 改 ai_guard 无 `[MANUAL-OVERRIDE]`

## 上一班

- 修复 multi-server MCP 审批恢复（grant scope 解析 + resume 加载 mcpBundle）；firecrawl/todoist 真调用验收通过；commit `4fa64f24`。
