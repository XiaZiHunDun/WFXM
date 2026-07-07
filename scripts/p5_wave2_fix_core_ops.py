#!/usr/bin/env python3
"""P5 wave2b: minimal mypy strict fixes for butler/core/*_ops.py."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ensure_import(src: str, name: str) -> str:
    if re.search(rf"\b{name}\b", src.split("def ", 1)[0]) is None and name not in src:
        return src
    if name == "cast" and "cast(" in src:
        if re.search(r"from typing import[^\n]*\bcast\b", src):
            return src
        if "from typing import" in src:
            return re.sub(
                r"(from typing import [^\n]+)",
                lambda m: m.group(1) + (", cast" if "cast" not in m.group(1) else ""),
                src,
                count=1,
            )
        return "from typing import cast\n" + src
    if name == "Any":
        if re.search(r"from typing import[^\n]*\bAny\b", src):
            return src
        if "from typing import" in src:
            return re.sub(
                r"(from typing import [^\n]+)",
                lambda m: m.group(1) + (", Any" if "Any" not in m.group(1) else ""),
                src,
                count=1,
            )
        return "from typing import Any\n" + src
    return src


def fix_file(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    orig = src

    src = re.sub(r": dict\)(?!])", ": dict[str, Any])", src)
    src = re.sub(r": dict \|", ": dict[str, Any] |", src)
    src = re.sub(r": dict,", ": dict[str, Any],", src)
    src = re.sub(r": dict$", ": dict[str, Any]", src, flags=re.MULTILINE)
    src = re.sub(r"list\[dict\]", "list[dict[str, Any]]", src)
    src = re.sub(r": list\)(?!])", ": list[Any])", src)
    src = re.sub(r"-> list:", "-> list[Any]:", src)
    src = re.sub(r"\bdict\[\]", "dict[str, Any]", src)
    src = re.sub(r"\blist\[\]", "list[Any]", src)

    # remove stale unused ignores on imports (strict may not need them)
    src = re.sub(
        r"  # type: ignore\[import-untyped\]\n",
        "\n",
        src,
    )

    if "dict[str, Any]" in src or ": dict[str, Any]" in src:
        src = ensure_import(src, "Any")
    if "list[Any]" in src:
        src = ensure_import(src, "Any")

    if src != orig:
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed = 0
    for p in sorted((ROOT / "butler/core").glob("*_ops.py")):
        if fix_file(p):
            changed += 1
            print("auto", p.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
