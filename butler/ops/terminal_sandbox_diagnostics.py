"""Terminal OS sandbox status for doctor / 诊断 / security audit."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy


def _terminal_enabled() -> bool:
    return env_truthy("BUTLER_ENABLE_TERMINAL", default=False)


def _sandbox_enabled() -> bool:
    return env_truthy("BUTLER_TERMINAL_SANDBOX", default=False)


def _sandbox_fail_closed() -> bool:
    return env_truthy("BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE", default=False)


@dataclass(frozen=True)
class TerminalSandboxStatus:
    terminal_enabled: bool
    sandbox_enabled: bool
    fail_if_unavailable: bool
    platform_system: str
    bwrap_path: str | None
    repo_sandbox_json: bool
    user_sandbox_json: bool
    butlerignore_present: bool

    @property
    def bwrap_available(self) -> bool:
        return bool(self.bwrap_path)

    @property
    def linux_host(self) -> bool:
        return self.platform_system.lower() == "linux"

    @property
    def sandbox_operational(self) -> bool:
        return (
            self.sandbox_enabled
            and self.linux_host
            and self.bwrap_available
        )

    @property
    def policy_summary(self) -> str:
        if not self.terminal_enabled:
            return "terminal 未启用"
        if not self.sandbox_enabled:
            return "仅应用层门控（白名单/path/审批）"
        if not self.linux_host:
            return "已配置沙箱开关，但非 Linux（bubblewrap 不可用）"
        if not self.bwrap_available:
            if self.fail_if_unavailable:
                return "沙箱已开但无 bwrap — terminal 将硬失败"
            return "沙箱已开但无 bwrap — 将降级为无沙箱执行"
        return "Linux bubblewrap 终端沙箱"


def collect_terminal_sandbox_status(
    *,
    workspace: Path | None = None,
) -> TerminalSandboxStatus:
    from butler.config import get_butler_home
    from butler.tools.terminal_sandbox import bubblewrap_path

    ws = workspace
    if ws is None:
        try:
            from butler.tools.path_safety import _default_project_workspace

            ws = _default_project_workspace()
        except Exception:
            ws = None

    repo_cfg = False
    ignore_present = False
    if ws is not None:
        repo_cfg = (ws / ".butler" / "sandbox.json").is_file()
        ignore_present = (ws / ".butlerignore").is_file() or (
            ws / ".butler" / ".butlerignore"
        ).is_file()

    home = get_butler_home()
    return TerminalSandboxStatus(
        terminal_enabled=_terminal_enabled(),
        sandbox_enabled=_sandbox_enabled(),
        fail_if_unavailable=_sandbox_fail_closed(),
        platform_system=platform.system(),
        bwrap_path=bubblewrap_path(),
        repo_sandbox_json=repo_cfg,
        user_sandbox_json=(home / "sandbox.json").is_file(),
        butlerignore_present=ignore_present,
    )


def audit_terminal_sandbox_findings(
    *,
    workspace: Path | None = None,
) -> list[Any]:
    """Return ``AuditFinding`` rows for ``run_security_audit``."""
    from butler.ops.security_audit import AuditFinding

    st = collect_terminal_sandbox_status(workspace=workspace)
    findings: list[AuditFinding] = []

    if not st.terminal_enabled:
        return findings

    if not st.sandbox_enabled:
        findings.append(
            AuditFinding(
                "warn",
                "TERMINAL_NO_OS_SANDBOX",
                "BUTLER_ENABLE_TERMINAL=1 但 BUTLER_TERMINAL_SANDBOX=0："
                "建议 Linux 网关启用 bubblewrap 终端沙箱（见 docs/architecture/v4-architecture.md §执行隔离）",
            )
        )
        return findings

    if not st.linux_host:
        findings.append(
            AuditFinding(
                "info",
                "TERMINAL_SANDBOX_NON_LINUX",
                "BUTLER_TERMINAL_SANDBOX=1 但宿主机非 Linux：仅应用层门控生效",
            )
        )
        return findings

    if not st.bwrap_available:
        level = "critical" if st.fail_if_unavailable else "warn"
        findings.append(
            AuditFinding(
                level,
                "TERMINAL_SANDBOX_NO_BWRAP",
                "已开启终端沙箱但未安装 bubblewrap（bwrap）；"
                + (
                    "terminal 将拒绝执行"
                    if st.fail_if_unavailable
                    else "将降级为无沙箱并打 warning"
                )
                + " — 安装: apt install bubblewrap",
            )
        )
    else:
        findings.append(
            AuditFinding(
                "info",
                "TERMINAL_SANDBOX_ACTIVE",
                f"终端 OS 沙箱: bubblewrap ({st.bwrap_path})",
            )
        )

    if not st.repo_sandbox_json and not st.user_sandbox_json:
        findings.append(
            AuditFinding(
                "info",
                "TERMINAL_SANDBOX_DEFAULT_POLICY",
                "未找到 sandbox.json：使用默认 workspace 可写 + 禁网；可复制 .butler/sandbox.json.example",
            )
        )

    if st.terminal_enabled and not st.butlerignore_present and workspace is not None:
        findings.append(
            AuditFinding(
                "info",
                "BUTLERIGNORE_MISSING",
                "项目无 .butlerignore：建议在仓库根添加以屏蔽密钥/产物路径",
            )
        )

    return findings


def format_terminal_sandbox_diagnostic_lines(
    *,
    workspace: Path | None = None,
) -> list[str]:
    st = collect_terminal_sandbox_status(workspace=workspace)
    lines = [f"Terminal 隔离: {st.policy_summary}"]
    if st.terminal_enabled:
        lines.append(
            f"  BUTLER_TERMINAL_SANDBOX={'1' if st.sandbox_enabled else '0'}"
            f" | bwrap={'✓' if st.bwrap_available else '—'}"
            f" | fail_closed={'1' if st.fail_if_unavailable else '0'}"
        )
        if st.sandbox_enabled and st.sandbox_operational:
            cfg_bits = []
            if st.repo_sandbox_json:
                cfg_bits.append("repo sandbox.json")
            if st.user_sandbox_json:
                cfg_bits.append("~/.butler/sandbox.json")
            if st.butlerignore_present:
                cfg_bits.append(".butlerignore")
            lines.append(
                "  配置: " + (", ".join(cfg_bits) if cfg_bits else "默认策略（workspace 可写 + 禁网）")
            )
            lines.append("  升权: Owner /批准沙箱外 <命令>")
    try:
        from butler.ops.runtime_metrics import snapshot_global

        counters = snapshot_global().get("counters") or {}
        run = sum(v for k, v in counters.items() if k.startswith("terminal_sandbox_run"))
        fail = sum(
            v for k, v in counters.items() if k.startswith("terminal_sandbox_failure")
        )
        esc = counters.get("terminal_sandbox_escalation_approved", 0)
        fallback = counters.get("terminal_sandbox_unavailable_fallback", 0)
        if run or fail or esc or fallback:
            lines.append(
                f"  累计: 沙箱执行 {run} | 沙箱失败 {fail} | 沙箱外批准 {esc} | 无 bwrap 降级 {fallback}"
            )
    except Exception:
        pass

    try:
        from butler.ops.env_profiles import (
            current_env_profile,
            profile_expectation,
            profile_mismatch_messages,
        )

        prof_name = current_env_profile()
        if prof_name:
            exp = profile_expectation(prof_name)
            if exp:
                lines.append(f"  Env profile: {prof_name} — {exp.description}")
        for msg in profile_mismatch_messages(bwrap_available=st.bwrap_available):
            lines.append(f"  ⚠ {msg}")
    except Exception:
        pass

    return lines


__all__ = [
    "TerminalSandboxStatus",
    "audit_terminal_sandbox_findings",
    "collect_terminal_sandbox_status",
    "format_terminal_sandbox_diagnostic_lines",
]
