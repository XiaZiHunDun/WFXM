"""Per-tool parameter boundary validators (AP-1 trajectory compliance).

Orthogonal to ``permissions/rules.py`` (policy allow/deny): this module checks
**parameter shape and hard security boundaries** before dispatch.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, cast

_PATH_TOOLS = frozenset({"read_file", "write_file", "patch", "delete_file"})
_WRITE_PATH_TOOLS = frozenset({"write_file", "patch", "delete_file"})

_DELEGATE_ROLES = frozenset({
    "butler",
    "dev",
    "dev_agent",
    "content",
    "content_agent",
    "review",
    "review_agent",
})

_MAX_TASK_LEN = 32_000
_MAX_CONTENT_LEN = 2_000_000
_MAX_PATCH_FIELD = 512_000


@dataclass(frozen=True)
class BoundaryViolation:
    tool: str
    code: str
    message: str

    def to_error_payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.message,
            "code": self.code,
            "tool": self.tool,
        }


def validate_tool_boundary(name: str, args: dict[str, Any] | None) -> BoundaryViolation | None:
    """Return a violation when args cross hard boundaries; else None."""
    tool = str(name or "").strip()
    if not tool:
        return BoundaryViolation("", "BOUNDARY_EMPTY_TOOL", "tool name is empty")
    payload = dict(args or {})
    checker = _CHECKERS.get(tool)
    if checker is None:
        return None
    from butler.permissions.tool_boundary_registry_ops import run_tool_boundary_checker_safe

    return cast(
        BoundaryViolation | None,
        run_tool_boundary_checker_safe(
            tool,
            checker,
            payload,
            violation_factory=BoundaryViolation,
        ),
    )


def _check_path_tool(args: dict[str, Any], *, for_write: bool) -> BoundaryViolation | None:
    from butler.tools.path_safety import check_tool_path

    path = str(args.get("path") or args.get("file_path") or "").strip()
    if not path:
        return BoundaryViolation(
            "path_tool",
            "BOUNDARY_PATH_MISSING",
            "path 参数不能为空",
        )
    if ".." in path.split("/") or path.startswith("~"):
        return BoundaryViolation(
            "path_tool",
            "BOUNDARY_PATH_TRAVERSAL",
            "路径不允许包含 .. 或以 ~ 开头",
        )
    result = check_tool_path(path, for_write=for_write)
    if not result.allowed:
        return BoundaryViolation(
            "path_tool",
            "BOUNDARY_PATH_UNSAFE",
            result.error or "路径不在工作区内",
        )
    return None


def _check_read_file(args: dict[str, Any]) -> BoundaryViolation | None:
    v = _check_path_tool(args, for_write=False)
    if v is not None:
        v = BoundaryViolation("read_file", v.code, v.message)
        return v
    limit = args.get("limit")
    if limit is not None:
        try:
            lim = int(limit)
            if lim < 1 or lim > 5000:
                return BoundaryViolation(
                    "read_file",
                    "BOUNDARY_READ_LIMIT",
                    "limit 须在 1–5000 之间",
                )
        except (TypeError, ValueError):
            return BoundaryViolation(
                "read_file",
                "BOUNDARY_READ_LIMIT",
                "limit 必须为整数",
            )
    return None


def _check_write_file(args: dict[str, Any]) -> BoundaryViolation | None:
    v = _check_path_tool(args, for_write=True)
    if v is not None:
        return BoundaryViolation("write_file", v.code, v.message)
    content = args.get("content")
    if content is not None and len(str(content)) > _MAX_CONTENT_LEN:
        return BoundaryViolation(
            "write_file",
            "BOUNDARY_CONTENT_TOO_LARGE",
            f"content 长度超过 {_MAX_CONTENT_LEN}",
        )
    return None


def _check_patch(args: dict[str, Any]) -> BoundaryViolation | None:
    v = _check_path_tool(args, for_write=True)
    if v is not None:
        return BoundaryViolation("patch", v.code, v.message)
    for field in ("old_string", "new_string"):
        val = args.get(field)
        if val is not None and len(str(val)) > _MAX_PATCH_FIELD:
            return BoundaryViolation(
                "patch",
                "BOUNDARY_PATCH_TOO_LARGE",
                f"{field} 长度超过 {_MAX_PATCH_FIELD}",
            )
    return None


def _check_delete_file(args: dict[str, Any]) -> BoundaryViolation | None:
    v = _check_path_tool(args, for_write=True)
    if v is not None:
        return BoundaryViolation("delete_file", v.code, v.message)
    return None


def _check_terminal(args: dict[str, Any]) -> BoundaryViolation | None:
    from butler.tools.path_safety import prepare_shell_command

    command = str(args.get("command") or "").strip()
    if not command:
        return BoundaryViolation(
            "terminal",
            "BOUNDARY_TERMINAL_EMPTY",
            "command 不能为空",
        )
    if len(command) > 16_000:
        return BoundaryViolation(
            "terminal",
            "BOUNDARY_TERMINAL_TOO_LONG",
            "command 过长",
        )
    result = prepare_shell_command(command)
    if not result.allowed:
        return BoundaryViolation(
            "terminal",
            "BOUNDARY_TERMINAL_UNSAFE",
            result.error or "terminal 命令未通过安全校验",
        )
    return None


def _check_delegate_task(args: dict[str, Any]) -> BoundaryViolation | None:
    task = str(args.get("task") or "").strip()
    if not task:
        return BoundaryViolation(
            "delegate_task",
            "BOUNDARY_DELEGATE_TASK_EMPTY",
            "task 不能为空",
        )
    if len(task) > _MAX_TASK_LEN:
        return BoundaryViolation(
            "delegate_task",
            "BOUNDARY_DELEGATE_TASK_TOO_LONG",
            f"task 长度超过 {_MAX_TASK_LEN}",
        )
    role = str(args.get("role") or "dev_agent").strip().lower()
    if role and role not in _DELEGATE_ROLES:
        return BoundaryViolation(
            "delegate_task",
            "BOUNDARY_DELEGATE_ROLE",
            f"role 不在允许列表: {sorted(_DELEGATE_ROLES)}",
        )
    return None


def _check_call_tool(args: dict[str, Any]) -> BoundaryViolation | None:
    """MCP ``call_tool`` — server and tool name must be non-empty strings."""
    server = str(args.get("server") or args.get("mcp_server") or "").strip()
    tool_name = str(args.get("tool") or args.get("tool_name") or "").strip()
    if not server:
        return BoundaryViolation(
            "call_tool",
            "BOUNDARY_MCP_SERVER",
            "MCP server 名不能为空",
        )
    if not tool_name:
        return BoundaryViolation(
            "call_tool",
            "BOUNDARY_MCP_TOOL",
            "MCP tool 名不能为空",
        )
    raw_args = args.get("arguments") or args.get("args")
    if raw_args is not None and not isinstance(raw_args, (dict, str)):
        return BoundaryViolation(
            "call_tool",
            "BOUNDARY_MCP_ARGS",
            "arguments 必须为 dict 或 JSON 字符串",
        )
    if isinstance(raw_args, str) and raw_args.strip():
        try:
            json.loads(raw_args)
        except json.JSONDecodeError:
            return BoundaryViolation(
                "call_tool",
                "BOUNDARY_MCP_ARGS_JSON",
                "arguments JSON 无效",
            )
    return None


_CHECKERS: dict[str, Any] = {
    "read_file": _check_read_file,
    "write_file": _check_write_file,
    "patch": _check_patch,
    "delete_file": _check_delete_file,
    "terminal": _check_terminal,
    "delegate_task": _check_delegate_task,
    "call_tool": _check_call_tool,
}


__all__ = ["BoundaryViolation", "validate_tool_boundary"]
