#!/usr/bin/env bash
# v5-switch.sh: stop v4 butler services, start v5 wiring.
#
# R10.3 SIMPLIFIED cutover (personal butler, single host).
# Replaces the 7-day traffic-shifting runbook in 015-preflight.md with a
# 5-10 minute direct stop+start. Per ADR-0001: "部署目标为单机自托管".
#
# v5 scope caveat: apps/api has /healthz + main routes; apps/wechat-gateway
# is Phase 3 stub (no real wechat iLink). So v5 currently provides HTTP
# API but not the wechat iLink the v4 butler-gateway.service provides.
# After switch: wechat iLink drops unless user manually keeps a bridge.
# See runbook for mitigation.

set -euo pipefail

REPO_ROOT="/home/ailearn/projects/WFXM"
V5_DIR="$REPO_ROOT/butler-v5"

# v4 services to stop (per discovery on 2026-08-13)
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

V5_API_PORT="${V5_API_PORT:-3000}"
HEALTH_URL="http://127.0.0.1:${V5_API_PORT}/healthz"
V5_LOG="/tmp/butler-v5.log"

log() { echo "[v5-switch $(date -Iseconds)] $*" >&2; }

log "=== R10.3 v5-switch (simplified) ==="

# Step 1: snapshot v4 state (for rollback safety)
log "Snapshotting active v4 services..."
ACTIVE_BEFORE=$(systemctl --user list-units --type=service --state=active --no-legend 2>/dev/null \
  | awk '{print $1}' | grep '^butler-' | sort)
log "v4 services currently active:"
echo "$ACTIVE_BEFORE" | sed 's/^/  /' >&2

# Step 2: stop v4 services (idempotent — only stops running ones)
log "Stopping v4 services..."
for svc in "${V4_SERVICES[@]}"; do
  if systemctl --user is-active --quiet "$svc" 2>/dev/null; then
    systemctl --user stop "$svc" 2>&1 | sed "s/^/  stop $svc: /" >&2
  else
    log "  skip $svc (not active)"
  fi
done

# Step 3: ensure v5 dependencies (postgres + wechat-mock) are up
log "Checking v5 dependencies (docker compose postgres + wechat-mock)..."
if command -v docker >/dev/null 2>&1 && [ -f "$V5_DIR/docker-compose.yml" ]; then
  (cd "$V5_DIR" && docker compose up -d postgres wechat-mock 2>&1) | sed 's/^/  docker: /' >&2 || \
    log "  WARN: docker compose failed; v5 may not start (postgres unreachable)"
else
  log "  WARN: docker not available; v5 may not start (postgres unreachable)"
fi

# Step 4: start v5 wiring in background (port 3000)
log "Starting v5 wiring on port ${V5_API_PORT} (logs: ${V5_LOG})..."
cd "$V5_DIR"
nohup pnpm dev > "$V5_LOG" 2>&1 &
V5_PID=$!
log "v5 started (pid=${V5_PID})"

# Step 5: wait for v5 /healthz to respond (up to 60s)
log "Waiting for v5 /healthz to respond..."
HEALTHY=0
for i in {1..60}; do
  if curl -sf -m 2 "$HEALTH_URL" >/dev/null 2>&1; then
    HEALTHY=1
    log "  v5 healthy after ${i}s"
    break
  fi
  sleep 1
done

if [ "$HEALTHY" -ne 1 ]; then
  log "ERROR: v5 did not respond to ${HEALTH_URL} within 60s"
  log "  Recent log tail:"
  tail -20 "$V5_LOG" 2>/dev/null | sed 's/^/    /' >&2
  log "  Auto-rolling back..."
  exec "$REPO_ROOT/butler-v5/scripts/cutover/v5-rollback.sh" --from-switch
fi

# Step 6: report
log "=== v5 switch complete ==="
log "  v4 services stopped: $(echo "$ACTIVE_BEFORE" | wc -l) total"
log "  v5 wiring: pid=${V5_PID} listening on :${V5_API_PORT}"
log "  v5 health: ${HEALTH_URL} returns 200"
log "  v5 log: tail -f ${V5_LOG}"
log ""
log "  NEXT STEPS (verify v5 is acceptable):"
log "    1. tail -f ${V5_LOG} to monitor v5 wiring logs"
log "    2. curl ${HEALTH_URL} to confirm v5 stable"
log "    3. Test wechat integration (currently NO iLink — v5 wechat-gateway is Phase 3 stub)"
log "    4. If v5 acceptable: systemctl --user enable butler-v5-gateway.service"
log "       (template at $REPO_ROOT/butler-v5/scripts/cutover/butler-v5-gateway.service)"
log "    5. If v5 unacceptable: $REPO_ROOT/butler-v5/scripts/cutover/v5-rollback.sh"
