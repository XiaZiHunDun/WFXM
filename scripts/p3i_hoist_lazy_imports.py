#!/usr/bin/env python3
"""P3-I: hoist function-scoped ``from butler.*`` to module top where safe."""

from __future__ import annotations

import argparse
import ast
import pathlib
import subprocess
import sys
import textwrap

# Proven import cycles — keep lazy in these (file_posix, module).
CYCLE_KEEP: set[tuple[str, str]] = {
    ("butler/core/tool_batch.py", "butler.core.tool_dispatch"),
    ("butler/core/tool_dispatch.py", "butler.core.tool_batch"),
    ("butler/core/tool_dispatch_doom_ops.py", "butler.core.tool_batch"),
    ("butler/cli/gateway_cli.py", "butler.main"),
    ("butler/tools/delegate_impl.py", "butler.orchestrator"),
    ("butler/ops/health_report_turn.py", "butler.ops.health_report"),
    ("butler/core/tool_batch_hooks.py", "butler.core.tool_batch"),
    ("butler/memory/butler_memory.py", "butler.memory.experience_consolidation"),
    ("butler/gateway/completion_notify.py", "butler.report"),
    ("butler/report/generator.py", "butler.report.acceptance_card"),
    ("butler/dev_engine/b9_prod_shaped_tasks.py", "butler.dev_engine.b9_live_fixed_tasks"),
    ("butler/dev_engine/b9_live_fixed_tasks.py", "butler.dev_engine.b9_prod_shaped_tasks"),
}

MIN_COUNT = 8


def _import_key(node: ast.ImportFrom) -> tuple:
    names = tuple(sorted((a.name, a.asname) for a in (node.names or [])))
    return (node.level or 0, node.module or "", names)


def _import_stmt(node: ast.ImportFrom) -> str:
    return ast.unparse(node).strip()


def _collect_imports(tree: ast.AST) -> tuple[set[tuple], list[tuple[ast.ImportFrom, int]]]:
    """Return (module_level_keys, lazy_nodes_with_depth)."""
    module_keys: set[tuple] = set()
    lazy: list[tuple[ast.ImportFrom, int]] = []

    class V(ast.NodeVisitor):
        def __init__(self) -> None:
            self.depth = 0
            self.in_type_checking = False

        def visit_If(self, node: ast.If) -> None:
            guard = False
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                guard = True
            elif (
                isinstance(node.test, ast.Attribute)
                and isinstance(node.test.value, ast.Name)
                and node.test.value.id == "typing"
                and node.test.attr == "TYPE_CHECKING"
            ):
                guard = True
            prev = self.in_type_checking
            if guard:
                self.in_type_checking = True
            self.generic_visit(node)
            self.in_type_checking = prev

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.depth += 1
            self.generic_visit(node)
            self.depth -= 1

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            mod = node.module or ""
            if not mod.startswith("butler"):
                return
            key = _import_key(node)
            if self.depth == 0 and not self.in_type_checking:
                module_keys.add(key)
            elif self.depth > 0:
                lazy.append((node, self.depth))

    V().visit(tree)
    return module_keys, lazy


def _insert_after_imports(lines: list[str], new_stmts: list[str]) -> list[str]:
    """Insert new import lines after the last contiguous top-level import block."""
    insert_at = 0
    i = 0
    n = len(lines)

    # Skip optional module docstring (triple-quoted string at file start).
    if i < n:
        stripped0 = lines[i].strip()
        if stripped0.startswith('"""') or stripped0.startswith("'''"):
            quote = stripped0[:3]
            if stripped0.count(quote) >= 2 and len(stripped0) > 6:
                insert_at = i + 1
                i += 1
            else:
                i += 1
                while i < n and quote not in lines[i]:
                    i += 1
                if i < n:
                    insert_at = i + 1
                    i += 1

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("from __future__"):
            insert_at = i + 1
            i += 1
            continue
        if stripped.startswith("import ") or stripped.startswith("from "):
            insert_at = i + 1
            # skip multiline import paren blocks
            if "(" in stripped and ")" not in stripped:
                i += 1
                while i < n and ")" not in lines[i]:
                    insert_at = i + 1
                    i += 1
                if i < n:
                    insert_at = i + 1
            i += 1
            continue
        if stripped == "" or stripped.startswith("#"):
            i += 1
            continue
        break
    out = lines[:insert_at]
    if out and out[-1].strip():
        out.append("")
    for stmt in new_stmts:
        out.append(stmt if stmt.endswith("\n") else stmt + "\n")
    if insert_at < n and (not out or out[-1].strip()):
        pass
    elif insert_at < n:
        out.append("")
    out.extend(lines[insert_at:])
    return out


