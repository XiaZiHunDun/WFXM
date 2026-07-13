"""从 shifts/ + tasks/ 派生 state.md 摘要。"""

from __future__ import annotations

from datetime import datetime

from butler.blackboard.shift_io import list_shift_cards
from butler.blackboard.task_io import list_claims, load_backlog


def render_snapshot(now: datetime | None = None) -> str:
    """生成完整 state.md 文本（不写盘）。"""
    now = now or datetime.now()
    last_synced = now.strftime("%Y-%m-%d %H:%M")

    cards = list_shift_cards()
    last_shift = cards[-1].shift_id if cards else "(none)"

    in_progress_lines: list[str] = []
    for claim in list_claims():
        if claim.status.value in ("claimed", "in_progress"):
            in_progress_lines.append(
                f"- [{claim.task_id}] ({claim.claimed_by}) status={claim.status.value}"
            )

    blocked_lines: list[str] = []
    try:
        bf = load_backlog()
        for t in bf.tasks:
            if t.status.value == "blocked":
                blocked_lines.append(f"- [{t.id}] {t.title}")
    except FileNotFoundError:
        pass

    recent_lines = [
        f"- {c.shift_id}: {c.intent[:60]}"
        for c in cards[-5:]
    ]

    sections = [
        "# WFXM BlackBoard State",
        "",
        f"_last_synced: {last_synced}_",
        f"_last_shift: {last_shift}_",
        "",
        "## 进行中",
        *(in_progress_lines or ["（暂无）"]),
        "",
        "## 待仲裁 / 阻塞",
        *(blocked_lines or ["（暂无）"]),
        "",
        "## 待认领",
        "- 详见 `tasks/backlog.yaml`",
        "",
        "## 最近 5 个班次",
        *(recent_lines or ["（暂无）"]),
        "",
    ]
    return "\n".join(sections)


def build_snapshot_markdown() -> str:
    """render_snapshot 的别名，方便 CLI 调用。"""
    return render_snapshot()