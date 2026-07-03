"""LangFuse sink — wraps eval_bridge when enabled."""

from __future__ import annotations

from typing import Any

from butler.contracts.eval_ports import SuiteRunResult


class LangFuseSink:
    backend_id = "langfuse"

    def write_suite_result(self, result: SuiteRunResult, payload: dict[str, Any]) -> str:
        from butler.eval_integration.sinks.langfuse_sink_ops import (
            push_langfuse_suite_scores_safe,
        )

        return push_langfuse_suite_scores_safe(result)

    def read_latest(self, suite_id: str) -> dict[str, Any] | None:
        return None
