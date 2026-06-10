"""Workspace and sensitive-path guards for Butler tools."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path
import logging


logger = logging.getLogger(__name__)

_BASE_TERMINAL_COMMANDS = {
    "cat",
    "echo",
    "false",
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
    raw = os.getenv(_EXTRA_TERMINAL_ENV, "").strip()
    if raw:
        for part in raw.replace(";", ",").split(","):
            name = part.strip()
            if name:
                allowed.add(name)
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


def current_workspace_root() -> Path | None:
    """Return the active Butler project workspace, if a turn has one."""
    try:
        orch = _current_orchestrator()
        if orch is None:
            return None
        manager = getattr(orch, "project_manager", None)
        session_key = ""
        try:
            from butler.execution_context import get_current_session_key

            session_key = str(get_current_session_key() or "").strip()
        except Exception:
            session_key = ""
        project = (
            manager.get_current(session_key=session_key)
            if manager and hasattr(manager, "get_current")
            else None
        )
        workspace = getattr(project, "workspace", None)
        if workspace:
            from butler.project.worktree import effective_workspace

            return effective_workspace(Path(workspace))
    except Exception:
        return None
    return None


def check_tool_path(path: str | os.PathLike[str], *, for_write: bool = False) -> PathSafetyResult:
    """Resolve and validate a tool path against workspace and sensitive path rules."""
    raw = str(path or ".")
    # Sprint 27 P1-3.3: Windows 绝对路径 (C:/, C:\\, \\\\server\\...) 在 Linux 上
    # 不被识别为绝对, resolve 后会变 relative 误判为 in-workspace.
    # 显式 fail-closed 为 outside workspace.
    if _is_windows_absolute_path(raw):
        return PathSafetyResult(
            False,
            raw,
            f"Access denied: Windows path is outside workspace ({raw})",
        )
    root = tool_safe_root()
    resolved = _resolve_tool_path(raw, root)

    sensitive_error = _sensitive_path_error(resolved, for_write=for_write)
    if sensitive_error:
        return PathSafetyResult(False, resolved, sensitive_error)

    hooks_error = _hooks_config_write_error(
        resolved, root, for_write=for_write
    )
    if hooks_error:
        return PathSafetyResult(False, resolved, hooks_error)

    if root is not None and not _is_relative_to(resolved, root):
        try:
            from butler.permissions import check_external_path_override

            override = check_external_path_override(str(resolved), for_write=for_write)
            if override is not None and override.allowed:
                return PathSafetyResult(True, resolved)
        except Exception as exc:
            logger.debug("check tool path skipped: %s", exc)
        return PathSafetyResult(
            False,
            resolved,
            f"Access denied: path is outside workspace ({root})",
        )
    hardlink_error = _hardlink_error(resolved)
    if hardlink_error:
        return PathSafetyResult(False, resolved, hardlink_error)

    return PathSafetyResult(True, resolved)


def default_tool_workdir() -> PathSafetyResult:
    """Return the default cwd for shell tools."""
    return PathSafetyResult(True, tool_safe_root())


def tool_safe_root() -> Path:
    """Return the active root that tools may access."""
    return current_workspace_root() or _configured_safe_root() or Path.cwd().resolve()


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
    if _uses_dynamic_interpreter(argv):
        return CommandSafetyResult(False, [], "Dynamic interpreter in pipe segment")
    if any("$" in token for token in argv):
        return CommandSafetyResult(False, [], "Shell variables in pipe segment")
    return CommandSafetyResult(True, argv)


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
            result = check_tool_path(candidate, for_write=_looks_like_write_command(text, candidate))
            if not result.allowed:
                return CommandSafetyResult(False, [], result.error)
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
    if _has_shell_metacharacters(text):
        return CommandSafetyResult(False, [], "Shell metacharacters are not allowed in terminal commands")
    if _uses_dynamic_interpreter(argv):
        return CommandSafetyResult(False, [], "Dynamic interpreter commands are not allowed")
    if any("$" in token for token in argv):
        return CommandSafetyResult(False, [], "Shell variables are not allowed in terminal commands")
    for candidate in _extract_command_paths(text):
        result = check_tool_path(candidate, for_write=_looks_like_write_command(text, candidate))
        if not result.allowed:
            return CommandSafetyResult(False, [], result.error)
    for candidate in _existing_argv_paths(argv[1:]):
        result = check_tool_path(candidate, for_write=_looks_like_write_command(text, candidate))
        if not result.allowed:
            return CommandSafetyResult(False, [], result.error)
    return CommandSafetyResult(True, argv)


def safe_subprocess_env() -> dict[str, str]:
    """Return a minimal environment for tool subprocesses."""
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": os.getenv("LANG", "C.UTF-8") or "C.UTF-8",
        "LC_ALL": os.getenv("LC_ALL", "C.UTF-8") or "C.UTF-8",
    }
    return {key: value for key, value in env.items() if value}


def _current_orchestrator():
    try:
        from butler.execution_context import get_current_orchestrator

        return get_current_orchestrator()
    except Exception:
        return None


def _configured_safe_root() -> Path | None:
    raw = os.getenv("BUTLER_TOOL_SAFE_ROOT", "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except Exception:
        return None


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


def _has_shell_metacharacters(command: str) -> bool:
    return bool(re.search(r"[|&;<>()`]", command))


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
    try:
        from butler.config import get_butler_settings

        global_dir = (
            get_butler_settings().butler_home / ".butler"
        ).resolve(strict=False)
        if _is_relative_to(resolved, global_dir) and resolved.name in _HOOK_CONFIG_NAMES:
            return "Access denied: path targets hooks configuration"
    except Exception:
        pass
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
