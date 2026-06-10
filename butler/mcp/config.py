"""Load and validate MCP server configuration."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from butler.env_parse import env_truthy, int_env
from butler.io.safe_load import safe_load_yaml
from butler.mcp.types import McpServerConfig, McpToolPolicy

logger = logging.getLogger(__name__)

_PRIVATE_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
})


def mcp_sdk_available() -> bool:
    try:
        import mcp  # noqa: F401

        return True
    except ImportError:
        return False


def mcp_enabled() -> bool:
    return env_truthy("BUTLER_MCP_ENABLED", default=False) and mcp_sdk_available()


def max_servers() -> int:
    try:
        return int_env("BUTLER_MCP_MAX_SERVERS", 3, min=0, max=20)
    except ValueError:
        return 3


def max_tools() -> int:
    try:
        return int_env("BUTLER_MCP_MAX_TOOLS", 20, min=0, max=100)
    except ValueError:
        return 20


def session_scoped() -> bool:
    return env_truthy("BUTLER_MCP_SESSION_SCOPED", default=True)


def stdio_allow_commands() -> frozenset[str]:
    raw = os.getenv("BUTLER_MCP_STDIO_ALLOW_COMMANDS", "python,python3,uvx")
    return frozenset(x.strip() for x in raw.split(",") if x.strip())


def http_hosts_allow_extra() -> list[str]:
    raw = os.getenv("BUTLER_MCP_HTTP_HOSTS_ALLOW", "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def allow_private_http() -> bool:
    return env_truthy("BUTLER_MCP_HTTP_ALLOW_PRIVATE", default=False)


def _expand_env(value: str) -> str:
    import re as _re

    def repl(m: _re.Match[str]) -> str:
        key = m.group(1)
        return os.getenv(key, "")

    return _re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, str(value or ""))


def _resolve_config_paths(workspace: Path | None = None) -> list[Path]:
    paths: list[Path] = []
    if workspace is not None:
        for rel in (".butler/mcp.yaml", ".butler/mcp.yml"):
            p = workspace / rel
            if p.is_file():
                paths.append(p)
    env_path = os.getenv("BUTLER_MCP_CONFIG", "").strip()
    if env_path:
        paths.append(Path(env_path).expanduser())
    else:
        try:
            from butler.config import get_butler_home

            for name in ("mcp.yaml", "mcp.yml"):
                p = get_butler_home() / name
                if p.is_file():
                    paths.append(p)
        except Exception:
            home = Path(os.path.expanduser("~/.butler/mcp.yaml"))
            if home.is_file():
                paths.append(home)
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _parse_tool_policy(raw: Any) -> McpToolPolicy:
    if not isinstance(raw, dict):
        return McpToolPolicy()
    allow = raw.get("allow") or []
    deny = raw.get("deny") or []
    if not isinstance(allow, list):
        allow = []
    if not isinstance(deny, list):
        deny = []
    return McpToolPolicy(
        allow=tuple(str(x).strip() for x in allow if str(x).strip()),
        deny=tuple(str(x).strip() for x in deny if str(x).strip()),
    )


def _parse_server(server_id: str, raw: dict[str, Any]) -> McpServerConfig | None:
    sid = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(server_id or "").strip())[:64]
    if not sid:
        return None
    transport = str(raw.get("transport") or "stdio").strip().lower()
    if transport not in ("stdio", "http"):
        logger.warning("MCP server %s: invalid transport %s", sid, transport)
        return None
    timeout = float(raw.get("timeout_seconds") or raw.get("timeout") or 60)
    tools = _parse_tool_policy(raw.get("tools"))
    classify_raw = raw.get("classify")
    classify: dict[str, str] = {}
    if isinstance(classify_raw, dict):
        classify = {str(k): str(v) for k, v in classify_raw.items()}
    if transport == "stdio":
        command = str(raw.get("command") or "").strip()
        if not command:
            return None
        args_raw = raw.get("args") or []
        args = tuple(str(a) for a in args_raw) if isinstance(args_raw, list) else ()
        env_raw = raw.get("env") or {}
        env = (
            {_expand_env(str(k)): _expand_env(str(v)) for k, v in env_raw.items()}
            if isinstance(env_raw, dict)
            else {}
        )
        return McpServerConfig(
            server_id=sid,
            transport="stdio",
            timeout_seconds=timeout,
            command=command,
            args=args,
            env=env,
            cwd=str(raw.get("cwd") or "").strip(),
            tools=tools,
            classify=classify,
        )
    url = _expand_env(str(raw.get("url") or "").strip())
    if not url:
        return None
    headers_raw = raw.get("headers") or {}
    headers = (
        {_expand_env(str(k)): _expand_env(str(v)) for k, v in headers_raw.items()}
        if isinstance(headers_raw, dict)
        else {}
    )
    hosts_raw = raw.get("hosts_allow") or []
    hosts = tuple(str(h).strip() for h in hosts_raw) if isinstance(hosts_raw, list) else ()
    return McpServerConfig(
        server_id=sid,
        transport="http",
        timeout_seconds=timeout,
        url=url,
        headers=headers,
        sse=bool(raw.get("sse")),
        hosts_allow=hosts,
        tools=tools,
        classify=classify,
    )


def load_mcp_servers(*, workspace: Path | None = None) -> list[McpServerConfig]:
    servers: dict[str, McpServerConfig] = {}
    for path in _resolve_config_paths(workspace):
        # Audit R2-19: corrupt MCP config used to silently skip
        # every server in that file. Now the safe_load helper
        # renames the corrupt file for forensic retention, logs
        # WARNING with exc_info, and records the event for /诊断.
        data = safe_load_yaml(path, default={}, kind="mcp_servers")
        if not isinstance(data, dict):
            continue
        block = data.get("servers")
        if not isinstance(block, dict):
            continue
        for sid, raw in block.items():
            if not isinstance(raw, dict):
                continue
            cfg = _parse_server(str(sid), raw)
            if cfg is not None:
                servers[cfg.server_id] = cfg
    ordered = list(servers.values())[: max_servers()]
    return ordered


def validate_stdio_command(config: McpServerConfig) -> str | None:
    cmd = Path(config.command).name if "/" in config.command or "\\" in config.command else config.command
    allowed = stdio_allow_commands()
    if cmd not in allowed:
        return f"stdio command '{cmd}' not in BUTLER_MCP_STDIO_ALLOW_COMMANDS"
    return None


def validate_http_url(config: McpServerConfig) -> str | None:
    try:
        parsed = urlparse(config.url)
    except Exception as exc:
        return f"invalid url: {exc}"
    if parsed.scheme not in ("http", "https"):
        return f"unsupported scheme: {parsed.scheme}"
    host = (parsed.hostname or "").lower()
    if not host:
        return "missing host"
    if not allow_private_http() and host in _PRIVATE_HOSTS:
        return f"private host blocked: {host}"
    allowed = set(config.hosts_allow) | set(http_hosts_allow_extra())
    if allowed and not any(host == h or host.endswith("." + h) for h in allowed):
        return f"host '{host}' not in hosts_allow"
    return None


def tool_allowed_by_policy(policy: McpToolPolicy, tool_name: str) -> bool:
    name = str(tool_name or "").strip()
    if not name:
        return False
    if policy.deny and name in policy.deny:
        return False
    if policy.allow:
        return name in policy.allow
    return True
