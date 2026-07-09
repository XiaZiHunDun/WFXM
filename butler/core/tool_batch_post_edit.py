"""Post-edit hooks for tool dispatch (extracted from tool_batch — Wave 4 cycle break)."""

from __future__ import annotations

import logging
from typing import Any, cast

from butler.core.best_effort import safe_best_effort
from butler.core.reasoning_trace import record_verify_fail_reflect
from butler.core.tool_batch_finalize import parse_tool_result_object
from butler.core.tool_batch_state import pop_pre_edit_snapshot, store_pre_edit_snapshot
from butler.dev_engine.b9_live_tuning import build_b9_verify_hint
from butler.dev_engine.coding_knowledge import dual_verify as ck_dual_verify
from butler.dev_engine.coding_knowledge_fixup import reactivate_coding_knowledge_on_verify_fail
from butler.dev_engine.dev_loop import transition
from butler.dev_engine.dev_state import DevPhase, EditRecord
from butler.dev_engine.dev_tools import _active_states, auto_verify_enabled, dev_engine_enabled
from butler.dev_engine.fix_strategy import enrich_fix_hint, suggest_fix_action
from butler.dev_engine.verify import select_auto_verify_levels, verify_layered
from butler import execution_context
from butler.plan.markdown_sync import sync_plan_file_to_transcript
from butler.tools.safe_root import get_tool_safe_root

logger = logging.getLogger(__name__)

_EDIT_TOOL_NAMES = frozenset({"write_file", "patch", "delete_file"})
_OP_NAME_MAP = {"write_file": "write", "delete_file": "delete", "patch": "patch"}


def tool_result_outcome(result: str) -> str:
    text = (result or "").strip()
    if not text:
        return "ok"
    head = text[:240].lower()
    if head.startswith("error:") or head.startswith('{"error"'):
        return "error"
    if text.startswith("{") and '"error"' in head:
        return "error"
    return "ok"


def capture_pre_edit_snapshot(name: str, args: dict[str, Any]) -> None:
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


def fetch_pre_edit_snapshot(path: str) -> str | None:
    """Pop a pre-edit snapshot if available."""

    def _do() -> str | None:
        from pathlib import Path as _Path

        p = _Path(path)
        if not p.is_absolute():
            p = get_tool_safe_root() / p
        return cast(str | None, pop_pre_edit_snapshot(str(p.resolve())))

    return cast(str | None, safe_best_effort(_do, label="tool_batch.fetch_pre_edit_snapshot", default=None))


def dev_engine_post_edit(name: str, args: dict[str, Any], result: str) -> None:
    """Record edit in DevState with proper snapshots for rollback (DD4)."""
    if name not in _EDIT_TOOL_NAMES:
        return
    if tool_result_outcome(result) != "ok":
        return

    def _do() -> None:
        if not dev_engine_enabled():
            return
        sk = str(execution_context.get_current_session_key() or "").strip() or "_default"
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

        snapshot = fetch_pre_edit_snapshot(path)
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


def maturity_post_edit(name: str, args: dict[str, Any], result: str) -> None:
    """Accumulate per-project line-edit stats for delete maturity gate."""
    if name not in ("write_file", "patch"):
        return
    if tool_result_outcome(result) != "ok":
        return

    def _do() -> None:
        from pathlib import Path

        from butler.project.maturity_ops import record_edit_maturity_safe

        parsed = parse_tool_result_object(result)
        resolved = None
        if parsed:
            raw = str(parsed.get("path") or "")
            if raw:
                resolved = Path(raw)
        record_edit_maturity_safe(name, args, resolved_path=resolved)

    safe_best_effort(_do, label="tool_batch.maturity_post_edit")


def plan_mode_post_edit(name: str, args: dict[str, Any], result: str) -> None:
    """Sync plan markdown bullets to transcript plan_step rows."""
    if name not in ("write_file", "patch"):
        return
    if tool_result_outcome(result) != "ok":
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
        sk = str(execution_context.get_current_session_key() or "").strip() or "default"
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


__all__ = [
    "capture_pre_edit_snapshot",
    "dev_engine_post_edit",
    "fetch_pre_edit_snapshot",
    "maturity_post_edit",
    "plan_mode_post_edit",
    "tool_result_outcome",
]
