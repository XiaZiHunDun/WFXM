"""Classify tool results — file mutation landed detection (Hermes subset)."""

from __future__ import annotations

import json
from typing import Any

FILE_MUTATING_TOOL_NAMES = frozenset({"write_file", "patch", "delete_file"})


def is_file_mutating_tool(tool_name: str) -> bool:
    return str(tool_name or "") in FILE_MUTATING_TOOL_NAMES


def _parse_result_dict(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result
    if not isinstance(result, str) or not result.strip():
        return None
    try:
        data = json.loads(result.strip())
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def file_mutation_result_landed(tool_name: str, result: Any) -> bool:
    """Return True when a file mutation result proves the write landed."""
    if not is_file_mutating_tool(tool_name):
        return False
    data = _parse_result_dict(result)
    if data is None or data.get("error"):
        return False
    if tool_name == "write_file":
        if data.get("success") is False:
            return False
        return bool(data.get("bytes_written") is not None or data.get("bytes") is not None)
    if tool_name == "patch":
        return data.get("success") is True and (
            data.get("replacements") is not None or bool(data.get("path"))
        )
    if tool_name == "delete_file":
        return data.get("success") is True and str(data.get("action") or "") == "deleted"
    return False


def mutation_result_not_landed(tool_name: str, result: Any) -> bool:
    """True when a mutating tool returned without error but lacks landed proof."""
    if not is_file_mutating_tool(tool_name):
        return False
    if file_mutation_result_landed(tool_name, result):
        return False
    data = _parse_result_dict(result)
    if data is not None and data.get("error"):
        return False
    lower = str(result or "")[:500].lower()
    if '"error"' in lower or result.startswith("Error"):
        return False
    return True


def mutation_not_landed_message(tool_name: str) -> str:
    return (
        f"{tool_name} 未返回可验证的写入成功标记（如 bytes/replacements/success）。"
        "请 read_file 确认或重试写入，勿声称已完成。"
    )


def annotate_mutation_not_landed(tool_name: str, result: str) -> tuple[str, bool]:
    """If mutation did not land, annotate result and return (result, failed)."""
    if not mutation_result_not_landed(tool_name, result):
        return result, False
    msg = mutation_not_landed_message(tool_name)
    data = _parse_result_dict(result)
    if isinstance(data, dict):
        payload = dict(data)
        payload["mutation_not_landed"] = True
        payload.setdefault("warning", msg)
        return json.dumps(payload, ensure_ascii=False, default=str), True
    return (result or "") + f"\n\n[mutation_not_landed: {msg}]", True


__all__ = [
    "FILE_MUTATING_TOOL_NAMES",
    "annotate_mutation_not_landed",
    "file_mutation_result_landed",
    "is_file_mutating_tool",
    "mutation_not_landed_message",
    "mutation_result_not_landed",
]
