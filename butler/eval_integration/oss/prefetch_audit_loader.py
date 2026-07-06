"""Load memory-prefetch faithfulness cases from session transcripts (MOD-8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.env_parse import int_env


def _sessions_root() -> Path:
    return Path(get_butler_home()) / "sessions"


def _iter_transcript_files(limit: int) -> list[Path]:
    root = _sessions_root()
    if not root.is_dir():
        return []
    files = sorted(root.glob("*/transcript.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[: max(1, limit)]


def _context_from_inject(payload: dict[str, Any]) -> str:
    terms = payload.get("terms")
    if isinstance(terms, list) and terms:
        return "\n".join(f"- {t}" for t in terms if str(t).strip())
    chars = int(payload.get("chars") or 0)
    if chars > 0:
        return f"[memory_prefetch injected {chars} chars]"
    return ""


def load_prefetch_audit_cases(*, limit_sessions: int | None = None) -> list[dict[str, Any]]:
    """Build RAGAS-style cases from recent ``knowledge_inject`` transcript rows."""
    cap = limit_sessions if limit_sessions is not None else int_env("BUTLER_EVAL_RAGAS_PREFETCH_SESSIONS", 40, min=1)
    cases: list[dict[str, Any]] = []
    for path in _iter_transcript_files(cap):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        last_user = ""
        pending_inject: dict[str, Any] | None = None
        session_id = path.parent.name
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            etype = str(row.get("type") or "")
            if etype == "user":
                last_user = str(row.get("content_preview") or "").strip()
                pending_inject = None
            elif etype == "knowledge_inject" and str(row.get("source") or "") == "memory_prefetch":
                if int(row.get("chars") or 0) > 0:
                    pending_inject = row
            elif etype == "assistant" and pending_inject is not None:
                answer = str(row.get("content_preview") or "").strip()
                ctx = _context_from_inject(pending_inject)
                if last_user and answer and ctx:
                    cases.append(
                        {
                            "id": f"audit_{session_id}_{len(cases)}",
                            "question": last_user,
                            "context": ctx,
                            "answer": answer,
                            "source": "transcript_audit",
                        }
                    )
                pending_inject = None
    return cases
