"""Security audit best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def mcp_http_audit_findings_safe(*, workspace: Path | None) -> list[Any]:
    def _run() -> list[Any]:
        import os

        from butler.mcp.config import http_mcp_servers_configured
        from butler.ops.security_audit import AuditFinding

        if not http_mcp_servers_configured(workspace=workspace):
            return []
        hosts = os.getenv("BUTLER_MCP_HTTP_HOSTS_ALLOW", "").strip()
        if hosts:
            return []
        return [
            AuditFinding(
                "warn",
                "MCP_HTTP_HOSTS_OPEN",
                "已配置 HTTP MCP server 但 BUTLER_MCP_HTTP_HOSTS_ALLOW 为空",
            )
        ]

    result = safe_best_effort(
        _run,
        label="security_audit.mcp_http",
        default=[],
    )
    return list(result) if isinstance(result, list) else []


def permissions_workflow_findings_safe(perms: Path) -> list[Any]:
    from butler.ops.security_audit import AuditFinding

    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(perms.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return []
        wf = data.get("workflow_steps")
        if not isinstance(wf, dict):
            return []
        findings: list[Any] = []
        for step_id, cfg in wf.items():
            if isinstance(cfg, dict) and cfg.get("requires_approval"):
                findings.append(
                    AuditFinding(
                        "info",
                        "WORKFLOW_APPROVAL",
                        f"workflow 步骤 {step_id} 需人工确认",
                    )
                )
        return findings
    except Exception:
        return [AuditFinding("warn", "PERMS_PARSE", "permissions.yaml 解析失败")]


def terminal_sandbox_audit_findings_safe(*, workspace: Path | None) -> list[Any]:
    def _run() -> list[Any]:
        from butler.ops.terminal_sandbox_diagnostics import audit_terminal_sandbox_findings

        return audit_terminal_sandbox_findings(workspace=workspace)

    result = safe_best_effort(
        _run,
        label="security_audit.terminal_sandbox",
        default=[],
    )
    return list(result) if isinstance(result, list) else []
