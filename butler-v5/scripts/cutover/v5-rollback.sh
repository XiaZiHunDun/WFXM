#!/usr/bin/env bash
# v5-rollback.sh: stop v5 wiring, restart v4 butler services.
#
# R10.3 rollback path. Run if v5-switch.sh leaves v5 in a bad state or
# if the user decides v5 isn't acceptable after evaluation.
#
# Two invocation modes:
#   v5-rollback.sh              (operator runs)
#   v5-rollback.sh --from-switch  (auto-called by v5-switch.sh on health failure)
#
# Re-runnable: idempotent on all steps.

set -euo pipefail

REPO_ROOT="/home/ailearn/projects/WFXM"
V5_DIR="$REPO_ROOT/butler-v5"
V5_API_PORT="${V5_API_PORT:-3000}"
HEALTH_URL="http://127.0.0.1:${V5_API_PORT}/healthz"

# v4 services to restart (same list as v5-switch.sh)
V4_SERVICES=(
  "butler-gateway.service"
  "butler-runtime-lingwen.service"
  "butler-morning-brief.service"
  "butler-push-drain.service"
  "butler-b9-weekly-gate.service"
  "butler-eval-sync.service"
  "butler-ops-cadence-weekly.service"
  "butler-ops-cadence-quarterly.service"
)

log() { echo "[v5-rollback $(date -Iseconds)] $*" >&2; }

log "=== R10.3 v5-rollback ==="

# Step 1: stop v5 wiring (port 3000 listener)
log "Stopping v5 wiring on port ${V5_API_PORT}..."
PIDS=$(lsof -t -i:"${V5_API_PORT}" 2>/dev/null || true)
if [ -n "$PIDS" ]; then
  log "  v5 PIDs on port ${V5_API_PORT}: ${PIDS}"
  for pid in $PIDS; do
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 2
  # Force kill if still alive
  PIDS2=$(lsof -t -i:"${V5_API_PORT}" 2>/dev/null || true)
  if [ -n "$PIDS2" ]; then
    log "  force-killing remaining: ${PIDS2}"
    for pid in $PIDS2; do
      kill -KILL "$pid" 2>/dev/null || true
    done
  fi
else
  log "  no listener on port ${V5_API_PORT} (already stopped?)"
fi

# Also kill any butler-v5 dev process tree
log "Killing pnpm dev / tsx processes for v5..."
pkill -f "pnpm dev" 2>/dev/null && log "  pkill pnpm dev: ok" || log "  pkill pnpm dev: nothing matched"
pkill -f "tsx src/index.ts" 2>/dev/null && log "  pkill tsx: ok" || log "  pkill tsx: nothing matched"
pkill -f "butler start" 2>/dev/null && log "  pkill 'butler start': ok" || log "  pkill 'butler start': nothing matched"

# Verify v5 is down
sleep 1
if curl -sf -m 2 "$HEALTH_URL" >/dev/null 2>&1; then
  log "WARN: v5 still responding to ${HEALTH_URL}; rollback may be incomplete"
else
  log "  v5 confirmed down"
fi

# Step 2: restart v4 butler services
log "Starting v4 butler services..."
for svc in "${V4_SERVICES[@]}"; do
  if [ -f "$HOME/.config/systemd/user/${svc}" ] || systemctl --user list-unit-files "${svc}" 2>/dev/null | grep -q "$svc"; then
    systemctl --user start "$svc" 2>&1 | sed "s/^/  start $svc: /" >&2 || \
      log "  WARN: failed to start $svc (may need manual start)"
  else
    log "  skip $svc (no unit file)"
  fi
done

# Step 3: report
log "=== v5 rollback complete ==="
log "  v5 wiring stopped on port ${V5_API_PORT}"
log "  v4 services restart initiated"
log ""
log "  VERIFY: ps -ef | grep butler.main"
log "          systemctl --user status butler-gateway.service"
log ""
log "  Re-attempt v5 later with:"
log "    $REPO_ROOT/butler-v5/scripts/cutover/v5-switch.sh"