"""Incremental memory extraction from session transcript JSONL (Codex memories/ subset)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy, int_env


def transcript_memory_enabled() -> bool:
    return env_truthy("BUTLER_TRANSCRIPT_MEMORY", default=False)


def transcript_memory_max_lines() -> int:
    import os

    try:
        return max(20, int_env("BUTLER_TRANSCRIPT_MEMORY_MAX_LINES", 400))
    except ValueError:
        return 400


def _read_transcript_rows(path: Path, max_lines: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    rows: list[dict[str, Any]] = []
    for ln in tail:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def transcript_rows_to_messages(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Map transcript JSONL rows to chat messages for PostSessionProcessor."""
    out: list[dict[str, str]] = []
    for row in rows:
        entry_type = str(row.get("type") or "")
        if entry_type == "user":
            text = str(row.get("content_preview") or row.get("content") or "").strip()
            if text:
                out.append({"role": "user", "content": text})
        elif entry_type == "assistant":
            text = str(row.get("content_preview") or row.get("content") or "").strip()
            if text:
                out.append({"role": "assistant", "content": text})
    return out


def build_transcript_dialogue(session_key: str) -> list[dict[str, str]]:
    from butler.core.session_transcript import transcript_path

    path = transcript_path(session_key)
    rows = _read_transcript_rows(path, transcript_memory_max_lines())
    return transcript_rows_to_messages(rows)


async def extract_memory_from_transcript_async(
    session_key: str,
    *,
    project_name: str = "",
) -> dict[str, Any]:
    """Run PostSession memory channel on transcript-derived messages."""
    messages = build_transcript_dialogue(session_key)
    if len(messages) < 4:
        return {
            "ok": True,
            "skipped": True,
            "reason": "insufficient_transcript_messages",
            "message_count": len(messages),
        }

    from butler.session.post_session import PostSessionProcessor
    from butler.transport.auxiliary_client import auxiliary_llm_call_factory

    processor = PostSessionProcessor(llm_call=auxiliary_llm_call_factory("post_session"))

    butler_memory = None
    project_memory = None
    from butler.memory.transcript_memory_pipeline_ops import load_transcript_memory_facades_safe

    butler_memory, project_memory = load_transcript_memory_facades_safe(project_name)

    result = await processor.process(
        messages,
        butler_memory=butler_memory,
        project_memory=project_memory,
        skill_manager=None,
        project_name=project_name or "",
    )
    return {
        "ok": True,
        "memory_updates": int(result.get("memory_updates") or 0),
        "errors": list(result.get("errors") or []),
        "message_count": len(messages),
    }


def extract_memory_from_transcript(
    session_key: str,
    *,
    project_name: str = "",
) -> dict[str, Any]:
    """Sync entry for gateway commands and lifecycle hooks."""
    if not transcript_memory_enabled():
        return {"ok": False, "error": "transcript_memory_disabled"}
    try:
        return asyncio.run(
            extract_memory_from_transcript_async(session_key, project_name=project_name)
        )
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                extract_memory_from_transcript_async(session_key, project_name=project_name)
            )
        finally:
            loop.close()
