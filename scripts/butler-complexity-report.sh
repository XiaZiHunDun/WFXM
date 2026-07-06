#!/usr/bin/env bash
# Complexity / size report for Butler Python sources (ENG-1).
#
# Usage:
#   bash scripts/butler-complexity-report.sh
#   bash scripts/butler-complexity-report.sh --json
#
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

JSON=0
for arg in "$@"; do
  case "$arg" in
    --json) JSON=1 ;;
    -h|--help)
      sed -n '1,8p' "$0"
      exit 0
      ;;
  esac
done

python3 - "$ROOT" "$JSON" <<'PY'
import ast
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
as_json = sys.argv[2] == "1"
min_fn = 80
min_file = 600

py_files = sorted(
    p for p in root.joinpath("butler").rglob("*.py")
    if "__pycache__" not in p.parts
)

large_files: list[dict] = []
long_funcs: list[dict] = []

for path in py_files:
    rel = path.relative_to(root).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.count("\n") + (1 if text else 0)
    if lines >= min_file:
        large_files.append({"path": rel, "lines": lines})
    try:
        tree = ast.parse(text)
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.end_lineno is None:
            continue
        span = node.end_lineno - node.lineno + 1
        if span >= min_fn:
            long_funcs.append(
                {
                    "path": rel,
                    "name": node.name,
                    "lines": span,
                    "start": node.lineno,
                }
            )

large_files.sort(key=lambda x: -x["lines"])
long_funcs.sort(key=lambda x: (-x["lines"], x["path"], x["name"]))

from butler.ops.lazy_import_budget import (
    LAZY_IMPORT_BUDGET,
    count_lazy_butler_imports,
    count_module_level_butler_imports,
)

lazy_imports = count_lazy_butler_imports()

report = {
    "python_files": len(py_files),
    "files_ge_600_lines": len(large_files),
    "functions_ge_80_lines": len(long_funcs),
    "lazy_from_butler_imports": lazy_imports,
    "large_files": large_files[:25],
    "long_functions": long_funcs[:40],
}

if as_json:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    sys.exit(0)

print("=== Butler complexity report (ENG-1) ===")
print(f"python_files={report['python_files']}")
print(f"files>={min_file}L={report['files_ge_600_lines']}")
print(f"functions>={min_fn}L={report['functions_ge_80_lines']}")
print(f"lazy_from_butler_imports={report['lazy_from_butler_imports']} (function-scoped)")
print(f"module_level_from_butler={count_module_level_butler_imports()}")
if report["lazy_from_butler_imports"] > LAZY_IMPORT_BUDGET:
    print(f"WARN: lazy imports exceed budget {LAZY_IMPORT_BUDGET}")
print("")
print(f"Top files (>={min_file} lines):")
for row in large_files[:15]:
    print(f"  {row['lines']:5d}  {row['path']}")
print("")
print(f"Top functions (>={min_fn} lines):")
for row in long_funcs[:20]:
    print(
        f"  {row['lines']:4d} L{row['start']:4d}  "
        f"{row['path']}::{row['name']}"
    )
PY
