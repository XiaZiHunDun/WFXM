"""R1-18 lazy-import budget gate (ENG continuation)."""

from __future__ import annotations

import pathlib

# Baseline 2026-06-29 (butler-complexity-report). Gate prevents growth; lower when cleaning imports.
LAZY_IMPORT_BUDGET = 3600  # 2026-06-30: ACL/eval_integration modules (+161 lazy imports)


def count_lazy_butler_imports(*, root: pathlib.Path | None = None) -> int:
    root = root or pathlib.Path("butler")
    total = 0
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        total += sum(
            1 for line in text.splitlines() if line.lstrip().startswith("from butler.")
        )
    return total


__all__ = ["LAZY_IMPORT_BUDGET", "count_lazy_butler_imports"]
