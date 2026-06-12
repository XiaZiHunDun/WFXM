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


def apply_selected_experience_lifecycle(
    *,
    experience_id: str,
    success: bool,
    renew_days: float = 30.0,
    demote_days: float = 14.0,
) -> dict[str, Any]:
    """Renew or demote the experience that guided this delegate run."""
    if not experience_id or not experience_id.strip():
        return {"action": "none"}
    import os

    from butler.config import get_butler_home
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary

    path = os.path.join(get_butler_home(), "coding_experiences.json")
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(path, theorem_lib=tlib)
    exp = xlib.get(experience_id)
    if exp is None:
        return {"action": "missing", "experience_id": experience_id}
    if success:
        ok = xlib.renew(experience_id, extend_days=renew_days)
        action = "renewed" if ok else "renew_failed"
    else:
        ok = xlib.demote(experience_id, shrink_days=demote_days)
        action = "demoted" if ok else "demote_failed"
    if ok:
        xlib.save_to_file(path)
    return {"action": action, "experience_id": experience_id, "success": success}


__all__ = [
    "apply_selected_experience_lifecycle",
    "record_experience_selection",
    "selections_path",
    "summarize_experience_selections",
]
