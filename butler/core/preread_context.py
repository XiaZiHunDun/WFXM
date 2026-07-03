"""PreRead: inject path history before read_file (claude-mem subset)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.memory_settings import resolve_memory_config


def preread_enabled() -> bool:
    return resolve_memory_config().preread_enabled


def build_preread_block(workspace: Path | None, file_path: str) -> str:
    if not preread_enabled() or workspace is None:
        return ""
    path = str(file_path or "").strip()
    if not path:
        return ""
    lines: list[str] = []
    from butler.core.preread_context_ops import build_preread_observation_lines_safe

    lines = build_preread_observation_lines_safe(workspace, path, limit=3)
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
