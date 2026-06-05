"""RAG / knowledge index lines for /诊断 (Sprint C)."""

from __future__ import annotations

from typing import Any
import logging


logger = logging.getLogger(__name__)


def _memory_substats_lines(stats: dict[str, Any]) -> list[str]:
    # Audit R2-4: orchestrator-level memory facade failed to initialize.
    # This is the worst-case degradation: every recall returns empty, but
    # the model has no way to know that. /诊断 must surface it loudly.
    lines: list[str] = []
    if stats.get("memory_offline"):
        err = str(stats.get("memory_init_error") or "").strip()
        suffix = f" ({err})" if err else ""
        lines.append(f"  记忆子系统: 离线 (initialization failed){suffix}")
    sem = stats.get("semantic_enabled")
    lines.append(f"  语义索引: {'开' if sem else '关'}")
    try:
        from butler.memory.semantic_config import hybrid_fts_weight, hybrid_vector_weight

        lines.append(
            f"  混合权重: 向量 {hybrid_vector_weight():.2f} / FTS {hybrid_fts_weight():.2f}"
        )
    except Exception as exc:
        logger.debug("format rag diagnostic lines skipped: %s", exc)
    if sem:
        lines.append(
            f"  向量行数: {stats.get('vector_rows', 0)} "
            f"(model={stats.get('vector_model') or '?'})"
        )
    # Audit R2-3: embedding provider degradation (e.g. openai key missing,
    # fastembed init failed, API probe timed out). Without this line the user
    # silently gets 64-bit hashing recall and never knows.
    if stats.get("embedding_degraded"):
        req_provider = str(stats.get("embedding_requested_provider") or "?")
        req_model = str(stats.get("embedding_requested_model") or "?")
        used_model = str(stats.get("embedding_used_model") or "hashing-v1")
        lines.append(
            f"  嵌入质量降级: 请求 {req_provider}/{req_model} → "
            f"实际使用 {used_model}"
        )
    kdb = stats.get("knowledge_db_keys")
    if kdb is not None:
        lines.append(f"  项目 knowledge.db keys: {kdb}")
    return lines


def _retrieval_history_lines(stats: dict[str, Any]) -> list[str]:
    # Audit R2-2: when the hybrid/vector path raised and we fell back to
    # FTS-only, the user (and the operator looking at /诊断) MUST see this.
    lines: list[str] = []
    last_mode = str(stats.get("rag_last_mode") or "").strip()
    if last_mode:
        lines.append(f"  最近检索模式: {last_mode}")
    if stats.get("rag_last_fallbacks") is not None and last_mode:
        lines.append(f"  最近 fallback: {int(stats.get('rag_last_fallbacks') or 0)}")
    if stats.get("rag_last_recall_degraded"):
        lines.append("  检索质量降级: 上轮 hybrid_search 异常,仅用 FTS")
    if stats.get("rag_last_candidates") is not None and last_mode:
        lines.append(f"  最近候选数: {int(stats.get('rag_last_candidates') or 0)}")
    last_query = str(stats.get("rag_last_query") or "").strip()
    if last_query:
        lines.append(f"  最近检索词: {last_query[:80]}")
    sub_n = stats.get("rag_last_sub_queries")
    if sub_n:
        lines.append(f"  最近子 query 数: {int(sub_n)}")
    return lines


def _mcp_degraded_lines(stats: dict[str, Any]) -> list[str]:
    # Audit R2-6: surface degraded MCP servers so the user (and operator
    # looking at /诊断) can see WHICH MCP servers are down and which
    # transport failed, not just the user-side "Unknown MCP tool" complaint.
    # Accepts either a list of (server_id, transport, last_error) tuples
    # (preferred, from McpConnectionManager.degraded_servers) or a plain
    # list of server_ids for backward compatibility.
    lines: list[str] = []
    degraded = stats.get("mcp_degraded")
    if not (isinstance(degraded, list) and degraded):
        return lines
    if isinstance(degraded[0], (tuple, list)) and len(degraded[0]) >= 3:
        rows = [(str(r[0]), str(r[1]), str(r[2])) for r in degraded]
    else:
        rows = [(str(sid), "?", "") for sid in degraded]
    lines.append(f"  MCP 降级: {len(rows)} 个 server 不可用")
    for sid, transport, err in rows:
        suffix = f": {err[:120]}" if err else ""
        lines.append(f"    - {sid} ({transport}){suffix}")
    return lines


def _feature_flag_lines() -> list[str]:
    lines: list[str] = []
    try:
        from butler.memory.query_decompose import subquery_enabled

        lines.append(f"  子 query 分解: {'开' if subquery_enabled() else '关'}")
    except Exception as exc:
        logger.debug("format rag diagnostic lines skipped: %s", exc)
    try:
        from butler.memory.corpus_router import corpus_routing_enabled

        lines.append(f"  多语料库路由: {'开' if corpus_routing_enabled() else '关'}")
    except Exception as exc:
        logger.debug("format rag diagnostic lines skipped: %s", exc)
    try:
        from butler.memory.corrective_recall import corrective_recall_enabled

        lines.append(f"  纠错召回: {'开' if corrective_recall_enabled() else '关'}")
    except Exception as exc:
        logger.debug("format rag diagnostic lines skipped: %s", exc)
    try:
        from butler.tools.web_fetch import web_fetch_enabled

        lines.append(f"  web_fetch: {'开' if web_fetch_enabled() else '关'}")
    except Exception as exc:
        logger.debug("format rag diagnostic lines skipped: %s", exc)
    return lines


def _mcp_profile_line(session_key: str) -> str:
    if not str(session_key or "").strip():
        return ""
    try:
        from butler.mcp.profiles import get_session_profile, mcp_profiles_enabled

        if mcp_profiles_enabled():
            return f"  MCP profile: {get_session_profile(session_key=session_key)}"
    except Exception as exc:
        logger.debug("format rag diagnostic lines skipped: %s", exc)
    return ""


def format_rag_diagnostic_lines(
    mem_stats: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    stats = mem_stats if isinstance(mem_stats, dict) else {}
    lines: list[str] = ["RAG / 检索:"]
    lines.extend(_memory_substats_lines(stats))
    lines.extend(_retrieval_history_lines(stats))
    lines.extend(_mcp_degraded_lines(stats))
    lines.extend(_feature_flag_lines())
    profile = _mcp_profile_line(session_key)
    if profile:
        lines.append(profile)
    return lines


__all__ = ["format_rag_diagnostic_lines"]
