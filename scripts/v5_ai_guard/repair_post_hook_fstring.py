#!/usr/bin/env python3
"""Repair broken f-string in post_tool_use_hook.py after step-02 bug."""

from __future__ import annotations

import sys
from pathlib import Path

BROKEN = '''    print(
        f"
[AI Guard] 请手动：cd butler-v5 && pnpm exec vitest run {' '.join(test_files)}",
        file=sys.stderr,
    )'''

FIXED = '''    print(
        f"\\n[AI Guard] 请手动：cd butler-v5 && pnpm exec vitest run {' '.join(test_files)}",
        file=sys.stderr,
    )'''


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent
    target = repo / "scripts" / "ai_guard" / "post_tool_use_hook.py"
    text = target.read_text(encoding="utf-8")
    if BROKEN not in text:
        print("SKIP: broken f-string not found (already fixed or not patched)")
        return 0
    target.write_text(text.replace(BROKEN, FIXED), encoding="utf-8")
    print("OK: repaired post_tool_use_hook.py f-string")
    return 0


if __name__ == "__main__":
    sys.exit(main())
