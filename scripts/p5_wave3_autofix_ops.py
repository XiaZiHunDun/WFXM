#!/usr/bin/env python3
"""P5 wave3: generic mypy strict autofix for *_ops.py."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ensure_import(src: str, name: str) -> str:
    if name not in src:
        return src
    if re.search(rf"from typing import[^\n]*\b{name}\b", src):
        return src
    if "from typing import" in src:
        return re.sub(
            r"(from typing import [^\n]+)",
            lambda m: m.group(1) + (f", {name}" if name not in m.group(1) else ""),
            src,
            count=1,
        )
    return f"from typing import {name}\n" + src


def generic_fix(src: str) -> str:
    # yaml
    if "import yaml" in src:
        src = re.sub(
            r"import yaml(?!  # type: ignore)",
            "import yaml  # type: ignore[import-untyped]",
            src,
        )
    # remove unused import-untyped ignores (strict may not need)
    src = re.sub(r"  # type: ignore\[import-untyped\](?=\n)", "", src)

    src = re.sub(r": dict\)(?!])", ": dict[str, Any])", src)
    src = re.sub(r": dict \|", ": dict[str, Any] |", src)
    src = re.sub(r": dict,", ": dict[str, Any],", src)
    src = re.sub(r"-> dict:", "-> dict[str, Any]:", src)
    src = re.sub(r"-> dict\)(?!])", "-> dict[str, Any])", src)
    src = re.sub(r": list\)(?!])", ": list[Any])", src)
    src = re.sub(r"-> list:", "-> list[Any]:", src)
    src = re.sub(r"-> list\)(?!])", "-> list[Any])", src)
    src = re.sub(r"list\[dict\]", "list[dict[str, Any]]", src)
    src = re.sub(r"\bdict\[\]", "dict[str, Any]", src)
    src = re.sub(r"\blist\[\]", "list[Any]", src)

    if "dict[str, Any]" in src or "list[Any]" in src:
        src = ensure_import(src, "Any")
    if "cast(" in src:
        src = ensure_import(src, "cast")
    if "Callable" in src and "from collections.abc import Callable" not in src:
        src = ensure_import(src, "Callable")

    # env_truthy
    src = re.sub(r"return env_truthy\(", "return bool(env_truthy(", src)

    # get_butler_home
    if "get_butler_home()" in src:
        src = ensure_import(src, "cast")
        src = re.sub(r"return get_butler_home\(\)", "return cast(Path, get_butler_home())", src)

    return src


def fix_path(path: Path) -> bool:
    orig = path.read_text(encoding="utf-8")
    new = generic_fix(orig)
    if new != orig:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> int:
    targets: list[Path] = []
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            targets.append(ROOT / arg)
    else:
        strict = {
            ln.strip()
            for ln in (ROOT / "scripts/p5_ops_strict_modules.txt").read_text().splitlines()
            if ln.strip()
        }
        for p in sorted((ROOT / "butler").rglob("*_ops.py")):
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if rel not in strict:
                targets.append(p)

    changed = 0
    for p in targets:
        if fix_path(p):
            changed += 1
            print("generic", p.relative_to(ROOT))
    print(f"generic-fixed {changed}/{len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
