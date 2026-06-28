"""ENG-7 layering: core/tools must not import butler.gateway for approval cards."""

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


def _gateway_imports(source: str) -> list[tuple[str, int]]:
    tree = ast.parse(source)
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "butler.gateway" or mod.startswith("butler.gateway."):
                out.append((mod, node.lineno))
    return out


@pytest.mark.parametrize("rel_path", _LAYERING_FILES)
def test_no_gateway_import_for_approval_cards(rel_path: str):
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    offenders = _gateway_imports(text)
    assert not offenders, f"{rel_path} still imports gateway: {offenders}"
