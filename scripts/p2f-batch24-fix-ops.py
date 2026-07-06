#!/usr/bin/env python3
"""P2-F Batch 24: minimal mypy fixes for butler/ops main modules."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ops_main_modules() -> list[Path]:
    out: list[Path] = []
    for p in sorted((ROOT / "butler/ops").glob("*.py")):
        if p.name.endswith("_ops.py"):
            continue
        out.append(p)
    return out


def ensure_import_cast(src: str) -> str:
    if "cast(" not in src:
        return src
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


def ensure_import_any(src: str) -> str:
    if re.search(r"\bdict\[str, Any\]", src) and "Any" not in src.split("from typing import", 1)[-1].split("\n", 1)[0] if "from typing import" in src else True:
        if "from typing import" in src:
            block = src.split("from typing import", 1)[1].split("\n", 1)[0]
            if "Any" not in block:
                src = re.sub(
                    r"(from typing import [^\n]+)",
                    lambda m: m.group(1) + ", Any",
                    src,
                    count=1,
                )
        elif "dict[str, Any]" in src or "Callable" in src:
            src = "from typing import Any\n" + src
    return src


def fix_file(path: Path) -> bool:
    src = path.read_text(encoding="utf-8")
    orig = src

    # yaml stubs
    src = re.sub(
        r"^import yaml$",
        "import yaml  # type: ignore[import-untyped]",
        src,
        flags=re.MULTILINE,
    )
    src = re.sub(
        r"^(\s+)import yaml$",
        r"\1import yaml  # type: ignore[import-untyped]",
        src,
        flags=re.MULTILINE,
    )

    # env_truthy bool returns
    src = re.sub(r"return env_truthy\(", "return bool(env_truthy(", src)

    # get_butler_home Path returns (single-line return)
    if "get_butler_home()" in src:
        src = ensure_import_cast(src)
        src = re.sub(
            r"return get_butler_home\(\)",
            "return cast(Path, get_butler_home())",
            src,
        )

    # bare dict in annotations
    src = re.sub(r": dict\)(?!])", ": dict[str, Any])", src)
    src = re.sub(r"-> dict:", "-> dict[str, Any]:", src)
    src = re.sub(r"-> dict\)(?!])", "-> dict[str, Any])", src)
    src = re.sub(r"\bdict\[\]", "dict[str, Any]", src)

    if src != orig:
        src = ensure_import_any(src)
        path.write_text(src, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed = 0
    for p in ops_main_modules():
        if fix_file(p):
            changed += 1
    print(f"Auto-fixed {changed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
