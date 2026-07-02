"""Memory layer stats for /诊断 and ops."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.memory.diagnostics_collect import (
    collect_embedding_snapshot_stats,
    collect_experience_vector_drift,
    collect_project_memory_stats,
    collect_retrieval_telemetry,
    collect_scope_stats,
    collect_semantic_vector_stats,
    collect_transcript_fts_stats,
)
from butler.session.lifecycle import CONVERSATION_CATEGORY
import logging


logger = logging.getLogger(__name__)

def _resolve_experience_db_path(db_path: Any) -> Path | None:
    """Return an existing SQLite path, or None (never create files from mocks)."""
    if db_path is None:
        return None
    from unittest.mock import Mock

    raw = getattr(db_path, "path", db_path)
    if isinstance(raw, Mock):
        return None
    try:
        resolved = Path(raw)
    except (TypeError, ValueError, OSError):
        return None
    if not resolved.exists():
        return None
    return resolved


def _experience_category_counts(db_path: Any) -> dict[str, int]:
    path = _resolve_experience_db_path(db_path)
    if path is None:
        return {}
    try:
        conn = sqlite3.connect(str(path))
        rows = conn.execute(
            "SELECT category, COUNT(*) FROM experiences GROUP BY category"
        ).fetchall()
        conn.close()
        return {str(cat or ""): int(n) for cat, n in rows}
    except sqlite3.Error:
        return {}


def _resolve_project_memory(orchestrator: Any, session_key: str = ""):
    """Project MEMORY for diagnostics; prefers session_key over global _project_memory."""
    pm = getattr(orchestrator, "_project_memory", None)
    proj = None
    pman = getattr(orchestrator, "project_manager", None)
    if pman is not None:
        proj = safe_best_effort(
            lambda: pman.get_current(session_key=session_key or ""),
            label="memory_diag.current_project",
            default=None,
        )
    if proj is not None:
        from butler.memory.project_memory import ProjectMemory

        ws = getattr(proj, "workspace", None)
        if ws is not None:
            root = Path(ws).expanduser()
            if root.is_dir():
                name = str(getattr(proj, "name", "") or root.name)
                return ProjectMemory(root), name
    if pm is not None:
        from butler.memory.semantic_project import resolve_project_display_name

        return pm, resolve_project_display_name(pm)
    return None, ""


def collect_memory_layer_stats(
    orchestrator: Any,
    *,
    session_key: str = "",
) -> dict[str, Any]:
    """Snapshot counts for owner profile, experience.db, and project MEMORY.md."""
    stats: dict[str, Any] = {
        "profile_entries": 0,
        "profile_chars": 0,
        "experience_by_category": {},
        "experience_long_term": 0,
        "conversation_rows": 0,
        "semantic_enabled": False,
        "vector_rows": 0,
        "vector_model": "",
        "profile_vector_rows": 0,
        "triplet_rows": 0,
        "project_name": "",
        "project_pending": 0,
        "project_bullets": 0,
        "project_chars": 0,
        "knowledge_db_keys": 0,
        # Audit R2-4: orchestrator-level "memory facade failed to initialize"
        # surfaced to /诊断 so the operator sees the whole subsystem is
        # down, not just degraded. Distinct from embedding_degraded (R2-3)
        # or recall_degraded (R2-2) which are sub-component degradations.
        "memory_offline": bool(getattr(orchestrator, "memory_offline", False)),
        "memory_init_error": str(
            getattr(orchestrator, "_memory_init_error", "") or ""
        ),
    }

    bm = getattr(orchestrator, "butler_memory", None)
    if bm is not None:
        prof = getattr(bm, "profile", None)
        if prof is not None:
            entries = getattr(prof, "_entries", None)
            if isinstance(entries, list):
                stats["profile_entries"] = len(entries)
                stats["profile_chars"] = sum(len(e) for e in entries)
            else:
                text = prof.read() if hasattr(prof, "read") else ""
                stats["profile_chars"] = len(text or "")

        sem = getattr(bm, "semantic", None)
        if sem is not None:
            stats["semantic_enabled"] = True
            stats.update(collect_semantic_vector_stats(sem))
        tri = bm.triplet_index() if hasattr(bm, "triplet_index") else None
        if tri is not None:
            count = safe_best_effort(
                tri.count,
                label="memory_diag.triplet_count",
                default=None,
            )
            if count is not None:
                stats["triplet_rows"] = count
        exp = getattr(bm, "experience", None)
        if exp is not None:
            by_cat = _experience_category_counts(getattr(exp, "db_path", None))
            stats["experience_by_category"] = by_cat
            stats["conversation_rows"] = by_cat.get(CONVERSATION_CATEGORY, 0)
            stats["experience_long_term"] = sum(
                n for k, n in by_cat.items() if k != CONVERSATION_CATEGORY
            )
            if stats.get("semantic_enabled") and sem is not None:
                stats.update(
                    collect_experience_vector_drift(
                        sem,
                        experience_long_term=stats["experience_long_term"],
                    )
                )

    pm, proj_name = _resolve_project_memory(orchestrator, session_key)
    if pm is not None:
        stats.update(collect_project_memory_stats(pm, proj_name))
        bm2 = getattr(orchestrator, "butler_memory", None)
        if bm2 is not None and hasattr(bm2, "triplet_index"):
            tri2 = bm2.triplet_index()
            if tri2 is not None:
                count = safe_best_effort(
                    lambda: tri2.count(project=proj_name or None),
                    label="memory_diag.project_triplet_count",
                    default=None,
                )
                if count is not None:
                    stats["triplet_rows"] = count
    if session_key:
        stats.update(collect_retrieval_telemetry(session_key))
    stats.update(collect_scope_stats(str(stats.get("project_name") or "")))
    stats.update(collect_transcript_fts_stats(session_key))
    stats.update(
        collect_embedding_snapshot_stats(int(stats.get("vector_rows") or 0))
    )
    return stats


def format_memory_diagnostic_lines(stats: dict[str, Any]) -> list[str]:
    """Human-readable lines for gateway /诊断."""
    if not stats:
        return ["记忆分层: 无数据"]

    try:
        from butler.memory_settings import format_memory_config_source_line

        config_line = format_memory_config_source_line()
    except ImportError:
        config_line = ""

    lines: list[str] = []
    if config_line:
        lines.append(config_line)
    def _embedding_status_line() -> str:
        from butler.ops.embedding_diagnostics import format_embedding_status_line

        snap = stats.get("embedding_snapshot")
        if isinstance(snap, dict):
            return format_embedding_status_line(snap)
        return format_embedding_status_line(
            vector_rows=int(stats.get("vector_rows") or 0),
        )

    embedding_line = safe_best_effort(
        _embedding_status_line,
        label="memory_diag.format_embedding_status",
        default=None,
    )
    if embedding_line:
        lines.append(embedding_line)
    lines.extend(
        [
            "记忆分层:",
            f"  Owner 画像: {stats.get('profile_entries', 0)} 条 / "
            f"{stats.get('profile_chars', 0)} 字",
            f"  Experience: 长期 {stats.get('experience_long_term', 0)} 条, "
            f"会话回声 {stats.get('conversation_rows', 0)} 条",
        ]
    )
    proj = stats.get("project_name") or "（未选项目）"
    lines.append(
        f"  项目 MEMORY ({proj}): 正式条目 {stats.get('project_bullets', 0)} 条, "
        f"Pending {stats.get('project_pending', 0)} 条"
    )
    if stats.get("semantic_enabled"):
        lines.append(
            f"  向量索引: {stats.get('vector_rows', 0)} 条 "
            f"(model={stats.get('vector_model') or '?'})"
        )
        pv = stats.get("profile_vector_rows", 0)
        if pv:
            lines.append(f"  Owner 画像向量: {pv} 条")
        tri_n = stats.get("triplet_rows", 0)
        if tri_n:
            lines.append(f"  三元组（仅展示）: {tri_n} 条 — /记忆图谱")
        kdb_n = stats.get("knowledge_db_keys", 0)
        if kdb_n:
            lines.append(f"  knowledge.db: {kdb_n} 键（与 facts.json 同步）")
        idx_exp = stats.get("experience_indexable")
        vec_exp = stats.get("experience_vectors")
        if idx_exp is not None and vec_exp is not None:
            sync_line = f"  向量同步: experience {vec_exp}/{idx_exp}"
            if stats.get("semantic_index_stale"):
                sync_line += " — 陈旧，建议 butler memory reindex"
            lines.append(sync_line)
        def _vector_sync_lines() -> list[str]:
            from butler.memory.vector_sync_telemetry import format_vector_sync_lines

            return format_vector_sync_lines()

        vector_lines = safe_best_effort(
            _vector_sync_lines,
            label="memory_diag.vector_sync_lines",
            default=[],
        )
        if vector_lines:
            lines.extend(vector_lines)
    else:
        lines.append("  向量索引: 关 (BUTLER_SEMANTIC_MEMORY=0)")
    if stats.get("embedding_degraded") or (
        isinstance(stats.get("embedding_snapshot"), dict)
        and stats["embedding_snapshot"].get("embedding_degraded")
    ):
        lines.append("  嵌入质量: ⚠ 已降级（见 doctor Embedding Recall@3）")
    jl = stats.get("transcript_jsonl_lines")
    ft = stats.get("transcript_fts_rows")
    if jl is not None and ft is not None and stats.get("fts_enabled", True):
        tline = f"  Transcript 索引: jsonl {jl} 行 / FTS {ft} 行"
        if stats.get("transcript_fts_stale"):
            tline += " — 陈旧，建议 butler transcript index --rebuild"
        lines.append(tline)
    ranking_lines = safe_best_effort(
        lambda: _format_retrieval_ranking_lines(),
        label="memory_diag.retrieval_ranking",
        default=[],
    )
    lines.extend(ranking_lines or [])
    from butler.memory.prefetch_cache import queue_prefetch_enabled

    lines.append(
        f"  预取 warm (QUEUE_PREFETCH): {'开' if queue_prefetch_enabled() else '关'}"
    )
    injected = stats.get("last_prefetch_chars")
    if injected is not None:
        lines.append(f"  上轮预取注入: {injected} 字")
    cache_hit = stats.get("memory_prefetch_cache_hit")
    if cache_hit is True:
        lines.append("  上轮预取缓存: 命中")
    elif cache_hit is False:
        lines.append("  上轮预取缓存: 未命中")
    elif injected is not None:
        lines.append("  上轮预取缓存: 未命中")
    cache_ready = stats.get("memory_prefetch_cache_ready")
    if cache_ready is True:
        lines.append("  当前句缓存: 就绪（下轮同句可命中）")
    elif cache_ready is False and stats.get("last_user_query"):
        lines.append("  当前句缓存: 无")
    mode = stats.get("memory_project_prefetch_mode")
    if mode:
        lines.append(f"  项目预取模式: {mode}")
    eff_lines = safe_best_effort(
        lambda: _format_effectiveness_lines(),
        label="memory_diag.effectiveness",
        default=[],
    )
    if eff_lines:
        lines.append("")
        lines.extend(eff_lines)
    scope = stats.get("memory_scope")
    if scope:
        def _scope_lines() -> list[str]:
            from butler.memory.scope_diagnostics import format_memory_scope_diagnostic_lines

            return format_memory_scope_diagnostic_lines(scope)

        scope_lines = safe_best_effort(
            _scope_lines,
            label="memory_diag.scope_lines",
            default=[],
        )
        if scope_lines:
            lines.append("")
            lines.extend(scope_lines)
    return lines


def _format_retrieval_ranking_lines() -> list[str]:
    from butler.memory.retrieval_ranking import memory_access_boost, memory_half_life_days
    from butler.memory.semantic_config import hybrid_fts_weight, hybrid_vector_weight

    return [
        f"  检索衰减: 半衰期 {memory_half_life_days():.0f} 天, "
        f"访问加权 {memory_access_boost():.2f}",
        f"  混合检索权重: 向量 {hybrid_vector_weight():.2f} / FTS {hybrid_fts_weight():.2f}",
    ]


def _format_effectiveness_lines() -> list[str]:
    from butler.memory.metrics_persist import format_effectiveness_lines

    return format_effectiveness_lines()
