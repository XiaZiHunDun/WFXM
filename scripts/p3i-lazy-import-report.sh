#!/usr/bin/env bash
# P3-I: report function-scoped lazy ``from butler.*`` imports vs budget.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH=.

python3 - <<'PY'
from butler.ops.lazy_import_budget import (
    LAZY_IMPORT_BUDGET,
    count_lazy_butler_imports,
    count_module_level_butler_imports,
    lazy_import_counts_by_file,
)

lazy = count_lazy_butler_imports()
mod = count_module_level_butler_imports()
print("=== P3-I lazy import report ===")
print(f"function_scoped_from_butler={lazy}")
print(f"module_level_from_butler={mod}")
print(f"LAZY_IMPORT_BUDGET={LAZY_IMPORT_BUDGET}")
print(f"headroom={LAZY_IMPORT_BUDGET - lazy}")
print("")
print("Top files (function-scoped):")
for path, n in sorted(lazy_import_counts_by_file().items(), key=lambda x: -x[1])[:20]:
    print(f"  {n:4d}  {path}")
if lazy > LAZY_IMPORT_BUDGET:
    raise SystemExit(1)
PY

echo "p3i-lazy-import-report: OK"
