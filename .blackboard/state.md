# WFXM BlackBoard State

_last_synced: 2026-08-23 15:38_
_handoff: docs/plans/active/v5-acceptance-handoff-2026-08.md_
_commit: bb20a07d (pushed main)_

## 验收状态 ✅

| 检查 | 结果 | 时间 |
| --- | --- | --- |
| `pnpm test:p4-acceptance` | 6/6 PASS | 2026-08-23 |
| `pnpm test` | 740 passed, 1 skipped | 2026-08-23 |
| `tsx cli/src/index.ts verify --api …` | 9 migrations + healthz ok | 2026-08-23 |
| `pnpm smoke:allowlist-production` | PASS | 2026-08-23 |
| `pnpm smoke:allowlist-slirp` | PASS（rawBlocked + proxyPath） | 2026-08-23 |
| `pnpm smoke:schedule` | PASS（tick fired=1） | 2026-08-23 |

开发主线已收口；**稳态运维**。

## 生产 env

- P2c allowlist ✅（`SANDBOX_NETWORK_MODE=allowlist`）
- **P2d slirp ✅**（`SANDBOX_EGRESS_ISOLATION=slirp`，2026-08-23 启用 + gateway 重启）
- `BUTLER_V5_DURABLE_MEMORY=1` ✅
- `BUTLER_V5_SCHEDULE_ENABLED=1` ✅（`config/schedule-jobs.json`）

## 下一可选（Owner 决策）

1. **live registry + slirp** — `pnpm smoke:allowlist-pnpm`（需 npm registry 出网）
2. **P3 立项** — MCP per-tool Grant / Provider 卸载失效

## 日常回归

```bash
cd butler-v5 && pnpm test:p4-acceptance
pnpm smoke:allowlist-production
pnpm smoke:allowlist-slirp
pnpm smoke:schedule
pnpm exec tsx cli/src/index.ts verify --api http://127.0.0.1:3000
```

## 不要做

- 不立项浏览器 / 完整 Web UI / RAG Studio
- 不把 `packages/application/_archive` 接回生产

## 上一班

- housekeeping 推送 `bb20a07d`；Schedule + P2d slirp 冒烟全绿；生产启用 slirp。
