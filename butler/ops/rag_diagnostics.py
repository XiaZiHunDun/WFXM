"""RAG / knowledge index lines for /诊断 (Sprint C)."""

from __future__ import annotations

from typing import Any

from butler.ops.rag_diagnostics_ops import (
    append_corrective_recall_flag_line,
    append_corpus_routing_flag_line,
    append_hybrid_weights_line,
    append_subquery_flag_line,
    append_unified_recall_flag_lines,
    append_web_fetch_flag_line,
    mcp_profile_line,
    recall_scope_order,
)


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
    append_hybrid_weights_line(lines)
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
    by_scope = stats.get("rag_by_scope")
    if isinstance(by_scope, dict) and by_scope:
        lines.append("  各 scope 最近召回:")
        order = recall_scope_order(by_scope)
        for scope in order:
            item = by_scope.get(scope) or {}
            mode = str(item.get("mode") or "?").strip()
            cand = int(item.get("candidates") or 0)
            q = str(item.get("query") or "").strip()[:60]
            fb = int(item.get("fallbacks") or 0)
            extra = f" fallback={fb}" if fb else ""
            degraded = " [降级]" if item.get("recall_degraded") else ""
            q_part = f' q="{q}"' if q else ""
            lines.append(
                f"    {scope}: mode={mode} candidates={cand}{extra}{q_part}{degraded}"
            )
        return lines

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
    append_subquery_flag_line(lines)
    append_corpus_routing_flag_line(lines)
    append_corrective_recall_flag_line(lines)
    append_web_fetch_flag_line(lines)
    append_unified_recall_flag_lines(lines)
    return lines


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
    profile = mcp_profile_line(session_key)
    if profile:
        lines.append(profile)
    return lines


__all__ = ["format_rag_diagnostic_lines"]
