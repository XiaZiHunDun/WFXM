"""Reasoning trace best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.execution_context import get_current_session_key
from butler.core.reflection_closure import maybe_persist_reflect_closure
from butler.dev_engine.fix_strategy import enrich_fix_hint, suggest_fix_action
from butler.core.plan_reason_graph import append_node, maybe_auto_link_plan_node
from butler.core.session_transcript import record_reason_graph_event
from butler.plan.mode import is_plan_mode
from butler.core.session_transcript import find_last_transcript_types, transcript_enabled
from butler.core.plan_reason_graph import summarize_graph


def resolve_session_key_safe(explicit: str = "") -> str:
    key = str(explicit or "").strip()
    if key:
        return key

    def _run() -> str:

        return str(get_current_session_key() or "").strip() or "default"

    result = safe_best_effort(_run, label="reasoning_trace.session_key", default="default")
    return result if isinstance(result, str) and result else "default"


def persist_reflect_closure_safe(
    *,
    trigger: str,
    cause: str,
    strategy: str,
    detail: str,
    session_key: str,
    source: str,
) -> None:
    def _run() -> None:

        maybe_persist_reflect_closure(
            trigger=trigger,
            cause=cause,
            strategy=strategy,
            detail=detail,
            session_key=session_key,
            source=source,
        )

    safe_best_effort(_run, label="reasoning_trace.reflect_closure", default=None)


def suggest_fix_strategy_safe(state: Any, diags: list) -> str:
    def _run() -> str:

        level = suggest_fix_action(diags, state)
        return enrich_fix_hint(level, state)

    result = safe_best_effort(_run, label="reasoning_trace.fix_strategy", default="retry_fix")
    return result if isinstance(result, str) else "retry_fix"


def sync_plan_step_to_graph_safe(
    session_key: str,
    *,
    title: str,
    step_kind: str,
    assumption: str,
    evidence: str,
    detail: str,
) -> None:
    def _run() -> None:

        if not is_plan_mode(session_key):
            return
        node = append_node(
            session_key,
            text=(detail or title or "")[:500],
            role=step_kind,
            title=title,
            assumption=assumption,
            evidence=evidence,
        )
        edges = maybe_auto_link_plan_node(session_key, node)
        record_reason_graph_event(
            session_key,
            action="node_added",
            node_id=str(node.get("id") or ""),
            role=step_kind,
            preview=(title or detail or "")[:120],
        )
        for edge in edges:
            record_reason_graph_event(
                session_key,
                action="edge_added",
                node_id=f"{edge.get('from')}->{edge.get('to')}",
                role=str(edge.get("rel") or "depends"),
                preview=(title or detail or "")[:120],
            )

    safe_best_effort(_run, label="reasoning_trace.plan_graph", default=None)


def transcript_trace_imports_ok() -> bool:
    def _run() -> bool:

        return True

    return safe_best_effort(_run, label="reasoning_trace.transcript_import", default=False) is True


def plan_graph_summary_line(session_key: str) -> str:
    def _run() -> str:

        stats = summarize_graph(session_key)
        if stats.get("nodes"):
            return (
                f"Plan 推理图: {stats.get('nodes', 0)} 节点 · {stats.get('edges', 0)} 边"
            )
        return ""

    result = safe_best_effort(_run, label="reasoning_trace.graph_summary", default="")
    return result if isinstance(result, str) else ""
