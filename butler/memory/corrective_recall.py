"""Corrective recall after tool failures (awesome-llm-apps corrective RAG subset)."""

from __future__ import annotations

import json
import re

from butler.memory_settings import resolve_memory_config

_FAILURE_HINTS = (
    "error",
    "failed",
    "failure",
    "exception",
    "not found",
    "permission denied",
    "timeout",
)


def corrective_recall_enabled() -> bool:
    return resolve_memory_config().corrective_recall_enabled


def should_trigger_corrective(tool_name: str, result_text: str) -> bool:
    if not corrective_recall_enabled():
        return False
    name = str(tool_name or "").strip()
    if not name or name in {"butler_recall", "search_project_knowledge"}:
        return False
    body = str(result_text or "").strip().lower()
    if len(body) < 8:
        return False
    if body.startswith("{") and '"error"' in body:
        return True
    return any(h in body for h in _FAILURE_HINTS)


def extract_query_from_task(task: str, *, max_len: int = 200) -> str:
    text = re.sub(r"\s+", " ", str(task or "").strip())
    return text[:max_len] if text else ""


def build_corrective_recall_block(
    *,
    task: str,
    tool_name: str,
    error_excerpt: str,
    scope: str = "project",
) -> str:
    """Run a lightweight recall and return markdown appendix for delegate context."""
    from butler.tools.memory_tools import tool_butler_recall

    query = extract_query_from_task(task)
    if not query:
        query = extract_query_from_task(error_excerpt, max_len=120)
    if not query:
        return ""
    try:
        raw = tool_butler_recall(scope=scope, query=query, limit=5)
        data = json.loads(raw) if raw.strip().startswith("{") else {"text": raw}
    except Exception:
        return ""
    hits = data.get("results") or data.get("items") or data.get("matches")
    if not hits and not data.get("content") and not data.get("text"):
        return ""
    lines = [
        "## Corrective recall",
        f"- 触发: 工具 `{tool_name}` 失败后的项目/经验检索",
        f"- 查询: {query[:120]}",
    ]
    if isinstance(hits, list):
        for i, row in enumerate(hits[:3], 1):
            if isinstance(row, dict):
                snippet = str(row.get("content") or row.get("text") or row)[:240]
            else:
                snippet = str(row)[:240]
            lines.append(f"  {i}. {snippet}")
    else:
        snippet = str(data.get("content") or data.get("text") or "")[:400]
        if snippet:
            lines.append(f"  - {snippet}")
    return "\n".join(lines)


__all__ = [
    "build_corrective_recall_block",
    "corrective_recall_enabled",
    "should_trigger_corrective",
]
