"""Shared B9 benchmark setup/oracle helpers (breaks prod_shaped ↔ live_fixed cycle)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from butler.dev_engine.b9_verify_utils import pytest_verify as _pytest_verify
from butler.dev_engine.edit_ops import apply_patch


def _verify_ws(ws: Path) -> tuple[bool, str]:
    return cast(tuple[bool, str], _pytest_verify(ws))


def _setup_b9l_multi_file_import(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "helpers.py").write_text(
        "def run():\n    return 42\n",
        encoding="utf-8",
    )
    (ws / "main.py").write_text(
        "from helper import run\n\n\ndef main():\n    return run()\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from main import main\n\n\ndef test_main():\n    assert main() == 42\n",
        encoding="utf-8",
    )


def _oracle_b9l_multi_file_import(ws: Path) -> None:
    _rec, err = apply_patch(ws / "main.py", "from helper import run", "from helpers import run")
    if err:
        raise RuntimeError(err)


def _verify_b9l_multi_file_import(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


def _setup_b9l_cross_module_rename(ws: Path) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    pkg = ws / "pkg"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text(
        "from pkg.client import Client\n\n__all__ = ['Client']\n",
        encoding="utf-8",
    )
    (pkg / "client.py").write_text(
        "class Client:\n    def getData(self):\n        return {}\n",
        encoding="utf-8",
    )
    (ws / "test_b9.py").write_text(
        "from pkg.client import Client\n\n\ndef test_rename():\n"
        "    c = Client()\n    assert hasattr(c, 'get_data')\n"
        "    assert not hasattr(c, 'getData')\n",
        encoding="utf-8",
    )


def _oracle_b9l_cross_module_rename(ws: Path) -> None:
    text = (ws / "pkg" / "client.py").read_text(encoding="utf-8")
    (ws / "pkg" / "client.py").write_text(text.replace("getData", "get_data"), encoding="utf-8")


def _verify_b9l_cross_module_rename(ws: Path) -> tuple[bool, str]:
    return _verify_ws(ws)


__all__ = [
    "_oracle_b9l_cross_module_rename",
    "_oracle_b9l_multi_file_import",
    "_setup_b9l_cross_module_rename",
    "_setup_b9l_multi_file_import",
    "_verify_b9l_cross_module_rename",
    "_verify_b9l_multi_file_import",
    "_verify_ws",
]
