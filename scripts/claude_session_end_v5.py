#!/usr/bin/env python3
"""Claude Code Stop hook — v5 state.md soft reminder (default) or legacy strict shift gate.

Usage (see .claude/settings.json Stop hook):
  BLACKBOARD_ROOT=/path/to/.blackboard python3 scripts/claude_session_end_v5.py

Default: validate state.md (_last_synced + four sections), WARN on stderr, exit 0.
Legacy: BLACKBOARD_STRICT=1 delegates to butler.blackboard.integrations.claude_session_end.

SSOT: docs/plans/decisions/v5-engineering-handoff-2026-08.md
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_STATE_SECTIONS = ("## 主线", "## 下一步", "## 不要做", "## 上一班")
_LAST_SYNCED_RE = re.compile(r"^_last_synced:\s*(.+?)_\s*$", re.MULTILINE)


def _blackboard_root() -> Path:
    env = os.environ.get("BLACKBOARD_ROOT")
    return Path(env) if env else Path.cwd() / ".blackboard"


def check_state_snapshot(*, root: Path | None = None, max_lines: int = 45) -> str | None:
    """Return warning text if state.md incomplete; None if OK."""
    state_path = (root or _blackboard_root()) / "state.md"
    if not state_path.is_file():
        return (
            "[blackboard] ⚠ 缺 .blackboard/state.md。"
            "会话结束前请写短快照（见 docs/plans/decisions/v5-engineering-handoff-2026-08.md）。"
        )
    text = state_path.read_text(encoding="utf-8")
    line_count = len(text.splitlines())
    if line_count > max_lines:
        return (
            f"[blackboard] ⚠ state.md 超过 {max_lines} 行（当前 {line_count}）；"
            "建议压到约 40 行内。"
        )
    synced = _LAST_SYNCED_RE.search(text)
    synced_val = synced.group(1).strip() if synced else ""
    if not synced_val or synced_val in {"(none)", "(pending)", "test"}:
        return "[blackboard] ⚠ state.md 缺有效 _last_synced；请更新后再结束会话。"
    for heading in _STATE_SECTIONS:
        if heading not in text:
            return (
                f"[blackboard] ⚠ state.md 缺 {heading} 段；"
                "见 docs/plans/decisions/v5-engineering-handoff-2026-08.md §2。"
            )
    return None


def main() -> int:
    if os.environ.get("BLACKBOARD_STRICT", "0") == "1":
        env = os.environ.copy()
        env["BLACKBOARD_STRICT"] = "1"
        proc = subprocess.run(
            [sys.executable, "-m", "butler.blackboard.integrations.claude_session_end"],
            env=env,
        )
        return proc.returncode

    max_lines_raw = os.environ.get("BLACKBOARD_STATE_MAX_LINES", "45")
    try:
        max_lines = max(20, int(max_lines_raw))
    except ValueError:
        max_lines = 45

    msg = check_state_snapshot(max_lines=max_lines)
    if msg:
        print(msg, file=sys.stderr)
    else:
        print("[blackboard] ✓ state.md 快照就绪", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
