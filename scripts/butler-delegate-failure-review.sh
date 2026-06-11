#!/usr/bin/env bash
# Weekly delegate failure annotation checklist (LangFuse phase 2).
#
# Usage:
#   bash scripts/butler-delegate-failure-review.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env" 2>/dev/null || true
  set +a
fi

HOST="${LANGFUSE_HOST:-http://localhost:3000}"

python3 - <<'PY'
import json
from butler.ops.delegate_failure_capture import DATASET_NAME, failure_audit_summary

summary = failure_audit_summary()
print("=== Butler 委派失败复盘（阶段 2）===")
print()
print(f"本地审计: {summary.get('audit_path', '(none)')}")
print(f"累计条数: {summary.get('total', 0)}")
by_reason = summary.get("by_reason") or {}
if by_reason:
    print("失败分类:")
    for reason, count in sorted(by_reason.items(), key=lambda x: -x[1]):
        print(f"  - {reason}: {count}")
else:
    print("失败分类: (暂无)")
print()
print("LangFuse 操作清单:")
print(f"  1. 打开 {DATASET_NAME} Dataset，查看新增生产 case")
print("  2. Traces 筛选 tool:delegate_task 或 span delegate:dev")
print("  3. 标注根因: tool_wrong / patch_wrong / no_test / verify_fail / other")
print("  4. 高价值 case 回灌: bash scripts/butler-delegate-failure-promote.sh")
print("  5. 离线审阅包: bash scripts/butler-delegate-failure-promote.sh --bundle")
print()
from butler.ops.delegate_failure_b9_import import export_b9_candidates
candidates = export_b9_candidates(limit=10)
print(f"B9 候选导出: {candidates.get('total', 0)} 条（见 promotion_checklist）")
if candidates.get("candidates"):
    print(json.dumps(candidates["candidates"][:3], ensure_ascii=False, indent=2))
print()
if summary.get("recent"):
    print("最近 10 条审计预览:")
    print(json.dumps(summary["recent"], ensure_ascii=False, indent=2))
PY

echo
echo "LangFuse UI: ${HOST}"
