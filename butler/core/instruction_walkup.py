"""Inject nearby AGENTS.md / project rules after read_file (OpenCode instruction.ts subset)."""

from __future__ import annotations

import threading
from pathlib import Path

_CLAIMS: dict[str, set[str]] = {}
_PENDING: dict[str, list[str]] = {}
_LOCK = threading.RLock()

_INSTRUCTION_FILENAMES = ("AGENTS.md", "CLAUDE.md", "RULES.md")


def _walkup_settings():
    from butler.context_settings import resolve_context_config

    return resolve_context_config().instruction_walkup


def walkup_enabled() -> bool:
    return _walkup_settings().enabled


def _session_key(session_key: str = "") -> str:
    from butler.core.instruction_walkup_ops import session_key_safe

    return session_key_safe(session_key)


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
        if len(_PENDING.get(key, [])) >= _walkup_settings().max_files:
            return
        try:
            body = inst.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return
        cap = _walkup_settings().max_chars
        if len(body) > cap:
            body = body[: cap - 20] + "\n…(truncated)"
        block = (
            f"## 邻近项目规则（read_file 触发，仅本轮参考）\n"
            f"来源: `{inst}`\n\n{body}"
        )
        _PENDING.setdefault(key, []).append(block)
        seen.add(claim)
        from butler.core.instruction_walkup_ops import resolve_rules_block_safe

        rules_block = resolve_rules_block_safe(resolved, workspace_root=workspace_root)
        if rules_block.strip():
            rules_claim = f"rules:{rules_block[:80]}"
            if rules_claim not in seen:
                _PENDING.setdefault(key, []).append(rules_block)
                seen.add(rules_claim)


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
