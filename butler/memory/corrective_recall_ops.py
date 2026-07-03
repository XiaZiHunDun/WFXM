"""Corrective recall fetch best-effort helpers (P0-A)."""

from __future__ import annotations

import json
from typing import Any


def fetch_corrective_recall_data_safe(
    *,
    scope: str,
    query: str,
) -> dict[str, Any] | None:
    try:
        from butler.tools.memory_tools import tool_butler_recall

        raw = tool_butler_recall(scope=scope, query=query, limit=5)
        if str(raw or "").strip().startswith("{"):
            data = json.loads(raw)
            return data if isinstance(data, dict) else {"text": raw}
        return {"text": raw}
    except Exception:
        return None
