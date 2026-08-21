#!/usr/bin/env python3
"""Optional: add PreToolUse hook to .claude/settings.json (idempotent)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKER_CMD = "pre_tool_use_hook.py"


def main() -> int:
    repo = Path(__file__).resolve().parent.parent.parent
    target = repo / ".claude" / "settings.json"
    if not target.is_file():
        print(f"ERROR: missing {target}", file=sys.stderr)
        return 1

    data = json.loads(target.read_text(encoding="utf-8"))
    hooks = data.setdefault("hooks", {})
    pretool = hooks.get("PreToolUse")
    if isinstance(pretool, list):
        for entry in pretool:
            for h in entry.get("hooks", []) or []:
                cmd = h.get("command", "")
                if MARKER_CMD in cmd:
                    print("SKIP: PreToolUse already configured")
                    return 0

    cmd = "python3 scripts/ai_guard/pre_tool_use_hook.py"
    new_entry = {
        "matcher": "",
        "hooks": [{"type": "command", "command": str(cmd)}],
    }
    hooks["PreToolUse"] = [new_entry]
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("OK: added PreToolUse to .claude/settings.json")
    print(f"     command: {cmd}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
