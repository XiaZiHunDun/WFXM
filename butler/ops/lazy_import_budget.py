"""R1-18 lazy-import budget gate (P3-I: function-scoped ``from butler.*`` only)."""

from __future__ import annotations

import ast
import pathlib

# Baseline 2026-07-06: function-scoped lazy imports (AST count). Gate prevents growth.
LAZY_IMPORT_BUDGET = 1975


def _count_butler_imports_in_tree(tree: ast.AST) -> tuple[int, int]:
    """Return (module_level, in_function) ``from butler.*`` import counts."""
    module_level = 0
    in_function = 0

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._in_function = 0

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            prev = self._in_function
            self._in_function += 1
            self.generic_visit(node)
            self._in_function = prev

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            prev = self._in_function
            self._in_function += 1
            self.generic_visit(node)
            self._in_function = prev

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            mod = node.module or ""
            if not mod.startswith("butler"):
                return
            if self._in_function:
                nonlocal in_function
                in_function += 1
            else:
                nonlocal module_level
                module_level += 1

    _Visitor().visit(tree)
    return module_level, in_function


def count_lazy_butler_imports(*, root: pathlib.Path | None = None) -> int:
    """Count ``from butler.*`` inside function bodies (true lazy imports)."""
    root = root or pathlib.Path("butler")
    total = 0
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        _, in_function = _count_butler_imports_in_tree(tree)
        total += in_function
    return total


def count_module_level_butler_imports(*, root: pathlib.Path | None = None) -> int:
    """Count module-level ``from butler.*`` (eager imports; reporting only)."""
    root = root or pathlib.Path("butler")
    total = 0
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        module_level, _ = _count_butler_imports_in_tree(tree)
        total += module_level
    return total


def lazy_import_counts_by_file(*, root: pathlib.Path | None = None) -> dict[str, int]:
    """Per-file function-scoped lazy import counts (for P3-I reports)."""
    root = root or pathlib.Path("butler")
    out: dict[str, int] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        _, in_function = _count_butler_imports_in_tree(tree)
        if in_function:
            out[path.as_posix()] = in_function
    return out


__all__ = [
    "LAZY_IMPORT_BUDGET",
    "count_lazy_butler_imports",
    "count_module_level_butler_imports",
    "lazy_import_counts_by_file",
]
