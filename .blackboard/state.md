# WFXM BlackBoard State

_last_synced: 2026-08-23 15:32_
_handoff: docs/plans/active/v5-acceptance-handoff-2026-08.md_
_commit: f852070e (pushed main)_

## 验收状态 ✅

| 检查 | 结果 | 时间 |
| --- | --- | --- |
| `pnpm test:p4-acceptance` | 6/6 PASS | 2026-08-23 |
| `pnpm test` | 740 passed, 1 skipped | 2026-08-23 |
| `tsx cli/src/index.ts verify --api …` | 9 migrations + healthz ok | 2026-08-23 |
| `pnpm smoke:allowlist-production` | PASS | 2026-08-23 |

开发主线已收口；进入**稳态运维**，不默认开新 P4 产品面。

## 生产 env

- P2c allowlist ✅（`SANDBOX_NETWORK_MODE=allowlist`）
- P2d slirp **未启用**（默认 `SANDBOX_EGRESS_ISOLATION=proxy`）
- `BUTLER_V5_DURABLE_MEMORY=1` ✅
- `BUTLER_V5_SCHEDULE_ENABLED` 默认关

## 下一可选（Owner 决策，非必做）

1. **P2d 生产 opt-in** — 设 `BUTLER_V5_SANDBOX_EGRESS_ISOLATION=slirp` → restart gateway → `pnpm smoke:allowlist-slirp`
2. **Schedule 点验** — `BUTLER_V5_SCHEDULE_ENABLED=1` + `config/schedule-jobs.json` → `pnpm smoke:schedule`
3. **P3 立项** — MCP per-tool Grant / Provider 卸载失效（需单独立项）

## 日常回归

```bash
cd butler-v5 && pnpm test
pnpm test:p4-acceptance
pnpm exec tsx cli/src/index.ts verify --api http://127.0.0.1:3000
pnpm smoke:allowlist-production
```

## 不要做

- 不立项浏览器 / 完整 Web UI / RAG Studio
- 不把 `packages/application/_archive` 接回生产

## 上一班

- 验收全绿（p4 + 740 tests + verify + production smoke）；黑板更新。
