## R10 Pre-flight Checklist (2026-08-12)

### Verified by AI

- [x] **Local 5-gate**: `pnpm format:check / lint / typecheck / test / typecheck-gate.sh` — all exit 0
  - format: All matched files use Prettier code style
  - lint: 0 warning / 0 error (`--max-warnings 0`)
  - typecheck: all workspace Done (cli / apps/api / apps/wechat-gateway / packages/*)
  - test: 379 passed (69 files), duration 41.66s
  - typecheck-gate.sh: typecheck / file-size / protected-files / deadcode 全 PASS
- [x] **CI butler-v5-gate**: run `31526638053` `butler-v5-gate: success` — 10 steps all green
  - Run overall conclusion = failure (v4 lint Ruff errors, pre-existing v4 backlog — not blocking R10)
- [x] **Dry-run prepare-cutover**: exit 0; manifest valid
  - `dryRun: true`, `eventsWritten: 0`, all steps `ok` or `skipped`
  - prepare-manifest.json emitted at `/tmp/r10-dryrun/prepare/`
- [x] **Dry-run final-cutover**: exit 0; manifest valid
  - `dryRun: true`, all 5 steps present (r7.1-prepare-complete / v4-read-only-window / r6.1-migration-pipeline / r5-r6-e2e-gate / v5-enabled)
  - 4 steps `skipped`, `r5-r6-e2e-gate` step `ok`
  - final-cutover-manifest.json emitted at `/tmp/r10-dryrun/final/`

### Owner-operator verification (NOT AI scope)

- [ ] **v4 ruff errors**: decision pending (9 errors, 6 auto-fixable via `ruff check --fix butler/`)
  - Option A: owner runs `ruff check --fix butler/`, commits, lint job green → R10 proceeds
  - Option B: owner accepts R10 with lint failure scope → R10 proceeds, v4 ruff fixed in R10+ follow-up
- [ ] **v4 Postgres snapshot taken**: snapshot of v4 production db before cutover (required for rollback)
- [ ] **Production traffic routing**: owner has access to change routing (load balancer / DNS / gateway config)
- [ ] **Rollback runbook**: documented + tested in staging (R10.3 below)
- [ ] **Monitoring dashboards**: alerts configured for v5 error rate / latency / event-store lag

### Owner approval

Owner signs here when all 5 items above are ready:

```
R10 ready:   ____________  (initials)  date: ____________
```

### AI confirmation

AI sub-agent: `claude-code`
Pre-flight timestamp: 2026-08-12T03:18:59Z (UTC)
Run ID verified: 31526638053