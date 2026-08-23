# WFXM BlackBoard State

_last_synced: 2026-08-23 15:40_
_handoff: docs/plans/active/v5-acceptance-handoff-2026-08.md_
_commit: (pending) sandbox SSL + registry smoke fix_

## 验收状态 ✅

| 检查 | 结果 |
| --- | --- |
| `pnpm test:p4-acceptance` | 6/6 PASS |
| `pnpm test` | 740 passed, 1 skipped |
| `pnpm smoke:allowlist-production` | PASS |
| `pnpm smoke:allowlist-slirp` | PASS |
| `pnpm smoke:allowlist-pnpm` | PASS（live registry HTTPS） |
| `pnpm smoke:schedule` | PASS |

## 生产 env

- P2c allowlist + **P2d slirp** ✅
- `BUTLER_V5_SANDBOX_EGRESS_UPSTREAM_PROXY=http://127.0.0.1:7890` ✅（mihomo）
- Durable Memory + Schedule ✅

## 下一主线（Owner）

- **P3 MCP 契约补全** — issue 草稿：`v5-p3-mcp-contract-issue-draft-2026-08.md`（待开 GitHub issue）
- 日常回归见下

## 日常回归

```bash
cd butler-v5 && pnpm test:p4-acceptance
pnpm smoke:allowlist-production
pnpm smoke:allowlist-slirp
pnpm smoke:allowlist-pnpm
pnpm smoke:schedule
```

## 上一班

- 修复 allowlist live registry 探测（`/etc/ssl` bind + python HTTPS）；pnpm smoke 全绿；P3 MCP issue 草稿。
