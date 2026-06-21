#!/usr/bin/env bash
# Install webnovel-write / webnovel-review via Butler registry（外部拉取，不读 ~/.claude/plugins）。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Butler marketplace 适配器 → GitHub Contents/raw（见 catalog/webnovel-writer-marketplace.json）
IDS=(
  marketplace:webnovel-writer/webnovel-write
  marketplace:webnovel-writer/webnovel-review
)

echo "== LingWen webnovel skills (Butler registry → GitHub) =="
fail=0
for id in "${IDS[@]}"; do
  echo "-- $id"
  if PYTHONPATH="$ROOT" butler skills install "$id" --yes; then
    echo "  ok"
  else
    echo "  failed — 检查公网/GitHub 可达或设置 GITHUB_TOKEN" >&2
    fail=$((fail + 1))
  fi
done

if [[ "$fail" -gt 0 ]]; then
  echo ""
  echo "备选（同等外部源，不经 marketplace 索引）："
  echo "  butler skills install github:lingfengQAQ/webnovel-writer/skills/webnovel-write/SKILL.md --yes"
  echo "  butler skills install github:lingfengQAQ/webnovel-writer/skills/webnovel-review/SKILL.md --yes"
  exit 1
fi

echo ""
PYTHONPATH="$ROOT" butler skills list 2>/dev/null | rg -i 'webnovel' || true
echo ""
echo "来源：butler/registry/catalog/skills/webnovel-writer-marketplace.json（GitHub 远程）"
echo "勿从 ~/.claude/plugins 复制 — 那是 Claude/Cursor IDE 缓存，非 Butler 技能源。"
