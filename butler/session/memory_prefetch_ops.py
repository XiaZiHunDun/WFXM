"""Best-effort helpers for per-turn memory prefetch (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def session_key_for_prefetch() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    return safe_best_effort(
        _run,
        label="memory_prefetch.session_key",
        default="",
    ) or ""


def prefetch_retrieval_counts(diagnostics: dict[str, Any] | None) -> tuple[int, int]:
    if not diagnostics:
        return 0, 0
    total = 0
    for key in (
        "memory_experience_hits",
        "memory_profile_vector_hits",
        "memory_project_query_hits",
    ):
        total += int(diagnostics.get(key, 0) or 0)
    for flag in (
        "memory_butler_context",
        "memory_project_context",
        "memory_pim_injected",
    ):
        if diagnostics.get(flag):
            total += 1
    if int(diagnostics.get("memory_facts_chars", 0) or 0) > 0:
        total += 1
    return total, total


def emit_prefetch_metrics(
    query: str,
    *,
    hit: bool,
    result_count: int,
    diagnostics: dict[str, Any] | None,
) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector
        from butler.memory.metrics_persist import flush_memory_metrics

        collector = get_collector()
        collector.on_prefetch(
            query=(query or "")[:120],
            hit=hit,
            result_count=result_count,
        )
        total, relevant = prefetch_retrieval_counts(diagnostics)
        if total > 0:
            collector.on_retrieval(
                total_returned=total,
                relevant=relevant,
                used_by_llm=0,
            )
            if diagnostics is not None:
                diagnostics["memory_prefetch_retrieval_total"] = total
        flush_memory_metrics()

    safe_best_effort(_run, label="memory_prefetch.metrics", default=None)


def session_read_recall_blocks_prefetch(query: str) -> bool | None:
    """Return True when prefetch should skip; None when gate check failed."""

    def _run() -> bool:
        from butler.core.session_recall_intent import is_session_read_recall_intent

        return bool(is_session_read_recall_intent(query))

    return safe_best_effort(
        _run,
        label="memory_prefetch.session_read_recall_gate",
        default=None,
    )


def butler_system_context(
    bm: Any,
    current_project: str,
    *,
    diagnostics: dict[str, Any] | None,
) -> str | None:
    def _run() -> str | None:
        ctx = bm.get_system_context(current_project)
        if ctx and str(ctx).strip():
            if diagnostics is not None:
                diagnostics["memory_butler_context"] = True
            return str(ctx).strip()
        return None

    result = safe_best_effort(
        _run,
        label="memory_prefetch.butler_context",
        default=None,
    )
    if result is None and diagnostics is not None:
        diagnostics.pop("memory_butler_error", None)
    return result


def profile_vector_lines(bm: Any, query: str) -> tuple[list[str], int] | None:
    def _run() -> tuple[list[str], int] | None:
        if not hasattr(bm, "search_profile_vectors"):
            return None
        prof_hits = bm.search_profile_vectors(query, limit=3)
        if not prof_hits:
            return None
        plines = [
            f"- {h.get('content', '')}".strip()
            for h in prof_hits
            if h.get("content")
        ]
        return (plines, len(plines)) if plines else None

    return safe_best_effort(
        _run,
        label="memory_prefetch.profile_vectors",
        default=None,
    )


def record_project_prefetch_telemetry(session_key: str, payload: dict[str, Any]) -> None:
    def _run() -> None:
        from butler.memory.retrieval_telemetry import record_last_retrieval

        record_last_retrieval(session_key, payload)

    safe_best_effort(_run, label="memory_prefetch.project_telemetry", default=None)


def pim_overview_line() -> str | None:
    def _run() -> str | None:
        from butler.core.pim_state import load_pim_state

        pim = load_pim_state()
        pim_line = pim.summary_line()
        if pim_line and pim_line != "(empty)":
            return pim_line
        return None

    return safe_best_effort(_run, label="memory_prefetch.pim", default=None)


def filter_prefetch_injection(merged: str) -> str:
    def _run() -> str:
        from butler.memory.injection_guard import filter_injection_from_prefetch

        return filter_injection_from_prefetch(merged)

    result = safe_best_effort(
        _run,
        label="memory_prefetch.injection_filter",
        default=None,
    )
    return merged if result is None else result


def record_prefetch_snippets(
    diagnostics: dict[str, Any] | None,
    merged: str,
) -> None:
    safe_best_effort(
        lambda: _record_prefetch_snippets(diagnostics, merged),
        label="memory_prefetch.snippet_capture",
        default=None,
    )


def _record_prefetch_snippets(
    diagnostics: dict[str, Any] | None,
    merged: str,
) -> None:
    from butler.memory.prefetch_retrieval_metrics import record_prefetch_snippets

    record_prefetch_snippets(diagnostics, merged)


def langfuse_on_prefetch(
    *,
    session_key: str,
    query: str,
    hit: bool,
    result_count: int,
    chars: int,
) -> None:
    def _run() -> None:
        from butler.ops.langfuse_tracer import get_current_trace, langfuse_enabled

        if not langfuse_enabled():
            return
        ctx = get_current_trace(session_key=session_key)
        if ctx is None:
            return
        ctx.on_memory_prefetch(
            query=(query or "")[:120],
            hit=hit,
            result_count=result_count,
            chars=chars,
        )

    safe_best_effort(_run, label="memory_prefetch.langfuse", default=None)


def reflection_closure_banner(session_key: str) -> str:
    def _run() -> str:
        from butler.core.reflection_closure import build_reflect_closure_banner

        return build_reflect_closure_banner(session_key=session_key)

    return safe_best_effort(
        _run,
        label="memory_prefetch.reflection_closure",
        default="",
    ) or ""


def github_grounding_should_skip(messages: list[dict]) -> bool:
    def _run() -> bool:
        from butler.mcp.github_grounding import (
            find_latest_github_issue_list_envelope,
            find_latest_github_repo_list_envelope,
        )

        if find_latest_github_repo_list_envelope(messages) is not None:
            return True
        return find_latest_github_issue_list_envelope(messages) is not None

    result = safe_best_effort(
        _run,
        label="memory_prefetch.github_grounding_skip",
        default=False,
    )
    return bool(result)


def normalize_prefetch_query(
    query: str,
    diagnostics: dict[str, Any] | None,
) -> str:
    def _run() -> str:
        from butler.core.input_stage import begin_input_stage, normalize_inbound_text

        begin_input_stage(diagnostics)
        return normalize_inbound_text(query)

    result = safe_best_effort(
        _run,
        label="memory_prefetch.input_stage",
        default=None,
    )
    return query if result is None else result


def record_knowledge_inject(
    session_key: str,
    *,
    chars: int,
    diagnostics: dict[str, Any] | None,
) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_knowledge_inject

        snippets = None
        if diagnostics is not None:
            raw = diagnostics.get("memory_prefetch_snippets")
            if isinstance(raw, list):
                snippets = [str(s) for s in raw]
        record_knowledge_inject(
            session_key,
            source="memory_prefetch",
            chars=chars,
            terms=snippets,
        )

    safe_best_effort(_run, label="memory_prefetch.knowledge_inject", default=None)


def apply_instruction_pre_llm_transform(messages: list[dict]) -> list[dict]:
    def _run() -> list[dict]:
        from butler.core.instruction_walkup import build_instruction_pre_llm_transform
        from butler.execution_context import get_current_session_key

        inst_transform = build_instruction_pre_llm_transform(
            session_key=str(get_current_session_key() or ""),
        )
        return inst_transform(messages)

    result = safe_best_effort(
        _run,
        label="memory_prefetch.instruction_transform",
        default=None,
    )
    return messages if result is None else result


def hybrid_experience_hits(
    orchestrator: Any,
    query: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    from butler.session.lifecycle import _current_project, _filter_ephemeral_experience

    def _run() -> list[dict[str, Any]]:
        from butler.memory.semantic_index import SemanticMemoryIndex, hybrid_experience_search

        bm = getattr(orchestrator, "butler_memory", None)
        if bm is None:
            return []
        exp = getattr(bm, "experience", None)
        if exp is None:
            return []
        semantic = getattr(bm, "semantic", None)
        if not isinstance(semantic, SemanticMemoryIndex):
            semantic = None
        return _filter_ephemeral_experience(
            hybrid_experience_search(
                semantic,
                exp.search,
                query,
                project=_current_project(orchestrator) or None,
                limit=limit,
                experience_store=exp,
            )
        )

    result = safe_best_effort(
        _run,
        label="memory_prefetch.experience_hits",
        default=None,
    )
    return result if result is not None else []


def collect_project_memory_prefetch_lines(
    *,
    pmem: Any,
    query: str,
    role: str,
    bm: Any,
    current_project: str,
    caps: dict[str, int],
    session_key: str,
    diagnostics: dict[str, Any] | None,
    empty_markers: frozenset[str],
) -> list[str]:
    def _run() -> list[str]:
        from butler.memory.project_memory import (
            ProjectMemory,
            filter_memory_hits_by_role,
            project_prefetch_max_chars,
        )
        from butler.memory.semantic_config import semantic_memory_enabled
        from butler.memory.semantic_index import SemanticMemoryIndex
        from butler.memory.semantic_project import (
            prefetch_project_memory_hits,
            resolve_project_display_name,
        )

        lines_out: list[str] = []
        facts_snip = ""
        if isinstance(pmem, ProjectMemory):
            facts_snip = pmem.facts_for_prefetch(
                max_chars=caps.get("facts_max_chars", 400)
            )
        if facts_snip:
            lines_out.append("## Project facts (auto)\n" + facts_snip)
            if diagnostics is not None:
                diagnostics["memory_facts_chars"] = len(facts_snip)

        q_strip = (query or "").strip()
        injected_project = False
        project_hits_limit = caps.get("project_hits", 5)
        if q_strip and current_project:
            sem = getattr(bm, "semantic", None) if bm is not None else None
            if not isinstance(sem, SemanticMemoryIndex):
                sem = None
            proj_name = resolve_project_display_name(pmem)
            hits, mode = prefetch_project_memory_hits(
                pmem,
                q_strip,
                project_name=proj_name or current_project,
                semantic=sem,
                limit=project_hits_limit,
                semantic_enabled=semantic_memory_enabled(),
            )
            sem_enabled = semantic_memory_enabled()
            hits = filter_memory_hits_by_role(hits, role)
            record_project_prefetch_telemetry(
                session_key,
                {
                    "mode": f"project-{mode}",
                    "fallbacks": 1 if sem_enabled and mode == "keyword" else 0,
                    "candidates": len(hits),
                    "query": q_strip,
                },
            )
            if hits:
                lines = [
                    f"- {h.get('content', '')}".strip()
                    for h in hits
                    if h.get("content")
                ]
                if lines:
                    title = "## Query-aligned project memory"
                    if mode == "keyword":
                        title = "## Query-aligned project memory (keyword)"
                    lines_out.append(title + "\n" + "\n".join(lines))
                    injected_project = True
                    if diagnostics is not None:
                        diagnostics["memory_project_query_hits"] = len(lines)
                        diagnostics["memory_project_prefetch_mode"] = mode
                        diagnostics["memory_project_semantic"] = mode == "vector"
        if not injected_project:
            ctx = pmem.get_context_for_agent(role)
            if ctx and ctx.strip() not in empty_markers:
                ctx_str = str(ctx).strip()
                max_proj = project_prefetch_max_chars(
                    role, default=caps["project_max_chars"]
                )
                if max_proj and len(ctx_str) > max_proj:
                    ctx_str = ctx_str[:max_proj] + "\n…(项目记忆已截断)"
                lines_out.append(ctx_str)
                if diagnostics is not None:
                    diagnostics["memory_project_context"] = True
        return lines_out

    result = safe_best_effort(
        _run,
        label="memory_prefetch.project_memory",
        default=None,
    )
    return result if isinstance(result, list) else []


__all__ = [
    "apply_instruction_pre_llm_transform",
    "butler_system_context",
    "collect_project_memory_prefetch_lines",
    "emit_prefetch_metrics",
    "filter_prefetch_injection",
    "github_grounding_should_skip",
    "hybrid_experience_hits",
    "langfuse_on_prefetch",
    "normalize_prefetch_query",
    "pim_overview_line",
    "prefetch_retrieval_counts",
    "profile_vector_lines",
    "record_knowledge_inject",
    "record_prefetch_snippets",
    "record_project_prefetch_telemetry",
    "reflection_closure_banner",
    "session_key_for_prefetch",
    "session_read_recall_blocks_prefetch",
]
