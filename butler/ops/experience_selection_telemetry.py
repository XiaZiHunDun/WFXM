"""Log coding experience retrieval hits during dev delegate (phase C telemetry)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def selections_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "experience_selections.jsonl"


def record_experience_selection(
    *,
    session_key: str = "",
    task_preview: str = "",
    experience_id: str = "",
    experience_mode: str = "",
    keywords: list[str] | None = None,
    role: str = "dev",
) -> None:
    if not experience_id:
        return
    path = selections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": time.time(),
        "session_key": session_key,
        "role": role,
        "task_preview": (task_preview or "")[:300],
        "experience_id": experience_id,
        "experience_mode": experience_mode,
        "keywords": (keywords or [])[:24],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize_experience_selections(*, limit: int = 200) -> dict[str, Any]:
    path = selections_path()
    if not path.is_file():
        return {"total": 0, "by_experience": {}, "path": str(path)}
    from collections import Counter

    by_exp: Counter[str] = Counter()
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += 1
        eid = str(row.get("experience_id") or "")
        if eid:
            by_exp[eid] += 1
    return {
        "total": total,
        "by_experience": dict(by_exp.most_common(12)),
        "path": str(path),
    }


__all__ = [
    "record_experience_selection",
    "selections_path",
    "summarize_experience_selections",
]
