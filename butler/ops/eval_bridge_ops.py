"""Eval bridge LangFuse helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def get_langfuse_client_safe() -> Any:
    def _run() -> Any:
        from butler.ops.langfuse_tracer import _get_client

        return _get_client()

    return safe_best_effort(_run, label="eval_bridge.langfuse_client", default=None)


def push_score_loud(client: Any, *, kwargs: dict[str, Any], score_name: str) -> bool:
    try:
        client.score(**kwargs)
        logger.debug("Pushed score: %s = %.4f", score_name, kwargs.get("value", 0))
        return True
    except Exception as exc:
        logger.warning("Failed to push score '%s': %s", score_name, exc)
        return False


def flush_langfuse_client_safe(client: Any) -> None:
    def _run() -> None:
        client.flush()

    safe_best_effort(_run, label="eval_bridge.langfuse_flush", default=None)


def create_dataset_loud(client: Any, *, name: str, description: str) -> str | None:
    try:
        ds = client.create_dataset(name=name, description=description)
        return str(getattr(ds, "id", name))
    except Exception as exc:
        logger.warning("Failed to create dataset '%s': %s", name, exc)
        return None


def push_dataset_item_loud(client: Any, *, kwargs: dict[str, Any]) -> bool:
    try:
        client.create_dataset_item(**kwargs)
        return True
    except Exception as exc:
        logger.warning("Failed to push dataset item: %s", exc)
        return False
