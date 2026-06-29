#!/usr/bin/env bash
# 发版 eval 预设：TCR + regression + 微信语料（MOD-3 release preset）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.
exec python -m butler.main eval run --preset release "$@"
