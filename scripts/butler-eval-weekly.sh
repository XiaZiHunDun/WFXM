#!/usr/bin/env bash
# Weekly LangFuse evaluation bundle — regression, corpus, LIVE benchmarks, health.
#
# Default: full weekly gate (includes B9 + SWE LIVE; requires LLM API).
#
# Usage:
#   bash scripts/butler-eval-weekly.sh
#   bash scripts/butler-eval-weekly.sh --skip-live      # no LLM cost
#   bash scripts/butler-eval-weekly.sh --no-langfuse
#   bash scripts/butler-eval-weekly.sh --with-experiment
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SKIP_LIVE=0
NO_LANGFUSE=0
WITH_EXPERIMENT=0
LOOKBACK=168

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-live) SKIP_LIVE=1 ;;
    --no-langfuse) NO_LANGFUSE=1 ;;
    --with-experiment) WITH_EXPERIMENT=1 ;;
    --lookback=*) LOOKBACK="${1#--lookback=}" ;;
    -h|--help)
      cat <<'EOF'
Usage: bash scripts/butler-eval-weekly.sh [OPTIONS]

Runs the recommended weekly LangFuse evaluation bundle in order:

  1. Regression gate (B1–B8 + MB + B9 oracle) + Dataset sync
  2. WeChat gateway corpus → LangFuse
  3. B9 LIVE fixed set — 13 tasks (LIVE unless --skip-live)
  4. SWE-bench Lite weekly subset (LIVE unless --skip-live)
  5. Assistant cross-dimension health → LangFuse
  6. Delegate failure review checklist (informational)

Options:
  --skip-live         Skip B9/SWE LIVE steps (oracle/corpus only; no LLM cost)
  --no-langfuse       Disable LangFuse push/sync where supported
  --with-experiment   Also run eval experiment variant comparison (slower)
  --lookback=HOURS    Assistant health lookback (default: 168)
  -h, --help          Show this help

Examples:
  bash scripts/butler-eval-weekly.sh
  bash scripts/butler-eval-weekly.sh --skip-live --no-langfuse
EOF
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

if [[ "$NO_LANGFUSE" -eq 1 ]]; then
  export BUTLER_LANGFUSE_ENABLED=0
fi

if [[ "$SKIP_LIVE" -eq 0 ]]; then
  export BUTLER_EVAL_LLM_BENCHMARK=1
fi

FAILED=0
STEP_RESULTS=()

run_step() {
  local name="$1"
  shift
  echo
  echo "════════════════════════════════════════════════════════════"
  echo "▶ $name"
  echo "════════════════════════════════════════════════════════════"
  if "$@"; then
    STEP_RESULTS+=("OK  $name")
  else
    local code=$?
    STEP_RESULTS+=("FAIL $name (exit $code)")
    FAILED=1
    echo "⚠ Step failed: $name (exit $code); continuing…" >&2
    return 0
  fi
}

# 1. Regression + dataset sync
REG_ARGS=(--sync-dataset)
if [[ "$NO_LANGFUSE" -eq 1 ]]; then
  REG_ARGS+=(--no-langfuse)
fi
run_step "Regression gate + Dataset sync" bash "$ROOT/scripts/butler-eval-regression.sh" "${REG_ARGS[@]}"

# 2. WeChat corpus
WC_ARGS=()
if [[ "$NO_LANGFUSE" -eq 1 ]]; then
  WC_ARGS+=(--no-langfuse)
fi
run_step "WeChat gateway corpus" bash "$ROOT/scripts/butler-eval-wechat-corpus.sh" "${WC_ARGS[@]}"

# 3–4. LIVE benchmarks (optional)
if [[ "$SKIP_LIVE" -eq 0 ]]; then
  run_step "B9 LIVE fixed set (10 tasks)" bash "$ROOT/scripts/butler-eval-b9-live.sh"
  run_step "SWE-bench Lite weekly subset (LIVE)" bash "$ROOT/scripts/butler-eval-swebench-live.sh"
else
  STEP_RESULTS+=("SKIP B9 LLM delegate (LIVE)")
  STEP_RESULTS+=("SKIP SWE-bench Lite weekly subset (LIVE)")
  echo
  echo "── Skipped LIVE benchmarks (--skip-live)"
fi

# Optional experiment comparison
if [[ "$WITH_EXPERIMENT" -eq 1 ]]; then
  EXP_ARGS=(--with-swe)
  if [[ "$NO_LANGFUSE" -eq 1 ]]; then
    EXP_ARGS+=(--no-langfuse)
  fi
  run_step "Eval experiment (variants)" bash "$ROOT/scripts/butler-eval-experiment.sh" "${EXP_ARGS[@]}"
fi

# 5. Assistant health
if [[ "$NO_LANGFUSE" -eq 1 ]]; then
  run_step "Assistant health snapshot" bash "$ROOT/scripts/butler-eval-assistant-health.sh" --lookback="$LOOKBACK"
else
  run_step "Assistant health + LangFuse push" bash "$ROOT/scripts/butler-eval-assistant-health.sh" --push --lookback="$LOOKBACK"
fi

# 6. Delegate failure review (informational; never fails the bundle)
echo
echo "════════════════════════════════════════════════════════════"
echo "▶ Delegate failure review (informational)"
echo "════════════════════════════════════════════════════════════"
bash "$ROOT/scripts/butler-delegate-failure-review.sh" || true
STEP_RESULTS+=("INFO Delegate failure review")

echo
echo "════════════════════════════════════════════════════════════"
echo "Weekly eval summary"
echo "════════════════════════════════════════════════════════════"
for line in "${STEP_RESULTS[@]}"; do
  echo "  $line"
done

if [[ "$FAILED" -ne 0 ]]; then
  echo
  echo "WEEKLY EVAL: FAILED (one or more steps)" >&2
  exit 1
fi

echo
echo "WEEKLY EVAL: PASSED"
