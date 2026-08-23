# WFXM BlackBoard State

_last_synced: 2026-08-23 16:29_
_handoff: docs/plans/active/v5-p3-mcp-contract-issue-draft-2026-08.md_
_commit: (pending) P3 MCP Owner API_

## P3 MCP 契约 ✅（#3 完成）

| 项 | 状态 |
| --- | --- |
| per-tool Grant + bootstrap revoke | ✅ |
| Owner API `GET /v1/owner/mcp/status` | ✅ |
| Owner API `POST .../mcp/servers/:id/revoke-grants` | ✅ |
| CLI `butler mcp status|revoke-grants` | ✅ |
| MCP trace 元数据（risk/sandbox/audit + grant mcp） | ✅ |
| 测试 | 749 passed |

## 日常回归

```bash
cd butler-v5 && pnpm test && pnpm test:p4-acceptance
butler mcp status --api http://127.0.0.1:3000
```

## 上一班

- P3 #3 收尾：Owner/CLI 手动 revoke + MCP status + execution trace 元数据。
