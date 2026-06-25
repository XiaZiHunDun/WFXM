"""Per-turn memory prefetch, injection and caching."""

from __future__ import annotations

import logging
from typing import Any

from butler.session.lifecycle import (
    _current_project,
    _EMPTY_MEMORY_MARKERS,
    _filter_ephemeral_experience,
    _render_turn_memory_context,
)

logger = logging.getLogger(__name__)


def prefetch_limits() -> dict[str, int]:
    """Env-tunable caps for per-turn memory injection (personal butler)."""
    import os

    def _int(name: str, default: int) -> int:
        try:
            from butler.env_parse import int_env

            return int_env(name, default, min=0)
        except ValueError:
            return default

    return {
        "max_chars": _int("BUTLER_PREFETCH_MAX_CHARS", 3000),
        "experience_hits": _int("BUTLER_PREFETCH_EXPERIENCE_HITS", 5),
        "project_hits": _int("BUTLER_PREFETCH_PROJECT_HITS", 5),
        "project_max_chars": _int("BUTLER_PREFETCH_PROJECT_MAX_CHARS", 1200),
        "facts_max_chars": _int("BUTLER_PREFETCH_FACTS_MAX_CHARS", 400),
        "total_max_chars": _int("BUTLER_PREFETCH_TOTAL_MAX_CHARS", 3500),
    }


def _prefetch_retrieval_counts(diagnostics: dict[str, Any] | None) -> tuple[int, int]:
    """Estimate injected memory item counts for P_r/R_r L2 metrics."""
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


def _emit_prefetch_metrics(
    query: str,
    *,
    hit: bool,
    result_count: int,
    diagnostics: dict[str, Any] | None,
) -> None:
    try:
        from butler.memory.memory_metrics import get_collector

        collector = get_collector()
        collector.on_prefetch(
            query=(query or "")[:120],
            hit=hit,
            result_count=result_count,
        )
        total, relevant = _prefetch_retrieval_counts(diagnostics)
        if total > 0:
            collector.on_retrieval(
                total_returned=total,
                relevant=relevant,
                used_by_llm=0,
            )
            if diagnostics is not None:
                diagnostics["memory_prefetch_retrieval_total"] = total
        from butler.memory.metrics_persist import flush_memory_metrics

        flush_memory_metrics()
    except Exception:
        pass


def _session_key_for_prefetch() -> str:
    try:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()
    except Exception:
        return ""


def _resolve_project_memory_for_turn(orchestrator: Any) -> Any:
    from butler.memory.diagnostics import _resolve_project_memory

    sk = _session_key_for_prefetch()
    pmem, _ = _resolve_project_memory(orchestrator, sk)
    return pmem


