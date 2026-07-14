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

violated_set=$(echo "$out" | grep -oE "violated[^]]*\]" | head -1 || echo "[]")
gate_count=$(echo "$out" | grep -c "CODING_STRICT_GATE" || true)
verdict="UNDETERMINED"
if [ "$gate_count" -gt 0 ]; then
    verdict="GATE_TRIGGERED"
fi

cat > "$REPORT" <<EOF
# G2-08 Phase B Pilot Report — $DATE

## 摘要

| 字段 | 值 |
|------|----|
| Sample | 灵文1号 ch001 复现任务 |
| Env | \`BUTLER_CODING_STRICT=1\` \`BUTLER_ACTIVE_PROJECT=LingWen1\` |
| Exit code | $task_rc |
| Gate 触发次数 | $gate_count |
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

### 阈值判定

- 阈值：违例捕获率 ≥ 85%
- 实测捕获率：$( [ "$gate_count" -gt 0 ] && echo "100%（gate 触发即捕获）" || echo "0%（gate 未触发）" )
- 结论：**$verdict**

## 关联

- spec: \`docs/superpowers/specs/2026-07-13-g2-08-strict-pilot-design.md\`
- plan: \`docs/superpowers/plans/2026-07-13-g2-08-strict-pilot.md\`
EOF

echo "[pilot] report written to $REPORT"
exit $task_rc
