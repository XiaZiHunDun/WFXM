#!/usr/bin/env bash
# Butler v4 — 运行时数据备份
# Usage: bash scripts/backup-butler-data.sh [--incremental DEST_DIR] [OUTPUT_PATH]
set -euo pipefail

BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
INCREMENTAL=0
INCR_DEST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --incremental)
      INCREMENTAL=1
      INCR_DEST="${2:-$HOME/butler-backups/latest}"
      shift
      ;;
    -h|--help)
      cat <<HELP
Butler v4 数据备份

Usage:
  bash scripts/backup-butler-data.sh [OUTPUT_PATH]
  bash scripts/backup-butler-data.sh --incremental [DEST_DIR]

Options:
  --incremental DEST   增量同步到目标目录（使用 rsync, 默认 ~/butler-backups/latest）
  -h, --help           显示此帮助

Examples:
  bash scripts/backup-butler-data.sh                           # 完整 tar.gz
  bash scripts/backup-butler-data.sh my-backup.tar.gz          # 指定输出
  bash scripts/backup-butler-data.sh --incremental             # 增量同步
  bash scripts/backup-butler-data.sh --incremental /mnt/nas/   # 增量到 NAS
HELP
      exit 0
      ;;
    *) break ;;
  esac
  shift
done

DEFAULT_OUTPUT="butler-backup-${TIMESTAMP}.tar.gz"
OUTPUT="${1:-$DEFAULT_OUTPUT}"

if [[ ! -d "$BUTLER_HOME" ]]; then
  echo "ERROR: Butler 数据目录不存在: $BUTLER_HOME" >&2
  exit 1
fi

echo "=== Butler 数据备份 ==="
echo "源目录: $BUTLER_HOME"
echo "输出: $OUTPUT"
echo ""

# 统计数据量
DATA_SIZE=$(du -sh "$BUTLER_HOME" 2>/dev/null | cut -f1)
echo "数据量: $DATA_SIZE"

# 备份内容清单
echo ""
echo "备份内容:"
for item in config.yaml config.yaml.bak butler.db sessions runtime skills wechat weixin tenants; do
  if [[ -e "$BUTLER_HOME/$item" ]]; then
    if [[ -d "$BUTLER_HOME/$item" ]]; then
      count=$(find "$BUTLER_HOME/$item" -type f 2>/dev/null | wc -l)
      echo "  ✓ $item/ ($count 个文件)"
    else
      echo "  ✓ $item"
    fi
  fi
done
echo ""

# 排除项：不备份临时文件和日志
EXCLUDES=(
  "--exclude=*.log"
  "--exclude=*.log.*"
  "--exclude=logrotate.state"
  "--exclude=__pycache__"
  "--exclude=*.pyc"
)

if [[ "$INCREMENTAL" -eq 1 ]]; then
  # 增量备份模式 (rsync)
  if ! command -v rsync &>/dev/null; then
    echo "ERROR: rsync 未安装" >&2
    exit 1
  fi
  echo "正在增量同步到: $INCR_DEST"
  mkdir -p "$INCR_DEST"
  rsync -a --delete \
    --exclude='*.log' --exclude='*.log.*' \
    --exclude='logrotate.state' \
    --exclude='__pycache__' --exclude='*.pyc' \
    "$BUTLER_HOME/" "$INCR_DEST/"
  SYNC_SIZE=$(du -sh "$INCR_DEST" 2>/dev/null | cut -f1)
  echo ""
  echo "=== 增量备份完成 ==="
  echo "目标: $INCR_DEST ($SYNC_SIZE)"
  echo ""
  echo "恢复: rsync -a ${INCR_DEST}/ ${BUTLER_HOME}/"
else
  # 完整备份模式 (tar.gz)
  echo "正在打包..."
  tar czf "$OUTPUT" \
    -C "$(dirname "$BUTLER_HOME")" \
    "${EXCLUDES[@]}" \
    "$(basename "$BUTLER_HOME")"

  BACKUP_SIZE=$(du -sh "$OUTPUT" 2>/dev/null | cut -f1)
  echo ""
  echo "=== 备份完成 ==="
  echo "文件: $OUTPUT ($BACKUP_SIZE)"
  echo ""
  echo "恢复命令: bash scripts/restore-butler-data.sh $OUTPUT"
fi
echo ""
echo "注意: 备份不包含 .env 文件（含密钥，需手动迁移）"
