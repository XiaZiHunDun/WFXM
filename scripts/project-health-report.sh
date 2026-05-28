#!/usr/bin/env bash
# Run project-health-check and persist a timestamped report.
set -euo pipefail

cd "$(dirname "$0")/.."

MODE="${1:-quick}"
if [[ "${MODE}" != "quick" && "${MODE}" != "full" ]]; then
  echo "Usage: $0 [quick|full]"
  exit 2
fi

REPORT_DIR="${REPORT_DIR:-logs/maintenance}"
mkdir -p "${REPORT_DIR}"

TS="$(date +%Y%m%d-%H%M%S)"
LOG_FILE="${REPORT_DIR}/health-${MODE}-${TS}.log"
MD_FILE="${REPORT_DIR}/health-${MODE}-${TS}.md"

START_EPOCH="$(date +%s)"
set +e
timeout 1800 bash scripts/project-health-check.sh "${MODE}" >"${LOG_FILE}" 2>&1
RC=$?
set -e
END_EPOCH="$(date +%s)"
DURATION="$((END_EPOCH - START_EPOCH))"

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
REV="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

STATUS_LABEL="OK"
if [[ "${RC}" -ne 0 ]]; then
  STATUS_LABEL="FAILED(${RC})"
fi

{
  echo "# 项目健康检查报告"
  echo
  echo "- 时间戳: ${TS}"
  echo "- 模式: ${MODE}"
  echo "- 分支: ${BRANCH}"
  echo "- 提交: ${REV}"
  echo "- 状态: ${STATUS_LABEL}"
  echo "- 耗时(秒): ${DURATION}"
  echo "- 原始日志: \`${LOG_FILE}\`"
  echo
  echo "## 最近 40 行日志"
  echo
  echo '```text'
  python3 - <<PY
from pathlib import Path
lines = Path("${LOG_FILE}").read_text(encoding="utf-8", errors="replace").splitlines()
for line in lines[-40:]:
    print(line)
PY
  echo '```'
} >"${MD_FILE}"

echo "health report markdown: ${MD_FILE}"
echo "health report log: ${LOG_FILE}"

if [[ "${RC}" -ne 0 ]]; then
  echo "project-health-report: failed"
  exit "${RC}"
fi

echo "project-health-report: OK"
