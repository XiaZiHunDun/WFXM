"""Workspace and sensitive-path guards for Butler tools."""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from pathlib import Path


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
            return Path(workspace).expanduser().resolve()
    except Exception:
        return None
    return None


def check_tool_path(path: str | os.PathLike[str], *, for_write: bool = False) -> PathSafetyResult:
    """Resolve and validate a tool path against workspace and sensitive path rules."""
    raw = str(path or ".")
    root = tool_safe_root()
    resolved = _resolve_tool_path(raw, root)

    sensitive_error = _sensitive_path_error(resolved, for_write=for_write)
    if sensitive_error:
        return PathSafetyResult(False, resolved, sensitive_error)

    if root is not None and not _is_relative_to(resolved, root):
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


def prepare_shell_command(command: str) -> CommandSafetyResult:
    """Validate a terminal command and return argv for ``shell=False`` execution."""
    text = command or ""
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
    return path.resolve(strict=False)


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
