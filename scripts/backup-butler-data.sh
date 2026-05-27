#!/usr/bin/env bash
# Butler v4 — 运行时数据备份
# Usage: bash scripts/backup-butler-data.sh [OUTPUT_PATH]
set -euo pipefail

BUTLER_HOME="${BUTLER_HOME:-$HOME/.butler}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
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

# 执行备份
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
echo ""
echo "注意: 备份不包含 .env 文件（含密钥，需手动迁移）"
