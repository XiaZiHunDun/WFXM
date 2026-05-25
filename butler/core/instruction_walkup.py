"""Inject nearby AGENTS.md / project rules after read_file (OpenCode instruction.ts subset)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

_CLAIMS: dict[str, set[str]] = {}
_PENDING: dict[str, list[str]] = {}
_LOCK = threading.RLock()

_INSTRUCTION_FILENAMES = ("AGENTS.md", "CLAUDE.md", "RULES.md")
_MAX_BLOCK_CHARS = 4000
_MAX_FILES_PER_TURN = 3


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "").strip() or default))
    except ValueError:
        return default


def walkup_enabled() -> bool:
    return os.getenv("BUTLER_INSTRUCTION_WALKUP", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _session_key(session_key: str = "") -> str:
    if session_key.strip():
        return session_key.strip()
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "default")
    except Exception:
        return "default"


def _find_instruction_file(start: Path, *, stop_at: Path | None = None) -> Path | None:
    current = start.resolve()
    stop = stop_at.resolve() if stop_at else None
    for _ in range(32):
        for name in _INSTRUCTION_FILENAMES:
            candidate = current / name
            if candidate.is_file():
                return candidate
        if stop is not None and current == stop:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def record_read_path(
    file_path: Path,
    *,
    session_key: str = "",
    workspace_root: Path | None = None,
) -> None:
    """Queue instruction snippet for the next LLM call after a successful read_file."""
    if not walkup_enabled():
        return
    key = _session_key(session_key)
    resolved = file_path.resolve()
    inst = _find_instruction_file(resolved.parent, stop_at=workspace_root)
    if inst is None:
        return
    claim = str(inst)
    with _LOCK:
        seen = _CLAIMS.setdefault(key, set())
        if claim in seen:
            return
        if len(_PENDING.get(key, [])) >= _int_env(
            "BUTLER_INSTRUCTION_WALKUP_MAX_FILES",
            _MAX_FILES_PER_TURN,
        ):
            return
        try:
            body = inst.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return
        cap = _int_env("BUTLER_INSTRUCTION_WALKUP_MAX_CHARS", _MAX_BLOCK_CHARS)
        if len(body) > cap:
            body = body[: cap - 20] + "\n…(truncated)"
        block = (
            f"## 邻近项目规则（read_file 触发，仅本轮参考）\n"
            f"来源: `{inst}`\n\n{body}"
        )
        _PENDING.setdefault(key, []).append(block)
        seen.add(claim)


def drain_pending_instructions(*, session_key: str = "") -> str:
    """Return and clear queued instruction blocks for this session."""
    key = _session_key(session_key)
    with _LOCK:
        blocks = _PENDING.pop(key, [])
    if not blocks:
        return ""
    return "\n\n".join(blocks)


def reset_instruction_claims(*, session_key: str = "") -> None:
    key = _session_key(session_key)
    with _LOCK:
        _CLAIMS.pop(key, None)
        _PENDING.pop(key, None)


def build_instruction_pre_llm_transform(*, session_key: str = ""):
    """Prepend drained instruction blocks to the latest user message."""

    def _transform(messages: list[dict]) -> list[dict]:
        block = drain_pending_instructions(session_key=session_key)
        if not block.strip():
            return messages
        out = [dict(m) if isinstance(m, dict) else m for m in messages]
        for idx in range(len(out) - 1, -1, -1):
            msg = out[idx]
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = str(msg.get("content") or "")
                if block not in content:
                    msg["content"] = f"{block}\n\n{content}".strip()
                break
        return out

    return _transform
