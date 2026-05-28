"""Pre-install security scan for MCP catalog and Skill bundles (REG-P4 / 主线 J P2)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from butler.env_parse import env_truthy
from butler.registry.mcp_catalog import McpCatalogEntry
from butler.registry.skill_types import SkillBundle
from butler.skills.guard import scan_skill_text

logger = logging.getLogger(__name__)

_BLOCK_CODES = frozenset(
    {
        "prompt_injection",
        "code_eval",
        "shell_exec",
        "subprocess",
        "private_url",
        "command_denied",
        "hash_mismatch",
    }
)


@dataclass
class InstallScanResult:
    verdict: str  # clean | warn | block
    issues: list[str] = field(default_factory=list)
    source: str = ""

    @property
    def ok_to_install(self) -> bool:
        return self.verdict != "block"


def install_pre_scan_enabled() -> bool:
    return env_truthy("BUTLER_INSTALL_PRE_SCAN", default=True)


def install_pre_scan_fail_closed() -> bool:
    return env_truthy("BUTLER_INSTALL_PRE_SCAN_FAIL_CLOSED", default=True)


def _finalize(issues: list[str], *, source: str) -> InstallScanResult:
    uniq = sorted(set(issues))
    verdict = "clean"
    if uniq:
        verdict = "warn"
    if any(code in _BLOCK_CODES for code in uniq):
        verdict = "block"
    if any(code in uniq for code in ("prompt_injection", "code_eval", "shell_exec", "subprocess")):
        verdict = "block"
    return InstallScanResult(verdict=verdict, issues=uniq, source=source)


def _scan_text_blob(text: str) -> list[str]:
    return scan_skill_text(text)


def pre_install_scan_mcp(
    entry: McpCatalogEntry,
    block: dict[str, Any],
) -> InstallScanResult:
    """Scan catalog template before writing mcp.yaml."""
    if not install_pre_scan_enabled():
        return InstallScanResult(verdict="clean", source="mcp")
    issues: list[str] = []
    trust = str(entry.trust or "").strip().lower()
    if trust in ("community", "untrusted"):
        issues.append("community_trust")
    blob = " ".join(
        [
            entry.title,
            entry.description,
            entry.note,
            str(block.get("command") or ""),
            str(block.get("url") or ""),
        ]
    )
    issues.extend(_scan_text_blob(blob))
    transport = str(block.get("transport") or entry.transport or "stdio").lower()
    if transport == "stdio":
        cmd = str(block.get("command") or entry.command or "").strip()
        if cmd:
            try:
                from butler.mcp.config import validate_stdio_command
                from butler.mcp.types import McpServerConfig

                cfg = McpServerConfig(server_id=entry.id, transport="stdio", command=cmd)
                err = validate_stdio_command(cfg)
                if err:
                    issues.append("command_denied")
            except Exception as exc:
                logger.debug("pre install scan mcp skipped: %s", exc)
    else:
        url = str(block.get("url") or entry.url or "").strip()
        if url:
            try:
                from butler.mcp.config import validate_http_url
                from butler.mcp.types import McpServerConfig

                cfg = McpServerConfig(server_id=entry.id, transport="http", url=url)
                err = validate_http_url(cfg)
                if err:
                    issues.append("private_url")
            except Exception:
                host = (urlparse(url).hostname or "").lower()
                if host in ("localhost", "127.0.0.1", "0.0.0.0"):
                    issues.append("private_url")
    return _finalize(issues, source=f"mcp:{entry.id}")


def pre_install_scan_skill(
    bundle: SkillBundle,
    *,
    source: str = "",
    expected_content_hash: str = "",
    actual_content_hash: str = "",
) -> InstallScanResult:
    """Scan skill bundle prior to install (market / hub)."""
    if not install_pre_scan_enabled():
        return InstallScanResult(verdict="clean", source="skill")
    issues: list[str] = []
    if expected_content_hash and actual_content_hash:
        if expected_content_hash.strip()[:16] != actual_content_hash.strip()[:16]:
            issues.append("hash_mismatch")
    for _rel, content in bundle.files.items():
        text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)
        issues.extend(scan_skill_text(text))
    return _finalize(issues, source=source or f"skill:{bundle.name}")


def format_scan_message(result: InstallScanResult) -> str:
    if result.verdict == "clean":
        return "安装前扫描: 通过"
    lines = [f"安装前扫描: {result.verdict} ({result.source})"]
    for issue in result.issues[:8]:
        lines.append(f"  • {issue}")
    if len(result.issues) > 8:
        lines.append(f"  … 另有 {len(result.issues) - 8} 项")
    return "\n".join(lines)


__all__ = [
    "InstallScanResult",
    "format_scan_message",
    "install_pre_scan_enabled",
    "install_pre_scan_fail_closed",
    "pre_install_scan_mcp",
    "pre_install_scan_skill",
]
