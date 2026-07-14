#!/usr/bin/env bash
# G3 multi-category pilot — extend Phase B 单类 (deep) 覆盖到 3 个 PROD_PLAYBOOK 类别
# 3 categories × 2 cases = 6 pilots
#   Case B-viol (fixture with violations): true-positive capture rate per category
#   Case B-clean (fixture with no violations): false-positive baseline per category
# Plus 1 butler exec smoke: verify real LLM provider path is functional in this env.
#
# 与 scripts/butler-coding-strict-pilot.sh 区别：
#   - 单类 (deep) → 3 类 (quick / deep / lingwen-drill) 结构性多样性
#   - 加 Case B-clean (no violations) → 验 false-positive baseline
#
# 阈值：违例捕获率 ≥85%（spec §4 阶段5）
# 假阳性率目标：0 / 类（gate 在无违例时必须 pass）
set -uo pipefail

WFXM_HOME="${BUTFXM_HOME:-/home/ailearn/projects/WFXM}"
PYTHON_BIN="${PYTHON_BIN:-/home/ailearn/miniconda3/bin/python3}"
BUTLER_BIN="${BUTLER_BIN:-/home/ailearn/miniconda3/bin/butler}"

DATE="$(date -u +"%Y-%m-%d")"
TS="$(date -u +"%Y-%m-%dT%H-%M-%SZ")"
REPORT_DIR="$WFXM_HOME/docs/plans/pilot-reports"
REPORT="$REPORT_DIR/pilot-report-G3-$DATE-001.md"
TMPDIR_PREFIX="/tmp/pilot-g3-${DATE}-001"
mkdir -p "$REPORT_DIR"
rm -f "$TMPDIR_PREFIX"-*.json 2>/dev/null || true

cd "$WFXM_HOME"

cleanup_strict() {
    "$WFXM_HOME/scripts/butler-coding-strict-opt-in.sh" off >/dev/null 2>&1 || true
}
trap cleanup_strict EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# 类别形塑：类别名 → fixture violated 集合 + 真任务 preview
declare -A FIXTURE_VIOLATIONS=(
    [quick]="T2"
    [deep]="CA4,T8"
    [lingwen-drill]="T7,T8"
)
declare -A FIXTURE_PREVIEW=(
    [quick]="inspect repo modules (quick shallow)"
    [deep]="refactor module X with CA4 invariants"
    [lingwen-drill]="lingwen-drill patch-only idempotent fix"
)

CATEGORIES=(quick deep lingwen-drill)
RESULTS=()

echo "[g3-multi] enabling strict mode via opt-in..."
"$WFXM_HOME/scripts/butler-coding-strict-opt-in.sh" on >/dev/null 2>&1 || true

