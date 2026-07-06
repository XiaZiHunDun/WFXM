"""Development engine tools — dev_verify, dev_rollback, dev_status, dev_search_symbols.

Registered when BUTLER_DEV_ENGINE=1.
These are the LLM-facing tools that interact with DevState.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast

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


def auto_review_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_AUTO_REVIEW", "0")
    return raw.strip().lower() in ("1", "true", "yes")


def review_strict_enabled() -> bool:
    raw = os.getenv("BUTLER_DEV_REVIEW_STRICT", "0")
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
    return cast(dict[str, Any], state.to_dict())


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

    activated = getattr(state, "_coding_knowledge_theorems", None)
    thm_violations: list[str] = []
    if activated and state.edit_history:
        from butler.dev_engine.dev_tools_ops import coding_knowledge_verify_safe

        thm_violations = coding_knowledge_verify_safe(
            state,
            test_passed=result.passed,
            test_detail=f"V1-V5: {result.status.value}",
        )

    if result.passed and not thm_violations:
        transition(state, "verify_pass")
    else:
        transition(state, "verify_fail", verify_result=result)

    out = result.to_dict()
    if thm_violations:
        out["theorem_violations"] = thm_violations
    if result.passed and not thm_violations and auto_review_enabled():
        from butler.dev_engine.dev_tools_ops import auto_review_after_verify_safe

        review_payload = auto_review_after_verify_safe(str(ws), session_key=session_key)
        if review_payload:
            out["review"] = review_payload
    return cast(dict[str, Any], out)


def tool_dev_review(
    workspace: str,
    *,
    changed_files: list[str] | None = None,
    session_key: str = "_default",
    llm_text: str = "",
    from_auto_verify: bool = False,
) -> dict[str, Any]:
    """Run static (+ optional LLM) code review; update DevState."""
    from butler.core.review_context_adapter import (
        merge_review_views,
        to_dev_review_view,
    )
    from butler.dev_engine.dev_loop import transition
    from butler.dev_engine.optimize_advisory import enrich_review_with_suggestions
    from butler.dev_engine.review_closure import summarize_review_for_delegate
    from butler.dev_engine.review_static import run_static_review

    ws = Path(workspace)
    state = get_or_create_state(session_key)
    edit_paths = [e.path for e in state.edit_history if e.path]
    static_view = run_static_review(
        ws,
        changed_files=changed_files,
        edit_paths=edit_paths,
    )
    views = [static_view]
    if llm_text.strip():
        views.append(to_dev_review_view(llm_text, source="llm_review"))
    view = enrich_review_with_suggestions(
        ws,
        merge_review_views(*views),
        changed_files=changed_files,
        edit_paths=edit_paths,
    )

    diagnostics: dict[str, Any] = {}
    from butler.dev_engine.dev_tools_ops import apply_dev_review_diagnostics_safe

    apply_dev_review_diagnostics_safe(view, diagnostics)

    if view.passed:
        event = "review_pass"
    else:
        event = "review_fail"
    from butler.dev_engine.dev_loop import get_valid_events, transition

    if event in get_valid_events(state.phase):
        transition(state, event, review_result=view)
    else:
        from butler.core.review_context_adapter import apply_dev_review_view_to_state

        apply_dev_review_view_to_state(view, state)

    from butler.dev_engine.dev_tools_ops import review_closure_hooks_safe

    review_closure_hooks_safe(
        view,
        session_key=session_key,
        task_preview=state.task_description[:200],
    )

    out = summarize_review_for_delegate(view)
    out["findings"] = [f.model_dump() for f in view.findings[:24]]
    out["phase"] = state.phase.value
    if from_auto_verify:
        out["auto_review"] = True
    if diagnostics:
        out["diagnostics"] = diagnostics
    return cast(dict[str, Any], out)


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


def _handler_dev_review(
    changed_files: str = "",
    llm_text: str = "",
    **kwargs: Any,
) -> str:
    from butler.tools.safe_root import get_tool_safe_root

    workspace = str(get_tool_safe_root())
    sk = _resolve_session_key()
    files = [f.strip() for f in str(changed_files or "").split(",") if f.strip()]
    return json.dumps(
        tool_dev_review(
            workspace,
            changed_files=files or None,
            session_key=sk,
            llm_text=str(llm_text or ""),
        ),
        ensure_ascii=False,
    )


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


def _handler_dev_search_symbols(**kwargs: Any) -> str:
    from butler.tools.safe_root import get_tool_safe_root

    name = kwargs.get("name") or kwargs.get("query") or kwargs.get("symbol")
    if not name or not str(name).strip():
        return json.dumps(
            {
                "error": "dev_search_symbols missing required argument: name",
                "code": "TOOL_ARGS_INVALID",
                "hint": "Pass name (function/class/variable to search).",
            },
            ensure_ascii=False,
        )
    workspace = str(get_tool_safe_root())
    sk = _resolve_session_key()
    return json.dumps(
        tool_dev_search_symbols(str(name).strip(), workspace, session_key=sk),
        ensure_ascii=False,
    )


def tool_run_pytest(
    path: str = "test_b9.py",
    *,
    timeout: int = 60,
    session_key: str = "_default",
) -> dict[str, Any]:
    """Run pytest on a single test file in the workspace (B9/dev benchmark helper)."""
    from butler.tools.path_safety import check_tool_path, tool_safe_root

    rel = (path or "test_b9.py").strip()
    safety = check_tool_path(rel, for_write=False)
    if not safety.allowed:
        return {"error": safety.error or "path denied", "code": "PATH_DENIED"}

    ws = tool_safe_root()
    test_fp = safety.path
    try:
        test_arg = str(test_fp.relative_to(ws))
    except ValueError:
        test_arg = test_fp.name

    from butler.dev_engine.dev_tools_ops import run_pytest_command_loud

    proc = run_pytest_command_loud(ws=ws, test_arg=test_arg, rel=rel, timeout=timeout)
    if isinstance(proc, dict):
        return proc

    out = f"{proc.stdout or ''}{proc.stderr or ''}"
    passed = proc.returncode == 0
    payload: dict[str, Any] = {
        "passed": passed,
        "exit_code": proc.returncode,
        "path": rel,
        "output_tail": out[-4000:],
    }
    if not passed:
        from butler.dev_engine.dev_tools_ops import build_b9_verify_hint_safe

        hint = build_b9_verify_hint_safe(out) or (
            "Fix implementation source files (not the test) and call run_pytest again."
        )
        payload["hint"] = hint
    return payload


def _handler_run_pytest(path: str = "test_b9.py", timeout: int = 60, **kwargs: Any) -> str:
    sk = _resolve_session_key()
    return json.dumps(
        tool_run_pytest(path, timeout=timeout, session_key=sk),
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
            return cast(dict[str, Any], m.to_dict())
        for cm in collector._completed:
            if cm.task_id == task_id:
                return cast(dict[str, Any], cm.to_dict())
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
    from butler.dev_engine.dev_tools_ops import resolve_session_key_safe

    return cast(str, resolve_session_key_safe())


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
        name="dev_review",
        description=(
            "运行确定性代码审查（边界/异常/体量/测试/安全）并返回结构化 findings。"
            "VERIFY 通过后建议调用；可与 review_agent 的 PASS/FAIL 文本合并。"
        ),
        schema={
            "type": "object",
            "properties": {
                "changed_files": {
                    "type": "string",
                    "description": "逗号分隔的相对路径；默认使用 EditHistory",
                    "default": "",
                },
                "llm_text": {
                    "type": "string",
                    "description": "可选 review_agent 输出全文",
                    "default": "",
                },
            },
        },
        handler=_handler_dev_review,
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
        name="run_pytest",
        description=(
            "在 workspace 内运行 pytest（默认 test_b9.py）。"
            "B9 基准推荐用此工具代替手写 terminal 命令。"
        ),
        schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "测试文件路径（默认 test_b9.py）",
                    "default": "test_b9.py",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数（5–120，默认 60）",
                    "default": 60,
                },
            },
        },
        handler=_handler_run_pytest,
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
