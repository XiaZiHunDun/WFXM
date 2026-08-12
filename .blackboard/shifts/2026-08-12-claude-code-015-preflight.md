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

- [x] **v4 ruff errors**: **DECIDED Option B** (accept lint failure scope for R10; v4 ruff fixed in R10+ follow-up)
  - Reason: butler-v5-gate already decoupled from v4 lint (R9 follow-up #2 `6c9cdd6f`); R10 doesn't need lint green
  - Note: 9 errors (6 auto-fixable) documented in shift card 011/012; R10+ fix path documented at [[project-progress-2026-08-12-r8]]
- [ ] **v4 Postgres snapshot taken**: snapshot of v4 production db before cutover (required for rollback)
- [ ] **Production traffic routing**: owner has access to change routing (load balancer / DNS / gateway config)
- [ ] **Rollback runbook**: documented + tested in staging (R10.3 below)
- [ ] **Monitoring dashboards**: alerts configured for v5 error rate / latency / event-store lag

### R10.1 — prepare-cutover --live (owner template)

Owner runs:

```bash
node butler-v5/scripts/cutover/prepare-cutover.mjs \
  --live --v4-root <real-v4-root> --out-dir <real-v4-root> \
  --adapter-postgres 2>&1 | tee /tmp/r10-1-prepare.log
```

Then fills in:

```
R10.1 timestamp: <ISO>
R10.1 prepare-manifest.json content: <paste JSON>
R10.1 eventsWritten: <count>
R10.1 elapsed: <seconds>
R10.1 issues: <description or "none">
```

### R10.2 — final-cutover --live (owner template)

Pre-condition: R10.1 prepare-manifest.json exists with eventsWritten > 0.

Owner runs:

```bash
node butler-v5/scripts/cutover/run-final-cutover.mjs \
  --live --v4-root <real-v4-root> --out-dir <v5-manifests-dir> 2>&1 | tee /tmp/r10-2-final.log
```

Then fills in:

```
R10.2 timestamp: <ISO>
R10.2 final-cutover-manifest.json content: <paste JSON>
R10.2 5 steps status: <list>
R10.2 v4 read-only window: <ISO start to end>
R10.2 issues: <description or "none">
```

### R10.3 — traffic shift + monitoring + rollback drill (owner template)

Owner executes in 4 phases + rollback + 24h monitoring:

```
Phase 1: 1% traffic to v5
- start/end: <ISO>
- v5 error rate: <%>; p99 latency: <ms>
- v4 baseline: <%>
- anomalies: <description>
- decision: proceed / hold / rollback

Phase 2: 10% traffic to v5
(same fields)

Phase 3: 50% traffic to v5
(same fields)

Phase 4: 100% traffic to v5
(same fields)

Rollback drill
- trigger time: <ISO>
- v4 traffic restored to 100%: yes/no
- rollback time (trigger to 100% v4): <seconds>
- issues: <description>
- verification (production served from v4 after rollback): yes/no

24h post-cutover monitoring
- time range: <ISO to ISO>
- v5 uptime: <%>
- v5 events processed: <count>
- v5 error budget consumed: <%>
- open incidents: <description>
```

### Owner approval (owner signs after each step)

```
R10.1 ready: ____________ (initials)  date: ____________
R10.2 ready: ____________ (initials)  date: ____________
R10.3 ready: ____________ (initials)  date: ____________
```

### AI confirmation

AI sub-agent: `claude-code`
Pre-flight timestamp: 2026-08-12T03:18:59Z (UTC)
Run ID verified: 31526638053