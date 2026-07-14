#!/usr/bin/env bash
# G2-08 CA4 严格模式 opt-in 工具
# 子命令: on | off | status | audit
# Env override: CODING_STRICT_STATE_FILE, CODING_STRICT_AUDIT_LOG
set -uo pipefail

STATE_FILE="${CODING_STRICT_STATE_FILE:-$HOME/.butler/runtime/coding_strict_state.yaml}"
AUDIT_LOG="${CODING_STRICT_AUDIT_LOG:-$HOME/.butler/audit/coding-strict-events.log}"
TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
ACTOR="${USER:-unknown}"

cmd_on() {
    mkdir -p "$(dirname "$STATE_FILE")" "$(dirname "$AUDIT_LOG")"
    cat > "$STATE_FILE" <<EOF
state: on
ts: "$TS"
by: "$ACTOR"
EOF
    echo "{\"ts\":\"$TS\",\"action\":\"opt-in\",\"actor\":\"$ACTOR\",\"env\":\"BUTLER_CODING_STRICT=1\"}" >> "$AUDIT_LOG"
    echo "strict mode enabled; restart processes to take effect"
    echo "state: $STATE_FILE"
}

cmd_off() {
    rm -f "$STATE_FILE"
    echo "{\"ts\":\"$TS\",\"action\":\"opt-off\",\"actor\":\"$ACTOR\"}" >> "$AUDIT_LOG"
    echo "strict mode disabled"
}

cmd_status() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        echo "state: off"
    fi
    if [ -n "${BUTLER_CODING_STRICT:-}" ]; then
        echo "env: BUTLER_CODING_STRICT=$BUTLER_CODING_STRICT"
    else
        echo "env: BUTLER_CODING_STRICT=0 (default)"
    fi
}

cmd_audit() {
    if [ -f "$AUDIT_LOG" ]; then
        tail -20 "$AUDIT_LOG"
    else
        echo "no audit log"
    fi
}

case "${1:-}" in
    on) cmd_on ;;
    off) cmd_off ;;
    status) cmd_status ;;
    audit) cmd_audit ;;
    *) echo "usage: $0 {on|off|status|audit}" >&2; exit 2 ;;
esac