"""ENG-7 layering: tools/core must not import butler.gateway (except execution_context seam)."""

from __future__ import annotations

import ast
import pathlib

import pytest

_LAYERING_FILES = (
    "butler/core/tool_orchestrator.py",
    "butler/tools/terminal_approval.py",
    "butler/tools/terminal_sandbox.py",
    "butler/tools/network_route_verify.py",
)

_GATEWAY_IMPORT_ALLOWLIST = frozenset({
    "butler/execution_context.py",
})


def _gateway_imports(source: str) -> list[tuple[str, int]]:
    tree = ast.parse(source)
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "butler.gateway" or mod.startswith("butler.gateway."):
                out.append((mod, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name
                if mod == "butler.gateway" or mod.startswith("butler.gateway."):
                    out.append((mod, node.lineno))
    return out


def _iter_layering_py_files() -> list[str]:
    root = pathlib.Path("butler")
    paths: list[str] = []
    for sub in ("tools", "core"):
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.as_posix()
            if rel in _GATEWAY_IMPORT_ALLOWLIST:
                continue
            paths.append(rel)
    return paths


@pytest.mark.parametrize("rel_path", _LAYERING_FILES)
def test_no_gateway_import_for_approval_cards(rel_path: str):
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    offenders = _gateway_imports(text)
    assert not offenders, f"{rel_path} still imports gateway: {offenders}"


@pytest.mark.parametrize("rel_path", _iter_layering_py_files())
def test_tools_and_core_no_direct_gateway_import(rel_path: str):
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    offenders = _gateway_imports(text)
    assert not offenders, (
        f"{rel_path} imports gateway directly; use butler.execution_context seam: "
        f"{offenders}"
    )
