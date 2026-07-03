"""Eval feedback best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def read_langfuse_scores_safe(
    *,
    lookback_hours: float,
    limit: int,
    snapshot_factory: Any,
) -> list[Any]:
    if not os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in ("1", "true", "yes"):
        return []

    try:
        import datetime as dt

        from langfuse import Langfuse  # type: ignore[import-untyped]

        client = Langfuse(
            host=os.getenv("LANGFUSE_HOST", "http://localhost:3000"),
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        )

        from_ts = dt.datetime.fromtimestamp(
            time.time() - lookback_hours * 3600,
            tz=dt.timezone.utc,
        )
        scores_page = client.api.score.get(limit=limit, from_timestamp=from_ts)
        snapshots: list[Any] = []
        cutoff = time.time() - lookback_hours * 3600

        for s in getattr(scores_page, "data", []) or []:
            ts = getattr(s, "timestamp", None)
            ts_epoch = 0.0
            if ts is not None:
                if hasattr(ts, "timestamp"):
                    ts_epoch = ts.timestamp()
                elif isinstance(ts, (int, float)):
                    ts_epoch = float(ts)
            if ts_epoch < cutoff:
                continue
            snapshots.append(
                snapshot_factory(
                    name=getattr(s, "name", ""),
                    value=float(getattr(s, "value", 0)),
                    comment=str(getattr(s, "comment", "") or ""),
                    trace_id=str(getattr(s, "trace_id", "") or ""),
                    timestamp=ts_epoch,
                )
            )

        client.shutdown()
        return snapshots[:limit]
    except ImportError:
        logger.debug("langfuse not installed, skip score reading")
        return []
    except Exception as exc:
        logger.warning("Failed to read LangFuse scores: %s", exc)
        return []


def routing_hint_from_overrides_safe() -> str:
    def _run() -> str:
        from butler.ops.tool_routing import routing_hint_from_overrides

        return str(routing_hint_from_overrides() or "")

    result = safe_best_effort(
        _run,
        label="eval_feedback.routing_hint",
        default="",
    )
    return str(result or "")


def build_feedback_context_safe(*, lookback_hours: float, analyse_fn: Any) -> str:
    def _run() -> str:
        report = analyse_fn(lookback_hours=lookback_hours)
        parts: list[str] = []
        if report.suggestions:
            parts.append(report.as_context_injection())
        hint = routing_hint_from_overrides_safe()
        if hint:
            parts.append(hint)
        return "\n".join(p for p in parts if p)

    result = safe_best_effort(
        _run,
        label="eval_feedback.context",
        default="",
    )
    return str(result or "")
