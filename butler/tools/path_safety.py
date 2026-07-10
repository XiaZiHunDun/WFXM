"""Workspace and sensitive-path guards for Butler tools."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from typing import Any, cast

from butler.tools.path_safety_ops import (
    workspace_from_project_safe,
    workspace_for_session_key_safe,
    default_project_workspace_safe,
    audit_session_key_safe,
    current_session_key_safe,
    orchestrator_workspace_safe,
    is_readable_session_tool_result_path_safe,
    external_path_override_allowed_safe,
    butlerignore_blocked_safe,
    current_orchestrator_safe,
    configured_safe_root_safe,
    hooks_global_dir_blocks_write,
)
from butler.tools.tool_scope import (
    environment_tool_scope_enabled,
    project_relative_path_anchors_to_workspace,
    resolve_environment_tool_root,
    workspace_anchor_strict_for_paths,
)

_BASE_TERMINAL_COMMANDS = {
    "cat",
    "echo",
    "false",
    "find",
    "head",
    "ls",
    "pwd",
    "sleep",
    "tail",
    "true",
}

# Pilot novel-factory scripts: enable with BUTLER_TERMINAL_ALLOWLIST_EXTRA=python3,bash
_EXTRA_TERMINAL_ENV = "BUTLER_TERMINAL_ALLOWLIST_EXTRA"
_PROFILE_ENV = "BUTLER_TERMINAL_PROFILE"

_TERMINAL_PROFILES: dict[str, frozenset[str]] = {
    "pilot": frozenset({"python3", "bash"}),
    "dev": frozenset({
        "python3",
        "bash",
        "pytest",
        "git",
        "rg",
        "pip",
        "pip3",
        "npm",
        "npx",
        "make",
    }),
}


def _allowed_terminal_commands() -> set[str]:
    allowed = set(_BASE_TERMINAL_COMMANDS)
    profile = os.getenv(_PROFILE_ENV, "").strip().lower()
    if profile in _TERMINAL_PROFILES:
        allowed.update(_TERMINAL_PROFILES[profile])
    from butler.execution_context import get_current_loop_role

    loop_role = get_current_loop_role()
    if loop_role == "butler":
        allowed.update(_TERMINAL_PROFILES.get("dev", frozenset()))
    raw = os.getenv(_EXTRA_TERMINAL_ENV, "").strip()
    if raw:
        for part in raw.replace(";", ",").split(","):
            name = part.strip()
            if name:
                allowed.add(name)
    if os.getenv("BUTLER_CC_BRIDGE", "").strip().lower() in ("1", "true", "yes", "on"):
        allowed.add("claude")
    return allowed


@dataclass(frozen=True)
class PathSafetyResult:
    allowed: bool
    path: Path
    error: str = ""


@dataclass(frozen=True)
class CommandSafetyResult:
    allowed: bool
    argv: list[str]
    error: str = ""
    is_pipe: bool = False


def _workspace_from_project(project: object | None) -> Path | None:

    return cast(Path | None, workspace_from_project_safe(project))


def _workspace_for_session_key(session_key: str) -> Path | None:

    return cast(Path | None, workspace_for_session_key_safe(session_key))


def _default_project_workspace() -> Path | None:

    return cast(Path | None, default_project_workspace_safe())


def _remap_projects_docs_trap(resolved: Path, *, session_ws: Path | None) -> Path:
    """Avoid ``projects/docs`` fixture dir when a project workspace is active."""
    safe = _configured_safe_root()
    if safe is None:
        return resolved
    trap = (safe / "docs").resolve(strict=False)
    try:
        if not resolved.is_relative_to(trap):
            return resolved
    except ValueError:
        return resolved
    ws = session_ws or _default_project_workspace()
    if ws is None:
        return resolved
    try:
        rel = resolved.relative_to(trap)
        candidate = (ws / "docs" / rel).resolve(strict=False)
    except ValueError:
        return resolved
    if candidate.exists():
        return candidate
    if not resolved.exists():
        return candidate
    return resolved


def current_workspace_root() -> Path | None:
    """Return the active Butler project workspace, if a turn has one."""

    session_key = current_session_key_safe()
    ws = orchestrator_workspace_safe(session_key)
    if ws is not None:
        return Path(ws)
    if session_key:
        ws = _workspace_for_session_key(session_key)
        if ws is not None:
            return ws
    sk = audit_session_key_safe(fallback="")
    if sk and sk != session_key:
        return _workspace_for_session_key(sk)
    ws = _default_project_workspace()
    if ws is not None:
        return ws
    return None


def workspace_anchor_strict_enabled() -> bool:
    return workspace_anchor_strict_for_paths()


def format_tool_workspace_line(session_key: str = "") -> str:
    sk = str(session_key or "").strip()
    if environment_tool_scope_enabled():
        root = resolve_environment_tool_root()
        hint = ""
        ws = _workspace_for_session_key(sk) if sk else None
        if ws is None and sk:
            ws = current_workspace_root()
        if ws is not None:
            hint = f" · 上下文项目 {ws}"
        return f"工具工作区: (环境) {root}{hint}"
    ws = _workspace_for_session_key(sk) if sk else None
    if ws is None:
        ws = current_workspace_root()
    if ws is not None:
        return f"工具工作区: {ws}"
    root = _configured_safe_root()
    if root is not None:
        return f"工具工作区: (safe_root) {root}"
    return "工具工作区: (cwd) " + str(Path.cwd().resolve())


def check_tool_path(path: str | os.PathLike[str], *, for_write: bool = False) -> PathSafetyResult:
    """Resolve and validate a tool path against workspace and sensitive path rules."""
    raw = str(path or ".")
    # Sprint 27 P1-3.3: Windows 绝对路径 (C:/, C:\\, \\\\server\\...) 在 Linux 上
    # 不被识别为绝对, resolve 后会变 relative 误判为 in-workspace.
    # 显式 fail-closed 为 outside workspace.
    if _is_windows_absolute_path(raw):
        return PathSafetyResult(
            False,
            Path(raw),
            f"Access denied: Windows path is outside workspace ({raw})",
        )
    session_ws = current_workspace_root()
    rel = not Path(raw).expanduser().is_absolute()
    if session_ws is not None and rel and (
        workspace_anchor_strict_enabled() or project_relative_path_anchors_to_workspace()
    ):
        root = session_ws
    else:
        root = tool_safe_root()
    resolved = _resolve_tool_path(raw, root)
    if session_ws is not None and rel and (
        workspace_anchor_strict_enabled() or project_relative_path_anchors_to_workspace()
    ):
        try:
            if not resolved.is_relative_to(session_ws.resolve(strict=False)):
                alt = _resolve_tool_path(raw, session_ws)
                if alt.is_relative_to(session_ws.resolve(strict=False)):
                    resolved = alt
        except (ValueError, AttributeError):
            pass

    resolved = _remap_projects_docs_trap(resolved, session_ws=session_ws)

    sensitive_error = _sensitive_path_error(resolved, for_write=for_write)
    if sensitive_error:
        return PathSafetyResult(False, resolved, sensitive_error)

    hooks_error = _hooks_config_write_error(
        resolved, root, for_write=for_write
    )
    if hooks_error:
        return PathSafetyResult(False, resolved, hooks_error)

    if not for_write:

        if is_readable_session_tool_result_path_safe(resolved):
            return PathSafetyResult(True, resolved)

    if root is not None and not _is_relative_to(resolved, root):

        override = external_path_override_allowed_safe(resolved, for_write=for_write)
        if override is True:
            return PathSafetyResult(True, resolved)
        return PathSafetyResult(
            False,
            resolved,
            f"Access denied: path is outside workspace ({root})",
        )
    hardlink_error = _hardlink_error(resolved)
    if hardlink_error:
        return PathSafetyResult(False, resolved, hardlink_error)

    ws = session_ws or root
    if ws is not None:

        blocked = butlerignore_blocked_safe(
            resolved,
            workspace=ws,
            for_write=for_write,
        )
        if blocked:
            return PathSafetyResult(False, resolved, blocked)

    return PathSafetyResult(True, resolved)


def default_tool_workdir() -> PathSafetyResult:
    """Return the default cwd for shell tools."""
    return PathSafetyResult(True, tool_safe_root())


def tool_safe_root() -> Path:
    """Return the active root that tools may access."""
    if environment_tool_scope_enabled():
        return resolve_environment_tool_root()
    ws = current_workspace_root()
    if ws is not None:
        return ws
    return _configured_safe_root() or Path.cwd().resolve()


def _pipe_mode_enabled() -> bool:
    return os.getenv("BUTLER_TERMINAL_PIPE", "").strip() == "1"


_PIPE_SAFE_COMMANDS = frozenset({
    "grep", "rg", "wc", "head", "tail", "sort", "uniq", "tr", "cut",
    "awk", "sed", "cat", "tee", "xargs", "find", "ls", "echo",
})


def _validate_pipe_segment(segment: str, allowed: set[str]) -> CommandSafetyResult:
    """Validate one pipe segment (no recursion into nested pipes)."""
    seg = segment.strip()
    if not seg:
        return CommandSafetyResult(False, [], "Empty pipe segment")
    try:
        argv = shlex.split(seg, posix=True)
    except ValueError as exc:
        return CommandSafetyResult(False, [], f"Invalid pipe segment: {exc}")
    if not argv:
        return CommandSafetyResult(False, [], "Empty pipe segment")
    cmd_name = Path(argv[0]).name
    all_allowed = allowed | _PIPE_SAFE_COMMANDS
    if "/" in argv[0] or cmd_name not in all_allowed:
        return CommandSafetyResult(False, [], f"Pipe segment command '{cmd_name}' not in allowlist")
    blocked = _dangerous_search_flags(cmd_name, argv)
    if blocked:
        return CommandSafetyResult(False, [], blocked)
    if _uses_dynamic_interpreter(argv):
        return CommandSafetyResult(False, [], "Dynamic interpreter in pipe segment")
    if any("$" in token for token in argv):
        return CommandSafetyResult(False, [], "Shell variables in pipe segment")
    return CommandSafetyResult(True, argv)


def _dangerous_search_flags(command_name: str, argv: list[str]) -> str | None:
    """Block search tools flags that bypass workspace boundaries or run shell."""
    if command_name == "find":
        for tok in argv[1:]:
            if tok in ("-exec", "-execdir", "-delete", "-ok", "-okdir"):
                return f"find {tok} is not allowed in terminal commands"
            if tok.startswith(("-exec=", "-execdir=", "-ok=", "-okdir=")):
                return f"find {tok.split('=')[0]} is not allowed in terminal commands"
    if command_name == "rg":
        for tok in argv[1:]:
            if tok == "--pre" or tok.startswith("--pre="):
                return "rg --pre executes arbitrary commands and is not allowed in terminal commands"
    if command_name == "grep":
        for tok in argv[1:]:
            if tok.startswith("--file="):
                return "grep --file with embedded path is not allowed in terminal commands"
    return None


def prepare_shell_command(command: str) -> CommandSafetyResult:
    """Validate a terminal command and return argv for ``shell=False`` execution.

    When ``BUTLER_TERMINAL_PIPE=1``, simple pipes are allowed between
    allowlisted commands. The result uses ``shell=True`` via ``bash -c``
    in that case, with each segment validated individually.
    """
    text = command or ""

    has_pipe = "|" in text
    has_other_meta = bool(re.search(r"[&;<>()`]", text))

    if has_pipe and _pipe_mode_enabled() and not has_other_meta:
        allowed = _allowed_terminal_commands()
        segments = text.split("|")
        if len(segments) > 5:
            return CommandSafetyResult(False, [], "Too many pipe segments (max 5)")
        for seg in segments:
            result = _validate_pipe_segment(seg, allowed)
            if not result.allowed:
                return result
        for candidate in _extract_command_paths(text):
            path_result = check_tool_path(candidate, for_write=_looks_like_write_command(text, candidate))
            if not path_result.allowed:
                return CommandSafetyResult(False, [], path_result.error)
        return CommandSafetyResult(True, ["bash", "-c", text], is_pipe=True)

    try:
        argv = shlex.split(text, posix=True)
    except ValueError as exc:
        return CommandSafetyResult(False, [], f"Invalid shell command: {exc}")
    if not argv:
        return CommandSafetyResult(False, [], "Command is empty")
    command_name = Path(argv[0]).name
    if "/" in argv[0] or command_name not in _allowed_terminal_commands():
        return CommandSafetyResult(False, [], "Terminal command is not in the allowlist")
    blocked = _dangerous_search_flags(command_name, argv)
    if blocked:
        return CommandSafetyResult(False, [], blocked)
    if _has_shell_metacharacters(text):
        return CommandSafetyResult(False, [], "Shell metacharacters are not allowed in terminal commands")
    if _uses_dynamic_interpreter(argv):
        return CommandSafetyResult(False, [], "Dynamic interpreter commands are not allowed")
    if any("$" in token for token in argv):
        return CommandSafetyResult(False, [], "Shell variables are not allowed in terminal commands")
    for candidate in _extract_command_paths(text):
        path_result = check_tool_path(candidate, for_write=_looks_like_write_command(text, candidate))
        if not path_result.allowed:
            return CommandSafetyResult(False, [], path_result.error)
    for candidate in _existing_argv_paths(argv[1:]):
        path_result = check_tool_path(candidate, for_write=_looks_like_write_command(text, candidate))
        if not path_result.allowed:
            return CommandSafetyResult(False, [], path_result.error)
    return CommandSafetyResult(True, argv)


def safe_subprocess_env() -> dict[str, str]:
    """Return a minimal environment for tool subprocesses."""
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": os.getenv("LANG", "C.UTF-8") or "C.UTF-8",
        "LC_ALL": os.getenv("LC_ALL", "C.UTF-8") or "C.UTF-8",
    }
    return {key: value for key, value in env.items() if value}


def _current_orchestrator() -> Any:

    return current_orchestrator_safe()


def _configured_safe_root() -> Path | None:

    return cast(Path | None, configured_safe_root_safe())


def _resolve_tool_path(raw: str, root: Path | None) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute() and root is not None:
        path = root / path
    resolved = path.resolve(strict=False)
    if path.is_symlink():
        target = resolved
        if root is not None and not target.is_relative_to(root.resolve()):
            import logging as _log

            _log.getLogger(__name__).warning(
                "Symlink %s resolves outside workspace: %s", path, target
            )
            raise PermissionError(
                f"Symlink target {target} is outside workspace {root}"
            )
    return resolved


def _extract_command_paths(command: str) -> list[str]:
    candidates: list[str] = []
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = command.split()

    for token in tokens:
        stripped = token.strip()
        if "://" in stripped:
            continue
        stripped = re.sub(r"^\d?>+", "", stripped)
        if stripped in {".", ".."} or stripped.startswith(("/", "~", "./", "../")) or "/" in stripped:
            candidates.append(stripped)

    for match in re.finditer(r"(?<![\w.-])(?:~?/[^ \t\n\r'\"`;|&<>$()]+)", command):
        candidate = match.group(0)
        if "://" not in candidate:
            candidates.append(candidate)

    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip(" '\"\t\n\r;|&<>`")
        if candidate and candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out


def _looks_like_write_command(command: str, candidate: str) -> bool:
    del candidate
    return bool(re.search(r"(^|\s)(>|>>|2>|tee|cp|mv|rm|touch|mkdir|chmod|chown)(\s|$)", command))


def _existing_argv_paths(tokens: list[str]) -> list[str]:
    root = tool_safe_root()
    out: list[str] = []
    for token in tokens:
        if not token or token.startswith("-") or "://" in token:
            continue
        if token.startswith(("/", "~", "./", "../")) or "/" in token:
            continue
        try:
            if (root / token).exists():
                out.append(token)
        except OSError:
            continue
    return out


def _strip_safe_io_redirections(command: str) -> str:
    """Remove stderr/stdout null redirects before metacharacter scan."""
    stripped = command
    for pattern in (
        r"\s+2>/dev/null",
        r"\s+1>/dev/null",
        r"\s+2>&1",
    ):
        stripped = re.sub(pattern, "", stripped)
    return stripped.strip()


def _has_shell_metacharacters(command: str) -> bool:
    return bool(re.search(r"[|&;<>()`]", _strip_safe_io_redirections(command)))


def _uses_dynamic_interpreter(argv: list[str]) -> bool:
    command = Path(argv[0]).name
    if command in {"sh", "bash", "zsh", "fish"} and "-c" in argv[1:]:
        return True
    if command in {"python", "python3", "node", "ruby", "perl", "php"}:
        return any(flag in argv[1:] for flag in {"-c", "-e"})
    return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# Sprint 27 P1-3.3: Windows 绝对路径检测.
#   形态 1: <drive>:[\\/]<rest>  (C:/..., C:\..., c:/..., Z:\foo\bar)
#   形态 2: UNC \\\\?\\<...> 或 \\\\<server>\\<share>  (\\\\server\\share\\file)
#   形态 3: 盘符相对形式 C:foo (无分隔符, 罕见, 也按 Windows 绝对处理)
_WINDOWS_DRIVE_PATH = re.compile(r"^[A-Za-z]:[\\/]|^[A-Za-z]:[^\\/]")
_WINDOWS_UNC_PATH = re.compile(r"^\\\\[?]?[A-Za-z0-9_.$-]+[\\/]")


def _is_windows_absolute_path(path_str: str) -> bool:
    """Return True if path_str looks like a Windows absolute path (drive or UNC)."""
    s = str(path_str or "").strip()
    if not s:
        return False
    return bool(_WINDOWS_DRIVE_PATH.match(s) or _WINDOWS_UNC_PATH.match(s))


_HOOK_CONFIG_NAMES = frozenset({"hooks.yaml", "hooks.yml"})


def _hooks_config_write_error(
    path: Path,
    workspace_root: Path | None,
    *,
    for_write: bool,
) -> str:
    """R3-2: block LLM tool writes to hook rule files (persistent RCE chain)."""
    if not for_write:
        return ""
    resolved = path.resolve(strict=False)

    if hooks_global_dir_blocks_write(resolved):
        return "Access denied: path targets hooks configuration"
    if workspace_root is None:
        return ""
    butler_dir = (workspace_root / ".butler").resolve(strict=False)
    if _is_relative_to(resolved, butler_dir) and resolved.name in _HOOK_CONFIG_NAMES:
        return "Access denied: path targets hooks configuration"
    return ""


def _sensitive_path_error(path: Path, *, for_write: bool) -> str:
    home = Path.home().resolve()
    sensitive_dirs = [
        home / ".ssh",
        home / ".aws",
        home / ".gnupg",
        home / ".kube",
        home / ".docker",
        home / ".azure",
        home / ".config" / "gh",
    ]
    sensitive_files = [
        home / ".netrc",
        home / ".pgpass",
        home / ".npmrc",
        home / ".pypirc",
        Path("/etc/sudoers"),
        Path("/etc/passwd"),
        Path("/etc/shadow"),
    ]
    if for_write:
        sensitive_files.extend([
            home / ".bashrc",
            home / ".zshrc",
            home / ".profile",
            home / ".bash_profile",
            home / ".zprofile",
        ])
        sensitive_dirs.extend([
            Path("/etc/sudoers.d"),
            Path("/etc/systemd"),
        ])

    for directory in sensitive_dirs:
        if _is_relative_to(path, directory.resolve(strict=False)):
            return "Access denied: path targets a sensitive location"
    if path in {p.resolve(strict=False) for p in sensitive_files}:
        return "Access denied: path targets a sensitive location"
    return ""


def _hardlink_error(path: Path) -> str:
    try:
        if path.exists() and path.is_file() and path.stat().st_nlink > 1:
            return "Access denied: hardlinked files are not allowed"
    except OSError:
        return ""
    return ""
