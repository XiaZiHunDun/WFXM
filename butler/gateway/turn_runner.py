"""Gateway turn execution — extracted from ButlerMessageHandler._handle_message_locked."""

from __future__ import annotations

import logging
import time as _time
from typing import Any

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.gateway.handler_helpers import _gateway_run_callbacks
from butler.session.lifecycle import attach_turn_memory_prefetch, sync_turn_memory

logger = logging.getLogger(__name__)


def execute_turn(
    *,
    handler,  # ButlerMessageHandler 实例（用于 _orchestrator, _session_registry, _format_response）
    loop: Any,  # AgentLoop 实例
    text: str,  # 原始用户文本
    augmented: str,  # 增强后的用户消息
    session_key: str,
    platform: str,
    external_id: str | None,
    loop_role: str,
    health: dict,  # 运行时诊断字典（可变，函数内会写入）
    welcome_prefix: str,
    prompt_hooks: Any,  # UserPromptSubmitHooks 结果
    ephemeral_system: str | None,
) -> str:
    _turn_started = _time.monotonic()

    original_loop_config = loop.config
    try:
        from butler.gateway.inbound_validate import validate_loop_messages_before_turn

        seq_err = validate_loop_messages_before_turn(loop.messages)
        if seq_err:
            return seq_err
    except Exception as exc:
        logger.debug("Loop message validation skipped: %s", exc)
    from butler.core.turn_token_budget import resolve_turn_budget

    loop.config, turn_budget, augmented = resolve_turn_budget(augmented, loop.config)
    if turn_budget:
        health["turn_token_budget"] = turn_budget
        health["turn_max_iterations"] = loop.config.max_iterations

    try:
        try:
            from butler.core.model_context import resolve_max_output_tokens

            max_out = resolve_max_output_tokens(
                handler._orchestrator,
                session_key=session_key,
                role=loop_role,
            )
            hygiene_compressed = loop.hygiene_compress_if_needed(
                max_output_tokens=max_out,
            )
            health["hygiene_compressed"] = hygiene_compressed
            health.update({
                k: v for k, v in getattr(loop, "diagnostics", {}).items()
                if str(k).startswith(("hygiene_", "context_"))
            })
        except Exception as exc:
            health["hygiene_error"] = str(exc)
            logger.warning("Gateway hygiene compression skipped: %s", exc)
        attach_turn_memory_prefetch(
            loop,
            handler._orchestrator,
            text,
            role=loop_role,
            diagnostics=health,
        )
        run_callbacks = _gateway_run_callbacks()

        def _run_turn(msg: str) -> LoopResult:
            run_kwargs: dict[str, Any] = {}
            if ephemeral_system:
                run_kwargs["ephemeral_system"] = ephemeral_system
            try:
                if run_callbacks is not None:
                    return loop.run(
                        msg,
                        run_callbacks=run_callbacks,
                        **run_kwargs,
                    )
                return loop.run(msg, **run_kwargs)
            except TypeError:
                if run_callbacks is not None:
                    return loop.run(msg, run_callbacks=run_callbacks)
                return loop.run(msg)

        try:
            from butler.core.todo_continuation import run_with_todo_continuation
            from butler.core.goal_loop import maybe_run_goal_continuation

            result = run_with_todo_continuation(
                loop,
                augmented,
                session_key,
                run_fn=_run_turn,
                run_callbacks=run_callbacks,
            )
            result = maybe_run_goal_continuation(
                loop,
                result,
                session_key,
                run_fn=_run_turn,
            )
        except Exception as exc:
            logger.debug("Todo/goal continuation fallback: %s", exc)
            result = _run_turn(augmented)
        health["loop"] = dict(getattr(result, "diagnostics", {}) or {})
        if getattr(result, "transition_reason", ""):
            health["loop_transition_reason"] = result.transition_reason
        if result.status == LoopStatus.INTERRUPTED:
            try:
                from butler.core.auto_continue import capture_auto_continue_pending

                capture_auto_continue_pending(
                    session_key,
                    user_preview=augmented,
                    reason="interrupt",
                    diagnostics=health.get("loop") if isinstance(health.get("loop"), dict) else None,
                )
            except Exception as exc:
                logger.debug("Auto continue capture skipped: %s", exc)
        sync_result = sync_turn_memory(
            handler._orchestrator,
            text,
            result.final_response or "",
            interrupted=result.status == LoopStatus.INTERRUPTED,
            status=result.status,
            session_id=session_key,
        )
        health["memory_sync"] = sync_result
        from butler.session.lifecycle import queue_prefetch_after_turn

        queue_prefetch_after_turn(
            handler._orchestrator,
            text,
            role=loop_role,
            session_id=session_key,
        )
        handler._session_registry.set_health(session_key, health)
        out = handler._format_response(result, platform)
        turn_elapsed = _time.monotonic() - _turn_started
        from butler.gateway.outbound_bridge import get_current_bridge

        br = get_current_bridge()
        if br is not None:
            br.record_turn_elapsed(turn_elapsed)
            health["outbound_events"] = br.recent_outbound_events()[-8:]
        try:
            from butler.gateway.item_event_sink import recent_thread_items

            items = recent_thread_items(8)
            if items:
                health["thread_items"] = items
        except Exception as exc:
            logger.debug("Thread items collection skipped: %s", exc)
        logger.info(
            "Gateway turn done session=%s elapsed=%.1fs out_len=%d",
            session_key,
            turn_elapsed,
            len(out or ""),
        )
        if welcome_prefix:
            out = f"{welcome_prefix}\n\n---\n\n{out}" if out else welcome_prefix
        return out
    except Exception as exc:
        health["error"] = str(exc)
        handler._session_registry.set_health(session_key, health)
        logger.error(
            "Message handling failed session=%s elapsed=%.1fs: %s",
            session_key,
            _time.monotonic() - _turn_started,
            exc,
            exc_info=True,
        )
        from butler.gateway.user_errors import format_gateway_user_error

        card = None
        try:
            from butler.gateway.error_cards import format_error_card

            exc_type = type(exc).__name__
            if "timeout" in exc_type.lower() or "Timeout" in exc_type:
                card = format_error_card(
                    "delegate_timeout",
                    role="agent",
                    elapsed=round(_time.monotonic() - _turn_started),
                )
            elif "Permission" in exc_type:
                card = format_error_card(
                    "permission_deny",
                    tool="message_handler",
                    reason=str(exc)[:200],
                )
            else:
                card = format_error_card(
                    "tool_error",
                    tool="message_handler",
                    error=str(exc),
                )
        except Exception:
            pass
        return card or format_gateway_user_error(exc)
    finally:
        loop.config = original_loop_config
