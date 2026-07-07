#!/usr/bin/env python3
"""Fix no-any-return in *_ops.py by wrapping return lines with cast()."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def mypy_errors(path: Path) -> list[tuple[int, str]]:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", str(path), "--follow-imports=skip", "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    out: list[tuple[int, str]] = []
    for ln in (r.stdout + r.stderr).splitlines():
        m = re.search(r":(\d+): error: (.+)$", ln)
        if m:
            out.append((int(m.group(1)), m.group(2)))
    return out


def parse_return_type(err: str) -> str | None:
    m = re.search(r'declared to return "([^"]+)"', err)
    return m.group(1) if m else None


def ensure_cast_import(src: str) -> str:
    if re.search(r"from typing import[^\n]*\bcast\b", src):
        return src
    if "from typing import" in src:
        return re.sub(r"(from typing import [^\n]+)", r"\1, cast", src, count=1)
    # After __future__ block
    m = re.search(r'(from __future__ import annotations\n\n)', src)
    if m:
        return src.replace(m.group(1), m.group(1) + "from typing import cast\n\n", 1)
    return "from typing import cast\n" + src


def fix_line(line: str, ret_type: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("return "):
        return None
    if stripped.endswith("("):
        return None  # multiline call — fix manually
    expr = stripped[7:]
    if expr.startswith("cast("):
        return None
    if " if isinstance(" in expr:
        return None
    indent = line[: len(line) - len(line.lstrip())]
    return f"{indent}return cast({ret_type}, {expr})"


def fix_file(path: Path) -> bool:
    errors = mypy_errors(path)
    no_any = [(ln, err) for ln, err in errors if "no-any-return" in err]
    if not no_any:
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    changed = False
    for lineno, err in no_any:
        ret_type = parse_return_type(err)
        if not ret_type:
            continue
        idx = lineno - 1
        if idx < 0 or idx >= len(lines):
            continue
        new_line = fix_line(lines[idx], ret_type)
        if new_line and new_line != lines[idx]:
            lines[idx] = new_line
            changed = True
    if not changed:
        return False
    src = "\n".join(lines) + ("\n" if path.read_text(encoding="utf-8").endswith("\n") else "")
    src = ensure_cast_import(src)
    path.write_text(src, encoding="utf-8")
    return True


def main() -> int:
    targets = sorted((ROOT / "butler").rglob("*_ops.py"))
    fixed = 0
    for p in targets:
        if fix_file(p):
            fixed += 1
            print("fixed", p.relative_to(ROOT))
    print(f"fixed {fixed} files")
    remaining = sum(1 for p in targets if mypy_errors(p))
    print(f"remaining with errors: {remaining}/{len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
