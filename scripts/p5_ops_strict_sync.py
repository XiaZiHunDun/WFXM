#!/usr/bin/env python3
"""Sync P5 *_ops.py strict module list into pyproject.toml."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _load_modules() -> list[str]:
    out = subprocess.check_output(
        [sys.executable, str(ROOT / "scripts" / "p5_ops_strict_modules.py"), "--modules"],
        cwd=ROOT,
        text=True,
    )
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def sync_pyproject(modules: list[str]) -> None:
    text = PYPROJECT.read_text(encoding="utf-8")
    lines = [f'    "{m}",' for m in modules]
    block = (
        "\n[[tool.mypy.overrides]]\n"
        "# P5: *_ops.py passing mypy strict (scripts/p5_ops_strict_modules.py)\n"
        "module = [\n"
        + "\n".join(lines)
        + "\n]\n"
        "strict = true\n"
    )
    marker = "# P5: *_ops.py passing mypy strict"
    if marker in text:
        pattern = re.compile(
            r"\n\[\[tool\.mypy\.overrides\]\]\n# P5: \*_ops\.py passing mypy strict.*?\nstrict = true\n",
            re.DOTALL,
        )
        text = pattern.sub("\n" + block, text)
    else:
        text = text.replace(
            "\n[tool.coverage.run]",
            "\n" + block + "\n[tool.coverage.run]",
        )
    PYPROJECT.write_text(text, encoding="utf-8")


def main() -> int:
    modules = _load_modules()
    print(f"P5 strict ops modules: {len(modules)}")
    sync_pyproject(modules)
    print("Updated pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
