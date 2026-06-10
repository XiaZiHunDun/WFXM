#!/usr/bin/env bash
# Phase 4 gate — 轨道 A（运营巩固）+ 轨道 B（灵文样板）自动化守门。
#
# Usage:
#   bash scripts/butler-phase4-smoke.sh
#   bash scripts/butler-phase4-smoke.sh --with-consistency   # A1: 跑 consistency-weekly（慢）
#   bash scripts/butler-phase4-smoke.sh --tier=full          # 发版级（等同 pre-release）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WITH_CONSISTENCY=0
TIER="standard"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-consistency) WITH_CONSISTENCY=1 ;;
    --tier=*) TIER="${1#--tier=}" ;;
    -h|--help)
      echo "Usage: $0 [--with-consistency] [--tier=standard|full]"
      exit 0
      ;;
    *) echo "Unknown: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi
export PYTHONPATH="${PYTHONPATH:-.}:."

echo "=== Phase 4 smoke (tier=$TIER) ==="
echo ""

echo "== [A4/B2] tiered smoke =="
if [[ "$TIER" == "full" ]]; then
  bash "$ROOT/scripts/butler-pre-release-smoke.sh"
else
  bash "$ROOT/scripts/butler-smoke.sh" --tier="$TIER"
fi

echo ""
echo "== [B1/B3] LingWen Lead smoke =="
bash "$ROOT/scripts/butler-lingwen-lead-smoke.sh"

echo ""
echo "== [A3/B3] Runtime smoke (mutating approval gate) =="
if [[ "$WITH_CONSISTENCY" -eq 1 ]]; then
  BUTLER_RUNTIME_RUN_CONSISTENCY=1 bash "$ROOT/scripts/butler-runtime-smoke.sh" 灵文1号
else
  bash "$ROOT/scripts/butler-runtime-smoke.sh" 灵文1号
fi

echo ""
echo "== [A2] Inbound media code path =="
bash "$ROOT/scripts/butler-inbound-media-smoke.sh"

echo ""
echo "== [O-track] Observability regression =="
bash "$ROOT/scripts/butler-eval-regression.sh" --no-langfuse

echo ""
echo "== [A6] Doctor observability =="
python3 -m butler.main doctor 2>&1 | rg -i "langfuse|embed|Recall|CRITICAL" || true

echo ""
echo "Phase 4 automated gate: PASSED"
echo "真机待办: A1 consistency-weekly 微信摘要、A2 M-img/M-voice、A5 /成本 对照账单"
echo "详见 docs/guides/phase4-ops-runbook.md"
