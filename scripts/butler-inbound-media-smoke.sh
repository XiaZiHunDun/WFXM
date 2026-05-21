#!/usr/bin/env bash
# 微信入站媒体（识图/语音）代码路径守门 — 非真机发图
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-.}:."
echo "== inbound media pytest =="
python3 -m pytest \
  tests/test_inbound_media.py \
  tests/test_wechat_ilink_media.py \
  -q --tb=line
echo "Inbound media smoke done. 真机：发截图 + 语音见 wechat-daily-smoke-checklist §媒体"
