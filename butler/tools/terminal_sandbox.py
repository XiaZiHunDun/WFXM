"""OS-level terminal sandbox (Linux bubblewrap; Cursor/CC-aligned subset)."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy
from butler.tools.butlerignore import credential_mask_paths

logger = logging.getLogger(__name__)

_BWRAP_CANDIDATES = ("bwrap", "bubblewrap")
_SANDBOX_FAILURE_MARKERS = (
    (re.compile(r"(?i)network|unshare-net|operation not permitted.*socket"), "network"),
    (re.compile(r"(?i)read-only file system|permission denied"), "filesystem"),
    (re.compile(r"(?i)no such file or directory"), "filesystem"),
)

_DEFAULT_CREDENTIAL_ENV_DENY = (
    "GITHUB_TOKEN",
    "GITLAB_TOKEN",
    "NPM_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


@dataclass(frozen=True)
class NetworkPolicy:
    default: str = "deny"
    allow: tuple[str, ...] = ()
    deny: tuple[str, ...] = ()


@dataclass(frozen=True)
class TerminalSandboxConfig:
    enabled: bool = False
    sandbox_type: str = "workspace_readwrite"
    additional_readwrite_paths: tuple[str, ...] = ()
    additional_readonly_paths: tuple[str, ...] = ()
    disable_tmp_write: bool = False
    network: NetworkPolicy = field(default_factory=NetworkPolicy)
    fail_if_unavailable: bool = False
    credential_env_deny: tuple[str, ...] = _DEFAULT_CREDENTIAL_ENV_DENY


@dataclass(frozen=True)
class SandboxFailure:
    constraint: str
    code: str
    message: str

    def escalate_hint(self, command: str) -> str:
        short = (command or "").strip()[:120]
        return (
            f"沙箱约束「{self.constraint}」阻止了命令执行。"
            f" Owner 可发「/批准沙箱外 {short}」后在 5 分钟内无沙箱重试。"
        )


def terminal_sandbox_enabled() -> bool:
    return env_truthy("BUTLER_TERMINAL_SANDBOX", default=False)


def sandbox_network_allowlist_mode() -> bool:
    """When true and sandbox.json has network allow entries, skip full net unshare."""
    return env_truthy("BUTLER_TERMINAL_SANDBOX_NETWORK_ALLOWLIST", default=False)


def sandbox_fail_if_unavailable() -> bool:
    return env_truthy("BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE", default=False)


def bubblewrap_path() -> str | None:
    for name in _BWRAP_CANDIDATES:
        found = shutil.which(name)
        if found:
            return found
    return None


def sandbox_runtime_available() -> bool:
    return bubblewrap_path() is not None


def _butler_home() -> Path:
    from butler.config import get_butler_home

    return get_butler_home()


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("invalid sandbox config %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def _merge_paths(*groups: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for raw in group:
            text = str(raw or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
    return tuple(out)


def _parse_network_policy(raw: dict[str, Any] | None) -> NetworkPolicy:
    if not isinstance(raw, dict):
        return NetworkPolicy()
    default = str(raw.get("default") or "deny").strip().lower()
    if default not in ("allow", "deny"):
        default = "deny"
    allow = tuple(str(x).strip() for x in (raw.get("allow") or []) if str(x).strip())
    deny = tuple(str(x).strip() for x in (raw.get("deny") or []) if str(x).strip())
    return NetworkPolicy(default=default, allow=allow, deny=deny)


def _resolve_config_path(path_text: str, *, workspace: Path, user_home: Path) -> str | None:
    raw = str(path_text or "").strip()
    if not raw:
        return None
    if raw.startswith("~/"):
        return str((user_home / raw[2:]).resolve(strict=False))
    if raw.startswith("./") or raw == ".":
        rel = raw[2:] if raw.startswith("./") else ""
        return str((workspace / rel).resolve(strict=False))
    if raw.startswith("/"):
        return str(Path(raw).resolve(strict=False))
    return str((workspace / raw).resolve(strict=False))


def load_terminal_sandbox_config(workspace: Path) -> TerminalSandboxConfig:
    """Merge user + repo ``sandbox.json`` (repo wins); env gates ``enabled``."""
    ws = workspace.resolve(strict=False)
    user_cfg = _read_json_file(_butler_home() / "sandbox.json")
    repo_cfg = _read_json_file(ws / ".butler" / "sandbox.json")

    sandbox_type = str(repo_cfg.get("type") or user_cfg.get("type") or "workspace_readwrite")
    if sandbox_type not in ("workspace_readwrite", "workspace_readonly", "insecure_none"):
        sandbox_type = "workspace_readwrite"

    rw_paths = _merge_paths(
        [str(x) for x in user_cfg.get("additionalReadwritePaths") or []],
        [str(x) for x in repo_cfg.get("additionalReadwritePaths") or []],
    )
    ro_paths = _merge_paths(
        [str(x) for x in user_cfg.get("additionalReadonlyPaths") or []],
        [str(x) for x in repo_cfg.get("additionalReadonlyPaths") or []],
    )

    user_home = Path.home()
    resolved_rw = tuple(
        p
        for p in (
            _resolve_config_path(item, workspace=ws, user_home=user_home) for item in rw_paths
        )
        if p
    )
    resolved_ro = tuple(
        p
        for p in (
            _resolve_config_path(item, workspace=ws, user_home=user_home) for item in ro_paths
        )
        if p
    )

    disable_tmp = bool(user_cfg.get("disableTmpWrite")) or bool(repo_cfg.get("disableTmpWrite"))
    network = _merge_network_policy(
        _parse_network_policy(user_cfg.get("networkPolicy")),
        _parse_network_policy(repo_cfg.get("networkPolicy")),
    )

    env_deny = os.getenv("BUTLER_SANDBOX_CREDENTIAL_ENV", "").strip()
    credential_env = (
        tuple(x.strip() for x in env_deny.split(",") if x.strip())
        if env_deny
        else _DEFAULT_CREDENTIAL_ENV_DENY
    )

    return TerminalSandboxConfig(
        enabled=terminal_sandbox_enabled() and sandbox_type != "insecure_none",
        sandbox_type=sandbox_type,
        additional_readwrite_paths=resolved_rw,
        additional_readonly_paths=resolved_ro,
        disable_tmp_write=disable_tmp,
        network=network,
        fail_if_unavailable=sandbox_fail_if_unavailable(),
        credential_env_deny=credential_env,
    )


def _merge_network_policy(user: NetworkPolicy, repo: NetworkPolicy) -> NetworkPolicy:
    default = "deny" if "deny" in (user.default, repo.default) else "allow"
    allow = _merge_paths(list(user.allow), list(repo.allow))
    deny = _merge_paths(list(user.deny), list(repo.deny))
    return NetworkPolicy(default=default, allow=allow, deny=deny)


def should_run_sandboxed(
    config: TerminalSandboxConfig,
    *,
    unsandboxed_approved: bool = False,
) -> bool:
    if unsandboxed_approved:
        return False
    if not config.enabled:
        return False
    if config.sandbox_type == "insecure_none":
        return False
    return True


def enrich_subprocess_env(base_env: dict[str, str], *, sandboxed: bool) -> dict[str, str]:
    env = dict(base_env)
    if sandboxed:
        env["BUTLER_SANDBOX"] = "1"
        try:
            env["BUTLER_ORIG_UID"] = str(os.getuid())
            env["BUTLER_ORIG_GID"] = str(os.getgid())
        except AttributeError:
            pass
    return env


def scrub_credential_env(env: dict[str, str], config: TerminalSandboxConfig) -> dict[str, str]:
    cleaned = dict(env)
    for name in config.credential_env_deny:
        cleaned.pop(name, None)
    return cleaned


def wrap_argv_with_bubblewrap(
    argv: list[str],
    *,
    workspace: Path,
    config: TerminalSandboxConfig,
) -> list[str]:
    """Wrap ``argv`` with bubblewrap; raises ``RuntimeError`` when bwrap missing."""
    bwrap = bubblewrap_path()
    if not bwrap:
        raise RuntimeError("bubblewrap (bwrap) not found on PATH")

    ws = str(workspace.resolve(strict=False))
    cmd: list[str] = [
        bwrap,
        "--die-with-parent",
        "--unshare-pid",
        "--ro-bind",
        "/",
        "/",
    ]

    if config.sandbox_type == "workspace_readwrite":
        cmd.extend(["--bind", ws, ws])
    else:
        cmd.extend(["--ro-bind", ws, ws])

    if not config.disable_tmp_write:
        cmd.extend(["--bind", "/tmp", "/tmp"])

    for extra in config.additional_readwrite_paths:
        if extra and extra != ws:
            cmd.extend(["--bind", extra, extra])
    for extra in config.additional_readonly_paths:
        if extra and extra not in config.additional_readwrite_paths:
            cmd.extend(["--ro-bind", extra, extra])

    for masked in credential_mask_paths():
        cmd.extend(["--tmpfs", masked])

    cmd.extend(["--dev", "/dev", "--proc", "/proc", "--chdir", ws])

    net_deny = config.network.default == "deny"
    has_allow = bool(config.network.allow)
    if net_deny and not (has_allow and sandbox_network_allowlist_mode()):
        cmd.append("--unshare-net")
    elif net_deny and has_allow and sandbox_network_allowlist_mode():
        logger.info(
            "sandbox network allowlist mode: skipping --unshare-net (hosts=%s)",
            ",".join(config.network.allow[:5]),
        )

    cmd.extend(["--setenv", "BUTLER_SANDBOX", "1"])
    cmd.append("--")
    cmd.extend(argv)
    return cmd


def classify_sandbox_failure(
    *,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    sandboxed: bool,
) -> SandboxFailure | None:
    if not sandboxed:
        return None
    if exit_code in (0, None):
        return None
    blob = f"{stdout}\n{stderr}"
    constraint = "unknown"
    for pattern, name in _SANDBOX_FAILURE_MARKERS:
        if pattern.search(blob):
            constraint = name
            break
    code = f"SANDBOX_{constraint.upper()}_DENIED"
    snippet = (stderr or stdout or "").strip().splitlines()
    detail = snippet[-1][:200] if snippet else f"exit_code={exit_code}"
    return SandboxFailure(
        constraint=constraint,
        code=code,
        message=detail,
    )


def format_sandbox_error_payload(
    failure: SandboxFailure,
    *,
    command: str,
    exit_code: int | None,
    output: str,
) -> dict[str, Any]:
    from butler.core.approval_cards import format_terminal_sandbox_card

    card = format_terminal_sandbox_card(command, constraint=failure.constraint)
    return {
        "ok": False,
        "error": failure.message,
        "code": failure.code,
        "sandbox_constraint": failure.constraint,
        "escalate_hint": card,
        "exit_code": exit_code,
        "output": output,
        "sandboxed": True,
    }


__all__ = [
    "NetworkPolicy",
    "SandboxFailure",
    "TerminalSandboxConfig",
    "bubblewrap_path",
    "classify_sandbox_failure",
    "enrich_subprocess_env",
    "format_sandbox_error_payload",
    "load_terminal_sandbox_config",
    "sandbox_fail_if_unavailable",
    "sandbox_network_allowlist_mode",
    "sandbox_runtime_available",
    "scrub_credential_env",
    "should_run_sandboxed",
    "terminal_sandbox_enabled",
    "wrap_argv_with_bubblewrap",
]
