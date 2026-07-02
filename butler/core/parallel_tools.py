"""Safe parallel execution of tool call batches."""

from __future__ import annotations

import logging
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

logger = logging.getLogger(__name__)

_NEVER_PARALLEL = frozenset({"delegate_task"})
_ALWAYS_PARALLEL = frozenset({"search_files", "list_directory"})
_PATH_SCOPED = frozenset({"read_file", "write_file", "patch"})


def _normalize_path(path: str) -> str:
    from butler.core.parallel_tools_ops import normalize_path_safe

    return normalize_path_safe(path)


def _paths_overlap(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a, b = _normalize_path(a), _normalize_path(b)
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _extract_scope_path(tool_name: str, args: dict) -> str | None:
    if tool_name in _PATH_SCOPED:
        return str(args.get("path", "") or "")
    return None


def should_parallelize_tool_batch(tool_calls: list[Any]) -> bool:
    if len(tool_calls) <= 1:
        return False
    from butler.core.parallel_tools_ops import batch_parallel_allowed

    guard = batch_parallel_allowed(tool_calls)
    if guard is False:
        return False
    names = [getattr(tc, "name", "") or (tc.get("name") if isinstance(tc, dict) else "") for tc in tool_calls]
    if any(n in _NEVER_PARALLEL for n in names):
        return False
    if all(n in _ALWAYS_PARALLEL for n in names):
        return True

    reserved: list[str] = []
    for tc in tool_calls:
        name = getattr(tc, "name", "") if not isinstance(tc, dict) else tc.get("name", "")
        if name not in _PATH_SCOPED:
            if name not in _ALWAYS_PARALLEL:
                return False
            continue
        from butler.core.parallel_tools_ops import parse_tool_args_safe

        args = parse_tool_args_safe(tc)
        path = _extract_scope_path(name, args)
        if path:
            if any(_paths_overlap(path, r) for r in reserved):
                return False
            reserved.append(path)
    return True


def execute_tools_parallel(
    tool_calls: list[Any],
    dispatch_fn: Callable[..., str],
    *,
    max_workers: int = 8,
    on_start: Callable[[str, dict], None] | None = None,
    on_complete: Callable[[str, str], None] | None = None,
    check_interrupt: Callable[[], bool] | None = None,
    precheck_tool: Callable[[str, dict], str | None] | None = None,
    prefetched: dict[str, str] | None = None,
) -> list[tuple[Any, str]]:
    """Execute tool calls in parallel; return list of (tool_call, result) in original order."""
    from butler.core.parallel_tools_ops import dispatch_parallel_tool_loud, parse_tool_args_safe

    def _run_one(tc: Any) -> tuple[Any, str]:
        name = tc.name if hasattr(tc, "name") else tc.get("name", "")
        args = parse_tool_args_safe(tc)
        tool_id = str(getattr(tc, "id", None) or "")
        if prefetched and tool_id in prefetched:
            if on_start:
                on_start(name, args)
            result = prefetched[tool_id]
            if on_complete:
                on_complete(name, result)
            return tc, result
        if precheck_tool:
            prechecked = precheck_tool(name, args)
            if prechecked is not None:
                return tc, prechecked
        if check_interrupt and check_interrupt():
            return tc, _finalize_parallel_tool_result(
                name,
                args,
                {"error": "interrupted", "code": "TOOL_INTERRUPTED"},
            )
        if on_start:
            on_start(name, args)
        result = dispatch_parallel_tool_loud(
            dispatch_fn,
            name,
            args,
            tool_id=tool_id,
            finalize=_finalize_parallel_tool_result,
        )
        if on_complete:
            on_complete(name, result)
        return tc, result

    if not should_parallelize_tool_batch(tool_calls):
        return [_run_one(tc) for tc in tool_calls]

    results: dict[int, tuple[Any, str]] = {}
    parent_context = copy_context()
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tool_calls))) as pool:
        futures = {
            pool.submit(parent_context.copy().run, _run_one, tc): i
            for i, tc in enumerate(tool_calls)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            results[idx] = fut.result()

    return [results[i] for i in range(len(tool_calls))]


def _finalize_parallel_tool_result(name: str, args: dict, result: Any) -> str:
    from butler.tools.registry import finalize_tool_result

    return finalize_tool_result(name, args, result)
