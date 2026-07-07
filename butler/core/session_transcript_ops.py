"""Best-effort transcript index / FTS / graph side effects (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def update_index_after_append_safe(
    path: Path,
    *,
    line_byte_offset: int,
    line_len: int,
) -> None:
    def _run() -> None:
        from butler.core.transcript_index import update_index_after_append

        update_index_after_append(
            path,
            line_byte_offset=line_byte_offset,
            line_len=line_len,
        )

    safe_best_effort(_run, label="session_transcript.index_after_append", default=None)


def index_transcript_line_safe(path: Path, entry: dict[str, Any]) -> None:
    def _run() -> None:
        from butler.core.transcript_fts import index_transcript_line

        line_no = 0
        with path.open(encoding="utf-8") as fh:
            for line_no, _ in enumerate(fh, start=1):
                pass
        index_transcript_line(path.parent.name, line_no=line_no, entry=entry)

    safe_best_effort(_run, label="session_transcript.fts_after_append", default=None)


def sync_plan_step_to_graph_safe(
    session_key: str,
    *,
    title: str = "",
    step_kind: str = "",
    assumption: str = "",
    evidence: str = "",
    detail: str = "",
) -> None:
    def _run() -> None:
        from butler.core.reasoning_trace import maybe_sync_plan_step_to_graph

        maybe_sync_plan_step_to_graph(
            session_key,
            title=title,
            step_kind=step_kind,
            assumption=assumption,
            evidence=evidence,
            detail=detail,
        )

    safe_best_effort(_run, label="session_transcript.plan_step_graph", default=None)


def load_tail_rows_safe(path: Path, *, max_lines: int) -> list[dict[str, Any]] | None:
    def _run() -> list[dict[str, Any]]:
        from butler.core.transcript_index import load_tail_rows

        rows = load_tail_rows(path, max_lines=max(1, int(max_lines)))
        return rows if isinstance(rows, list) else []

    result = safe_best_effort(
        _run,
        label="session_transcript.load_tail_index",
        default=None,
    )
    return result if isinstance(result, list) else None


def load_tail_full_read_safe(path: Path, *, max_lines: int) -> list[dict[str, Any]] | None:
    def _run() -> list[dict[str, Any]]:
        from butler.core.transcript_index import _load_tail_full_read

        rows = _load_tail_full_read(path, max_lines=max(1, int(max_lines)))
        return rows if isinstance(rows, list) else []

    result = safe_best_effort(
        _run,
        label="session_transcript.load_tail_full_read",
        default=None,
    )
    return result if isinstance(result, list) else None
