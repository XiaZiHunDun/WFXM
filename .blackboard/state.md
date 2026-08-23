# WFXM BlackBoard State

_last_synced: 2026-08-23 16:05_
_handoff: docs/plans/active/v5-p3-mcp-contract-issue-draft-2026-08.md_
_commit: (pending) P3 MCP Grant scope_

## P3 MCP 契约 ✅（#3 首包）

| 项 | 状态 |
| --- | --- |
| `McpToolCapability` + Grant scope 规范化 | ✅ domain `mcp-tool-capability.ts` |
| Policy `grantMatchesAction` per-tool | ✅ |
| 审批签发 `scope.mcp` | ✅ `approval-runtime` |
| Provider 卸载 revoke | ✅ `mcp-grant-lifecycle` + bootstrap |
| 测试 | 748 passed |

## 日常回归

```bash
cd butler-v5 && pnpm test
pnpm test:p4-acceptance
```

## 上一班

- 实现 GitHub #3 P3 MCP 首包：per-tool Grant scope、卸载 revoke、provider 元数据骨架。
