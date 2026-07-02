"""Per-turn memory prefetch, injection and caching."""

from __future__ import annotations

import logging
from typing import Any

from butler.session.lifecycle import (
    _EMPTY_MEMORY_MARKERS,
    _render_turn_memory_context,
)
from butler.session.memory_prefetch_ops import (
    apply_instruction_pre_llm_transform,
    butler_system_context,
    emit_prefetch_metrics,
    filter_prefetch_injection,
    github_grounding_should_skip,
    hybrid_experience_hits,
    langfuse_on_prefetch,
    normalize_prefetch_query,
    pim_overview_line,
    profile_vector_lines,
    record_knowledge_inject,
    record_prefetch_snippets,
    record_project_prefetch_telemetry,
    reflection_closure_banner,
    session_key_for_prefetch,
    session_read_recall_blocks_prefetch,
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


def _resolve_project_memory_for_turn(orchestrator: Any) -> Any:
    from butler.memory.diagnostics import _resolve_project_memory

    sk = session_key_for_prefetch()
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
    return hybrid_experience_hits(orchestrator, q, limit=hit_limit)


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
    session_key = session_key_for_prefetch()
    if use_cache:
        from butler.memory.prefetch_cache import get_cached_prefetch

        cached = get_cached_prefetch(session_key, query)
        if cached is not None:
            if diagnostics is not None:
                diagnostics["memory_prefetch_cache_hit"] = True
            return _decorate_prefetch_for_turn(cached, diagnostics, session_key=session_key)
        if diagnostics is not None:
            diagnostics["memory_prefetch_cache_hit"] = False

    caps = prefetch_limits()
    hit_limit = limit if limit is not None else caps["experience_hits"]
    parts: list[str] = []

    recall_skip = session_read_recall_blocks_prefetch(query)
    if recall_skip is True:
        if diagnostics is not None:
            diagnostics["memory_prefetch_skipped"] = "session_read_recall"
        emit_prefetch_metrics(query, hit=False, result_count=0, diagnostics=diagnostics)
        return ""

    from butler.session.lifecycle import _current_project

    current_project = _current_project(orchestrator)

    bm = getattr(orchestrator, "butler_memory", None)
    if bm is not None:
        ctx = butler_system_context(
            bm,
            current_project,
            diagnostics=diagnostics,
        )
        if ctx:
            parts.append(ctx)

        q_strip = (query or "").strip()
        if q_strip:
            hits = peek_experience_hits(orchestrator, query, limit=hit_limit)
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
                        from butler.memory.semantic_index import SemanticMemoryIndex

                        semantic = getattr(bm, "semantic", None)
                        if not isinstance(semantic, SemanticMemoryIndex):
                            semantic = None
                        diagnostics["memory_semantic_enabled"] = semantic is not None
                        if semantic is not None:
                            diagnostics["memory_vector_rows"] = semantic.count_rows()
            prof = profile_vector_lines(bm, q_strip)
            if prof is not None:
                plines, count = prof
                parts.append("## Owner profile (vector)\n" + "\n".join(plines))
                if diagnostics is not None:
                    diagnostics["memory_profile_vector_hits"] = count

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

    pim_line = pim_overview_line()
    if pim_line:
        parts.append(f"## PIM overview\n{pim_line}")
        if diagnostics is not None:
            diagnostics["memory_pim_injected"] = True

    merged = "\n\n".join(p for p in parts if p.strip())
    total_cap = caps["total_max_chars"]
    if total_cap and len(merged) > total_cap:
        merged = merged[:total_cap] + "\n…(记忆预取已截断)"
        if diagnostics is not None:
            diagnostics["memory_prefetch_truncated"] = True
    if diagnostics is not None:
        diagnostics["memory_prefetch_chars"] = len(merged)
    merged = filter_prefetch_injection(merged)
    merged = _normalize_prefetch_body(merged, diagnostics)
    if merged.strip():
        from butler.memory.prefetch_cache import set_cached_prefetch

        set_cached_prefetch(session_key, query, merged)
        record_prefetch_snippets(diagnostics, merged)

    hit = bool(merged.strip())
    result_count = int(diagnostics.get("memory_experience_hits", 0) if diagnostics else 0)
    emit_prefetch_metrics(query, hit=hit, result_count=result_count, diagnostics=diagnostics)

    langfuse_on_prefetch(
        session_key=session_key,
        query=query,
        hit=hit,
        result_count=result_count,
        chars=len(merged),
    )

    return _decorate_prefetch_for_turn(merged, diagnostics, session_key=session_key)


def _normalize_prefetch_body(
    body: str,
    diagnostics: dict[str, Any] | None,
) -> str:
    from butler.core.memory_context_adapter import adapt_memory_prefetch_content

    return adapt_memory_prefetch_content(body, source="memory_prefetch", diagnostics=diagnostics)


def _decorate_prefetch_for_turn(
    body: str,
    diagnostics: dict[str, Any] | None,
    *,
    session_key: str = "",
) -> str:
    merged = str(body or "").strip()
    banner = reflection_closure_banner(session_key)
    if banner.strip():
        merged = f"{banner}\n\n{merged}".strip() if merged else banner.strip()
        if diagnostics is not None:
            diagnostics["reflection_closure_injected"] = True
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

    sk = str(session_id or "").strip() or session_key_for_prefetch()

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
        if github_grounding_should_skip(messages):
            if diagnostics is not None:
                diagnostics["memory_context_injected"] = False
                diagnostics["memory_prefetch_skipped_github_grounding"] = True
            return [dict(m) if isinstance(m, dict) else m for m in messages]
        effective_query = normalize_prefetch_query(query, diagnostics)
        ctx = prefetch_turn_memory(
            orchestrator, effective_query, role=role, diagnostics=diagnostics
        )
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
                sk = session_key_for_prefetch()
                if sk:
                    record_knowledge_inject(
                        sk,
                        chars=min(len(ctx), cap),
                        diagnostics=diagnostics,
                    )
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
        prepared = apply_instruction_pre_llm_transform(prepared)
        if existing:
            return existing(prepared)
        return prepared

    callbacks.pre_llm_transform = _composed
    callbacks.pre_llm_transform._butler_memory_transform = True
    callbacks.pre_llm_transform._butler_base_transform = existing