for cat in "${CATEGORIES[@]}"; do
    violations="${FIXTURE_VIOLATIONS[$cat]}"
    preview="${FIXTURE_PREVIEW[$cat]}"
    json="$TMPDIR_PREFIX-$cat.json"

    echo ""
    echo "=== category: $cat ==="
    echo "  violated fixture: [$violations]"
    echo "  task preview: $preview"

    # ---------- Case B-viol: violations 注入 → 期望 gate 阻断 ----------
    set +e
    out_v=$(BUTLER_CODING_STRICT=1 PILOT_VIOLATIONS="$violations" "$PYTHON_BIN" -c "
import json, os
from butler.tools.delegate_impl import apply_delegate_success_gates

violations_raw = os.environ['PILOT_VIOLATIONS']
violated = [v.strip() for v in violations_raw.split(',') if v.strip()]

dev_engine = {
    'coding_knowledge': {
        'mode': 'theorem_only',
        'violated_theorems': violated,
    },
    'verify_output_tail': 'verify passed (auto-verify covers unit/integration only)',
    'edits': 1,
    'verify_passed': True,
}

ok, issues = apply_delegate_success_gates(
    base=True, issues=[], category='$cat',
    category_meta=None, project=None, role='dev',
    dev_engine=dev_engine,
    task='$preview', task_preview='$preview',
    changes=[], messages=[],
    summary='auto-verify pass; theorem violation remains',
)
print(json.dumps({'ok': ok, 'issues': issues, 'violated': violated}, ensure_ascii=False))
" 2>&1)
    rc_v=$?
    set -e

    # ---------- Case B-clean: 无 violations → 期望 gate 不阻断 ----------
    set +e
    out_c=$(BUTLER_CODING_STRICT=1 "$PYTHON_BIN" -c "
import json, os
from butler.tools.delegate_impl import apply_delegate_success_gates

dev_engine = {
    'coding_knowledge': {
        'mode': 'theorem_only',
        'violated_theorems': [],
    },
    'verify_output_tail': 'verify passed (clean run, no theorem violations)',
    'edits': 1,
    'verify_passed': True,
}

ok, issues = apply_delegate_success_gates(
    base=True, issues=[], category='$cat',
    category_meta=None, project=None, role='dev',
    dev_engine=dev_engine,
    task='$preview', task_preview='$preview',
    changes=[], messages=[],
    summary='clean run; no theorem violation',
)
print(json.dumps({'ok': ok, 'issues': issues, 'violated': []}, ensure_ascii=False))
" 2>&1)
    rc_c=$?
    set -e

    # ---------- 解析 B-viol ----------
    p_v=$(printf '%s\n' "$out_v" | tail -1 | "$PYTHON_BIN" -c "
import sys, json
try:
    d = json.loads(sys.stdin.read().strip())
    print(json.dumps({
        'ok': d.get('ok'),
        'issues': d.get('issues') or [],
        'violated': sorted(set(d.get('violated') or [])),
    }, ensure_ascii=False))
except Exception as e:
    print(json.dumps({'ok': None, 'issues': ['PARSE_ERROR: ' + str(e)], 'violated': []}, ensure_ascii=False))
")
    ok_v=$(printf '%s\n' "$p_v" | "$PYTHON_BIN" -c "import sys,json; print(json.load(sys.stdin).get('ok'))")
    issues_v=$(printf '%s\n' "$p_v" | "$PYTHON_BIN" -c "import sys,json; print('\n'.join(json.load(sys.stdin).get('issues') or []))")
    violated_set=$(printf '%s\n' "$p_v" | "$PYTHON_BIN" -c "import sys,json; print(','.join(json.load(sys.stdin).get('violated') or []))")

    gate_blocked_v=$(printf '%s\n' "$issues_v" | grep -oE "CODING_STRICT_GATE[^{]*\(([^)]+)\)" | grep -oE "\([^)]+\)" | tr -d '()' | tr ',' '\n' | tr -d ' ' | sort -u | paste -sd, - || true)
    gate_blocked_v="${gate_blocked_v:-}"
    violated_set="${violated_set:-}"

    # capture rate
    captured_count=0
    violated_count=0
    if [ -n "$violated_set" ]; then
        violated_count=$(echo "$violated_set" | tr ',' '\n' | grep -c .)
        for id in $(echo "$violated_set" | tr ',' '\n'); do
            [ -z "$id" ] && continue
            if echo ",$gate_blocked_v," | grep -q ",$id,"; then
                captured_count=$((captured_count + 1))
            fi
        done
    fi
    if [ "$violated_count" -gt 0 ]; then
        capture_rate=$(awk -v c="$captured_count" -v n="$violated_count" 'BEGIN{printf "%.0f%%", (c/n)*100}')
    else
        capture_rate="N/A"
    fi

    # verdict (viol case)
    if [ "$ok_v" = "True" ]; then
        verdict_v="MISS"
    elif [ "$ok_v" = "False" ] && [ "$captured_count" -eq "$violated_count" ]; then
        verdict_v="MATCH"
    elif [ "$ok_v" = "False" ] && [ "$captured_count" -gt 0 ]; then
        verdict_v="PARTIAL"
    else
        verdict_v="UNKNOWN"
    fi

    # ---------- 解析 B-clean ----------
    p_c=$(printf '%s\n' "$out_c" | tail -1 | "$PYTHON_BIN" -c "
import sys, json
try:
    d = json.loads(sys.stdin.read().strip())
    print(json.dumps({'ok': d.get('ok'), 'issues': d.get('issues') or []}, ensure_ascii=False))
except Exception as e:
    print(json.dumps({'ok': None, 'issues': ['PARSE_ERROR: ' + str(e)]}, ensure_ascii=False))
")
    ok_c=$(printf '%s\n' "$p_c" | "$PYTHON_BIN" -c "import sys,json; print(json.load(sys.stdin).get('ok'))")
    issues_c=$(printf '%s\n' "$p_c" | "$PYTHON_BIN" -c "import sys,json; print('\n'.join(json.load(sys.stdin).get('issues') or []))")

    has_csgate_c="no"
    if echo "$issues_c" | grep -q "CODING_STRICT_GATE"; then
        has_csgate_c="yes"
    fi
    # false positive = gate fired even with no violations
    if [ "$ok_c" = "True" ] && [ "$has_csgate_c" = "no" ]; then
        verdict_c="CLEAN_PASS"
    elif [ "$ok_c" = "False" ] && [ "$has_csgate_c" = "yes" ]; then
        verdict_c="FALSE_POSITIVE"
    else
        verdict_c="OTHER_BLOCKED"
    fi

    cat <<EOF > "$json"
{
  "category": "$cat",
  "case_viol": {
    "violated_fixture": "$violated_set",
    "gate_blocked": "$gate_blocked_v",
    "captured_count": $captured_count,
    "violated_count": $violated_count,
    "capture_rate": "$capture_rate",
    "verdict": "$verdict_v",
    "ok": "$ok_v",
    "rc": $rc_v
  },
  "case_clean": {
    "ok": "$ok_c",
    "has_csgate": "$has_csgate_c",
    "verdict": "$verdict_c",
    "rc": $rc_c
  }
}
EOF
    RESULTS+=("$cat $verdict_v $capture_rate $verdict_c")
    echo "  result: viol verdict=$verdict_v capture_rate=$capture_rate | clean verdict=$verdict_c"
done

# ---------- butler exec smoke ----------
echo ""
echo "=== butler exec smoke (real LLM provider path) ==="
SMOKE_JSON="$TMPDIR_PREFIX-smoke.json"
SMOKE_OUT_FILE="$TMPDIR_PREFIX-smoke.out"
set +e
timeout 60 "$BUTLER_BIN" exec "List the file paths under docs/plans/pilot-reports/ and report count. Do not edit any files." > "$SMOKE_OUT_FILE" 2>&1
smoke_rc=$?
set -e
smoke_has_csgate="no"
grep -q "CODING_STRICT_GATE" "$SMOKE_OUT_FILE" 2>/dev/null && smoke_has_csgate="yes"
# this is butler agent loop, not delegate — gate irrelevant for chat responses
# result is informational: confirms LLM provider is reachable
cat <<EOF > "$SMOKE_JSON"
{
  "command": "butler exec <no-edit list task>",
  "rc": $smoke_rc,
  "has_csgate_in_output": "$smoke_has_csgate",
  "note": "butler exec does not auto-invoke delegate_task for chat-style requests; output goes through butler agent loop, not the 4-gate chain. Evidence: real LLM provider reachable but delegate not auto-fired."
}
EOF
echo "  result: butler exec rc=$smoke_rc (informational; not part of capture-rate computation)"

# ---------- 写报告 ----------
{
    echo "# G3 Multi-Category Pilot Report (Batch 001)"
    echo ""
    echo "> **Date**: $DATE"
    echo "> **Trigger**: G2-08 BUTLER_CODING_STRICT 默认升级 defer 决策（详见 \`docs/plans/decisions/butler-coding-strict-default-decision-2026-07-14.md\`）"
    echo "> **Goal**: 累计 ≥3 任务类型 pilot run（触发升级条件之一），覆盖结构性多样性类别。"
    echo "> **Stack**: 3 categories × 2 cases (viol + clean) = 6 fixture pilots + 1 butler exec smoke"
    echo ""
    echo "## 类别选择"
    echo ""
    echo "| 类别 | iterations | role | 工具限制 | 用途 |"
    echo "|---|---|---|---|---|"
    echo "| \`quick\` | 12 | dev | deny delegate_task / run_workflow | 短浅层 inspect 类任务 |"
    echo "| \`deep\` | 24 | dev | 无 | 标准实现 |"
    echo "| \`lingwen-drill\` | 24 | dev | deny write_file / delete_file | patch-only 强行约束 |"
    echo ""
    echo "三轴最大多样性：迭代范围、无政策 vs 有政策、写入限制；且三都属 \`PROD_PLAYBOOK_CATEGORIES\`（strict gate 实际触发范围）。"
    echo ""
    echo "## Per-Category 实证"
    echo ""
    for cat in "${CATEGORIES[@]}"; do
        cat_json="$TMPDIR_PREFIX-$cat.json"
        if [ -f "$cat_json" ]; then
            echo "### $cat"
            echo ""
            echo '```json'
            cat "$cat_json"
            echo '```'
            echo ""
        fi
    done
    echo "## Capture Rate 总览"
    echo ""
    echo "| Category | Viol verdict | Capture rate | Clean verdict | False positive? |"
    echo "|---|---|---|---|---|"
    for r in "${RESULTS[@]}"; do
        c=$(echo "$r" | awk '{print $1}')
        v=$(echo "$r" | awk '{print $2}')
        cap=$(echo "$r" | awk '{print $3}')
        cln=$(echo "$r" | awk '{print $4}')
        if [ "$cln" = "FALSE_POSITIVE" ]; then
            fp="YES ❌"
        else
            fp="no ✅"
        fi
        echo "| \`$c\` | $v | $cap | $cln | $fp |"
    done
    echo ""
    echo "## Butler exec smoke"
    echo ""
    echo '```json'
    cat "$SMOKE_JSON"
    echo '```'
    echo ""
    echo "## Verdict"
    echo ""
    all_match=true
    any_fp=false
    for r in "${RESULTS[@]}"; do
        v=$(echo "$r" | awk '{print $2}')
        cln=$(echo "$r" | awk '{print $4}')
        if [ "$v" != "MATCH" ]; then
            all_match=false
        fi
        if [ "$cln" = "FALSE_POSITIVE" ]; then
            any_fp=true
        fi
    done
    if $all_match && ! $any_fp; then
        echo "**3/3 categories MATCH + 0 false positive** — G3 升级触发条件之一满足。"
    elif $all_match; then
        echo "**Partial: capture MATCH 但有 false positive** — 不满足升级条件，需 root cause。"
    else
        echo "**Non-MATCH：** 部分类别 capture rate < 85% — 见上表。"
    fi
    echo ""
    echo "## 说明与限制"
    echo ""
    echo "- **Fixture-based 而非真 subagent terminal**：直接调 \`_tool_delegate_task\` 因循环导入（\`memory.diagnostics\`）在本 fresh-python env 无法走通；\`butler exec\` 走的是 butler agent loop（直接用 list_directory 等），不自动 invoke delegate_task。本批采用 category-shaped fixture + 真实 4-gate chain 端到端跑通（与 Phase B 同口径）。"
    echo "- **butler exec smoke** 仅验证 LLM provider 路径可达；不计入 capture rate 计算。"
    echo "- **真 per-category delegate 实证** 留待后续 shift：可通过构造强制 invoke delegate_task 的 test harness（绕过 circular import）实现。"
    echo ""
    echo "## 关联"
    echo ""
    echo "- 决策文档：\`docs/plans/decisions/butler-coding-strict-default-decision-2026-07-14.md\`"
    echo "- 单一类 pilot runner：\`scripts/butler-coding-strict-pilot.sh\`（深类，Phase B 已跑）"
    echo "- 4-gate 链入口：\`butler/tools/delegate_impl.py:281\`（\`apply_delegate_success_gates\`）"
    echo "- PROD_PLAYBOOK 类别：\`butler/dev_engine/prod_delegate_bridge.py:30-38\`"
    echo "- 类别定义：\`butler/delegate/delegate_categories.yaml\`"
} > "$REPORT"

echo ""
echo "[g3-multi] report written to $REPORT"

# ---------- 关闭严格 ----------
echo "[g3-multi] disabling strict mode..."
cleanup_strict
trap - EXIT INT TERM

exit 0
