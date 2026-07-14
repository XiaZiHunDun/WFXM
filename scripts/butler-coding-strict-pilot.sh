#!/usr/bin/env bash
# G2-08 Task 4: Phase B 真实 pilot — 灵文1号 ch001 复现任务
# 跑通即过；exit 0 / exit 1 由任务执行结果决定。
set -uo pipefail

WFXM_HOME="${BUTFXM_HOME:-/home/ailearn/projects/WFXM}"
PROJECT="LingWen1"
DATE="$(date -u +"%Y-%m-%d")"
REPORT_DIR="$WFXM_HOME/docs/plans/pilot-reports"
REPORT="$REPORT_DIR/pilot-report-G2-08-$DATE.md"
mkdir -p "$REPORT_DIR"

cd "$WFXM_HOME"

echo "[pilot] enabling strict mode via opt-in..."
"$WFXM_HOME/scripts/butler-coding-strict-opt-in.sh" on

echo "[pilot] running LingWen1 ch001 reproduce under BUTLER_CODING_STRICT=1..."
set +e
out=$(BUTLER_CODING_STRICT=1 BUTLER_ACTIVE_PROJECT="$PROJECT" \
    /home/ailearn/miniconda3/bin/python3 -m butler.tools.delegate_impl \
        --project "$PROJECT" --task ch001-reproduce --role dev \
        --category deep 2>&1)
task_rc=$?
set -e

# 注: set -uo pipefail 下, grep 无匹配时返 rc=1; pipefail 会让整个管道退出非零,
#     进而 set -e 在赋值后退出脚本 → 报告未写。所有 grep 末端加 || true 兜底。
violated_set=$(echo "$out" | grep -oE "violated[^]]*\]" | head -1 || true)
violated_set="${violated_set:-[]}"
# spec §4 阶段5: 精确捕获率 = |violated_set ∩ gate_blocked_ids| / |violated_set|
# gate_blocked_ids 来自 CODING_STRICT_GATE 行末尾括号内的 ID 列表 (参考 b9_delegate_gate.py:404)
gate_blocked=$(echo "$out" | grep -oE "CODING_STRICT_GATE: theorem violations remain \([^)]+\)" | sed -E 's/.*\(([^)]+)\).*/\1/' | tr ',' '\n' | tr -d ' ' | sort -u | paste -sd, - || true)
gate_blocked="${gate_blocked:-}"
# violated_set 形如 "violated ['CA4', 'T8']"，剥出 ID 列表
violated_ids=$(echo "$violated_set" | grep -oE "\[[^]]*\]" | tr -d '[]' | tr ',' '\n' | tr -d ' "' | sort -u | paste -sd, - || true)
violated_ids="${violated_ids:-}"
violated_count=0
captured_count=0
if [ -n "$violated_ids" ]; then
    violated_count=$(echo "$violated_ids" | tr ',' '\n' | wc -l)
    if [ -n "$gate_blocked" ]; then
        captured_count=$(comm -12 <(echo "$violated_ids" | tr ',' '\n' | sort -u) <(echo "$gate_blocked" | tr ',' '\n' | sort -u) | wc -l)
    fi
fi
if [ "$violated_count" -gt 0 ]; then
    capture_rate=$(awk -v c="$captured_count" -v v="$violated_count" 'BEGIN{printf "%.4f", c/v}')
else
    capture_rate="0.0000"
fi
verdict="UNDETERMINED"
if [ "$violated_count" -eq 0 ]; then
    verdict="NO_VIOLATIONS"
elif [ "$captured_count" -eq 0 ]; then
    verdict="NO_GATE"
else
    # 阈值 85%
    pass=$(awk -v r="$capture_rate" 'BEGIN{print (r+0 >= 0.85) ? 1 : 0}')
    if [ "$pass" -eq 1 ]; then
        verdict="MATCH"
    else
        verdict="PARTIAL"
    fi
fi

cat > "$REPORT" <<EOF
# G2-08 Phase B Pilot Report — $DATE

## 摘要

| 字段 | 值 |
|------|----|
| Sample | 灵文1号 ch001 复现任务 |
| Env | \`BUTLER_CODING_STRICT=1\` \`BUTLER_ACTIVE_PROJECT=LingWen1\` |
| Exit code | $task_rc |
| Violated 集合 | $violated_set |
| Gate 阻断 ID | $gate_blocked |
| 捕获数 / 违例数 | $captured_count / $violated_count |
| 捕获率 | $capture_rate |
| Verdict | $verdict |

## 详细

### 任务输出（尾部 2000 字符）

\`\`\`
$(echo "$out" | tail -c 2000)
\`\`\`

### Violated 集合

\`\`\`
$violated_set
\`\`\`

### Gate 阻断 ID（来自 CODING_STRICT_GATE 行）

\`\`\`
$gate_blocked
\`\`\`

### 阈值判定

- 阈值：违例捕获率 ≥ 85%（spec §4 阶段5）
- 实测捕获率：$capture_rate ($captured_count / $violated_count)
- 结论：**$verdict**

## 关联

- spec: \`docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md\`
- plan: \`docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md\`
EOF

echo "[pilot] report written to $REPORT"
exit $task_rc
