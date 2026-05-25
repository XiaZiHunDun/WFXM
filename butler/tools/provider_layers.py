"""Tool provider layering for diagnostics (Dify ToolProvider subset)."""

from __future__ import annotations

from collections import Counter


def tool_provider_layer(name: str) -> str:
    n = str(name or "").strip()
    if not n:
        return "unknown"
    if n.startswith("mcp_") or n.startswith("mcp."):
        return "mcp"
    if n in {"run_workflow", "delegate_task"}:
        return "workflow"
    if n in {"butler_remember", "butler_recall", "search_transcript"}:
        return "memory"
    if n.startswith("http_") or n.endswith("_http"):
        return "http"
    return "builtin"


def summarize_tool_layers(tool_names: list[str]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for name in tool_names:
        counts[tool_provider_layer(name)] += 1
    return dict(counts)


def format_tool_layers_line(tool_names: list[str]) -> str:
    summary = summarize_tool_layers(tool_names)
    if not summary:
        return "工具分层: (无)"
    parts = [f"{layer}={count}" for layer, count in sorted(summary.items())]
    return "工具分层: " + ", ".join(parts)
