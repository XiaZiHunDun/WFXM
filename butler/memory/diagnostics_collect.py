"""Optional memory stats collectors for ``diagnostics.collect_memory_layer_stats`` (P2-F)."""

from __future__ import annotations

from typing import Any, Callable, cast

from butler.core.best_effort import safe_best_effort
from butler.memory.semantic_index import SOURCE_OWNER_PROFILE
from butler.memory.semantic_health import experience_vector_drift
from butler.memory.semantic_index import SOURCE_EXPERIENCE
from butler.memory.knowledge_db import ProjectKnowledgeDb
from butler.memory.retrieval_telemetry import get_last_retrieval, get_last_retrieval_by_scope
from butler.config import get_butler_home
from butler.memory.scope_diagnostics import collect_memory_scope_stats
from butler.ops.transcript_diagnostics import transcript_fts_drift
from butler.ops.embedding_diagnostics import collect_embedding_snapshot


def collect_semantic_vector_stats(sem: Any) -> dict[str, Any]:
    def _run() -> dict[str, Any]:

        out: dict[str, Any] = {
            "vector_rows": sem.count_rows(),
            "vector_model": getattr(sem, "model_id", "") or "",
            "profile_vector_rows": sem.count_by_source(SOURCE_OWNER_PROFILE),
        }
        embedder = getattr(sem, "embedder", None)
        if embedder is not None:
            out["embedding_degraded"] = bool(getattr(embedder, "degraded", False))
            out["embedding_requested_provider"] = str(
                getattr(embedder, "requested_provider", "") or ""
            )
            out["embedding_requested_model"] = str(
                getattr(embedder, "requested_model", "") or ""
            )
            out["embedding_used_model"] = str(getattr(embedder, "model_id", "") or "")
        return out

    return safe_best_effort(_run, label="memory_diag.semantic_vectors", default={}) or {}


def collect_experience_vector_drift(
    sem: Any,
    *,
    experience_long_term: int,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:

        vec_exp = sem.count_by_source(SOURCE_EXPERIENCE)
        return cast(
            dict[str, Any],
            experience_vector_drift(
                experience_long_term=experience_long_term,
                experience_vectors=vec_exp,
            ),
        )

    return safe_best_effort(_run, label="memory_diag.experience_drift", default={}) or {}


def collect_project_memory_stats(pm: Any, proj_name: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        out: dict[str, Any] = {}
        md = getattr(pm, "markdown", None)
        if md is not None:
            out["project_pending"] = len(md.list_pending())
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
            out["project_bullets"] = bullets
            out["project_chars"] = chars
        facts_store = getattr(pm, "facts", None)
        if facts_store is not None:

            kdb = ProjectKnowledgeDb(
                ProjectKnowledgeDb.path_for_memory_dir(facts_store.path.parent)
            )
            out["knowledge_db_keys"] = kdb.count_keys()
        if proj_name:
            out["project_name"] = proj_name
        return out

    return safe_best_effort(_run, label="memory_diag.project_memory", default={}) or {}


def collect_retrieval_telemetry(session_key: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:

        out: dict[str, Any] = {}
        by_scope = get_last_retrieval_by_scope(session_key)
        if by_scope:
            out["rag_by_scope"] = by_scope
        last = get_last_retrieval(session_key)
        if last:
            out["rag_last_mode"] = str(last.get("mode") or "")
            out["rag_last_fallbacks"] = int(last.get("fallbacks") or 0)
            out["rag_last_candidates"] = int(last.get("candidates") or 0)
            out["rag_last_query"] = str(last.get("query") or "")
            out["rag_last_recall_degraded"] = bool(last.get("recall_degraded"))
            if last.get("sub_query_count"):
                out["rag_last_sub_queries"] = int(last.get("sub_query_count") or 0)
        return out

    return safe_best_effort(_run, label="memory_diag.retrieval_telemetry", default={}) or {}


def merge_optional_stats(stats: dict[str, Any], patch: dict[str, Any]) -> None:
    if patch:
        stats.update(patch)


def collect_scope_stats(project_name: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:

        return {
            "memory_scope": collect_memory_scope_stats(
                butler_home=get_butler_home(),
                project_name=project_name,
            )
        }

    return safe_best_effort(_run, label="memory_diag.scope_stats", default={}) or {}


def collect_transcript_fts_stats(session_key: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:

        return cast(dict[str, Any], transcript_fts_drift(session_key=session_key))

    return safe_best_effort(_run, label="memory_diag.transcript_fts", default={}) or {}


def collect_embedding_snapshot_stats(vector_rows: int) -> dict[str, Any]:
    def _run() -> dict[str, Any]:

        return {
            "embedding_snapshot": collect_embedding_snapshot(
                vector_rows=vector_rows,
            )
        }

    return safe_best_effort(_run, label="memory_diag.embedding_snapshot", default={}) or {}


def run_optional_collector(
    stats: dict[str, Any],
    fn: Callable[[], dict[str, Any]],
    *,
    label: str,
) -> None:
    merge_optional_stats(stats, safe_best_effort(fn, label=label, default={}) or {})


__all__ = [
    "collect_embedding_snapshot_stats",
    "collect_experience_vector_drift",
    "collect_project_memory_stats",
    "collect_retrieval_telemetry",
    "collect_scope_stats",
    "collect_semantic_vector_stats",
    "collect_transcript_fts_stats",
    "merge_optional_stats",
    "run_optional_collector",
]
