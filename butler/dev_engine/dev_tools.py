"""Development engine tools — dev_verify, dev_rollback, dev_status, dev_search_symbols.

Registered when BUTLER_DEV_ENGINE=1.
These are the LLM-facing tools that interact with DevState.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_active_states: dict[str, Any] = {}


def dev_engine_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_ENGINE", "1")
    return raw.strip().lower() in ("1", "true", "yes")


def auto_verify_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_AUTO_VERIFY", "1")
    return raw.strip().lower() in ("1", "true", "yes")


def rollback_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_ROLLBACK_ENABLED", "1")
    return raw.strip().lower() in ("1", "true", "yes")


def diagnostics_inject_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_DIAGNOSTICS_INJECT", "1")
    return raw.strip().lower() in ("1", "true", "yes")


def coding_strict_enabled() -> bool:
    """CA4: strict mode — output only if both theorem + test pass."""
    raw = os.getenv("BUTLER_CODING_STRICT", "0")
    return raw.strip().lower() in ("1", "true", "yes")


def get_or_create_state(session_key: str = "_default") -> Any:
    """Get or create DevState for session."""
    from butler.dev_engine.dev_loop import create_dev_state

    if session_key not in _active_states:
        _active_states[session_key] = create_dev_state()
    return _active_states[session_key]


def set_state(session_key: str, state: Any) -> None:
    _active_states[session_key] = state


def clear_state(session_key: str = "_default") -> None:
    _active_states.pop(session_key, None)


def tool_dev_status(session_key: str = "_default") -> dict[str, Any]:
    """Return current DevState summary for the LLM."""
    state = get_or_create_state(session_key)
    return state.to_dict()


def tool_dev_verify(
    workspace: str,
    *,
    levels: str = "lint,test",
    session_key: str = "_default",
) -> dict[str, Any]:
    """Run layered verification + coding knowledge theorem check, update DevState."""
    from butler.dev_engine.dev_loop import transition
    from butler.dev_engine.verify import verify_layered

    ws = Path(workspace)
    state = get_or_create_state(session_key)
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
                    test_detail=f"V1-V5: {result.status.value}",
                )
                thm_violations = ck_result.violated_theorems
                state.coding_knowledge.violated_theorems = thm_violations
        except Exception as exc:
            logger.debug("coding knowledge verify skipped: %s", exc)

    if result.passed and not thm_violations:
        transition(state, "verify_pass")
    else:
        transition(state, "verify_fail", verify_result=result)

    out = result.to_dict()
    if thm_violations:
        out["theorem_violations"] = thm_violations
    return out


def tool_dev_rollback(
    n: int = 1,
    *,
    session_key: str = "_default",
) -> dict[str, Any]:
    """Rollback last N edits and update DevState (DT5)."""
    from butler.dev_engine.edit_ops import rollback_edits

    state = get_or_create_state(session_key)

    if not state.edit_history:
        return {"rolled_back": 0, "errors": [], "message": "No edits to rollback"}

    to_rollback = state.edit_history[-n:]
    errors = rollback_edits(to_rollback)

    rolled_back = len(to_rollback) - len(errors)
    state.edit_history = state.edit_history[:-n] if n <= len(state.edit_history) else []

    return {
        "rolled_back": rolled_back,
        "remaining_edits": len(state.edit_history),
        "errors": errors,
    }


def tool_dev_search_symbols(
    name: str,
    workspace: str,
    *,
    session_key: str = "_default",
) -> dict[str, Any]:
    """Search for function/class/variable definitions in the workspace."""
    from butler.dev_engine.code_search import search_symbols

    ws = Path(workspace)
    state = get_or_create_state(session_key)
    hits = search_symbols(name, ws)

    from butler.dev_engine.dev_state import SearchHit

    state.search_context = hits

    if hits:
        from butler.dev_engine.dev_loop import transition

        transition(state, "files_found")

    return {
        "query": name,
        "hits": len(hits),
        "results": [
            {"path": h.path, "line": h.range_start, "snippet": h.snippet}
            for h in hits[:20]
        ],
    }


# ── Tool handlers for registry (JSON string wrappers) ──────────


def _handler_dev_status(**kwargs: Any) -> str:
    sk = _resolve_session_key()
    return json.dumps(tool_dev_status(sk), ensure_ascii=False)


def _handler_dev_verify(
    levels: str = "lint,test",
    **kwargs: Any,
) -> str:
    from butler.tools.safe_root import get_tool_safe_root

    workspace = str(get_tool_safe_root())
    sk = _resolve_session_key()
    return json.dumps(
        tool_dev_verify(workspace, levels=levels, session_key=sk),
        ensure_ascii=False,
    )


def _handler_dev_rollback(n: int = 1, **kwargs: Any) -> str:
    if not rollback_enabled():
        return json.dumps({"error": "Rollback disabled (BUTLER_DEV_ROLLBACK_ENABLED=0)"})
    sk = _resolve_session_key()
    return json.dumps(
        tool_dev_rollback(n, session_key=sk),
        ensure_ascii=False,
    )


def _handler_dev_search_symbols(name: str, **kwargs: Any) -> str:
    from butler.tools.safe_root import get_tool_safe_root

    workspace = str(get_tool_safe_root())
    sk = _resolve_session_key()
    return json.dumps(
        tool_dev_search_symbols(name, workspace, session_key=sk),
        ensure_ascii=False,
    )


def tool_dev_metrics(
    detail: str = "summary",
    task_id: str = "",
) -> dict[str, Any]:
    """Return development effectiveness metrics."""
    from butler.dev_engine.dev_metrics import get_collector

    collector = get_collector()
    if detail == "task" and task_id:
        m = collector.get_task_metrics(task_id)
        if m:
            return m.to_dict()
        for cm in collector._completed:
            if cm.task_id == task_id:
                return cm.to_dict()
        return {"error": f"Task {task_id} not found"}

    agg = collector.aggregate()
    result: dict[str, Any] = {"aggregate": agg.to_dict()}
    if detail == "full":
        result["completed_tasks"] = [t.to_dict() for t in collector._completed[-20:]]
        result["active_tasks"] = [t.to_dict() for t in collector._tasks.values()]
    return result


def _handler_dev_metrics(detail: str = "summary", task_id: str = "", **kwargs: Any) -> str:
    return json.dumps(
        tool_dev_metrics(detail=detail, task_id=task_id),
        ensure_ascii=False,
    )


def _resolve_session_key() -> str:
    try:
        from butler.execution_context import get_audit_session_key

        return get_audit_session_key(fallback="_default")
    except Exception:
        return "_default"


# ── Registration ────────────────────────────────────────────────


def register_dev_engine_tools(register_fn: Any) -> None:
    """Register dev engine tools into Butler tool registry."""
    if not dev_engine_enabled():
        return

    register_fn(
        name="dev_status",
        description=(
            "查看当前开发状态：阶段(PLAN/LOCATE/EDIT/VERIFY/FIX)、迭代次数、"
            "编辑历史、验证结果、诊断信息。在开发任务任意阶段调用。"
        ),
        schema={"type": "object", "properties": {}},
        handler=_handler_dev_status,
        toolset="dev_engine",
    )

    register_fn(
        name="dev_verify",
        description=(
            "运行分层验证（lint/typecheck/test/build）并返回结构化诊断。"
            "在完成编辑后调用以验证修改的正确性。"
        ),
        schema={
            "type": "object",
            "properties": {
                "levels": {
                    "type": "string",
                    "description": "逗号分隔的验证层级: lint,typecheck,test,build",
                    "default": "lint,test",
                },
            },
        },
        handler=_handler_dev_verify,
        toolset="dev_engine",
    )

    register_fn(
        name="dev_rollback",
        description=(
            "回滚最近 N 次编辑操作，恢复文件到编辑前状态。"
            "当编辑方向错误或修复循环失败时使用。"
        ),
        schema={
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "description": "回滚的编辑次数（默认 1）",
                    "default": 1,
                },
            },
        },
        handler=_handler_dev_rollback,
        toolset="dev_engine",
    )

    register_fn(
        name="dev_search_symbols",
        description=(
            "搜索函数/类/变量的定义位置。"
            "在 LOCATE 阶段使用，定位需要编辑的代码位置。"
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "要搜索的符号名称（函数名/类名/变量名）",
                },
            },
            "required": ["name"],
        },
        handler=_handler_dev_search_symbols,
        toolset="dev_engine",
    )

    register_fn(
        name="dev_metrics",
        description=(
            "查看开发引擎效果度量：任务完成率、编辑精度、修复收敛率、"
            "首次通过率、平均迭代次数。用于评估开发能力的实际表现。"
        ),
        schema={
            "type": "object",
            "properties": {
                "detail": {
                    "type": "string",
                    "description": "详细程度: summary(聚合指标) | full(含任务列表) | task(单任务)",
                    "default": "summary",
                },
                "task_id": {
                    "type": "string",
                    "description": "查询单个任务时的 task_id（detail=task 时使用）",
                    "default": "",
                },
            },
        },
        handler=_handler_dev_metrics,
        toolset="dev_engine",
    )
