#!/usr/bin/env bash
# Regenerate gateway catalog YAMLs and fail if git working tree differs.
# reference/用户语料 is gitignored (主公维护); CI runners skip regen and trust committed YAML.
set -euo pipefail
cd "$(dirname "$0")/../.."

REF_CORPUS="reference/用户语料/1.md"
if [[ ! -f "$REF_CORPUS" ]]; then
  echo "SKIP: $REF_CORPUS not present (reference/ is local-only)"
  echo "OK: corpus drift regen skipped on CI; committed catalog YAMLs are SSOT on runner"
  exit 0
fi

echo "==> build_reference_strict_catalog.py"
python3 scripts/build_reference_strict_catalog.py

echo "==> ingest_reference_user_corpus.py"
python3 scripts/ingest_reference_user_corpus.py

echo "==> generate_production_catalog.py"
python3 scripts/generate_production_catalog.py

LW=tests/corpus/suites/wechat_real/lw_real
for f in reference_utterance_strict.yaml utterance_multiturn_catalog.yaml \
         reference_utterance_catalog.yaml production_utterance_catalog.yaml; do
  if ! git diff --exit-code -- "$LW/$f" >/dev/null 2>&1; then
    echo "DRIFT: $LW/$f differs from generated output" >&2
    git diff --stat -- "$LW/$f" >&2 || true
    exit 1
  fi
done

echo "OK: gateway catalog YAMLs match generators"

echo "==> build_intent_crosswalk.py"
python3 scripts/corpus/build_intent_crosswalk.py
if ! git diff --exit-code -- tests/corpus/intent_crosswalk.yaml >/dev/null 2>&1; then
  echo "DRIFT: tests/corpus/intent_crosswalk.yaml differs from generated output" >&2
  git diff --stat -- tests/corpus/intent_crosswalk.yaml >&2 || true
  exit 1
fi
echo "OK: intent_crosswalk.yaml matches generator"
