#!/usr/bin/env bash
# G2-08 Task 3: Phase A 控型 smoke — 直接调 apply_coding_strict_pilot_gate，
# 不走真实 delegate 链。验 gate 机制在 4 组合下行为。
set -uo pipefail

WFXM_HOME="${WFXM_HOME:-/home/ailearn/projects/WFXM}"
PASS=0
FAIL=0

run_gate() {
    local desc="$1"
    local strict_env="$2"
    local role="$3"
    local category="$4"
    local violated_json="$5"
    local expect_ok="$6"
    local expect_gate="$7"

    set +e
    out=$(cd "$WFXM_HOME" && BUTLER_CODING_STRICT="$strict_env" \
        /home/ailearn/miniconda3/bin/python3 -c "
from butler.dev_engine.b9_delegate_gate import apply_coding_strict_pilot_gate
import json, sys
ck = {'violated': $violated_json}
ok, issues = apply_coding_strict_pilot_gate(
    category='$category', role='$role',
    dev_engine={'coding_knowledge': ck},
    base_success=True,
)
print(json.dumps({'ok': ok, 'issues': issues}))
" 2>&1)
    rc=$?
    set -e

    got_ok=$(echo "$out" | python3 -c "import sys,json; d=json.loads(sys.stdin.read().strip().splitlines()[-1]); print(d['ok'])" 2>/dev/null || echo "")
    got_gate=$(echo "$out" | grep -c "CODING_STRICT_GATE" || true)

    if [ "$got_ok" = "$expect_ok" ] && [ "$got_gate" -eq "$expect_gate" ]; then
        echo "PASS: $desc (ok=$got_ok gate=$got_gate)"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $desc (got ok=$got_ok gate=$got_gate, expected ok=$expect_ok gate=$expect_gate)"
        echo "  output: $out"
        FAIL=$((FAIL + 1))
    fi
}

# Case 1: strict=1 + dev + deep + violated 非空 → 阻断
run_gate "strict=1_dev_deep_violated_blocks" "1" "dev" "deep" "[\"CA4\",\"T8\"]" "False" "1"

# Case 2: strict=0 → 放行
run_gate "strict=0_advisory_passes" "0" "dev" "deep" "[\"CA4\",\"T8\"]" "True" "0"

# Case 3: role=content → 放行
run_gate "role_content_passes" "1" "content" "deep" "[\"CA4\",\"T8\"]" "True" "0"

# Case 4: category=other（不在 pilot set）→ 放行
run_gate "category_other_passes" "1" "dev" "other" "[\"CA4\",\"T8\"]" "True" "0"

echo "Result: $PASS pass / $FAIL fail"
[ "$FAIL" -eq 0 ]
