"""Tool call batch execution extracted from AgentLoop."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, cast

from butler.core.best_effort import safe_best_effort
from butler.core.batch_sequence_guard import (
    BatchSequenceGuard,
    batch_stale_guard_enabled,
    reorder_reads_before_destructive,
)
from butler.core.finish_tool_truncate import truncate_tool_calls_at_finish
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.parallel_tools import execute_tools_parallel
from butler.core.reasoning_trace import record_verify_fail_reflect
from butler.core.tool_batch_hooks import build_tool_batch_hooks
from butler.core.tool_batch_runner import (
    append_tool_role_messages,
    extract_batch_followups,
    run_sequential_tool_calls,
)
from butler.core.tool_batch_state import (
    pop_pre_edit_snapshot,
    store_pre_edit_snapshot,
)
from butler.dev_engine.b9_live_tuning import build_b9_verify_hint
from butler.dev_engine.coding_knowledge import dual_verify as ck_dual_verify
from butler.dev_engine.coding_knowledge_fixup import reactivate_coding_knowledge_on_verify_fail
from butler.dev_engine.dev_loop import transition
from butler.dev_engine.dev_state import DevPhase, EditRecord
from butler.dev_engine.dev_tools import _active_states, auto_verify_enabled, dev_engine_enabled
from butler.dev_engine.fix_strategy import enrich_fix_hint, suggest_fix_action
from butler.dev_engine.verify import select_auto_verify_levels, verify_layered
from butler.execution_context import get_current_session_key
from butler.plan.markdown_sync import sync_plan_file_to_transcript
from butler.tool_guardrails import ToolCallGuardrailController
from butler.tools.safe_root import get_tool_safe_root
from butler.transport.reasoning_replay import store_reasoning_on_message
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


_EDIT_TOOL_NAMES = frozenset({"write_file", "patch", "delete_file"})

_OP_NAME_MAP = {"write_file": "write", "delete_file": "delete", "patch": "patch"}


def _capture_pre_edit_snapshot(name: str, args: dict[str, Any]) -> None:
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
            p = get_tool_safe_root() / p
        if p.is_file() and p.stat().st_size < 512_000:
            store_pre_edit_snapshot(str(p.resolve()), p.read_text(encoding="utf-8"))

    safe_best_effort(_do, label="tool_batch.pre_edit_snapshot")


def _fetch_pre_edit_snapshot(path: str) -> str | None:
    """Pop a pre-edit snapshot if available."""

    def _do() -> str | None:
        from pathlib import Path as _Path

        p = _Path(path)
        if not p.is_absolute():
            p = get_tool_safe_root() / p
        return cast(str | None, pop_pre_edit_snapshot(str(p.resolve())))

    return cast(str | None, safe_best_effort(_do, label="tool_batch.fetch_pre_edit_snapshot", default=None))


def _dev_engine_post_edit(name: str, args: dict[str, Any], result: str) -> None:
    """Record edit in DevState with proper snapshots for rollback (DD4).

    Called from ``_dispatch_one`` after a successful edit tool,
    where both ``args`` and ``result`` are available.
    """
    if name not in _EDIT_TOOL_NAMES:
        return
    if _tool_result_outcome(result) != "ok":
        return

    def _do() -> None:
        if not dev_engine_enabled():
            return
        sk = str(get_current_session_key() or "").strip() or "_default"
        state = _active_states.get(sk)
        if state is None:
            return

        import time

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

        if state.phase == DevPhase.PLAN:
            transition(state, "plan_trivial")
        elif state.phase == DevPhase.LOCATE:
            transition(state, "files_found")
        transition(state, "edit_success", edit_record=record)

        if auto_verify_enabled() and path:
            _run_auto_verify(state, path)

    safe_best_effort(_do, label="tool_batch.dev_engine_post_edit")


def _plan_mode_post_edit(name: str, args: dict[str, Any], result: str) -> None:
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

            p = _Path(path)
            if not p.is_absolute():
                p = get_tool_safe_root() / p
            if p.is_file():
                content = p.read_text(encoding="utf-8", errors="replace")
            else:
                return
        sk = str(get_current_session_key() or "").strip() or "default"
        sync_plan_file_to_transcript(sk, path, content)

    safe_best_effort(_do, label="tool_batch.plan_mode_post_edit")


def _run_auto_verify(state: Any, path: str) -> None:
    """Run auto-verify after edit and inject fix hints (DD2 + DA4 + CA4)."""

    def _do() -> None:
        from pathlib import Path as _Path

        def _resolve_workspace() -> _Path:
            return _Path(get_tool_safe_root())

        ws = (
            safe_best_effort(
                _resolve_workspace,
                label="tool_batch.auto_verify.workspace",
                default=_Path(path).parent if path else _Path("."),
            )
            or (_Path(path).parent if path else _Path("."))
        )

        edited_files = [path] if path else []
        delegate_cat = str(getattr(state, "_delegate_category", "") or "")
        levels = select_auto_verify_levels(edited_files, delegate_category=delegate_cat)
        result = verify_layered(ws, levels=levels)

        thm_violations: list[str] = []
        activated = getattr(state, "_coding_knowledge_theorems", None)
        if activated and state.edit_history:

            def _ck_verify() -> None:
                nonlocal thm_violations

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
                reactivate_coding_knowledge_on_verify_fail(state)

            safe_best_effort(_reactivate_ck, label="tool_batch.auto_verify.ck_fixup")

            def _record_reflect() -> None:
                record_verify_fail_reflect(state, result)

            safe_best_effort(_record_reflect, label="tool_batch.auto_verify.reflect")

            def _enrich_hint() -> None:
                fix_level = suggest_fix_action(result.diagnostics, state)
                hint = enrich_fix_hint(fix_level, state)
                tail = getattr(result, "output_tail", "") or ""

                def _b9_hint() -> str | None:
                    return cast(str | None, build_b9_verify_hint(tail))

                b9_hint = cast(
                    str | None,
                    safe_best_effort(_b9_hint, label="tool_batch.auto_verify.b9_hint"),
                )
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
    messages: list[dict[str, Any]],
    response: NormalizedResponse,
) -> None:
    """Append the assistant message that requested tool calls."""
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
    messages: list[dict[str, Any]],
    config: LoopConfig,
    callbacks: LoopCallbacks,
    guardrails: ToolCallGuardrailController | None,
    dispatch_tool: Callable[[str, dict[str, Any]], str],
    interrupt_check: Callable[[], bool],
    prefetched: dict[str, str] | None = None,
) -> ToolBatchStats:
    """Run a tool batch and append tool role messages."""
    if not response.tool_calls:
        return ToolBatchStats()

    def _maybe_truncate_finish() -> None:
        truncated = truncate_tool_calls_at_finish(list(response.tool_calls))
        if len(truncated) < len(response.tool_calls):
            response.tool_calls = truncated

    safe_best_effort(_maybe_truncate_finish, label="tool_batch.finish_truncate")

    def _maybe_reorder_reads() -> None:
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
        if batch_stale_guard_enabled():
            batch_guard = BatchSequenceGuard()

    safe_best_effort(_init_batch_guard, label="tool_batch.stale_guard_init")

    from butler.core.tool_dispatch import dispatch_one_tool

    on_start, on_complete, precheck_tool, hook_state = build_tool_batch_hooks(
        callbacks=callbacks,
        guardrails=guardrails,
        batch_guard=batch_guard,
        interrupt_check=interrupt_check,
    )

    def _dispatch_one(name: str, args: dict[str, Any], *, tool_call_id: str = "") -> str:
        return cast(
            str,
            dispatch_one_tool(
                name,
                args,
                tool_call_id=tool_call_id,
                batch_guard=batch_guard,
                prefetched=prefetched,
                guardrails=guardrails,
                dispatch_tool=dispatch_tool,
            ),
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
        pairs = run_sequential_tool_calls(
            list(response.tool_calls),
            dispatch_one=_dispatch_one,
            on_start=on_start,
            on_complete=on_complete,
            guardrails=guardrails,
            batch_guard=batch_guard,
            interrupt_check=interrupt_check,
        )

    session_key = str(get_current_session_key() or "").strip()
    append_tool_role_messages(pairs, messages, session_key=session_key)
    clarification, waiting = extract_batch_followups(pairs)

    return ToolBatchStats(
        tools_started=hook_state.tools_started,
        clarification_question=clarification,
        waiting_confirmation_message=waiting,
    )


from butler.core.tool_batch_finalize import (  # noqa: E402 — P1-C re-exports
    dispatch_tool_with_envelope,
    finalize_fallback_tool_result,
    finalize_guardrail_halt_result,
    finalize_unenveloped_failure_result,
    parse_tool_result_object,
)