def _remove_node_lines(source: str, node: ast.AST) -> str:
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    end = getattr(node, "end_lineno", node.lineno) - 1
    # drop trailing blank line if import was alone in block
    new_lines = lines[:start] + lines[end + 1 :]
    return "".join(new_lines)


def process_file(path: pathlib.Path, *, dry_run: bool = False) -> dict:
    rel = path.as_posix()
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"path": rel, "error": str(e), "removed": 0, "hoisted": 0}

    module_keys, lazy_nodes = _collect_imports(tree)
    if not lazy_nodes:
        return {"path": rel, "removed": 0, "hoisted": 0, "kept_cycle": 0}

    to_remove: list[ast.ImportFrom] = []
    to_hoist: list[ast.ImportFrom] = []
    kept_cycle = 0

    for node, _depth in lazy_nodes:
        mod = node.module or ""
        key = _import_key(node)
        if (rel, mod) in CYCLE_KEEP:
            kept_cycle += 1
            continue
        if key in module_keys:
            to_remove.append(node)
        else:
            to_hoist.append(node)
            module_keys.add(key)

    if not to_remove and not to_hoist:
        return {"path": rel, "removed": 0, "hoisted": 0, "kept_cycle": kept_cycle}

    # Remove bottom-up to preserve line numbers
    all_remove = sorted(to_remove + to_hoist, key=lambda n: n.lineno, reverse=True)
    new_source = source
    for node in all_remove:
        new_source = _remove_node_lines(new_source, node)

    hoist_stmts = []
    seen_hoist: set[tuple] = set()
    for node in to_hoist:
        key = _import_key(node)
        if key in seen_hoist:
            continue
        seen_hoist.add(key)
        hoist_stmts.append(_import_stmt(node))

    if hoist_stmts:
        lines = new_source.splitlines(keepends=True)
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        new_source = "".join(_insert_after_imports(lines, hoist_stmts))

    if dry_run:
        return {
            "path": rel,
            "removed": len(to_remove),
            "hoisted": len(seen_hoist),
            "kept_cycle": kept_cycle,
        }

    path.write_text(new_source, encoding="utf-8")
    return {
        "path": rel,
        "removed": len(to_remove),
        "hoisted": len(seen_hoist),
        "kept_cycle": kept_cycle,
    }


def verify_import() -> bool:
    r = subprocess.run(
        [sys.executable, "-c", "import butler; import butler.main"],
        cwd=pathlib.Path("."),
        env={**dict(**__import__("os").environ), "PYTHONPATH": "."},
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def count_lazy() -> int:
    sys.path.insert(0, ".")
    from butler.ops.lazy_import_budget import count_lazy_butler_imports

    return count_lazy_butler_imports()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--min", type=int, default=MIN_COUNT)
    parser.add_argument("--file", action="append", dest="files")
    args = parser.parse_args()

    sys.path.insert(0, ".")
    from butler.ops.lazy_import_budget import lazy_import_counts_by_file

    if args.files:
        targets = [pathlib.Path(f) for f in args.files]
    else:
        by_file = lazy_import_counts_by_file()
        targets = [
            pathlib.Path(p) for p, c in sorted(by_file.items(), key=lambda x: -x[1]) if c >= args.min
        ]

    start = count_lazy()
    print(f"START: {start}")

    changed: list[dict] = []
    batch_size = 10
    for i, path in enumerate(targets):
        result = process_file(path, dry_run=args.dry_run)
        if result.get("removed") or result.get("hoisted"):
            changed.append(result)
            print(
                f"  {result['path']}: removed_dup={result.get('removed',0)} "
                f"hoisted={result.get('hoisted',0)} kept_cycle={result.get('kept_cycle',0)}"
            )
        if not args.dry_run and (i + 1) % batch_size == 0:
            if not verify_import():
                print("IMPORT FAILED after batch — stop", file=sys.stderr)
                print(f"COUNT: {count_lazy()}")
                return 1
            print(f"  batch {(i+1)//batch_size} ok, count={count_lazy()}")

    if not args.dry_run:
        if not verify_import():
            print("IMPORT FAILED at end", file=sys.stderr)
            return 1
        end = count_lazy()
        print(f"END: {end} (delta {start - end})")
        print(f"FILES CHANGED: {len(changed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
