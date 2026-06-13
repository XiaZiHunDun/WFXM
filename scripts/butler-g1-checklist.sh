#!/usr/bin/env bash
# G1 开放项守门：成本基线信号、OT2 审计、入站媒体 pytest、真机勾选提示。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

echo "=== G1-06 代码守门：inbound media ==="
bash scripts/butler-inbound-media-smoke.sh

echo ""
echo "=== G1-02 成本汇总（7 日）==="
python3 -m butler.ops.cost_calibration_cli report --days 7 || true

echo ""
echo "=== G1/G2 边界观测（G1-02/04 信号）==="
python3 - <<'PY' || true
import json
from butler.ops.boundary_observability import collect_boundary_observations

for o in collect_boundary_observations():
    if o.gap_id.startswith("G1"):
        print(o.line(verbose=True))
PY

echo ""
echo "=== G1-04 OT2 观测窗 ==="
python3 - <<'PY' || true
import json
from butler.ops.boundary_observability import g1_04_observation_window_status

w = g1_04_observation_window_status()
print(
    f"  窗 {w['window_start']}→{w['window_end']} "
    f"剩 {w['days_remaining']}d · 窗内 {w['feedback_in_window']} 条 · 7d {w['feedback_7d']} 条"
)
if w.get("closure_ready"):
    print("  ✅ closure_ready — 可结案更新 theory-implementation-gap-register")
print(json.dumps(w, ensure_ascii=False, indent=2))
PY

echo ""
echo "=== G1 真机（须主公微信操作）==="
echo "  G1-08：已搁置（灵文试点；非平台 G1）"
echo "  G1-06：✅ 2026-06-10 真机已验（M-img/M-voice）；复测可按需重跑 inbound smoke"
echo ""
echo "=== G1-02 录入账单基线（替换为控制台实际值）==="
echo '  butler cost set-baseline --usd <USD> --input-tokens <N> --output-tokens <N> --note "控制台账期"'
echo ""
echo "勾选后更新 projects/LingWen1/docs/pilot-log.md §G1 清单执行"
