#!/usr/bin/env bash
# CI / pre-push Ruff gate — aligned with project-health-check subset + active change surfaces.
set -euo pipefail
cd "$(dirname "$0")/.."

python3 -m ruff check \
  butler/config_service.py \
  butler/tools/config_tools.py \
  butler/tools/web_search.py \
  butler/tools/multimodal_tools.py \
  butler/gateway/error_cards.py \
  butler/gateway/commands/ \
  butler/ops/head_to_head.py \
  butler/ops/head_to_head_common.py \
  butler/tools/delegate_role_guard.py \
  butler/tools/delegate_phases.py \
  butler/dev_engine/verify.py \
  --select=E,F \
  --ignore=E501,E402 \
  --output-format=concise
