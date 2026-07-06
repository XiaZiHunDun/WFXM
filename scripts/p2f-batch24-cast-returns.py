#!/usr/bin/env python3
"""Apply cast() wrappers for common no-any-return patterns in butler/ops."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mypy_errors(path: Path) -> list[str]:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", str(path), "--follow-imports=skip"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return [ln for ln in (r.stdout + r.stderr).splitlines() if ": error:" in ln]


def ensure_typing(path: Path, src: str, names: set[str]) -> str:
    need = {n for n in names if n in src or f"{n}(" in src}
    if not need:
        return src
    if "from typing import" in src:
        m = re.search(r"from typing import ([^\n]+)", src)
        if m:
            existing = {x.strip() for x in m.group(1).split(",")}
            add = sorted(need - existing)
            if add:
                src = src.replace(m.group(0), m.group(0) + ", " + ", ".join(add), 1)
    else:
        src = f"from typing import {', '.join(sorted(need))}\n" + src
    if "from collections.abc import Callable" not in src and "Callable" in need:
        src = "from collections.abc import Callable\n" + src
    return src


def fix_no_any_return(path: Path, src: str, errors: list[str]) -> str:
    for err in errors:
        if "no-any-return" not in err:
            continue
        m = re.search(r":(\d+):", err)
        if not m:
            continue
        line_no = int(m.group(1))
        lines = src.splitlines()
        if line_no < 1 or line_no > len(lines):
            continue
        line = lines[line_no - 1]
        if "cast(" in line or "return " not in line:
            continue
        ret_m = re.search(r"return (.+)$", line.strip())
        if not ret_m:
            continue
        expr = ret_m.group(1)
        if "->" in err or "dict[str, Any]" in err:
            cast_type = "dict[str, Any]"
        elif "list[str]" in err:
            cast_type = "list[str]"
        elif "list[Any]" in err:
            cast_type = "list[Any]"
        elif "Path" in err:
            cast_type = "Path"
        elif "bool" in err:
            cast_type = "bool"
        elif "float" in err:
            cast_type = "float"
        elif "int" in err:
            cast_type = "int"
        elif "str" in err:
            cast_type = "str"
        elif "tuple[bool, str]" in err:
            cast_type = "tuple[bool, str]"
        elif "VariantResult" in err:
            cast_type = "VariantResult"
        elif "Literal" in err:
            cast_type = "ProfileName" if "ProfileName" in src else "str"
        else:
            continue
        indent = line[: len(line) - len(line.lstrip())]
        lines[line_no - 1] = f"{indent}return cast({cast_type}, {expr})"
        src = "\n".join(lines) + ("\n" if src.endswith("\n") else "")
    return src


def main() -> int:
    fixed = 0
    for p in sorted((ROOT / "butler/ops").glob("*.py")):
        if p.name.endswith("_ops.py"):
            continue
        errs = mypy_errors(p)
        if not errs:
            continue
        src = p.read_text(encoding="utf-8")
        new = fix_no_any_return(p, src, errs)
        if new != src:
            new = ensure_typing(p, new, {"cast", "Any"})
            p.write_text(new, encoding="utf-8")
            fixed += 1
    print(f"cast-wrapped returns in {fixed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
