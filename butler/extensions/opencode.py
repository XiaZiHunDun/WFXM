"""OpenCode integration bridge (D-L4-3).

Provides three integration modes for delegating coding tasks to OpenCode:

1. **TERMINAL_SUBPROCESS** — ``opencode run --format json`` as a subprocess.
   Simplest; no long-lived process. Cold start per invocation.

2. **HTTP_SERVER** — ``opencode serve`` as a managed sidecar, communicate via
   REST API (session create → prompt → SSE events → idle).
   Best for production: session reuse, permission management.

3. **MCP_BRIDGE** — Butler exposes tools as an MCP server that OpenCode
   connects to. (Note: OpenCode is an MCP *client*, not server.)

Environment variables:
  BUTLER_OPENCODE_ENABLED   — "1" to enable (default "0")
  BUTLER_OPENCODE_MODE      — "subprocess" | "http" | "mcp" (default "subprocess")
  BUTLER_OPENCODE_BIN       — path to opencode binary (default "opencode")
  BUTLER_OPENCODE_URL       — HTTP server URL (for http mode)
  BUTLER_OPENCODE_PASSWORD  — server password (for http mode)
  BUTLER_OPENCODE_TIMEOUT   — max seconds per task (default 600)
  BUTLER_OPENCODE_AGENT     — agent to use: "build" | "plan" (default "build")
  BUTLER_OPENCODE_MODEL     — model override (e.g. "anthropic/claude-sonnet-4-20250514")
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class OpenCodeMode(Enum):
    TERMINAL_SUBPROCESS = "subprocess"
    HTTP_SERVER = "http"
    MCP_BRIDGE = "mcp"


class OpenCodeBridge(Protocol):
    """Protocol for OpenCode integration."""

    def is_available(self) -> bool: ...

    def execute_task(
        self,
        task: str,
        *,
        workspace: str,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]: ...

    def get_mode(self) -> OpenCodeMode: ...


def _env(key: str, default: str = "") -> str:
    return (os.getenv(key, default) or default).strip()


def _env_int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


def opencode_enabled() -> bool:
    return _env("BUTLER_OPENCODE_ENABLED", "0") in ("1", "true", "yes")


# ─── Subprocess mode ────────────────────────────────────────────────

@dataclass
class SubprocessEvent:
    """A single event from ``opencode run --format json`` output."""
    type: str
    content: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _parse_json_events(stdout: str) -> list[SubprocessEvent]:
    """Parse NDJSON event stream from opencode run --format json."""
    events: list[SubprocessEvent] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            events.append(SubprocessEvent(
                type=data.get("type", "unknown"),
                content=data.get("content", data.get("text", "")),
                raw=data,
            ))
        except json.JSONDecodeError:
            events.append(SubprocessEvent(type="raw", content=line))
    return events


def _extract_result_text(events: list[SubprocessEvent]) -> str:
    """Extract the final text result from the event stream."""
    text_parts: list[str] = []
    for ev in events:
        if ev.type in ("text", "assistant"):
            if ev.content:
                text_parts.append(ev.content)
    if text_parts:
        return "\n".join(text_parts)
    return "\n".join(ev.content for ev in events if ev.content)


class OpenCodeSubprocess:
    """Execute tasks via ``opencode run --format json``."""

    def __init__(self) -> None:
        self._bin = _env("BUTLER_OPENCODE_BIN", "opencode")
        self._agent = _env("BUTLER_OPENCODE_AGENT", "build")
        self._model = _env("BUTLER_OPENCODE_MODEL", "")
        self._default_timeout = _env_int("BUTLER_OPENCODE_TIMEOUT", 600)

    def is_available(self) -> bool:
        return shutil.which(self._bin) is not None

    def get_mode(self) -> OpenCodeMode:
        return OpenCodeMode.TERMINAL_SUBPROCESS

    def execute_task(
        self,
        task: str,
        *,
        workspace: str,
        timeout_seconds: int = 0,
    ) -> dict[str, Any]:
        timeout = timeout_seconds or self._default_timeout
        t0 = time.time()

        cmd = [
            self._bin, "run", task,
            "--dir", workspace,
            "--format", "json",
            "--agent", self._agent,
            "--dangerously-skip-permissions",
        ]
        if self._model:
            cmd.extend(["--model", self._model])

        logger.info("OpenCode subprocess: %s (timeout=%ds)", " ".join(cmd[:6]), timeout)

        from butler.extensions.opencode_ops import run_subprocess_opencode_task

        return run_subprocess_opencode_task(
            cmd=cmd,
            timeout=timeout,
            t0=t0,
            mode_value=self.get_mode().value,
            parse_events=_parse_json_events,
            extract_text=_extract_result_text,
        )


# ─── HTTP server mode ───────────────────────────────────────────────

class OpenCodeHTTPServer:
    """Communicate with a running ``opencode serve`` via REST API."""

    def __init__(self) -> None:
        self._url = _env("BUTLER_OPENCODE_URL", "http://127.0.0.1:4096").rstrip("/")
        self._password = _env("BUTLER_OPENCODE_PASSWORD", "")
        self._agent = _env("BUTLER_OPENCODE_AGENT", "build")
        self._model = _env("BUTLER_OPENCODE_MODEL", "")
        self._default_timeout = _env_int("BUTLER_OPENCODE_TIMEOUT", 600)

    def _headers(self, workspace: str) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "x-opencode-directory": workspace,
        }
        if self._password:
            import base64
            creds = base64.b64encode(f"user:{self._password}".encode()).decode()
            headers["Authorization"] = f"Basic {creds}"
        return headers

    def is_available(self) -> bool:
        from butler.extensions.opencode_ops import http_health_available_safe

        return http_health_available_safe(self._url)

    def get_mode(self) -> OpenCodeMode:
        return OpenCodeMode.HTTP_SERVER

    def execute_task(
        self,
        task: str,
        *,
        workspace: str,
        timeout_seconds: int = 0,
    ) -> dict[str, Any]:
        timeout = timeout_seconds or self._default_timeout
        t0 = time.time()
        from butler.extensions.opencode_ops import run_http_opencode_task

        return run_http_opencode_task(
            lambda: self._execute_http_task(task, workspace=workspace, t0=t0),
            mode_value=self.get_mode().value,
            t0=t0,
        )

    def _execute_http_task(
        self,
        task: str,
        *,
        workspace: str,
        t0: float,
    ) -> dict[str, Any]:
        import httpx

        headers = self._headers(workspace)
        timeout = self._default_timeout

        # 1. Create session
        create_body: dict[str, Any] = {"agent": self._agent}
        if self._model:
            create_body["model"] = self._model
        create_resp = httpx.post(
            f"{self._url}/session",
            json=create_body,
            headers=headers,
            timeout=30,
        )
        if create_resp.status_code not in (200, 201):
            return {
                "ok": False,
                "result": f"创建 session 失败: {create_resp.status_code} {create_resp.text[:300]}",
                "mode": self.get_mode().value,
                "elapsed_seconds": round(time.time() - t0, 2),
            }
        session_data = create_resp.json()
        session_id = session_data.get("id") or session_data.get("sessionID", "")

        # 2. Send prompt
        prompt_resp = httpx.post(
            f"{self._url}/session/{session_id}/message",
            json={"parts": [{"type": "text", "text": task}]},
            headers=headers,
            timeout=30,
        )
        if prompt_resp.status_code not in (200, 201, 202):
            return {
                "ok": False,
                "result": f"发送 prompt 失败: {prompt_resp.status_code}",
                "mode": self.get_mode().value,
                "elapsed_seconds": round(time.time() - t0, 2),
                "session_id": session_id,
            }

        # 3. Poll for completion (SSE or polling)
        result_text = self._poll_until_idle(session_id, workspace, timeout, t0)
        elapsed = time.time() - t0

        return {
            "ok": True,
            "result": result_text[:10000] if result_text else "(no output)",
            "mode": self.get_mode().value,
            "elapsed_seconds": round(elapsed, 2),
            "session_id": session_id,
        }

    def _poll_until_idle(
        self,
        session_id: str,
        workspace: str,
        timeout: int,
        t0: float,
    ) -> str:
        """Poll session status until idle or timeout."""
        poll_interval = 2.0

        while (time.time() - t0) < timeout:
            from butler.extensions.opencode_ops import poll_session_status_safe

            transcript = poll_session_status_safe(
                lambda: self._poll_session_once(session_id, workspace),
            )
            if transcript is not None:
                return transcript

            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.2, 10.0)

        return "(timeout waiting for OpenCode session to complete)"

    def _poll_session_once(self, session_id: str, workspace: str) -> str | None:
        import httpx

        headers = self._headers(workspace)
        resp = httpx.get(
            f"{self._url}/session/{session_id}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", {})
            status_type = status.get("type", "") if isinstance(status, dict) else str(status)
            if status_type in ("idle", "completed", "error"):
                return self._fetch_transcript(session_id, workspace)
        return None

    def _fetch_transcript(self, session_id: str, workspace: str) -> str:
        """Fetch the assistant messages from the completed session."""
        from butler.extensions.opencode_ops import fetch_session_transcript_safe

        return fetch_session_transcript_safe(
            lambda: self._fetch_transcript_inner(session_id, workspace),
        )

    def _fetch_transcript_inner(self, session_id: str, workspace: str) -> str:
        import httpx

        headers = self._headers(workspace)
        resp = httpx.get(
            f"{self._url}/session/{session_id}/message",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            messages = resp.json()
            if isinstance(messages, list):
                parts: list[str] = []
                for msg in messages:
                    if msg.get("role") == "assistant":
                        for part in msg.get("parts", []):
                            if part.get("type") == "text" and part.get("text"):
                                parts.append(part["text"])
                return "\n".join(parts) if parts else "(no assistant output)"
        return "(failed to fetch transcript)"


# ─── MCP Bridge mode (stub — OpenCode doesn't expose MCP server) ────

class OpenCodeMCPBridge:
    """MCP bridge mode — requires Butler to expose an MCP server for OpenCode.

    This mode configures OpenCode as an MCP *client* connecting to Butler's
    MCP server. Not implemented as standalone bridge; use HTTP or subprocess.
    """

    def is_available(self) -> bool:
        return False

    def get_mode(self) -> OpenCodeMode:
        return OpenCodeMode.MCP_BRIDGE

    def execute_task(
        self,
        task: str,
        *,
        workspace: str,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "result": (
                "MCP Bridge 模式需要 Butler 作为 MCP Server、OpenCode 作为 MCP Client。"
                "当前推荐使用 subprocess 或 http 模式。"
                "如需 MCP 模式，请配置 BUTLER_MCP_ENABLED=1 并在 OpenCode 的 "
                "opencode.jsonc 中添加 Butler 为 MCP server。"
            ),
            "mode": self.get_mode().value,
            "elapsed_seconds": 0,
        }


# ─── Factory ────────────────────────────────────────────────────────

def get_opencode_bridge() -> OpenCodeBridge:
    """Get the active OpenCode bridge based on BUTLER_OPENCODE_MODE."""
    if not opencode_enabled():
        return _DisabledBridge()

    mode = _env("BUTLER_OPENCODE_MODE", "subprocess")
    if mode == "http":
        return OpenCodeHTTPServer()
    if mode == "mcp":
        return OpenCodeMCPBridge()
    return OpenCodeSubprocess()


class _DisabledBridge:
    """Returned when BUTLER_OPENCODE_ENABLED is not set."""

    def is_available(self) -> bool:
        return False

    def get_mode(self) -> OpenCodeMode:
        return OpenCodeMode.TERMINAL_SUBPROCESS

    def execute_task(
        self,
        task: str,
        *,
        workspace: str,
        timeout_seconds: int = 600,
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "result": (
                "OpenCode 扩展未启用。设置 BUTLER_OPENCODE_ENABLED=1 并安装 opencode 后重试。"
                "详见 docs/architecture/v4-architecture.md §5.2 D-L4-3。"
            ),
            "mode": "disabled",
            "elapsed_seconds": 0,
        }
