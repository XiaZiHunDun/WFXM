#!/usr/bin/env bash
# Corpus evaluation helper — tests/corpus/
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.

MODE="${1:-mock}"
shift || true
case "$MODE" in
  mock)
    exec python3 -m pytest tests/corpus -m "corpus and corpus_mock" -q "$@"
    ;;
  smoke)
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
    export BUTLER_RUN_REAL_API_SMOKE=1
    exec python3 -m pytest tests/corpus/runners/test_agent_loop_rubric.py \
      -m "corpus_live and corpus_smoke" -v "$@"
    ;;
  live)
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
    export BUTLER_RUN_REAL_API_SMOKE=1
    export CORPUS_ARCHIVE="${CORPUS_ARCHIVE:-1}"
    exec python3 -m pytest tests/corpus/runners/test_agent_loop_rubric.py \
      -m corpus_live -v "$@"
    ;;
  gateway)
    # L0 health + L1 单轮/变体抽检/多轮 + L2 黄金路径（微信真实语料模块一键）
    exec python3 -m pytest \
      tests/corpus/runners/test_gateway_module_health.py \
      tests/corpus/runners/test_gateway_scripted.py \
      tests/corpus/runners/test_gateway_utterance_catalog.py \
      tests/corpus/runners/test_gateway_utterance_variants.py \
      tests/corpus/runners/test_gateway_multiturn_catalog.py \
      tests/corpus/runners/test_gateway_golden.py \
      tests/test_gateway_dev_conversations.py \
      -m "corpus and corpus_mock" -q "$@"
    ;;
  gateway-live)
    set -a
    # shellcheck source=/dev/null
    source .env 2>/dev/null || true
    set +a
    export BUTLER_RUN_REAL_API_SMOKE=1
    export CORPUS_ARCHIVE="${CORPUS_ARCHIVE:-1}"
    exec python3 -m pytest tests/corpus/runners/test_gateway_live_corpus.py \
      -m "corpus_live and corpus_smoke" -v "$@"
    ;;
  gateway-all)
    # 含未打 corpus marker 的 gateway 测试时可用（与 gateway 等价若 dev 已标 marker）
    exec python3 -m pytest \
      tests/corpus/runners/test_gateway_module_health.py \
      tests/corpus/runners/test_gateway_scripted.py \
      tests/corpus/runners/test_gateway_utterance_catalog.py \
      tests/corpus/runners/test_gateway_multiturn_catalog.py \
      tests/corpus/runners/test_gateway_golden.py \
      -q "$@"
    ;;
  drift)
    exec "$(dirname "$0")/corpus/check_corpus_drift.sh" "$@"
    ;;
  ops)
    # 运营快照：production 池 + gateway live 归档（无需 API）
    exec python3 "$(dirname "$0")/corpus/summarize_runs.py" "$@"
    ;;
  gateway-ops)
    # production 运营门禁 + 全量 mock gateway
    python3 -m pytest tests/corpus/runners/test_gateway_production_ops.py -q "$@" || exit 1
    exec "$0" gateway "$@"
    ;;
  unified)
    # 阶段 5：AgentLoop mock + 微信语料 mock + 交叉索引门禁
    exec python3 -m pytest \
      tests/corpus/runners/test_agent_loop_rubric.py \
      tests/corpus/runners/test_corpus_cross_channel.py \
      tests/corpus/runners/test_gateway_module_health.py \
      tests/corpus/runners/test_gateway_scripted.py \
      tests/corpus/runners/test_gateway_utterance_catalog.py \
      tests/corpus/runners/test_gateway_utterance_variants.py \
      tests/corpus/runners/test_gateway_multiturn_catalog.py \
      tests/corpus/runners/test_gateway_golden.py \
      tests/corpus/runners/test_gateway_production_ops.py \
      tests/test_gateway_dev_conversations.py \
      -m "corpus and corpus_mock" -q "$@"
    ;;
  pr-gate)
    exec "$(dirname "$0")/corpus/pr_corpus_gate.sh" "$@"
    ;;
  *)
    echo "Usage: $0 {mock|smoke|live|gateway|gateway-live|gateway-all|gateway-ops|unified|pr-gate|ops|drift}" >&2
    exit 1
    ;;
esac
