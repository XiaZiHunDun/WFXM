#!/usr/bin/env bash
# Run G1-04 closure apply only when ot2_closure_ready (exit 0 from check).
# B9-only / 窗未结束：跳过（不自动 --pipeline-only）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== G1-04 closure (if ready) =="
if ! bash "$ROOT/scripts/butler-g1-04-closure-check.sh"; then
  ec=$?
  case "$ec" in
    2) echo "G1-04: 观测窗未结束 — skip apply（预期）" ;;
    3) echo "G1-04: 仅 B9 测评证据 — skip apply（需生产用量或手动 --pipeline-only）" ;;
    *) echo "G1-04: not ready (exit $ec) — skip apply" ;;
  esac
  exit 0
fi

echo ""
bash "$ROOT/scripts/butler-g1-04-closure-apply.sh"
echo ""
echo "Next: git diff && git commit -m 'docs: close G1-04 OT2 window (production evidence)' && git push"
