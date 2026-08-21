#!/usr/bin/env python3
"""Repair stdin blocking in ai_guard hooks (TTY + CLI mode)."""

from __future__ import annotations

import sys
from pathlib import Path

STDIN_FIX = '''    if sys.stdin.isatty():
        return {}
    try:'''

STDIN_OLD = '''    try:
        raw = sys.stdin.read()'''


def patch_stdin_read(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if "if sys.stdin.isatty():" in text:
        return False
    if STDIN_OLD not in text:
        print(f"WARN: stdin anchor not found in {path.name}", file=sys.stderr)
        return False
    path.write_text(text.replace(STDIN_OLD, STDIN_FIX + "\n        raw = sys.stdin.read()"), encoding="utf-8")
    print(f"OK: patched stdin guard in {path.name}")
    return True


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent
    changed = False
    for name in ("post_tool_use_hook.py", "pre_tool_use_hook.py"):
        if patch_stdin_read(repo / "scripts" / "ai_guard" / name):
            changed = True
    if not changed:
        print("SKIP: stdin guard already present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
