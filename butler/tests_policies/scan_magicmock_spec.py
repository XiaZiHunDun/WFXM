"""Sprint 23 TST-10-6: AST scanner enforcing ``MagicMock(spec=...)``.

Scans ``tests/`` for ``MagicMock()`` / ``Mock()`` calls without a
``spec=`` / ``spec_set=`` / ``wraps=`` keyword. Reports each
violation as a :class:`Violation` (path / lineno / func_name /
snippet).

Why ``spec=`` matters (Sprint 11 audit TST-10-6):

1. **Silent API drift**: ``MagicMock()`` auto-creates any attribute
   on access. ``mock.foo()`` succeeds even if the real object has no
   ``.foo`` — production crashes, tests pass.
2. **Type checker blindness**: ``mock.bar().baz()`` is ``Any`` for
   mypy / pyright when the mock has no ``spec``. Renaming a method
   on the real class doesn't ripple into the test.
3. **Refactor fragility**: changing the real interface (e.g.
   ``project_manager`` -> ``project_registry``) leaves a mountain
   of green tests that exercise dead attributes.

Per-line opt-out is supported via ``# noqa: magicmock-no-spec`` on
the same line as the call.

CLI::

    python -m butler.tests_policies.scan_magicmock_spec tests/
    python -m butler.tests_policies.scan_magicmock_spec tests/ --report
    python -m butler.tests_policies.scan_magicmock_spec file.py  # single file
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import pathlib
import sys
from typing import Iterable

# Accepted spec-providing keywords (any of these satisfies the policy).
_SPEC_KEYWORDS = frozenset({"spec", "spec_set", "wraps"})

# MagicMock / Mock factory names (covers both ``MagicMock()`` direct
# call and ``unittest.mock.MagicMock()`` qualified form).
_FACTORY_NAMES = frozenset({"MagicMock", "Mock", "AsyncMock"})

# Comment that opts a single call out of the policy.
_NOQA_TAG = "noqa: magicmock-no-spec"


@dataclasses.dataclass(frozen=True)
class Violation:
    path: pathlib.Path
    lineno: int
    func_name: str
    snippet: str

    def format_report(self) -> str:
        return f"{self.path}:{self.lineno} [{self.func_name}]  {self.snippet.strip()}"


def _is_factory_call(node: ast.Call) -> bool:
    """True if ``node`` is a call to MagicMock / Mock / AsyncMock."""
    func = node.func
    if isinstance(func, ast.Name) and func.id in _FACTORY_NAMES:
        return True
    if isinstance(func, ast.Attribute) and func.attr in _FACTORY_NAMES:
        return True
    return False


def _has_spec_kwarg(node: ast.Call) -> bool:
    return any(kw.arg in _SPEC_KEYWORDS for kw in node.keywords)


def _line_has_noqa(source_lines: list[str], lineno: int) -> bool:
    """True if the given line carries a ``# noqa: magicmock-no-spec`` tag.

    ``lineno`` is 1-based (matches ``ast.Lineno``).
    """
    if lineno < 1 or lineno > len(source_lines):
        return False
    return _NOQA_TAG in source_lines[lineno - 1]


def _enclosing_func(tree: ast.Module, target_lineno: int) -> str:
    """Return the name of the smallest function / method enclosing ``target_lineno``."""
    best: tuple[int, str] | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = node.end_lineno
            if end is None:
                continue
            if node.lineno <= target_lineno <= end:
                if best is None or node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1] if best else "<module>"


def scan_file(path: pathlib.Path) -> list[Violation]:
    """Scan a single ``.py`` file and return a list of violations.

    Returns an empty list on parse errors (the file is not python) or
    when the file has no offending calls.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []
    source_lines = text.splitlines()
    out: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_factory_call(node):
            continue
        if _has_spec_kwarg(node):
            continue
        if _line_has_noqa(source_lines, node.lineno):
            continue
        snippet = source_lines[node.lineno - 1] if node.lineno <= len(source_lines) else ""
        out.append(
            Violation(
                path=path,
                lineno=node.lineno,
                func_name=_enclosing_func(tree, node.lineno),
                snippet=snippet,
            )
        )
    return out


def scan_paths(paths: Iterable[pathlib.Path]) -> list[Violation]:
    """Scan a collection of files and/or directories.

    Directories are walked recursively for ``*.py`` files. Missing
    paths are silently skipped (CLI ergonomics).
    """
    out: list[Violation] = []
    for p in paths:
        if p.is_dir():
            for child in sorted(p.rglob("*.py")):
                out.extend(scan_file(child))
        elif p.is_file():
            out.extend(scan_file(p))
    return out


def _format_report(violations: list[Violation]) -> str:
    if not violations:
        return "0 violations"
    lines = [f"{len(violations)} violation(s):", ""]
    for v in violations:
        lines.append(v.format_report())
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan_magicmock_spec",
        description=(
            "Detect MagicMock() / Mock() / AsyncMock() calls without "
            "spec=/spec_set=/wraps= in test files. Per-line opt-out via "
            "'# noqa: magicmock-no-spec'."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="+",
        type=pathlib.Path,
        help="Files or directories to scan.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print human-readable report (default: exit code only).",
    )
    args = parser.parse_args(argv)

    violations = scan_paths(args.paths)

    if args.report:
        print(_format_report(violations))
    else:
        if violations:
            print(
                f"{len(violations)} MagicMock() violation(s). "
                f"Use --report for details.",
                file=sys.stderr,
            )

    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
