"""Compaction audit best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def checkpoint_preview_len_safe(session_key: str) -> int | None:
    def _run() -> int | None:
        from butler.core.compaction_checkpoint import load_checkpoint

        ckpt = load_checkpoint(session_key)
        if isinstance(ckpt, dict):
            preview = str(ckpt.get("compression_summary_preview") or "")
            return len(preview) if preview else None
        return None

    return safe_best_effort(_run, label="compaction_audit.checkpoint", default=None)


def discover_sessions_imports_ok() -> bool:
    def _run() -> bool:
        from butler.config import get_butler_home  # noqa: F401
        from butler.core.session_transcript import transcript_path  # noqa: F401

        return True

    return safe_best_effort(_run, label="compaction_audit.imports", default=False) is True
