"""delegate_yield tool — mark delegate task complete without polling (OpenClaw subset)."""

from __future__ import annotations

import json
from typing import Any, Callable


def _tool_delegate_yield(
    task_id: str = "",
    success: bool = True,
    summary: str = "",
    report_headline: str = "",
    **_,
) -> str:
    from butler.runtime.task_store import complete_task, get_task, list_recent_tasks

    tid = str(task_id or "").strip()
    if not tid:
        try:
            from butler.execution_context import get_current_session_key

            sk = str(get_current_session_key() or "").strip()
            recent = list_recent_tasks(sk, limit=1)
            if recent:
                tid = str(recent[0].get("task_id") or "")
        except Exception:
            pass
    if not tid:
        return json.dumps({
            "ok": False,
            "error": "task_id required (or run from child delegate session)",
            "code": "TASK_ID_MISSING",
        }, ensure_ascii=False)

    rec = complete_task(
        tid,
        success=bool(success),
        report_headline=str(report_headline or summary or "")[:300],
        summary=str(summary or "")[:4000],
    )
    if rec is None:
        existing = get_task(tid)
        if existing is None:
            return json.dumps({
                "ok": False,
                "error": f"Unknown task_id: {tid}",
            }, ensure_ascii=False)
        return json.dumps({
            "ok": True,
            "task_id": tid,
            "status": existing.get("status"),
            "note": "already finalized",
        }, ensure_ascii=False)
    return json.dumps({
        "ok": True,
        "task_id": tid,
        "status": rec.get("status"),
        "child_session_key": rec.get("child_session_key"),
        "hint": "监督方请读 /任务 或 task 记录，勿反复轮询 list 工具",
    }, ensure_ascii=False)


def register_delegate_yield_tools(register: Callable[..., None]) -> None:
    register(
        name="delegate_yield",
        description=(
            "Finalize a delegate_task by task_id with success/failure summary. "
            "Prefer this over polling list_runtime_jobs or repeated delegate_task."
        ),
        schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task id from delegate_task"},
                "success": {"type": "boolean", "default": True},
                "summary": {"type": "string", "description": "Result summary for supervisor"},
                "report_headline": {"type": "string"},
            },
        },
        handler=_tool_delegate_yield,
        toolset="delegation",
    )
