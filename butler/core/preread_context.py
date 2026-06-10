"""PreRead: inject path history before read_file (claude-mem subset)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import logging

from butler.memory_settings import resolve_memory_config


logger = logging.getLogger(__name__)

def preread_enabled() -> bool:
    return resolve_memory_config().preread_enabled


def build_preread_block(workspace: Path | None, file_path: str) -> str:
    if not preread_enabled() or workspace is None:
        return ""
    path = str(file_path or "").strip()
    if not path:
        return ""
    lines: list[str] = []
    try:
        from butler.memory.observer_queue import list_observations_for_path

        obs = list_observations_for_path(workspace, path, limit=3)
        for row in obs:
            preview = str(row.get("preview") or "").strip()
            tool = str(row.get("tool") or "")
            if preview:
                lines.append(f"- [{tool}] {preview[:160]}")
    except Exception as exc:
        logger.debug("build preread block skipped: %s", exc)
    if not lines:
        return ""
    return "## PreRead 路径历史\n" + "\n".join(lines[:5])


def inject_preread_into_args(args: dict[str, Any], block: str) -> dict[str, Any]:
    if not block.strip():
        return args
    out = dict(args)
    hint = str(out.get("_butler_preread") or "").strip()
    out["_butler_preread"] = f"{hint}\n{block}".strip() if hint else block.strip()
    return out


__all__ = ["build_preread_block", "inject_preread_into_args", "preread_enabled"]
