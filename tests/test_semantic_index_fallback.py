"""R2-2: Surface recall_degraded flag + exc_info on semantic_index fallback.

Per audit R2-2 in docs/reviews/project-deep-audit-2026-06-r1to8.md:
- 3 except sites in semantic_index.py swallowed embedding/DB/provider errors
  silently with logger.warning. The user had no signal that recall quality
  collapsed to FTS-only.
- Fix: change logger.warning → logger.error(..., exc_info=True) at all 3 sites
  and surface a recall_degraded=True flag in the retrieval telemetry so /诊断
  can show "记忆检索降级" to the user/LLM.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from butler.execution_context import use_execution_context
from butler.memory.diagnostics import collect_memory_layer_stats
from butler.memory.retrieval_telemetry import (
    clear_last_retrieval,
    get_last_retrieval,
    record_last_retrieval,
)
from butler.memory.semantic_index import (
    _hybrid_experience_search_once,
    hybrid_experience_search,
    index_experience_row,
)
from butler.ops.rag_diagnostics import format_rag_diagnostic_lines


def _make_semantic_with_hybrid(side_effect) -> MagicMock:
    """Build a MagicMock semantic whose hybrid_search follows ``side_effect``."""
    sem = MagicMock()
    sem.hybrid_search.side_effect = side_effect
    return sem


def _fts_stub(hits: list[dict] | None = None) -> MagicMock:
    """Build a MagicMock fts_search that returns the given hits (default 1)."""
    fts = MagicMock()
    fts.return_value = list(hits or [{"id": 1, "content": "fts-hit", "score": 0.5}])
    return fts


# ---------------------------------------------------------------------------
# 1. Primary recall fallback (line 458-459) — semantic.hybrid_search raises
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_recall_degraded_true_on_primary_error():
    """Primary path: semantic.hybrid_search raises → recall_degraded=True."""
    session_key = "s-r2-2-primary"
    clear_last_retrieval(session_key)
    sem = _make_semantic_with_hybrid(side_effect=RuntimeError("embed OOM"))
    fts = _fts_stub([{"id": 1, "content": "fts", "score": 0.5}])

    orch = MagicMock()
    with use_execution_context(orch, session_key=session_key):
        out = hybrid_experience_search(
            sem, fts, "query", project="p", limit=3
        )

    # FTS still returns hits (audit: 记忆质量塌方但用户无感)
    assert out and out[0]["content"] == "fts"
    last = get_last_retrieval(session_key)
    assert last["mode"] == "fts-error-fallback"
    assert last["recall_degraded"] is True


# ---------------------------------------------------------------------------
# 2. Global recall fallback (line 473-474) — primary returns empty, global raises
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_recall_degraded_true_on_global_error():
    """Global path: primary returns [] then global raises → recall_degraded=True."""
    session_key = "s-r2-2-global"
    clear_last_retrieval(session_key)
    # First hybrid_search returns []; second (global) raises.
    sem = MagicMock()
    sem.hybrid_search.side_effect = [[], RuntimeError("provider 鉴权失效")]
    fts = _fts_stub(
        [
            {"id": 1, "content": "first-fts", "score": 0.5},
            {"id": 2, "content": "global-fts", "score": 0.3},
        ]
    )

    orch = MagicMock()
    with use_execution_context(orch, session_key=session_key):
        out = hybrid_experience_search(
            sem, fts, "query", project="p", limit=3
        )

    assert out
    last = get_last_retrieval(session_key)
    assert last["mode"] == "fts-fallback-global"
    assert last["recall_degraded"] is True


# ---------------------------------------------------------------------------
# 3. Success path — semantic.hybrid_search returns hits, no fallback
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_recall_degraded_false_on_success():
    """No fallback path: semantic returns hits → recall_degraded=False."""
    session_key = "s-r2-2-success"
    clear_last_retrieval(session_key)
    sem = MagicMock()
    sem.hybrid_search.return_value = [
        {"id": 1, "content": "vec-hit", "score": 0.9, "retrieval": "hybrid-vector"}
    ]
    fts = _fts_stub([{"id": 2, "content": "fts-hit", "score": 0.5}])

    orch = MagicMock()
    with use_execution_context(orch, session_key=session_key):
        out = hybrid_experience_search(
            sem, fts, "query", project="p", limit=3
        )

    assert out
    last = get_last_retrieval(session_key)
    assert last["mode"] == "hybrid"
    assert last["recall_degraded"] is False


# ---------------------------------------------------------------------------
# 4. UPSERT path (line 413-414) — write failure must log error+exc_info
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_upsert_logs_error_with_exc_info(caplog):
    """index_experience_row: upsert raises → logger.error with exc_info=True."""
    sem = MagicMock()
    sem.upsert.side_effect = RuntimeError("DB 锁")
    caplog.set_level(logging.DEBUG, logger="butler.memory.semantic_index")

    index_experience_row(
        sem,
        row_id=42,
        project="p",
        category="experience",
        content="重要的记忆",
    )

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "expected at least one ERROR log"
    rec = next(
        r
        for r in error_records
        if "Semantic index upsert failed" in r.getMessage()
    )
    assert rec.exc_info is not None, "exc_info must be set so the traceback is captured"
    assert rec.exc_info[1].args[0] == "DB 锁"


# ---------------------------------------------------------------------------
# 5. Primary fallback logs error+exc_info (NOT warning)
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_primary_fallback_logs_error_with_exc_info(caplog):
    """Primary fallback: logger.error with exc_info, NOT logger.warning."""
    sem = _make_semantic_with_hybrid(side_effect=RuntimeError("provider 鉴权失效"))
    fts = _fts_stub()
    caplog.set_level(logging.DEBUG, logger="butler.memory.semantic_index")

    _hybrid_experience_search_once(sem, fts, "q", project="p", limit=2)

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "expected at least one ERROR log on fallback"
    rec = next(r for r in error_records if "Hybrid search failed" in r.getMessage())
    assert rec.exc_info is not None

    # Critical audit contract: warning level is no longer used for this event.
    warning_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and "Hybrid search failed" in r.getMessage()
    ]
    assert not warning_records, "warning is too quiet for a hard failure; exc_info would be lost"


# ---------------------------------------------------------------------------
# 6. Global fallback logs error+exc_info (NOT warning)
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_global_fallback_logs_error_with_exc_info(caplog):
    """Global fallback: logger.error with exc_info, NOT logger.warning."""
    sem = MagicMock()
    sem.hybrid_search.side_effect = [[], RuntimeError("DB 锁")]
    fts = _fts_stub(
        [
            {"id": 1, "content": "first-fts", "score": 0.5},
            {"id": 2, "content": "global-fts", "score": 0.3},
        ]
    )
    caplog.set_level(logging.DEBUG, logger="butler.memory.semantic_index")

    _hybrid_experience_search_once(sem, fts, "q", project="p", limit=2)

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, "expected at least one ERROR log on global fallback"
    rec = next(
        r
        for r in error_records
        if "Hybrid global fallback failed" in r.getMessage()
    )
    assert rec.exc_info is not None

    warning_records = [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING
        and "Hybrid global fallback failed" in r.getMessage()
    ]
    assert not warning_records, "warning is too quiet for a hard failure"


# ---------------------------------------------------------------------------
# 7. /诊断 surface — collect_memory_layer_stats reads recall_degraded
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_collect_memory_layer_stats_surfaces_recall_degraded():
    """diagnostics.py must surface recall_degraded from retrieval telemetry."""
    session_key = "s-r2-2-stats"
    clear_last_retrieval(session_key)
    record_last_retrieval(
        session_key,
        {
            "mode": "fts-error-fallback",
            "fallbacks": 1,
            "candidates": 3,
            "query": "x",
            "recall_degraded": True,
        },
    )
    orch = MagicMock()
    orch.butler_memory = None
    orch._project_memory = None
    orch.project_manager.get_current.return_value = None

    stats = collect_memory_layer_stats(orch, session_key=session_key)

    assert stats["rag_last_recall_degraded"] is True


# ---------------------------------------------------------------------------
# 8. /诊断 display — format_rag_diagnostic_lines shows degraded status
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_format_rag_diagnostic_lines_shows_degraded():
    """When recall_degraded=True, /诊断 must include a visible degraded line."""
    lines = format_rag_diagnostic_lines(
        {
            "semantic_enabled": True,
            "vector_rows": 12,
            "rag_last_mode": "fts-error-fallback",
            "rag_last_fallbacks": 1,
            "rag_last_candidates": 3,
            "rag_last_recall_degraded": True,
        }
    )

    degraded_lines = [ln for ln in lines if "降级" in ln or "degraded" in ln.lower()]
    assert degraded_lines, (
        "audit R2-2 requires a visible 'recall degraded' line in /诊断 output"
    )
    # And it should mention the FTS-only fallback so the user understands
    # the qualitative loss.
    text = "\n".join(lines)
    assert "fts" in text.lower() or "FTS" in text


# ---------------------------------------------------------------------------
# 9. Internal tuple extension — _hybrid_experience_search_once returns degraded flag
# ---------------------------------------------------------------------------


@pytest.mark.module_test
def test_internal_search_once_returns_degraded_flag():
    """Internal helper returns 4-tuple with degraded bool as the 4th element.

    Public hybrid_experience_search API is unchanged (still returns list[dict]);
    the degraded flag is surfaced through retrieval_telemetry instead.
    """
    sem = _make_semantic_with_hybrid(side_effect=RuntimeError("OOM"))
    fts = _fts_stub()
    out, mode, fallbacks, degraded = _hybrid_experience_search_once(
        sem, fts, "q", project="p", limit=2
    )
    assert mode == "fts-error-fallback"
    assert degraded is True

    # Success path: degraded=False
    sem2 = MagicMock()
    sem2.hybrid_search.return_value = [{"id": 1, "content": "v", "score": 0.9}]
    fts2 = _fts_stub()
    out, mode, fallbacks, degraded = _hybrid_experience_search_once(
        sem2, fts2, "q", project="p", limit=2
    )
    assert mode == "hybrid"
    assert degraded is False
