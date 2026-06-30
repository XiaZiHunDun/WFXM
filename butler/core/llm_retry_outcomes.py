"""LLM retry outcome metrics extracted from ``llm_retry`` (P1-C)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.llm_retry_safe import safe_call
from butler.transport.llm_client import LLMClient

logger = logging.getLogger(__name__)


def record_llm_interrupt(client: LLMClient) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        provider = str(getattr(client, "provider_name", "") or "?")[:24]
        inc("llm_request", labels={"provider": provider, "outcome": "interrupt"})

    safe_call(_run, "record interrupt skipped", _logger=logger)


def record_llm_failure(client: LLMClient, last_error: Exception | None) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        provider = str(getattr(client, "provider_name", "") or "?")[:24]
        inc("llm_request", labels={"provider": provider, "outcome": "fail"})
        if last_error is not None:
            err_type = type(last_error).__name__
            inc("llm_error", labels={"provider": provider, "error_type": err_type})

    safe_call(_run, "record failure skipped", _logger=logger)


__all__ = ["record_llm_failure", "record_llm_interrupt"]
