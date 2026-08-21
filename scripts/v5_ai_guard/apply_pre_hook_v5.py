#!/usr/bin/env python3
"""Idempotent patch: add Butler v5 protected files to pre_tool_use_hook.py."""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "# === Butler v5 protected (auto) ==="

V5_FILES = [
    "butler-v5/packages/persistence/src/migrations/0001_initial.sql",
    "butler-v5/apps/api/src/wechat-inbound-butler.ts",
    "butler-v5/packages/runtime/src/agent-kernel.ts",
    "butler-v5/packages/runtime/src/run-engine.ts",
    "butler-v5/packages/runtime/src/capability-boundary.ts",
    "butler-v5/apps/api/src/tool-boundary.ts",
    "butler-v5/apps/api/src/workspace-tools.ts",
]

V5_DIR_PATTERNS = [
    '(r"^butler-v5/packages/persistence/src/migrations/", "v5 生产 schema"),',
]


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent
    target = repo / "scripts" / "ai_guard" / "pre_tool_use_hook.py"
    if not target.is_file():
        print(f"ERROR: missing {target}", file=sys.stderr)
        return 1

    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print("SKIP: pre_tool_use_hook.py already has v5 protected block")
        return 0

    anchor = '    ".blackboard/README.md",\n}'
    if anchor not in text:
        print("ERROR: PROTECTED_FILES anchor not found", file=sys.stderr)
        return 1

    lines = ["    " + MARKER]
    for path in V5_FILES:
        lines.append(f'    "{path}",')
    insertion = "\n".join(lines) + "\n"
    text = text.replace(anchor, '    ".blackboard/README.md",\n' + insertion + "}")

    dir_anchor = '    (r"^\\.blackboard/", "黑板交接机制"),\n]'
    if dir_anchor not in text:
        print("ERROR: PROTECTED_DIR_PATTERNS anchor not found", file=sys.stderr)
        return 1

    dir_lines = ["    " + MARKER]
    dir_lines.extend(f"    {p}" for p in V5_DIR_PATTERNS)
    text = text.replace(
        dir_anchor,
        '    (r"^\\.blackboard/", "黑板交接机制"),\n' + "\n".join(dir_lines) + "\n]",
    )

    target.write_text(text, encoding="utf-8")
    print("OK: patched pre_tool_use_hook.py with v5 protected files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
