"""Best-effort and fail-closed helpers for ``AgentLoop`` (P0-A / P2-F)."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort
from butler.transport.fallback import FallbackEntry
from butler.permissions.doom_loop import check_doom_loop_ask
from butler.tool_guardrails import synthetic_result
from butler.transport.provider_health import filter_fallback_chain
from butler.ops.runtime_metrics import inc
from butler.core.agent_loop_phases import _phase_maybe_compact_turn
from butler.core.loop_types import LoopStatus
from butler.hooks.runner import run_stop_hooks
from butler.transport.provider_health import record_provider_failure
from butler.core.context_transform_registry import refresh_model_binding
from butler.core.reflexion_ephemeral import maybe_apply_reflexion

logger = logging.getLogger(__name__)


def doom_loop_block_on_ask(decision: Any, tool_name: str, args: dict[str, Any]) -> str | None:
    """Fail-closed doom-loop ask gate for prefetched tool calls."""
    try:

        if check_doom_loop_ask(decision, tool_name, args):

            return str(synthetic_result(decision))
    except Exception:
        logger.exception(
            "Doom-loop ask check failed; failing closed (synthetic block) for %s",
            tool_name,
        )

        return str(synthetic_result(decision))
    return None


def filter_fallback_chain_safe(chain: list[FallbackEntry]) -> list[FallbackEntry]:
    def _run() -> list[FallbackEntry]:

        out = filter_fallback_chain(chain)
        return out if isinstance(out, list) else chain

    result = safe_best_effort(
        _run,
        label="agent_loop.fallback_chain_filter",
        default=None,
    )
    return chain if result is None else result


def emit_skipped_plugin_metric(label: str) -> None:
    def _run() -> None:

        inc("best_effort_skip", labels={"path": label[:48]})

    safe_best_effort(_run, label="agent_loop.skipped_plugin_metric", default=None)


def maybe_compact_turn_safe(loop: Any, state: Any) -> bool:

    return bool(
        run_plugin_step(
            loop,
            "compact_turn",
            lambda: _phase_maybe_compact_turn(loop, state),
            default=False,
        )
    )


def run_stop_hooks_safe(
    loop: Any,
    *,
    steer_session: str,
    iteration: int,
    start_time: float,
    final_text: str,
) -> Any | None:
    def _run() -> Any:

        return run_stop_hooks(
            status=LoopStatus.RUNNING.value,
            last_assistant_message=final_text,
            session_key=steer_session,
            iterations=iteration,
            tool_calls=loop._tool_calls_count,
            elapsed_seconds=time.time() - start_time,
        )

    return run_plugin_step(loop, "stop_hooks", _run, default=None)


def record_provider_failure_safe(loop: Any) -> None:
    def _run() -> None:

        record_provider_failure(
            getattr(loop.client, "provider", "") or "",
            getattr(loop.client, "model", "") or "",
        )

    run_plugin_step(loop, "provider_failure_recording", _run, default=None)


def refresh_model_binding_safe(loop: Any) -> None:
    def _run() -> None:

        refresh_model_binding(loop)

    run_plugin_step(loop, "refresh_model_binding", _run, default=None)


def run_after_tools_plugins_safe(loop: Any, stats: Any) -> None:
    def _run() -> None:
        loop._messages[:] = loop._plugins.after_tools(
            loop._messages,
            tool_stats=stats,
        )

    run_plugin_step(loop, "after_tools_middleware", _run, default=None)


def apply_reflexion_safe(loop: Any) -> None:
    if loop._guardrails is None:
        return

    def _run() -> None:
        counts = getattr(loop._guardrails, "_same_tool_failure_counts", {}) or {}
        if not counts:
            return
        worst_tool, worst_n = max(counts.items(), key=lambda kv: kv[1])

        maybe_apply_reflexion(
            loop.diagnostics,
            tool_name=worst_tool,
            failure_count=int(worst_n),
        )

    run_plugin_step(loop, "reflexion_apply", _run, default=None)


def run_plugin_step(loop: Any, label: str, fn: Callable[[], Any], *, default: Any = None) -> Any:
    try:
        return fn()
    except Exception as exc:
        loop._record_skipped_plugin(label, exc)
        return default


__all__ = [
    "apply_reflexion_safe",
    "doom_loop_block_on_ask",
    "emit_skipped_plugin_metric",
    "filter_fallback_chain_safe",
    "maybe_compact_turn_safe",
    "record_provider_failure_safe",
    "refresh_model_binding_safe",
    "run_after_tools_plugins_safe",
    "run_plugin_step",
    "run_stop_hooks_safe",
]
