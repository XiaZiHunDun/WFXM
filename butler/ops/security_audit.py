"""Static security audit (OpenClaw doctor subset)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditFinding:
    level: str  # info | warn | critical
    code: str
    message: str


def run_security_audit(*, workspace: Path | None = None) -> list[AuditFinding]:
    findings: list[AuditFinding] = []

    if os.getenv("BUTLER_ENABLE_TERMINAL", "0").strip() in ("1", "true", "yes"):
        findings.append(
            AuditFinding(
                "warn",
                "TERMINAL_ENABLED",
                "BUTLER_ENABLE_TERMINAL=1：确认 permissions.yaml 已限制危险命令",
            )
        )

    owner = os.getenv("BUTLER_OWNER_WECHAT_ID", "").strip()
    allow = os.getenv("BUTLER_GATEWAY_ALLOWLIST", "").strip()
    if not owner and not allow:
        findings.append(
            AuditFinding(
                "critical",
                "NO_GATEWAY_OWNER",
                "未配置 BUTLER_OWNER_WECHAT_ID 或 BUTLER_GATEWAY_ALLOWLIST",
            )
        )

    if os.getenv("BUTLER_MCP_ENABLED", "0").strip() in ("1", "true", "yes"):
        hosts = os.getenv("BUTLER_MCP_HTTP_HOSTS_ALLOW", "").strip()
        if not hosts:
            findings.append(
                AuditFinding(
                    "warn",
                    "MCP_HTTP_HOSTS_OPEN",
                    "BUTLER_MCP_ENABLED=1 但 BUTLER_MCP_HTTP_HOSTS_ALLOW 为空",
                )
            )

    if os.getenv("BUTLER_MCP_HTTP_ALLOW_PRIVATE", "0").strip() in ("1", "true", "yes"):
        findings.append(
            AuditFinding(
                "warn",
                "MCP_PRIVATE_HTTP",
                "BUTLER_MCP_HTTP_ALLOW_PRIVATE=1 允许内网 MCP Host",
            )
        )

    if workspace is not None:
        perms = workspace / ".butler" / "permissions.yaml"
        if perms.is_file():
            try:
                import yaml

                data = yaml.safe_load(perms.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    wf = data.get("workflow_steps")
                    if isinstance(wf, dict):
                        for step_id, cfg in wf.items():
                            if isinstance(cfg, dict) and cfg.get("requires_approval"):
                                findings.append(
                                    AuditFinding(
                                        "info",
                                        "WORKFLOW_APPROVAL",
                                        f"workflow 步骤 {step_id} 需人工确认",
                                    )
                                )
            except Exception:
                findings.append(
                    AuditFinding("warn", "PERMS_PARSE", "permissions.yaml 解析失败")
                )

    disable_compact = os.getenv("BUTLER_DISABLE_AUTO_COMPACT", "").strip().lower()
    if disable_compact in ("1", "true", "yes"):
        findings.append(
            AuditFinding(
                "info",
                "AUTO_COMPACT_OFF",
                "BUTLER_DISABLE_AUTO_COMPACT=1 长会话可能更易溢出",
            )
        )

    return findings


def format_audit_report(findings: list[AuditFinding]) -> str:
    if not findings:
        return "Butler doctor: 未发现配置级安全问题。"
    lines = ["Butler doctor 安全审计:"]
    for level in ("critical", "warn", "info"):
        bucket = [f for f in findings if f.level == level]
        if not bucket:
            continue
        lines.append(f"\n[{level.upper()}]")
        for f in bucket:
            lines.append(f"- ({f.code}) {f.message}")
    return "\n".join(lines)
