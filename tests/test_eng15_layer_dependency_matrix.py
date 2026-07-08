"""ENG-15: layer dependency matrix — AST import rules vs v4-layer-model §4."""

from __future__ import annotations

import ast
import pathlib

import pytest

from tests.layer_import_rules import is_forbidden_import, resolve_layer

_SKIP_PREFIXES = (
    "butler/contracts/",
    "tests/",
    "scripts/",
)


def _iter_butler_py_files() -> list[str]:
    root = pathlib.Path("butler")
    paths: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.as_posix()
        if any(rel.startswith(p) for p in _SKIP_PREFIXES):
            continue
        paths.append(rel)
    return paths


def _collect_imports(source: str) -> list[tuple[str, int]]:
    tree = ast.parse(source)
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod:
                out.append((mod, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out


def _violations_for_file(rel_path: str) -> list[str]:
    layer = resolve_layer(rel_path)
    if layer is None:
        return []
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    offenders: list[str] = []
    for mod, lineno in _collect_imports(text):
        bad, hint = is_forbidden_import(layer, mod, rel_path)
        if bad:
            offenders.append(f"{rel_path}:{lineno} [{layer}] imports {mod!r} — {hint}")
    return offenders


@pytest.mark.parametrize("rel_path", _iter_butler_py_files())
def test_layer_dependency_matrix(rel_path: str):
    offenders = _violations_for_file(rel_path)
    assert not offenders, "\n".join(offenders)


def collect_all_violations() -> list[str]:
    """CLI entry for butler-layer-import-gate.sh."""
    all_off: list[str] = []
    for rel in _iter_butler_py_files():
        all_off.extend(_violations_for_file(rel))
    return all_off
