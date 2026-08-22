# WFXM BlackBoard State

_last_synced: 2026-08-22 17:35_
_handoff: docs/plans/active/v5-acceptance-handoff-2026-08.md_

## 生产 env

- P2c allowlist ✅（`SANDBOX_NETWORK_MODE=allowlist`）
- P2d slirp 未启用（默认 `SANDBOX_EGRESS_ISOLATION=proxy`）
- `pnpm smoke:allowlist-slirp` ✅（rawBlocked + proxyPath）

## 当前主线

- **P2d slirp MVP ✅** — iptables 隔离 + in-netns 探测通过
- **上游代理** — `BUTLER_V5_SANDBOX_EGRESS_UPSTREAM_PROXY`（mihomo 等 host 出网）
- **AI guard** — [#2 已关闭](https://github.com/XiaZiHunDun/WFXM/issues/2)；清单 `v5-ai-guard-migration-checklist-2026-08.md`

## P2d 启用

```bash
# ~/.config/butler-v5/env
BUTLER_V5_SANDBOX_EGRESS_ISOLATION=slirp
# 若 host 需系统代理出网：
# BUTLER_V5_SANDBOX_EGRESS_UPSTREAM_PROXY=http://127.0.0.1:7890
systemctl --user restart butler-v5-gateway.service
pnpm smoke:allowlist-slirp
```

## 日常回归

```bash
cd butler-v5 && pnpm test
pnpm smoke:allowlist-production
pnpm smoke:allowlist-slirp   # P2d opt-in 点验
```

## 上一班

- 修复 slirp iptables（PATH/xtables.lock/串行）；探测全绿；AI guard issue #2。
