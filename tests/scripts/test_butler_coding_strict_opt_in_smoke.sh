#!/usr/bin/env bash
# G2-08 Task 2: opt-in script smoke (4 case).
# 用 mktemp + env override 隔离真实 ~/.butler/ 路径。
set -uo pipefail

SCRIPT="${BUTFXM_HOME:-/home/ailearn/projects/WFXM}/scripts/butler-coding-strict-opt-in.sh"
AUDIT_DIR="$(mktemp -d)"
export CODING_STRICT_STATE_FILE="$AUDIT_DIR/state.yaml"
export CODING_STRICT_AUDIT_LOG="$AUDIT_DIR/events.log"
PASS=0
FAIL=0

run_case() {
    local name="$1"
    shift
    if "$@"; then
        echo "PASS: $name"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $name"
        FAIL=$((FAIL + 1))
    fi
}

case1_on_should_create_state() {
    set +e
    out=$("$SCRIPT" on 2>&1)
    rc=$?
    set -e
    [ "$rc" -eq 0 ] && [ -f "$CODING_STRICT_STATE_FILE" ] && \
        grep -q "state: on" "$CODING_STRICT_STATE_FILE" && \
        [ -f "$CODING_STRICT_AUDIT_LOG" ] && \
        grep -q '"action":"opt-in"' "$CODING_STRICT_AUDIT_LOG"
}

case2_off_should_remove_state() {
    set +e
    out=$("$SCRIPT" off 2>&1)
    rc=$?
    set -e
    [ "$rc" -eq 0 ] && [ ! -f "$CODING_STRICT_STATE_FILE" ]
}

case3_status_should_report_state() {
    "$SCRIPT" on >/dev/null 2>&1
    out=$("$SCRIPT" status 2>&1)
    [[ "$out" == *"state: on"* ]]
}

case4_audit_should_tail_events() {
    "$SCRIPT" on >/dev/null 2>&1
    "$SCRIPT" off >/dev/null 2>&1
    out=$("$SCRIPT" audit 2>&1)
    [[ "$out" == *'"action":"opt-in"'* ]] && [[ "$out" == *'"action":"opt-off"'* ]]
}

run_case "on_should_create_state_and_audit_entry" case1_on_should_create_state
run_case "off_should_remove_state" case2_off_should_remove_state
run_case "status_should_report_on_or_off" case3_status_should_report_state
run_case "audit_should_tail_recent_events" case4_audit_should_tail_events

rm -rf "$AUDIT_DIR"
echo "Result: $PASS pass / $FAIL fail"
[ "$FAIL" -eq 0 ]