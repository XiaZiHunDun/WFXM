"""Invalidate stale reads in the same tool batch after destructive writes (PR3b)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy

DESTRUCTIVE_BATCH_TOOLS = frozenset({
    "write_file",
    "patch",
    "edit_file",
    "apply_patch",
})

STALE_READ_BATCH_TOOLS = frozenset({
    "read_file",
    "grep",
    "search_files",
    "search_code",
    "glob",
    "list_directory",
    "list_dir",
})

STALE_SKIP_CODE = "BATCH_STALE_READ_SKIPPED"
STALE_PREFETCH_CODE = "BATCH_STALE_PREFETCH"


def batch_stale_guard_enabled() -> bool:
    return env_truthy("BUTLER_BATCH_STALE_GUARD", default=True)


def is_destructive_batch_tool(tool_name: str) -> bool:
    name = str(tool_name or "").strip().lower()
    if name in DESTRUCTIVE_BATCH_TOOLS:
        return True
    return name.startswith(("write_", "edit_", "patch"))


def is_stale_read_batch_tool(tool_name: str) -> bool:
    name = str(tool_name or "").strip().lower()
    if name in STALE_READ_BATCH_TOOLS:
        return True
    return name.startswith(("read_", "search_", "grep", "list_"))


def batch_has_destructive_and_reads(tool_calls: list[Any]) -> bool:
    names = []
    for tc in tool_calls:
        names.append(getattr(tc, "name", "") or "")
    has_write = any(is_destructive_batch_tool(n) for n in names)
    has_read = any(is_stale_read_batch_tool(n) for n in names)
    return has_write and has_read


def _tool_call_name(tc: Any) -> str:
    if isinstance(tc, dict):
        return str((tc.get("function") or {}).get("name") or tc.get("name") or "")
    return str(getattr(tc, "name", "") or "")


def _tool_call_args(tc: Any) -> dict[str, Any]:
    from butler.core.batch_sequence_guard_ops import parse_batch_tool_args_safe

    return parse_batch_tool_args_safe(tc)


def reorder_reads_before_destructive(tool_calls: list[Any]) -> list[Any]:
    """Move read_file ahead of patch on the same path within one batch (read-before-edit)."""
    if not batch_has_destructive_and_reads(tool_calls):
        return tool_calls
    ordered = list(tool_calls)
    changed = True
    while changed:
        changed = False
        for i, dest_tc in enumerate(ordered):
            dest_name = _tool_call_name(dest_tc)
            if dest_name != "patch":
                continue
            dest_paths = extract_tool_scope_paths(dest_name, _tool_call_args(dest_tc))
            has_prior_read = False
            for k in range(0, i):
                if _tool_call_name(ordered[k]) != "read_file":
                    continue
                prior_paths = extract_tool_scope_paths(
                    "read_file", _tool_call_args(ordered[k]),
                )
                if any(
                    _paths_overlap(dp, rp) for dp in dest_paths for rp in prior_paths
                ):
                    has_prior_read = True
                    break
            if has_prior_read:
                continue
            for j in range(i + 1, len(ordered)):
                read_name = _tool_call_name(ordered[j])
                if read_name != "read_file":
                    continue
                read_paths = extract_tool_scope_paths(read_name, _tool_call_args(ordered[j]))
                if not any(
                    _paths_overlap(dp, rp) for dp in dest_paths for rp in read_paths
                ):
                    continue
                read_tc = ordered.pop(j)
                ordered.insert(i, read_tc)
                changed = True
                break
            if changed:
                break
    return ordered


def _normalize_path(path: str) -> str:
    from butler.core.batch_sequence_guard_ops import normalize_batch_path_safe

    return normalize_batch_path_safe(path)


def _paths_overlap(a: str, b: str) -> bool:
    if not a or not b:
        return False
    a_norm, b_norm = _normalize_path(a), _normalize_path(b)
    return (
        a_norm == b_norm
        or a_norm.startswith(b_norm + "/")
        or b_norm.startswith(a_norm + "/")
    )


def extract_tool_scope_paths(tool_name: str, args: dict[str, Any] | None) -> list[str]:
    name = str(tool_name or "").strip().lower()
    payload = args if isinstance(args, dict) else {}
    paths: list[str] = []
    for key in ("path", "file", "directory", "root", "target"):
        raw = str(payload.get(key) or "").strip()
        if raw:
            paths.append(raw)
    if name in ("grep", "search_files") and not paths:
        pattern = str(payload.get("pattern") or "").strip()
        if pattern and (pattern.startswith("/") or pattern.startswith(".")):
            paths.append(pattern)
    return paths


def destructive_tool_succeeded(tool_name: str, result: str) -> bool:
    if not is_destructive_batch_tool(tool_name):
        return False
    from butler.tool_guardrails import classify_tool_failure

    failed, _ = classify_tool_failure(tool_name, result)
    if failed:
        return False
    try:
        data = json.loads(result or "")
    except json.JSONDecodeError:
        return True
    if isinstance(data, dict) and data.get("ok") is False:
        return False
    if isinstance(data, dict) and data.get("error"):
        return False
    return True


def build_stale_batch_skip_payload(
    tool_name: str,
    *,
    code: str = STALE_SKIP_CODE,
    invalidated_by: str = "",
    path: str = "",
) -> dict[str, Any]:
    scope = path or "(unknown)"
    writer = invalidated_by or "write/patch"
    return {
        "ok": False,
        "tool": tool_name,
        "code": code,
        "error": (
            f"同批工具序列已终止：{writer} 已修改 {scope}，"
            f"跳过后续过时的 {tool_name}（请在新一轮重新读取）。"
        ),
        "batch_stale_guard": {
            "invalidated_by": writer,
            "path": scope,
        },
    }


@dataclass
class BatchSequenceGuard:
    """Per-batch state: paths mutated by successful destructive tools."""

    invalidated_paths: list[str] = field(default_factory=list)
    last_writer: str = ""
    skips: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def should_skip_stale_read(self, tool_name: str, args: dict[str, Any] | None) -> bool:
        if not batch_stale_guard_enabled():
            return False
        if not is_stale_read_batch_tool(tool_name):
            return False
        with self._lock:
            if not self.invalidated_paths:
                return False
            snapshot = list(self.invalidated_paths)
        for scope in extract_tool_scope_paths(tool_name, args):
            if any(_paths_overlap(scope, inv) for inv in snapshot):
                return True
        return False

    def note_tool_result(self, tool_name: str, args: dict[str, Any] | None, result: str) -> None:
        if not batch_stale_guard_enabled():
            return
        if not destructive_tool_succeeded(tool_name, result):
            return
        with self._lock:
            for path in extract_tool_scope_paths(tool_name, args):
                norm = _normalize_path(path)
                if norm and norm not in self.invalidated_paths:
                    self.invalidated_paths.append(norm)
            self.last_writer = str(tool_name or "").strip()
        from butler.core.batch_sequence_guard_ops import record_edit_paths_safe

        record_edit_paths_safe(tool_name, args)
    def record_skip(self) -> None:
        with self._lock:
            self.skips += 1


def stale_skip_result(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    guard: BatchSequenceGuard,
    code: str = STALE_SKIP_CODE,
) -> dict[str, Any]:
    paths = extract_tool_scope_paths(tool_name, args)
    path = paths[0] if paths else ""
    guard.record_skip()
    return build_stale_batch_skip_payload(
        tool_name,
        code=code,
        invalidated_by=guard.last_writer,
        path=path,
    )


__all__ = [
    "BatchSequenceGuard",
    "STALE_PREFETCH_CODE",
    "STALE_SKIP_CODE",
    "batch_has_destructive_and_reads",
    "reorder_reads_before_destructive",
    "batch_stale_guard_enabled",
    "build_stale_batch_skip_payload",
    "destructive_tool_succeeded",
    "is_destructive_batch_tool",
    "is_stale_read_batch_tool",
    "stale_skip_result",
]
