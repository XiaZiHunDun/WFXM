"""RAG / knowledge index lines for /诊断 (Sprint C)."""

from __future__ import annotations

from typing import Any


def format_rag_diagnostic_lines(
    mem_stats: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    stats = mem_stats if isinstance(mem_stats, dict) else {}
    lines = ["RAG / 检索:"]
    sem = stats.get("semantic_enabled")
    lines.append(f"  语义索引: {'开' if sem else '关'}")
    if sem:
        lines.append(
            f"  向量行数: {stats.get('vector_rows', 0)} "
            f"(model={stats.get('vector_model') or '?'})"
        )
    kdb = stats.get("knowledge_db_keys")
    if kdb is not None:
        lines.append(f"  项目 knowledge.db keys: {kdb}")
    try:
        from butler.memory.corpus_router import corpus_routing_enabled

        lines.append(f"  多语料库路由: {'开' if corpus_routing_enabled() else '关'}")
    except Exception:
        pass
    try:
        from butler.memory.corrective_recall import corrective_recall_enabled

        lines.append(f"  纠错召回: {'开' if corrective_recall_enabled() else '关'}")
    except Exception:
        pass
    try:
        from butler.tools.web_fetch import web_fetch_enabled

        lines.append(f"  web_fetch: {'开' if web_fetch_enabled() else '关'}")
    except Exception:
        pass
    sk = str(session_key or "").strip()
    if sk:
        try:
            from butler.mcp.profiles import get_session_profile, mcp_profiles_enabled

            if mcp_profiles_enabled():
                lines.append(f"  MCP profile: {get_session_profile(session_key=sk)}")
        except Exception:
            pass
    return lines


__all__ = ["format_rag_diagnostic_lines"]
