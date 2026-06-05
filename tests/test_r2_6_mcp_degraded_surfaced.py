"""R2-6: Surface degraded MCP servers to model and /诊断.

Per audit R2-6 in docs/reviews/project-deep-audit-2026-06-r1to8.md:
- butler/mcp/manager.py:171-179 (connect path): logger.warning, no exc_info
- butler/mcp/manager.py:265-270 (call_tool runtime path): silent fail,
  no logger at all
- Degraded status is internal: user only sees "Unknown MCP tool" later,
  no clue which server is down or which tools remain available.

Fix:
  1. logger.warning → logger.error(..., exc_info=exc) at the connect
     catch site so the full stack is preserved.
  2. Add logger.error(..., exc_info=exc) to call_tool runtime catch
     (currently no log at all — silent).
  3. Add public method McpConnectionManager.degraded_servers(sk)
     returning [(server_id, transport, last_error), ...] tuples.
  4. Surface degraded servers in format_rag_diagnostic_lines with a
     visible "MCP degraded: N server(s) unavailable" section.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from butler.mcp import manager as mcp_manager_mod
from butler.mcp.config import McpServerConfig
from butler.mcp.manager import McpConnectionManager
from butler.mcp.types import McpServerStatus, McpToolRef


def _make_handle(server_id: str, transport: str = "http") -> mcp_manager_mod._ServerHandle:
    cfg = McpServerConfig(
        server_id=server_id,
        transport=transport,  # type: ignore[arg-type]
        url="http://localhost:0",
    )
    return mcp_manager_mod._ServerHandle(cfg)


# ── 1. Connect path: ERROR level + exc_info, not WARNING ─────────────────


@pytest.mark.module_test
class TestConnectLogsErrorWithExcInfo:
    def test_connect_exception_emits_logger_error_with_exc_info(self, caplog):
        """Audit R2-6 requires the connect catch site to use logger.error
        with exc_info=exc, so the full traceback is preserved in the log.
        """
        caplog.set_level(logging.DEBUG, logger="butler.mcp.manager")

        mgr = McpConnectionManager()
        handle = _make_handle("github", transport="http")
        mgr._global_handles["github"] = handle

        def _boom(_self, h, *, workspace):
            raise RuntimeError("connection refused")

        with patch.object(mgr, "_connect_handle", _boom):
            with mgr._with_handles("s-r2-6") as handles:
                mgr._ensure_connected_locked(
                    "s-r2-6",
                    handles,
                    [handle.config],
                    workspace=None,
                )

        records = [
            r for r in caplog.records
            if r.name == "butler.mcp.manager" and "MCP connect" in r.getMessage()
        ]
        assert records, "expected at least one log record from connect path"
        for r in records:
            assert r.levelno >= logging.ERROR, (
                f"connect exception should log at ERROR or higher, got "
                f"levelno={r.levelno} ({r.levelname})"
            )
            assert r.exc_info is not None, (
                "connect exception log must carry exc_info so the full "
                "stack is preserved"
            )

    def test_no_warning_level_for_connect_exception(self, caplog):
        """No WARNING-level record should be emitted for MCP connect
        failures after R2-6.
        """
        caplog.set_level(logging.DEBUG, logger="butler.mcp.manager")

        mgr = McpConnectionManager()
        handle = _make_handle("github", transport="http")
        mgr._global_handles["github"] = handle

        def _boom(_self, h, *, workspace):
            raise RuntimeError("connection refused")

        with patch.object(mgr, "_connect_handle", _boom):
            with mgr._with_handles("s-r2-6-warn") as handles:
                mgr._ensure_connected_locked(
                    "s-r2-6-warn",
                    handles,
                    [handle.config],
                    workspace=None,
                )

        warn_records = [
            r for r in caplog.records
            if r.name == "butler.mcp.manager"
            and r.levelno == logging.WARNING
            and "MCP connect" in r.getMessage()
        ]
        assert not warn_records, (
            f"connect exception must not log at WARNING; got {warn_records}"
        )


# ── 2. call_tool runtime path: silent-fail → logger.error + exc_info ──────


@pytest.mark.module_test
class TestCallToolRuntimeLogsErrorWithExcInfo:
    def test_call_tool_runtime_exception_emits_logger_error_with_exc_info(
        self, caplog,
    ):
        """Audit R2-6 requires call_tool runtime catch to log at ERROR
        with exc_info — currently the runtime path silently swallows the
        exception.
        """
        caplog.set_level(logging.DEBUG, logger="butler.mcp.manager")

        mgr = McpConnectionManager()
        handle = _make_handle("github", transport="http")
        # Make sure ensure_connected can short-circuit (it would otherwise
        # try to load real MCP configs and overwrite our mock handle).
        ref = McpToolRef(
            server_id="github",
            original_name="ping",
            registered_name="mcp_github_ping",
            classification="readonly",
            input_schema={},
        )
        handle.session = object()  # truthy, so we skip ensure_connected
        with mgr._with_handles("s-r2-6-rt") as handles:
            handles["github"] = handle

        with patch("butler.mcp.manager.run_mcp_async") as mock_run:
            mock_run.side_effect = RuntimeError("runtime boom")
            payload = mgr.call_tool(
                "s-r2-6-rt",
                ref,
                {},
                workspace=None,
            )

        assert "ok" in payload and "false" in payload.lower()

        records = [
            r for r in caplog.records
            if r.name == "butler.mcp.manager"
            and "call" in r.getMessage().lower()
        ]
        assert records, (
            "expected at least one log record from call_tool runtime path; "
            "audit R2-6 requires the silent fail to become visible"
        )
        for r in records:
            assert r.levelno >= logging.ERROR, (
                f"call_tool runtime exception should log at ERROR or higher, "
                f"got levelno={r.levelno}"
            )
            assert r.exc_info is not None, (
                "call_tool runtime log must carry exc_info"
            )

    def test_no_silent_runtime_call_tool_exception(self, caplog):
        """The runtime path must emit at least one log record; before R2-6
        it was completely silent.
        """
        caplog.set_level(logging.DEBUG, logger="butler.mcp.manager")

        mgr = McpConnectionManager()
        handle = _make_handle("github", transport="http")
        ref = McpToolRef(
            server_id="github",
            original_name="ping",
            registered_name="mcp_github_ping",
            classification="readonly",
            input_schema={},
        )
        handle.session = object()
        with mgr._with_handles("s-r2-6-rt-silent") as handles:
            handles["github"] = handle

        with patch("butler.mcp.manager.run_mcp_async") as mock_run:
            mock_run.side_effect = RuntimeError("runtime boom")
            mgr.call_tool("s-r2-6-rt-silent", ref, {}, workspace=None)

        runtime_records = [
            r for r in caplog.records
            if r.name == "butler.mcp.manager"
            and ("call" in r.getMessage().lower() or "github" in r.getMessage())
        ]
        assert runtime_records, (
            "audit R2-6 requires call_tool runtime failures to be logged, "
            "not silently swallowed"
        )


# ── 3. Public degraded_servers(sk) accessor ───────────────────────────────


@pytest.mark.module_test
class TestDegradedServersAccessor:
    def test_degraded_servers_returns_list_with_transport_and_error(self):
        """McpConnectionManager.degraded_servers(sk) must return a list
        of (server_id, transport, last_error) tuples for every handle
        whose status.degraded is True, scoped to *sk*.
        """
        mgr = McpConnectionManager()
        sk = "s-r2-6-degraded"
        with mgr._with_handles(sk) as handles:
            h1 = _make_handle("github", transport="http")
            h1.status = McpServerStatus(
                server_id="github", transport="http",
                degraded=True, last_error="connection refused",
            )
            h2 = _make_handle("jira", transport="stdio")
            h2.status = McpServerStatus(
                server_id="jira", transport="stdio",
                degraded=True, last_error="command not found",
            )
            h3 = _make_handle("ok", transport="http")
            h3.status = McpServerStatus(
                server_id="ok", transport="http",
                degraded=False, connected=True,
            )
            handles["github"] = h1
            handles["jira"] = h2
            handles["ok"] = h3

        result = mgr.degraded_servers(sk)
        assert isinstance(result, list)
        ids = {row[0] for row in result}
        assert "github" in ids
        assert "jira" in ids
        assert "ok" not in ids

        # Verify tuple shape: (server_id, transport, last_error)
        for row in result:
            assert isinstance(row, tuple)
            assert len(row) == 3
            sid, transport, err = row
            assert isinstance(sid, str)
            assert isinstance(transport, str)
            assert isinstance(err, str)

        # Verify transport + last_error fields are present
        github_row = next(r for r in result if r[0] == "github")
        assert github_row[1] == "http"
        assert "refused" in github_row[2]
        jira_row = next(r for r in result if r[0] == "jira")
        assert jira_row[1] == "stdio"
        assert "command" in jira_row[2]

    def test_degraded_servers_empty_when_all_healthy(self):
        mgr = McpConnectionManager()
        sk = "s-r2-6-healthy"
        with mgr._with_handles(sk) as handles:
            h = _make_handle("ok", transport="http")
            h.status = McpServerStatus(
                server_id="ok", transport="http", degraded=False,
            )
            handles["ok"] = h
        assert mgr.degraded_servers(sk) == []


# ── 4. /诊断 display — format_rag_diagnostic_lines includes degraded ──────


@pytest.mark.module_test
class TestFormatRagDiagnosticShowsMcpDegraded:
    def test_rag_diagnostics_lines_include_degraded_servers(self):
        """format_rag_diagnostic_lines must surface degraded MCP servers
        with server_id and a one-line reason so the user (and operator
        looking at /诊断) can see which MCP servers are down.
        """
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        lines = format_rag_diagnostic_lines(
            {
                "semantic_enabled": False,
                "mcp_degraded": [
                    ("github", "http", "connection refused"),
                    ("jira", "stdio", "command not found"),
                ],
            }
        )
        text = "\n".join(lines)
        assert "MCP" in text
        assert "degraded" in text.lower() or "降级" in text or "不可用" in text
        assert "github" in text
        assert "jira" in text
        # Per-scope reason should also be present
        assert "connection refused" in text or "refused" in text
        assert "command not found" in text or "command" in text

    def test_rag_diagnostics_lines_omit_degraded_when_empty(self):
        """Healthy MCP should NOT emit the degraded section."""
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        lines = format_rag_diagnostic_lines(
            {
                "semantic_enabled": False,
                "mcp_degraded": [],
            }
        )
        text = "\n".join(lines)
        # No "MCP degraded" line should appear when no servers are degraded
        assert "MCP 降级" not in text
        assert "MCP degraded" not in text
