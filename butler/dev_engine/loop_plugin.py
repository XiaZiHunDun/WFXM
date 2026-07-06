"""DevEnginePlugin — injects DevState context into LLM messages.

Registered as a LoopPlugin when role=dev and BUTLER_DEV_ENGINE=1.
Implements:
  - before_model: inject dev_state_context_block + fix hints
  - after_tools: inject diagnostics after verify failures
"""

from __future__ import annotations

import os
from typing import Any, cast


def verify_fix_pin_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_VERIFY_FIX_PIN", "1")
    return raw.strip().lower() in ("1", "true", "yes", "on")


class DevEnginePlugin:
    """Loop plugin that injects DevState into LLM context (DD1/DD2)."""

    def __init__(self, session_key: str = "_default"):
        self._session_key = session_key

    def before_model(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Inject DevState summary as a system-level context block."""
        from butler.dev_engine.loop_plugin_ops import inject_dev_before_model_safe

        return cast(list[dict[str, Any]], inject_dev_before_model_safe(self._session_key, messages))

    def after_tools(
        self,
        messages: list[dict[str, Any]],
        *,
        tool_stats: Any = None,
    ) -> list[dict[str, Any]]:
        """After tool batch, inject diagnostic summary if verify failed."""
        from butler.dev_engine.loop_plugin_ops import inject_dev_after_tools_safe

        return cast(list[dict[str, Any]], inject_dev_after_tools_safe(self._session_key, messages))


def create_dev_engine_plugin(session_key: str = "_default") -> DevEnginePlugin:
    return DevEnginePlugin(session_key=session_key)
