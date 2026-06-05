"""Memory layer stats for /诊断 and ops."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

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
    except Exception:
        return {}


def _resolve_project_memory(orchestrator: Any, session_key: str = ""):
    """Project MEMORY for diagnostics; prefers session_key over global _project_memory."""
    pm = getattr(orchestrator, "_project_memory", None)
    proj = None
    pman = getattr(orchestrator, "project_manager", None)
    if pman is not None:
        try:
            proj = pman.get_current(session_key=session_key or "")
        except Exception:
            proj = None
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
            try:
                stats["vector_rows"] = sem.count_rows()
                stats["vector_model"] = getattr(sem, "model_id", "") or ""
                from butler.memory.semantic_index import SOURCE_OWNER_PROFILE

                stats["profile_vector_rows"] = sem.count_by_source(
                    SOURCE_OWNER_PROFILE
                )
            except Exception as exc:
                logger.debug("collect memory layer stats skipped: %s", exc)
        tri = bm.triplet_index() if hasattr(bm, "triplet_index") else None
        if tri is not None:
            try:
                stats["triplet_rows"] = tri.count()
            except Exception as exc:
                logger.debug("collect memory layer stats skipped: %s", exc)
        exp = getattr(bm, "experience", None)
        if exp is not None:
            by_cat = _experience_category_counts(getattr(exp, "db_path", None))
            stats["experience_by_category"] = by_cat
            stats["conversation_rows"] = by_cat.get(CONVERSATION_CATEGORY, 0)
            stats["experience_long_term"] = sum(
                n for k, n in by_cat.items() if k != CONVERSATION_CATEGORY
            )

    pm, proj_name = _resolve_project_memory(orchestrator, session_key)
    if pm is not None:
        stats["project_name"] = proj_name
        bm2 = getattr(orchestrator, "butler_memory", None)
        if bm2 is not None and hasattr(bm2, "triplet_index"):
            tri2 = bm2.triplet_index()
            if tri2 is not None:
                try:
                    stats["triplet_rows"] = tri2.count(project=proj_name or None)
                except Exception as exc:
                    logger.debug("collect memory layer stats skipped: %s", exc)
        md = getattr(pm, "markdown", None)
        if md is not None:
            try:
                stats["project_pending"] = len(md.list_pending())
            except Exception:
                stats["project_pending"] = 0
            try:
                sections = md.get_all_sections()
                bullets = 0
                chars = 0
                for name, body in sections.items():
                    if name == "Pending":
                        continue
                    for line in (body or "").splitlines():
                        if line.strip().startswith("- "):
                            bullets += 1
                            chars += len(line)
                stats["project_bullets"] = bullets
                stats["project_chars"] = chars
            except Exception as exc:
                logger.debug("collect memory layer stats skipped: %s", exc)
        facts_store = getattr(pm, "facts", None)
        if facts_store is not None:
            try:
                from butler.memory.knowledge_db import ProjectKnowledgeDb

                kdb = ProjectKnowledgeDb(
                    ProjectKnowledgeDb.path_for_memory_dir(facts_store.path.parent)
                )
                stats["knowledge_db_keys"] = kdb.count_keys()
            except Exception as exc:
                logger.debug("collect memory layer stats skipped: %s", exc)
    if session_key:
        try:
            from butler.memory.retrieval_telemetry import get_last_retrieval

            last = get_last_retrieval(session_key)
            if last:
                stats["rag_last_mode"] = str(last.get("mode") or "")
                stats["rag_last_fallbacks"] = int(last.get("fallbacks") or 0)
                stats["rag_last_candidates"] = int(last.get("candidates") or 0)
                stats["rag_last_query"] = str(last.get("query") or "")
                # Audit R2-2: surface recall-quality collapse to /诊断.
                stats["rag_last_recall_degraded"] = bool(last.get("recall_degraded"))
                if last.get("sub_query_count"):
                    stats["rag_last_sub_queries"] = int(last.get("sub_query_count") or 0)
        except Exception as exc:
            logger.debug("collect memory layer stats skipped: %s", exc)
    return stats


def format_memory_diagnostic_lines(stats: dict[str, Any]) -> list[str]:
    """Human-readable lines for gateway /诊断."""
    if not stats:
        return ["记忆分层: 无数据"]

    lines = [
        "记忆分层:",
        f"  Owner 画像: {stats.get('profile_entries', 0)} 条 / "
        f"{stats.get('profile_chars', 0)} 字",
        f"  Experience: 长期 {stats.get('experience_long_term', 0)} 条, "
        f"会话回声 {stats.get('conversation_rows', 0)} 条",
    ]
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
    else:
        lines.append("  向量索引: 关 (BUTLER_SEMANTIC_MEMORY=0)")
    try:
        from butler.memory.retrieval_ranking import (
            memory_access_boost,
            memory_half_life_days,
        )

        lines.append(
            f"  检索衰减: 半衰期 {memory_half_life_days():.0f} 天, "
            f"访问加权 {memory_access_boost():.2f}"
        )
        from butler.memory.semantic_config import hybrid_fts_weight, hybrid_vector_weight

        lines.append(
            f"  混合检索权重: 向量 {hybrid_vector_weight():.2f} / FTS {hybrid_fts_weight():.2f}"
        )
    except Exception as exc:
        logger.debug("format memory diagnostic lines skipped: %s", exc)
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
    return lines
