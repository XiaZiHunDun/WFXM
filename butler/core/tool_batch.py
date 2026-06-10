"""Tool call batch execution extracted from AgentLoop."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.parallel_tools import execute_tools_parallel
from butler.core.steer import apply_steer_to_tool_results
from butler.tool_guardrails import (
    GuardrailDecision,
    ToolCallGuardrailController,
    append_guidance,
    synthetic_result,
)
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


_EDIT_TOOL_NAMES = frozenset({"write_file", "patch", "delete_file"})

_OP_NAME_MAP = {"write_file": "write", "delete_file": "delete", "patch": "patch"}

_pre_edit_snapshots: dict[str, str] = {}


def _capture_pre_edit_snapshot(name: str, args: dict) -> None:
    """Capture file content before an edit tool runs (for rollback)."""
    if name not in _EDIT_TOOL_NAMES:
        return
    path = str(args.get("path") or "")
    if not path:
        return
    try:
        from pathlib import Path as _Path
        p = _Path(path)
        if not p.is_absolute():
            from butler.tools.safe_root import get_tool_safe_root
            p = get_tool_safe_root() / p
        if p.is_file() and p.stat().st_size < 512_000:
            _pre_edit_snapshots[str(p.resolve())] = p.read_text(encoding="utf-8")
    except Exception:
        pass


def _fetch_pre_edit_snapshot(path: str) -> str | None:
    """Pop a pre-edit snapshot if available."""
    try:
        from pathlib import Path as _Path
        p = _Path(path)
        if not p.is_absolute():
            from butler.tools.safe_root import get_tool_safe_root
            p = get_tool_safe_root() / p
        return _pre_edit_snapshots.pop(str(p.resolve()), None)
    except Exception:
        return None


def _dev_engine_post_edit(name: str, args: dict, result: str) -> None:
    """Record edit in DevState with proper snapshots for rollback (DD4).

    Called from ``_dispatch_one`` after a successful edit tool,
    where both ``args`` and ``result`` are available.
    """
    if name not in _EDIT_TOOL_NAMES:
        return
    if _tool_result_outcome(result) != "ok":
        return
    try:
        from butler.dev_engine.dev_tools import (
            _active_states,
            dev_engine_enabled,
        )

        if not dev_engine_enabled():
            return
        from butler.execution_context import get_current_session_key

        sk = str(get_current_session_key() or "").strip() or "_default"
        state = _active_states.get(sk)
        if state is None:
            return

        import time

        from butler.dev_engine.dev_state import EditRecord

        path = str(args.get("path") or "")
        if not path:
            try:
                import json as _j
                parsed = _j.loads(result)
                path = str(parsed.get("path") or parsed.get("file") or "")
            except Exception:
                pass

        op = _OP_NAME_MAP.get(name, name)
        record = EditRecord(path=path, operation=op, timestamp=time.time())

        snapshot = _fetch_pre_edit_snapshot(path)
        if op == "patch":
            record.patch_old = str(args.get("old_string") or "")
            record.patch_new = str(args.get("new_string") or "")
            record.original_content = snapshot
        elif op == "write":
            record.new_content = str(args.get("content") or "")
            record.original_content = snapshot
        elif op == "delete":
            record.original_content = snapshot

        from butler.dev_engine.dev_loop import transition
        transition(state, "edit_success", edit_record=record)

        from butler.dev_engine.dev_tools import auto_verify_enabled
        if auto_verify_enabled() and path:
            _run_auto_verify(state, path)
    except Exception:
        pass


def _run_auto_verify(state: Any, path: str) -> None:
    """Run auto-verify after edit and inject fix hints (DD2 + DA4 + CA4)."""
    try:
        from pathlib import Path as _Path

        from butler.dev_engine.dev_loop import transition
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.verify import verify_layered

        try:
            from butler.tools.safe_root import get_tool_safe_root
            ws = _Path(get_tool_safe_root())
        except Exception:
            ws = _Path(path).parent
        from butler.dev_engine.verify import auto_verify_levels, verify_level_for_edit

        edited_files = [path] if path else []
        levels = auto_verify_levels() or verify_level_for_edit(edited_files)
        result = verify_layered(ws, levels=levels)

        thm_violations: list[str] = []
        activated = getattr(state, "_coding_knowledge_theorems", None)
        if activated and state.edit_history:
            try:
                from butler.dev_engine.coding_knowledge import dual_verify as ck_dual_verify
                last_edit = state.edit_history[-1]
                code = last_edit.new_content or last_edit.patch_new or ""
                if code:
                    ck_result = ck_dual_verify(
                        code, activated,
                        test_passed=result.passed,
                        test_detail=f"auto-verify: {result.status.value}",
                    )
                    thm_violations = ck_result.violated_theorems
                    state.coding_knowledge.violated_theorems = thm_violations
            except Exception:
                pass

        if result.passed and not thm_violations:
            transition(state, "verify_pass")
        else:
            transition(state, "verify_fail", verify_result=result)
            if state.phase == DevPhase.FIX:
                transition(state, "fix_applied")
            try:
                from butler.dev_engine.fix_strategy import suggest_fix_action
                fix_level = suggest_fix_action(result.diagnostics, state)
                state._last_fix_hint = fix_level.value
            except Exception:
                pass
    except Exception:
        pass


def _tool_result_outcome(result: str) -> str:
    text = (result or "").strip()
    if not text:
        return "ok"
    head = text[:240].lower()
    if head.startswith("error:") or head.startswith('{"error"'):
        return "error"
    if text.startswith("{") and '"error"' in head:
        return "error"
    return "ok"


@dataclass(frozen=True)
class ToolBatchStats:
    """Counters produced while executing a tool batch."""

    tools_started: int = 0
    clarification_question: str | None = None
    waiting_confirmation_message: str | None = None


def append_assistant_tool_calls(
    messages: list[dict],
    response: NormalizedResponse,
) -> None:
    """Append the assistant message that requested tool calls."""
    from butler.transport.reasoning_replay import store_reasoning_on_message

    assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
    store_reasoning_on_message(assistant_msg, response.reasoning)
    tool_call_records = []
    for tc in response.tool_calls or []:
        tc_id = tc.id or f"call_{uuid.uuid4().hex[:8]}"
        if not tc.id:
            tc.id = tc_id
        tool_call_records.append({
            "id": tc_id,
            "type": "function",
            "function": {"name": tc.name, "arguments": tc.arguments},
        })
    assistant_msg["tool_calls"] = tool_call_records
    messages.append(assistant_msg)


def process_tool_calls(
    *,
    response: NormalizedResponse,
    messages: list[dict],
    config: LoopConfig,
    callbacks: LoopCallbacks,
    guardrails: ToolCallGuardrailController | None,
    dispatch_tool: Callable[[str, dict], str],
    interrupt_check: Callable[[], bool],
    prefetched: dict[str, str] | None = None,
) -> ToolBatchStats:
    """Run a tool batch and append tool role messages."""
    if not response.tool_calls:
        return ToolBatchStats()

    try:
        from butler.core.finish_tool_truncate import truncate_tool_calls_at_finish

        truncated = truncate_tool_calls_at_finish(list(response.tool_calls))
        if len(truncated) < len(response.tool_calls):
            response.tool_calls = truncated
    except Exception as exc:
        logger.debug("process tool calls skipped: %s", exc)
    if callbacks.on_stream_boundary:
        callbacks.on_stream_boundary()

    append_assistant_tool_calls(messages, response)

    if guardrails and guardrails.halt_decision:
        return ToolBatchStats()

    tools_started = 0
    batch_guard = None
    try:
        from butler.core.batch_sequence_guard import BatchSequenceGuard, batch_stale_guard_enabled

        if batch_stale_guard_enabled():
            batch_guard = BatchSequenceGuard()
    except Exception:
        batch_guard = None

    from butler.core.tool_call_limits import get_tool_call_limiter
    from butler.core.tool_retry import run_tool_with_retry
    from butler.core.tool_result_cache import get_cached_result, set_cached_result
    from butler.execution_context import get_current_session_key

    def _dispatch_one(name: str, args: dict, *, tool_call_id: str = "") -> str:
        try:
            from butler.core.two_phase_confirm import two_phase_block_message

            block = two_phase_block_message(
                name,
                args,
                tool_call_id=tool_call_id,
            )
            if block:
                return finalize_fallback_tool_result(
                    name,
                    args,
                    {
                        "ok": False,
                        "code": "TWO_PHASE_PENDING",
                        "error": block,
                        "tool": name,
                    },
                )
        except Exception as exc:
            logger.debug("dispatch one skipped: %s", exc)
        if batch_guard is not None and batch_guard.should_skip_stale_read(name, args):
            from butler.core.batch_sequence_guard import (
                STALE_PREFETCH_CODE,
                STALE_SKIP_CODE,
                stale_skip_result,
            )

            code = (
                STALE_PREFETCH_CODE
                if prefetched and tool_call_id and tool_call_id in prefetched
                else STALE_SKIP_CODE
            )
            payload = stale_skip_result(name, args, guard=batch_guard, code=code)
            return finalize_fallback_tool_result(name, args, payload)
        if prefetched and tool_call_id and tool_call_id in prefetched:
            result = prefetched[tool_call_id]
            if batch_guard is not None:
                batch_guard.note_tool_result(name, args, result)
            return result
        session_key = str(get_current_session_key() or "").strip()
        cached = get_cached_result(name, args, session_key=session_key)
        if cached is not None:
            result = cached
            pending_warn = None
            if guardrails:
                before = guardrails.before_call(name, args)
                if before.action == "warn" and before.code == "doom_loop_soft_nudge":
                    pending_warn = before
                if before.should_halt:
                    return finalize_fallback_tool_result(name, args, synthetic_result(before))
                after = guardrails.after_call(name, args, result)
                if after.should_halt:
                    guardrails.set_halt_decision(after)
                    return finalize_guardrail_halt_result(name, args, result, after)
                if after.action == "warn":
                    result = append_guidance(result, after)
                elif pending_warn is not None:
                    result = append_guidance(result, pending_warn)
            return result
        blocked = get_tool_call_limiter().before_call(name)
        if blocked:
            return finalize_fallback_tool_result(name, args, blocked)
        pending_warn = None
        if guardrails:
            before = guardrails.before_call(name, args)
            if before.action == "warn" and before.code == "doom_loop_soft_nudge":
                pending_warn = before
            if before.action == "ask" and before.code == "doom_loop":
                try:
                    from butler.permissions.doom_loop import check_doom_loop_ask

                    block_msg = check_doom_loop_ask(before, name, args)
                    if block_msg:
                        ask_dec = GuardrailDecision(
                            action="block",
                            code="doom_loop",
                            message=block_msg,
                            tool_name=name,
                        )
                        return finalize_fallback_tool_result(
                            name, args, synthetic_result(ask_dec)
                        )
                except Exception:
                    return finalize_fallback_tool_result(name, args, synthetic_result(before))
            if before.should_halt:
                return finalize_fallback_tool_result(name, args, synthetic_result(before))
        _capture_pre_edit_snapshot(name, args)
        result = run_tool_with_retry(name, args, dispatch_tool)
        try:
            from butler.core.tool_error_policy import (
                apply_tool_error_policy,
                should_halt_loop_on_tool_error,
            )

            result = apply_tool_error_policy(result, tool_name=name)
            if should_halt_loop_on_tool_error(result, tool_name=name) and guardrails:
                guardrails.set_halt_decision(
                    GuardrailDecision(
                        action="block",
                        code="tool_error_stop",
                        message="工具错误策略: stop（勿重复同调用）",
                        tool_name=name,
                    )
                )
        except Exception as exc:
            logger.debug("dispatch one skipped: %s", exc)
        set_cached_result(name, args, result, session_key=session_key)
        if guardrails:
            after = guardrails.after_call(name, args, result)
            if after.should_halt:
                guardrails.set_halt_decision(after)
                try:
                    from butler.ops.retry_buckets import record_recovery_event

                    reason = str(getattr(after, "reason", "") or "tool_guardrail_halt")[:32]
                    record_recovery_event(reason or "tool_guardrail_halt")
                except Exception as exc:
                    logger.debug("dispatch one skipped: %s", exc)
                result = finalize_guardrail_halt_result(name, args, result, after)
            elif after.action == "warn":
                result = append_guidance(result, after)
            elif pending_warn is not None:
                result = append_guidance(result, pending_warn)
        if batch_guard is not None:
            batch_guard.note_tool_result(name, args, result)
        _dev_engine_post_edit(name, args, result)
        return result

    def _transcript_source() -> str:
        try:
            from butler.execution_context import get_current_workflow_step

            if get_current_workflow_step():
                return "workflow"
            from butler.core.delegate_context import get_parent_messages

            if get_parent_messages():
                return "delegate"
        except Exception as exc:
            logger.debug("transcript source skipped: %s", exc)
        return "loop"

    def _on_start(name: str, args: dict) -> None:
        nonlocal tools_started
        tools_started += 1
        try:
            import json as _json

            from butler.core.session_transcript import record_tool_action
            from butler.execution_context import get_current_session_key

            sk = str(get_current_session_key() or "").strip()
            if sk:
                record_tool_action(
                    sk,
                    tool_name=name,
                    args_preview=_json.dumps(args, ensure_ascii=False, default=str)[:400],
                    source=_transcript_source(),
                )
        except Exception as exc:
            logger.debug("on start skipped: %s", exc)
        if callbacks.on_tool_start:
            callbacks.on_tool_start(name, args)

    def _on_complete(name: str, result: str) -> None:
        try:
            from butler.ops.runtime_metrics import inc

            outcome = _tool_result_outcome(result)
            tool_label = str(name or "?")[:48]
            inc("tool_call", labels={"tool": tool_label, "outcome": outcome})
        except Exception as exc:
            logger.debug("on complete skipped: %s", exc)
        try:
            from butler.ops.cost_tracker import get_session_cost

            session_key = str(get_current_session_key() or "").strip()
            if session_key:
                get_session_cost(session_key).record_tool_call(name)
        except Exception:
            pass
        try:
            from butler.core.pim_state import on_pim_tool_success

            outcome = _tool_result_outcome(result)
            if outcome == "ok":
                on_pim_tool_success(name)
        except Exception:
            pass
        if callbacks.on_tool_complete:
            callbacks.on_tool_complete(name, result)

    def _precheck_tool(name: str, args: dict) -> str | None:
        if interrupt_check():
            return finalize_fallback_tool_result(
                name,
                args,
                {"error": "interrupted", "code": "TOOL_INTERRUPTED"},
            )
        if guardrails and guardrails.halt_decision:
            return finalize_fallback_tool_result(
                name,
                args,
                synthetic_result(guardrails.halt_decision),
            )
        if batch_guard is not None and batch_guard.should_skip_stale_read(name, args):
            from butler.core.batch_sequence_guard import stale_skip_result

            return finalize_fallback_tool_result(
                name,
                args,
                stale_skip_result(name, args, guard=batch_guard),
            )
        return None

    if config.enable_parallel_tools and len(response.tool_calls) > 1:
        pairs = execute_tools_parallel(
            response.tool_calls,
            lambda n, a, *, tool_call_id="": _dispatch_one(n, a, tool_call_id=tool_call_id),
            on_start=_on_start,
            on_complete=_on_complete,
            check_interrupt=interrupt_check,
            precheck_tool=_precheck_tool,
            prefetched=prefetched,
        )
    else:
        pairs = []
        batch_interrupted = False
        for tc in response.tool_calls:
            try:
                args = tc.args_dict()
            except Exception as exc:
                logger.warning("args_dict() parse failed for tool %s: %s", tc.name, exc)
                args = {}
            if batch_interrupted or interrupt_check():
                batch_interrupted = True
                result = finalize_fallback_tool_result(
                    tc.name,
                    args,
                    {"error": "interrupted", "code": "TOOL_INTERRUPTED"},
                )
                pairs.append((tc, result))
                continue
            if guardrails and guardrails.halt_decision:
                pairs.append((
                    tc,
                    finalize_fallback_tool_result(
                        tc.name,
                        args,
                        synthetic_result(guardrails.halt_decision),
                    ),
                ))
                continue
            if batch_guard is not None and batch_guard.should_skip_stale_read(tc.name, args):
                from butler.core.batch_sequence_guard import stale_skip_result

                pairs.append((
                    tc,
                    finalize_fallback_tool_result(
                        tc.name,
                        args,
                        stale_skip_result(tc.name, args, guard=batch_guard),
                    ),
                ))
                continue
            _on_start(tc.name, args)
            result = _dispatch_one(tc.name, args, tool_call_id=str(tc.id or ""))
            _on_complete(tc.name, result)
            pairs.append((tc, result))
            if interrupt_check():
                batch_interrupted = True

    from butler.core.tool_result_storage import (
        maybe_spill_tool_result,
        normalize_empty_tool_result,
    )

    session_key = str(get_current_session_key() or "").strip()
    for tc, result in pairs:
        normalized = normalize_empty_tool_result(result, tool_name=tc.name)
        content = maybe_spill_tool_result(
            normalized,
            tool_name=tc.name,
            tool_use_id=tc.id or "",
            session_key=session_key,
        )
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "content": content,
        })

    apply_steer_to_tool_results(messages, len(pairs))

    clarification: str | None = None
    waiting: str | None = None
    for tc, result in pairs:
        payload = parse_tool_result_object(result)
        if isinstance(payload, dict) and payload.get("code") == "TWO_PHASE_PENDING":
            waiting = str(payload.get("error") or "").strip() or None
            if waiting:
                break
        if tc.name != "ask_clarification":
            continue
        if isinstance(payload, dict) and payload.get("code") == "CLARIFICATION":
            clarification = str(payload.get("question") or "").strip() or None
            if clarification:
                break

    return ToolBatchStats(
        tools_started=tools_started,
        clarification_question=clarification,
        waiting_confirmation_message=waiting,
    )


def dispatch_tool_with_envelope(
    tool_dispatcher: Callable[[str, dict], str] | None,
    name: str,
    args: dict,
) -> str:
    """Dispatch through the configured handler and normalize failures."""
    if tool_dispatcher:
        try:
            result = tool_dispatcher(name, args)
            return finalize_unenveloped_failure_result(name, args, result)
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return finalize_fallback_tool_result(
                name,
                args,
                {
                    "error": f"Tool execution failed: {exc}",
                    "code": "TOOL_DISPATCH_ERROR",
                },
            )
    return finalize_fallback_tool_result(
        name,
        args,
        {
            "error": f"No tool dispatcher configured, cannot run '{name}'",
            "code": "TOOL_DISPATCH_ERROR",
        },
    )


def finalize_fallback_tool_result(name: str, args: dict, result: Any) -> str:
    from butler.tools.registry import finalize_tool_result

    return finalize_tool_result(name, args, result)


def finalize_guardrail_halt_result(
    name: str,
    args: dict,
    result: str,
    decision: Any,
) -> str:
    from butler.tools.registry import finalize_tool_result, pop_last_tool_audit_for_tool

    pop_last_tool_audit_for_tool(name)
    payload = parse_tool_result_object(result)
    if payload is None:
        payload = {"error": result or decision.message}
    else:
        payload = dict(payload)
    for key in ("ok", "tool", "code"):
        payload.pop(key, None)
    payload["error"] = decision.message
    payload["guardrail"] = {
        "action": decision.action,
        "code": decision.code,
        "count": decision.count,
    }
    return finalize_tool_result(name, args, payload)


def finalize_unenveloped_failure_result(name: str, args: dict, result: str) -> str:
    payload = parse_tool_result_object(result)
    if not isinstance(payload, dict):
        return result
    if payload.get("ok") is False and payload.get("tool") and payload.get("code"):
        return result
    failed = (
        "error" in payload
        or payload.get("success") is False
        or (isinstance(payload.get("exit_code"), int) and payload["exit_code"] != 0)
    )
    if failed:
        payload = dict(payload)
        payload.setdefault("code", "TOOL_ERROR")
        return finalize_fallback_tool_result(name, args, payload)
    return result


def parse_tool_result_object(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None
