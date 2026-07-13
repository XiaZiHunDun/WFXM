"""state.md 元数据读写 + log.md append-only 流。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from butler.blackboard import paths as bb_paths


@dataclass
class StateMeta:
    last_synced: str
    last_shift: str


_META_RE = re.compile(r"^_(last_synced|last_shift):\s*(.+?)_\s*$", re.MULTILINE)


def read_state_meta() -> StateMeta:
    """从 state.md 顶部解析 _last_synced / _last_shift。"""
    text = bb_paths.STATE_PATH.read_text(encoding="utf-8")
    matches = dict(_META_RE.findall(text))
    return StateMeta(
        last_synced=matches.get("last_synced", ""),
        last_shift=matches.get("last_shift", ""),
    )


def update_state_meta(*, last_synced: str | None = None, last_shift: str | None = None) -> None:
    """替换 state.md 中匹配的 _last_xxx_ 行；不存在则追加。"""
    state_path = bb_paths.STATE_PATH
    text = state_path.read_text(encoding="utf-8")
    if last_synced is not None:
        new_line = f"_last_synced: {last_synced}_"
        text, n = re.subn(r"^_last_synced:.*$", new_line, text, count=1, flags=re.MULTILINE)
        if n == 0:
            text = new_line + "\n" + text
    if last_shift is not None:
        new_line = f"_last_shift: {last_shift}_"
        text, n = re.subn(r"^_last_shift:.*$", new_line, text, count=1, flags=re.MULTILINE)
        if n == 0:
            text = new_line + "\n" + text
    state_path.write_text(text, encoding="utf-8")


def append_log_entry(shift_id: str, agent: str, summary: str) -> None:
    """append 一段摘要到 log.md（保留所有历史条目）。"""
    block = f"\n## {shift_id} · {agent}\n\n{summary.strip()}\n"
    with bb_paths.LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(block)