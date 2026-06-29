"""Tool call batch execution extracted from AgentLoop."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort
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

    def _do() -> None:
        from pathlib import Path as _Path

        p = _Path(path)
        if not p.is_absolute():
            from butler.tools.safe_root import get_tool_safe_root

            p = get_tool_safe_root() / p
        if p.is_file() and p.stat().st_size < 512_000:
            _pre_edit_snapshots[str(p.resolve())] = p.read_text(encoding="utf-8")

    safe_best_effort(_do, label="tool_batch.pre_edit_snapshot")


def _fetch_pre_edit_snapshot(path: str) -> str | None:
    """Pop a pre-edit snapshot if available."""

    def _do() -> str | None:
        from pathlib import Path as _Path

        p = _Path(path)
        if not p.is_absolute():
            from butler.tools.safe_root import get_tool_safe_root

            p = get_tool_safe_root() / p
        return _pre_edit_snapshots.pop(str(p.resolve()), None)

    return safe_best_effort(_do, label="tool_batch.fetch_pre_edit_snapshot", default=None)


def _dev_engine_post_edit(name: str, args: dict, result: str) -> None:
    """Record edit in DevState with proper snapshots for rollback (DD4).

    Called from ``_dispatch_one`` after a successful edit tool,
    where both ``args`` and ``result`` are available.
    """
    if name not in _EDIT_TOOL_NAMES:
        return
    if _tool_result_outcome(result) != "ok":
        return

    def _do() -> None:
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
            parsed = parse_tool_result_object(result)
            if parsed:
                path = str(parsed.get("path") or parsed.get("file") or "")

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
        from butler.dev_engine.dev_state import DevPhase

        if state.phase == DevPhase.PLAN:
            transition(state, "plan_trivial")
        elif state.phase == DevPhase.LOCATE:
            transition(state, "files_found")
        transition(state, "edit_success", edit_record=record)

        from butler.dev_engine.dev_tools import auto_verify_enabled

        if auto_verify_enabled() and path:
            _run_auto_verify(state, path)

    safe_best_effort(_do, label="tool_batch.dev_engine_post_edit")


def _plan_mode_post_edit(name: str, args: dict, result: str) -> None:
    """Sync plan markdown bullets to transcript plan_step rows."""
    if name not in ("write_file", "patch"):
        return
    if _tool_result_outcome(result) != "ok":
        return

    def _do() -> None:
        path = str(args.get("path") or args.get("file_path") or "")
        parsed = parse_tool_result_object(result)
        if parsed:
            path = path or str(parsed.get("path") or parsed.get("file") or "")
        if not path:
            return
        content = str(args.get("content") or "")
        if not content and name == "write_file":
            return
        if not content:
            from pathlib import Path as _Path

            from butler.tools.safe_root import get_tool_safe_root

            p = _Path(path)
            if not p.is_absolute():
                p = get_tool_safe_root() / p
            if p.is_file():
                content = p.read_text(encoding="utf-8", errors="replace")
            else:
                return
        from butler.execution_context import get_current_session_key
        from butler.plan.markdown_sync import sync_plan_file_to_transcript

        sk = str(get_current_session_key() or "").strip() or "default"
        sync_plan_file_to_transcript(sk, path, content)

    safe_best_effort(_do, label="tool_batch.plan_mode_post_edit")


def _run_auto_verify(state: Any, path: str) -> None:
    """Run auto-verify after edit and inject fix hints (DD2 + DA4 + CA4)."""

    def _do() -> None:
        from pathlib import Path as _Path

        from butler.dev_engine.dev_loop import transition
        from butler.dev_engine.dev_state import DevPhase
        from butler.dev_engine.verify import select_auto_verify_levels, verify_layered

        try:
            from butler.tools.safe_root import get_tool_safe_root

            ws = _Path(get_tool_safe_root())
        except Exception as exc:
            logger.debug("auto_verify workspace resolve skipped: %s", exc)
            ws = _Path(path).parent

        edited_files = [path] if path else []
        delegate_cat = str(getattr(state, "_delegate_category", "") or "")
        levels = select_auto_verify_levels(edited_files, delegate_category=delegate_cat)
        result = verify_layered(ws, levels=levels)

        thm_violations: list[str] = []
        activated = getattr(state, "_coding_knowledge_theorems", None)
        if activated and state.edit_history:

            def _ck_verify() -> None:
                nonlocal thm_violations
                from butler.dev_engine.coding_knowledge import dual_verify as ck_dual_verify

                last_edit = state.edit_history[-1]
                code = last_edit.new_content or last_edit.patch_new or ""
                if not code:
                    return
                ck_result = ck_dual_verify(
                    code,
                    activated,
                    test_passed=result.passed,
                    test_detail=f"auto-verify: {result.status.value}",
                )
                thm_violations = ck_result.violated_theorems
                state.coding_knowledge.violated_theorems = thm_violations

            safe_best_effort(_ck_verify, label="tool_batch.auto_verify.coding_knowledge")

        if result.passed and not thm_violations:
            transition(state, "verify_pass")
        else:
            transition(state, "verify_fail", verify_result=result)
            if state.phase == DevPhase.FIX:
                transition(state, "fix_applied")

            def _reactivate_ck() -> None:
                from butler.dev_engine.coding_knowledge_fixup import (
                    reactivate_coding_knowledge_on_verify_fail,
                )

                reactivate_coding_knowledge_on_verify_fail(state)

            safe_best_effort(_reactivate_ck, label="tool_batch.auto_verify.ck_fixup")

            def _record_reflect() -> None:
                from butler.core.reasoning_trace import record_verify_fail_reflect

                record_verify_fail_reflect(state, result)

            safe_best_effort(_record_reflect, label="tool_batch.auto_verify.reflect")

            def _enrich_hint() -> None:
                from butler.dev_engine.fix_strategy import enrich_fix_hint, suggest_fix_action

                fix_level = suggest_fix_action(result.diagnostics, state)
                hint = enrich_fix_hint(fix_level, state)
                tail = getattr(result, "output_tail", "") or ""

                def _b9_hint() -> str | None:
                    from butler.dev_engine.b9_live_tuning import build_b9_verify_hint

                    return build_b9_verify_hint(tail)

                b9_hint = safe_best_effort(_b9_hint, label="tool_batch.auto_verify.b9_hint")
                if b9_hint:
                    hint = f"{hint}: {b9_hint}"
                state._last_fix_hint = hint

            safe_best_effort(_enrich_hint, label="tool_batch.auto_verify.fix_hint")

    safe_best_effort(_do, label="tool_batch.auto_verify")


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

    def _maybe_truncate_finish() -> None:
        from butler.core.finish_tool_truncate import truncate_tool_calls_at_finish

        truncated = truncate_tool_calls_at_finish(list(response.tool_calls))
        if len(truncated) < len(response.tool_calls):
            response.tool_calls = truncated

    safe_best_effort(_maybe_truncate_finish, label="tool_batch.finish_truncate")

    def _maybe_reorder_reads() -> None:
        from butler.core.batch_sequence_guard import reorder_reads_before_destructive

        response.tool_calls = reorder_reads_before_destructive(list(response.tool_calls))

    safe_best_effort(_maybe_reorder_reads, label="tool_batch.reorder_reads")
    if callbacks.on_stream_boundary:
        callbacks.on_stream_boundary()

    append_assistant_tool_calls(messages, response)

    if guardrails and guardrails.halt_decision:
        return ToolBatchStats()

    tools_started = 0
    batch_guard = None

    def _init_batch_guard() -> None:
        nonlocal batch_guard
        from butler.core.batch_sequence_guard import BatchSequenceGuard, batch_stale_guard_enabled

        if batch_stale_guard_enabled():
            batch_guard = BatchSequenceGuard()

    safe_best_effort(_init_batch_guard, label="tool_batch.stale_guard_init")

    from butler.core.tool_batch_hooks import build_tool_batch_hooks
    from butler.core.tool_dispatch import dispatch_one_tool
    from butler.execution_context import get_current_session_key

    on_start, on_complete, precheck_tool, hook_state = build_tool_batch_hooks(
        callbacks=callbacks,
        guardrails=guardrails,
        batch_guard=batch_guard,
        interrupt_check=interrupt_check,
    )

    def _dispatch_one(name: str, args: dict, *, tool_call_id: str = "") -> str:
        return dispatch_one_tool(
            name,
            args,
            tool_call_id=tool_call_id,
            batch_guard=batch_guard,
            prefetched=prefetched,
            guardrails=guardrails,
            dispatch_tool=dispatch_tool,
        )

    if config.enable_parallel_tools and len(response.tool_calls) > 1:
        pairs = execute_tools_parallel(
            response.tool_calls,
            lambda n, a, *, tool_call_id="": _dispatch_one(n, a, tool_call_id=tool_call_id),
            on_start=on_start,
            on_complete=on_complete,
            check_interrupt=interrupt_check,
            precheck_tool=precheck_tool,
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
            on_start(tc.name, args)
            result = _dispatch_one(tc.name, args, tool_call_id=str(tc.id or ""))
            on_complete(tc.name, result)
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
        tools_started=hook_state.tools_started,
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
        try:
            from butler.tools.registry import finalize_tool_result

            return finalize_tool_result(
                name,
                args,
                {"preview": str(result)[:200]},
            )
        except Exception as exc:
            logger.debug("finalize_unenveloped preview skipped: %s", exc)
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