def peek_experience_hits(
    orchestrator: Any,
    query: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Experience hybrid hits for skill injection policy (no full prefetch assembly)."""
    q = (query or "").strip()
    if not q:
        return []
    caps = prefetch_limits()
    hit_limit = limit if limit is not None else caps["experience_hits"]
    bm = getattr(orchestrator, "butler_memory", None)
    if bm is None:
        return []
    exp = getattr(bm, "experience", None)
    if exp is None:
        return []
    try:
        from butler.memory.semantic_index import SemanticMemoryIndex, hybrid_experience_search

        semantic = getattr(bm, "semantic", None)
        if not isinstance(semantic, SemanticMemoryIndex):
            semantic = None
        return _filter_ephemeral_experience(
            hybrid_experience_search(
                semantic,
                exp.search,
                q,
                project=_current_project(orchestrator) or None,
                limit=hit_limit,
                experience_store=exp,
            )
        )
    except Exception as exc:
        logger.debug("peek experience hits skipped: %s", exc)
        return []


def prefetch_turn_memory(
    orchestrator: Any,
    query: str,
    *,
    role: str = "default",
    limit: int | None = None,
    diagnostics: dict[str, Any] | None = None,
    use_cache: bool = True,
) -> str:
    """Collect query-relevant Butler/project memory for the next turn."""
    session_key = _session_key_for_prefetch()
    if use_cache:
        from butler.memory.prefetch_cache import get_cached_prefetch

        cached = get_cached_prefetch(session_key, query)
        if cached is not None:
            if diagnostics is not None:
                diagnostics["memory_prefetch_cache_hit"] = True
            return cached
        if diagnostics is not None:
            diagnostics["memory_prefetch_cache_hit"] = False

    caps = prefetch_limits()
    hit_limit = limit if limit is not None else caps["experience_hits"]
    parts: list[str] = []

    try:
        from butler.core.session_recall_intent import is_session_read_recall_intent

        if is_session_read_recall_intent(query):
            if diagnostics is not None:
                diagnostics["memory_prefetch_skipped"] = "session_read_recall"
            _emit_prefetch_metrics(query, hit=False, result_count=0, diagnostics=diagnostics)
            return ""
    except Exception as exc:
        logger.debug("session read recall prefetch gate skipped: %s", exc)

    current_project = _current_project(orchestrator)

    bm = getattr(orchestrator, "butler_memory", None)
    if bm is not None:
        try:
            ctx = bm.get_system_context(current_project)
            if ctx and ctx.strip() not in _EMPTY_MEMORY_MARKERS:
                parts.append(str(ctx).strip())
                if diagnostics is not None:
                    diagnostics["memory_butler_context"] = True
        except Exception as exc:
            if diagnostics is not None:
                diagnostics["memory_butler_error"] = str(exc)
            logger.debug("Butler memory prefetch skipped: %s", exc)

        try:
            from butler.memory.semantic_index import SemanticMemoryIndex

            semantic = getattr(bm, "semantic", None)
            if not isinstance(semantic, SemanticMemoryIndex):
                semantic = None
            if (query or "").strip():
                hits = peek_experience_hits(
                    orchestrator, query, limit=hit_limit
                )
                if hits:
                    lines = [
                        f"- [{h.get('project', '') or 'global'}] {h.get('content', '')}".strip()
                        for h in hits
                        if h.get("content")
                    ]
                    if lines:
                        parts.append("## Query-aligned experience\n" + "\n".join(lines))
                        if diagnostics is not None:
                            diagnostics["memory_experience_hits"] = len(lines)
                            diagnostics["memory_semantic_enabled"] = semantic is not None
                            if semantic is not None:
                                diagnostics["memory_vector_rows"] = semantic.count_rows()
                if semantic is not None and hasattr(bm, "search_profile_vectors"):
                    try:
                        prof_hits = bm.search_profile_vectors(query, limit=3)
                        if prof_hits:
                            plines = [
                                f"- {h.get('content', '')}".strip()
                                for h in prof_hits
                                if h.get("content")
                            ]
                            if plines:
                                parts.append(
                                    "## Owner profile (vector)\n" + "\n".join(plines)
                                )
                                if diagnostics is not None:
                                    diagnostics["memory_profile_vector_hits"] = len(
                                        plines
                                    )
                    except Exception as exc:
                        logger.debug("Profile vector prefetch skipped: %s", exc)
        except Exception as exc:
            if diagnostics is not None:
                diagnostics["memory_experience_error"] = str(exc)
            logger.debug("Experience prefetch skipped: %s", exc)

    pmem = _resolve_project_memory_for_turn(orchestrator)
    q_strip = (query or "").strip()
    project_hits_limit = caps.get("project_hits", 5)
    if pmem is not None:
        try:
            facts_snip = ""
            from butler.memory.project_memory import ProjectMemory

            if isinstance(pmem, ProjectMemory):
                facts_snip = pmem.facts_for_prefetch(
                    max_chars=caps.get("facts_max_chars", 400)
                )
            if facts_snip:
                parts.append("## Project facts (auto)\n" + facts_snip)
                if diagnostics is not None:
                    diagnostics["memory_facts_chars"] = len(facts_snip)

            injected_project = False
            if q_strip and current_project:
                from butler.memory.semantic_config import semantic_memory_enabled
                from butler.memory.semantic_index import SemanticMemoryIndex
                from butler.memory.semantic_project import (
                    prefetch_project_memory_hits,
                    resolve_project_display_name,
                )

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
                from butler.memory.project_memory import filter_memory_hits_by_role

                hits = filter_memory_hits_by_role(hits, role)
                try:
                    from butler.memory.retrieval_telemetry import record_last_retrieval

                    record_last_retrieval(
                        session_key,
                        {
                            "mode": f"project-{mode}",
                            "fallbacks": 1 if sem_enabled and mode == "keyword" else 0,
                            "candidates": len(hits),
                            "query": q_strip,
                        },
                    )
                except Exception as exc:
                    logger.debug("Prefetch telemetry recording skipped: %s", exc)
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
                        parts.append(title + "\n" + "\n".join(lines))
                        injected_project = True
                        if diagnostics is not None:
                            diagnostics["memory_project_query_hits"] = len(lines)
                            diagnostics["memory_project_prefetch_mode"] = mode
                            diagnostics["memory_project_semantic"] = mode == "vector"
            if not injected_project:
                ctx = pmem.get_context_for_agent(role)
                if ctx and ctx.strip() not in _EMPTY_MEMORY_MARKERS:
                    ctx_str = str(ctx).strip()
                    from butler.memory.project_memory import project_prefetch_max_chars

                    max_proj = project_prefetch_max_chars(
                        role, default=caps["project_max_chars"]
                    )
                    if max_proj and len(ctx_str) > max_proj:
                        ctx_str = ctx_str[:max_proj] + "\n…(项目记忆已截断)"
                    parts.append(ctx_str)
                    if diagnostics is not None:
                        diagnostics["memory_project_context"] = True
        except Exception as exc:
            if diagnostics is not None:
                diagnostics["memory_project_error"] = str(exc)
            logger.debug("Project memory prefetch skipped: %s", exc)

    try:
        from butler.core.pim_state import load_pim_state

        pim = load_pim_state()
        pim_line = pim.summary_line()
        if pim_line and pim_line != "(empty)":
            parts.append(f"## PIM overview\n{pim_line}")
            if diagnostics is not None:
                diagnostics["memory_pim_injected"] = True
    except Exception as exc:
        logger.debug("PIM prefetch skipped: %s", exc)

    merged = "\n\n".join(p for p in parts if p.strip())
    total_cap = caps["total_max_chars"]
    if total_cap and len(merged) > total_cap:
        merged = merged[:total_cap] + "\n…(记忆预取已截断)"
        if diagnostics is not None:
            diagnostics["memory_prefetch_truncated"] = True
    if diagnostics is not None:
        diagnostics["memory_prefetch_chars"] = len(merged)
    try:
        from butler.memory.injection_guard import filter_injection_from_prefetch

        merged = filter_injection_from_prefetch(merged)
    except Exception as exc:
        logger.debug("Prefetch injection filter skipped: %s", exc)
    if merged.strip():
        from butler.memory.prefetch_cache import set_cached_prefetch

        set_cached_prefetch(session_key, query, merged)
        try:
            from butler.memory.prefetch_retrieval_metrics import record_prefetch_snippets

            record_prefetch_snippets(diagnostics, merged)
        except Exception as exc:
            logger.debug("prefetch snippet capture skipped: %s", exc)

    hit = bool(merged.strip())
    result_count = int(diagnostics.get("memory_experience_hits", 0) if diagnostics else 0)
    _emit_prefetch_metrics(query, hit=hit, result_count=result_count, diagnostics=diagnostics)

    try:
        from butler.ops.langfuse_tracer import get_current_trace, langfuse_enabled
        if langfuse_enabled():
            ctx = get_current_trace(session_key=session_key)
            if ctx is not None:
                ctx.on_memory_prefetch(
                    query=(query or "")[:120],
                    hit=hit,
                    result_count=result_count,
                    chars=len(merged),
                )
    except Exception:
        pass

    return merged


def queue_prefetch_after_turn(
    orchestrator: Any,
    query: str,
    *,
    role: str = "default",
    session_id: str = "",
) -> None:
    """Warm prefetch cache in background after a turn completes."""
    from butler.memory.prefetch_cache import schedule_prefetch_warm

    sk = str(session_id or "").strip() or _session_key_for_prefetch()

    def _build() -> str:
        from butler.execution_context import use_execution_context

        with use_execution_context(orchestrator, session_key=sk):
            return prefetch_turn_memory(
                orchestrator,
                query,
                role=role,
                use_cache=False,
            )

    schedule_prefetch_warm(_build, session_key=sk, query=query)


def inject_turn_memory(
    orchestrator: Any,
    user_msg: str,
    *,
    role: str = "default",
    max_chars: int | None = None,
) -> str:
    """Prepend relevant memory context to a user turn."""
    if not (user_msg or "").strip():
        return user_msg
    ctx = prefetch_turn_memory(orchestrator, user_msg, role=role)
    if not ctx.strip():
        return user_msg
    cap = max_chars if max_chars is not None else prefetch_limits()["max_chars"]
    return _render_turn_memory_context(ctx, user_msg, max_chars=cap)


def build_memory_pre_llm_transform(
    orchestrator: Any,
    query: str,
    *,
    role: str = "default",
    max_chars: int | None = None,
    diagnostics: dict[str, Any] | None = None,
):
    cap = max_chars if max_chars is not None else prefetch_limits()["max_chars"]
    """Build an API-time memory injection transform that does not mutate history."""

    def _transform(messages: list[dict]) -> list[dict]:
        try:
            from butler.mcp.github_grounding import find_latest_github_repo_list_envelope

            if find_latest_github_repo_list_envelope(messages) is not None:
                if diagnostics is not None:
                    diagnostics["memory_context_injected"] = False
                    diagnostics["memory_prefetch_skipped_github_grounding"] = True
                out = [dict(m) if isinstance(m, dict) else m for m in messages]
                if existing:
                    return existing(out)
                return out
            from butler.mcp.github_grounding import find_latest_github_issue_list_envelope

            if find_latest_github_issue_list_envelope(messages) is not None:
                if diagnostics is not None:
                    diagnostics["memory_context_injected"] = False
                    diagnostics["memory_prefetch_skipped_github_grounding"] = True
                out = [dict(m) if isinstance(m, dict) else m for m in messages]
                if existing:
                    return existing(out)
                return out
        except Exception as exc:
            logger.debug("GitHub grounding prefetch skip check failed: %s", exc)
        try:
            from butler.core.input_stage import begin_input_stage, normalize_inbound_text

            begin_input_stage(diagnostics)
            query = normalize_inbound_text(query)
        except Exception as exc:
            logger.debug("Input stage normalize skipped: %s", exc)
        ctx = prefetch_turn_memory(orchestrator, query, role=role, diagnostics=diagnostics)
        if not ctx.strip():
            if diagnostics is not None:
                diagnostics["memory_context_injected"] = False
            return [dict(m) if isinstance(m, dict) else m for m in messages]

        out = [dict(m) if isinstance(m, dict) else m for m in messages]
        for idx in range(len(out) - 1, -1, -1):
            msg = out[idx]
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = str(msg.get("content") or "")
                msg["content"] = _render_turn_memory_context(
                    ctx,
                    content,
                    max_chars=cap,
                )
                if diagnostics is not None:
                    diagnostics["memory_context_injected"] = True
                    diagnostics["memory_context_chars"] = min(len(ctx), cap)
                try:
                    from butler.execution_context import get_current_session_key
                    from butler.core.session_transcript import record_knowledge_inject

                    sk = str(get_current_session_key() or "").strip()
                    if sk:
                        record_knowledge_inject(
                            sk,
                            source="memory_prefetch",
                            chars=min(len(ctx), cap),
                        )
                except Exception as exc:
                    logger.debug("Prefetch context injection budget skipped: %s", exc)
                break
        return out

    return _transform


def attach_turn_memory_prefetch(
    agent_loop: Any,
    orchestrator: Any,
    query: str,
    *,
    role: str = "default",
    diagnostics: dict[str, Any] | None = None,
) -> None:
    """Attach ephemeral memory prefetch to an AgentLoop callback chain."""
    callbacks = getattr(agent_loop, "callbacks", None)
    if callbacks is None:
        return
    existing = getattr(callbacks, "pre_llm_transform", None)
    if getattr(existing, "_butler_memory_transform", False):
        existing = getattr(existing, "_butler_base_transform", None)
    memory_transform = build_memory_pre_llm_transform(
        orchestrator,
        query,
        role=role,
        diagnostics=diagnostics,
    )

    def _composed(messages: list[dict]) -> list[dict]:
        prepared = memory_transform(messages)
        try:
            from butler.core.instruction_walkup import build_instruction_pre_llm_transform
            from butler.execution_context import get_current_session_key

            inst_transform = build_instruction_pre_llm_transform(
                session_key=str(get_current_session_key() or ""),
            )
            prepared = inst_transform(prepared)
        except Exception as exc:
            logger.debug("Instruction pre-LLM transform skipped: %s", exc)
        if existing:
            return existing(prepared)
        return prepared

    callbacks.pre_llm_transform = _composed
    callbacks.pre_llm_transform._butler_memory_transform = True
    callbacks.pre_llm_transform._butler_base_transform = existing
