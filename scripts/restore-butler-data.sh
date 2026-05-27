#!/usr/bin/env bash
# Butler v4 — 运行时数据恢复
# Usage: bash scripts/restore-butler-data.sh <backup.tar.gz> [--force]
set -euo pipefail

BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
FORCE=0

if [[ $# -lt 1 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
  cat <<HELP
Butler v4 数据恢复

Usage:
  bash scripts/restore-butler-data.sh <backup.tar.gz> [--force]

Options:
  --force   覆盖已有数据（默认会先备份已有数据）

Examples:
  bash scripts/restore-butler-data.sh butler-backup-20260527.tar.gz
  bash scripts/restore-butler-data.sh butler-backup-20260527.tar.gz --force
HELP
  exit 0
fi

BACKUP="$1"
shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) FORCE=1 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

if [[ ! -f "$BACKUP" ]]; then
  echo "ERROR: 备份文件不存在: $BACKUP" >&2
  exit 1
fi

echo "=== Butler 数据恢复 ==="
echo "备份源: $BACKUP"
echo "目标: $BUTLER_HOME"
echo ""

# 预检：列出备份内容
echo "备份内容预览:"
TAR_LIST=$(tar tzf "$BACKUP" 2>/dev/null || true)
echo "$TAR_LIST" | head -20 || true
TOTAL_FILES=$(echo "$TAR_LIST" | wc -l)
echo "..."
echo "(共 $TOTAL_FILES 个条目)"
echo ""

# 检测 tar 内的顶层目录名
TAR_TOP=$(echo "$TAR_LIST" | head -1 | cut -d/ -f1)
echo "备份内部根: $TAR_TOP"

# 如果目标已存在，先做安全备份
if [[ -d "$BUTLER_HOME" ]] && [[ "$FORCE" -eq 0 ]]; then
  EXISTING_SIZE=$(du -sh "$BUTLER_HOME" 2>/dev/null | cut -f1)
  if [[ "$EXISTING_SIZE" != "0" ]] && [[ -n "$(ls -A "$BUTLER_HOME" 2>/dev/null)" ]]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    SAFETY_BACKUP="${BUTLER_HOME}.pre-restore-${TIMESTAMP}.tar.gz"
    echo "已有数据 ($EXISTING_SIZE)，先做安全备份..."
    tar czf "$SAFETY_BACKUP" -C "$(dirname "$BUTLER_HOME")" "$(basename "$BUTLER_HOME")"
    echo "  安全备份: $SAFETY_BACKUP"
    echo ""
  fi
fi

# 恢复：解包到临时目录再移动，确保路径正确对齐
echo "正在恢复..."
TMPDIR=$(mktemp -d)
tar xzf "$BACKUP" -C "$TMPDIR"

# 将解包内容移动到 BUTLER_HOME
mkdir -p "$BUTLER_HOME"
EXTRACTED="$TMPDIR/$TAR_TOP"
if [[ -d "$EXTRACTED" ]]; then
  cp -a "$EXTRACTED"/. "$BUTLER_HOME"/
else
  cp -a "$TMPDIR"/. "$BUTLER_HOME"/
fi
rm -rf "$TMPDIR"

# 验证
echo ""
echo "恢复后验证:"
for item in config.yaml butler.db sessions skills; do
  if [[ -e "$BUTLER_HOME/$item" ]]; then
    echo "  ✓ $item"
  else
    echo "  ✗ $item (缺失)"
  fi
done

echo ""
echo "=== 恢复完成 ==="
echo ""
echo "后续步骤:"
echo "  1. 检查 $BUTLER_HOME/config.yaml 配置是否适合新环境"
echo "  2. 确保 .env 中的 API keys 已正确设置"
echo "  3. 运行 butler doctor 验证健康状态"
echo "  4. 如需重建向量索引: butler memory reindex"
