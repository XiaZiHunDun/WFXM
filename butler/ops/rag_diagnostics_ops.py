"""Best-effort probes for RAG / 诊断 lines (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.memory.semantic_config import hybrid_fts_weight, hybrid_vector_weight
from butler.memory.recall_scopes import RECALL_SCOPES
from butler.memory.query_decompose import subquery_enabled
from butler.memory.corpus_router import corpus_routing_enabled
from butler.memory.corrective_recall import corrective_recall_enabled
from butler.tools.web_fetch import web_fetch_enabled
from butler.memory.unified_recall_config import observation_recall_enabled, unified_recall_enabled
from butler.mcp.profiles import get_session_profile, mcp_profiles_enabled


def append_probe_line(
    lines: list[str],
    *,
    label: str,
    build: Callable[[], str],
) -> None:
    def _run() -> None:
        line = str(build() or "").strip()
        if line:
            lines.append(line)

    safe_best_effort(_run, label=label, default=None)


def append_hybrid_weights_line(lines: list[str]) -> None:
    def _build() -> str:

        return (
            f"  混合权重: 向量 {hybrid_vector_weight():.2f} / "
            f"FTS {hybrid_fts_weight():.2f}"
        )

    append_probe_line(lines, label="rag_diagnostics.hybrid_weights", build=_build)


def recall_scope_order(by_scope: dict[str, Any]) -> list[str]:
    def _run() -> list[str]:

        order = [s for s in RECALL_SCOPES if s in by_scope]
        order.extend(sorted(set(by_scope.keys()) - set(order)))
        return order

    result = safe_best_effort(
        _run,
        label="rag_diagnostics.recall_scopes",
        default=None,
    )
    if isinstance(result, list):
        return result
    return sorted(by_scope.keys())


def append_subquery_flag_line(lines: list[str]) -> None:
    def _build() -> str:

        return f"  子 query 分解: {'开' if subquery_enabled() else '关'}"

    append_probe_line(lines, label="rag_diagnostics.subquery", build=_build)


def append_corpus_routing_flag_line(lines: list[str]) -> None:
    def _build() -> str:

        return f"  多语料库路由: {'开' if corpus_routing_enabled() else '关'}"

    append_probe_line(lines, label="rag_diagnostics.corpus_routing", build=_build)


def append_corrective_recall_flag_line(lines: list[str]) -> None:
    def _build() -> str:

        return f"  纠错召回: {'开' if corrective_recall_enabled() else '关'}"

    append_probe_line(lines, label="rag_diagnostics.corrective_recall", build=_build)


def append_web_fetch_flag_line(lines: list[str]) -> None:
    def _build() -> str:

        return f"  web_fetch: {'开' if web_fetch_enabled() else '关'}"

    append_probe_line(lines, label="rag_diagnostics.web_fetch", build=_build)


def append_unified_recall_flag_lines(lines: list[str]) -> None:
    def _run() -> None:

        lines.append(
            f"  统一 hybrid 召回: {'开' if unified_recall_enabled() else '关'}"
        )
        lines.append(
            f"  observation 辅助召回: {'开' if observation_recall_enabled() else '关'}"
        )

    safe_best_effort(_run, label="rag_diagnostics.unified_recall", default=None)


def mcp_profile_line(session_key: str) -> str:
    if not str(session_key or "").strip():
        return ""

    def _run() -> str:

        if mcp_profiles_enabled():
            return f"  MCP profile: {get_session_profile(session_key=session_key)}"
        return ""

    result = safe_best_effort(
        _run,
        label="rag_diagnostics.mcp_profile",
        default="",
    )
    return str(result or "")
