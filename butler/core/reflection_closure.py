"""Reflection closure: persist reflect episodes and inject recent hints on next turn."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_REFLECT_HINT_MAX = 280
_DEFAULT_HINT_LIMIT = 2


def reflection_closure_enabled() -> bool:
    return bool(env_truthy("BUTLER_REFLECTION_CLOSURE", default=True))


def reflection_closure_inject_enabled() -> bool:
    if not reflection_closure_enabled():
        return False
    return bool(env_truthy("BUTLER_REFLECTION_CLOSURE_INJECT", default=True))


def _experience_path() -> Path:
    from butler.core.reflection_closure_ops import experience_path_safe

    return cast(Path, experience_path_safe())


def _should_persist() -> bool:
    from butler.core.reflection_closure_ops import should_persist_reflect

    return bool(should_persist_reflect())


def persist_reflect_episode(
    *,
    trigger: str,
    cause: str = "",
    strategy: str = "",
    detail: str = "",
    session_key: str = "",
    source: str = "reflect",
    tool_name: str = "",
    failure_count: int = 0,
) -> None:
    """Append a reflect episode to reflexion.jsonl (closure write path)."""
    if not _should_persist():
        return
    path = _experience_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": "reflect",
        "trigger": str(trigger or "")[:48],
        "cause": str(cause or "")[:400],
        "strategy": str(strategy or "")[:120],
        "detail": str(detail or "")[:200],
        "session_key": str(session_key or "")[:120],
        "source": str(source or "")[:48],
    }
    if tool_name:
        row["tool"] = str(tool_name)[:64]
    if failure_count:
        row["failure_count"] = int(failure_count)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("reflection closure write skipped: %s", exc)


def load_recent_reflect_hints(
    *,
    limit: int | None = None,
    session_key: str = "",
) -> list[str]:
    """Read recent reflect episodes as short injection lines."""
    if not reflection_closure_inject_enabled():
        return []
    cap = limit if limit is not None else _DEFAULT_HINT_LIMIT
    path = _experience_path()
    if not path.is_file():
        return []
    sk = str(session_key or "").strip()
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in reversed(lines[-80:]):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if sk and str(row.get("session_key") or "") not in ("", sk):
            continue
        rows.append(row)
        if len(rows) >= cap:
            break
    hints: list[str] = []
    for row in rows:
        trigger = str(row.get("trigger") or row.get("kind") or "reflect")
        cause = str(row.get("cause") or row.get("error") or "").strip()
        strategy = str(row.get("strategy") or "").strip()
        tool = str(row.get("tool") or "").strip()
        parts = [f"[{trigger}]"]
        if tool:
            parts.append(f"tool={tool}")
        if cause:
            parts.append(cause[:160])
        if strategy:
            parts.append(f"→ {strategy[:80]}")
        hint = " ".join(parts).strip()
        if hint:
            hints.append(hint[:_REFLECT_HINT_MAX])
    return hints


def build_reflect_closure_banner(
    *,
    session_key: str = "",
    limit: int | None = None,
) -> str:
    hints = load_recent_reflect_hints(limit=limit, session_key=session_key)
    if not hints:
        return ""
    body = "\n".join(f"- {h}" for h in hints)
    return f"## Reflection（近期）\n{body}\n请避免重复已失败策略。"


def maybe_persist_reflect_closure(
    *,
    trigger: str,
    cause: str = "",
    strategy: str = "",
    detail: str = "",
    session_key: str = "",
    source: str = "reflect",
) -> None:
    if not reflection_closure_enabled():
        return
    persist_reflect_episode(
        trigger=trigger,
        cause=cause,
        strategy=strategy,
        detail=detail,
        session_key=session_key,
        source=source,
    )


__all__ = [
    "build_reflect_closure_banner",
    "load_recent_reflect_hints",
    "maybe_persist_reflect_closure",
    "persist_reflect_episode",
    "reflection_closure_enabled",
    "reflection_closure_inject_enabled",
]
