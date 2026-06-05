"""Pre-install security scan for MCP catalog and Skill bundles (REG-P4 / 主线 J P2)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

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
        # Audit R2-5: SSRF guard unavailable → hard-fail install.
        # 旧实现里 `except Exception` 把 ImportError 降级为子串检查,
        # 漏掉云元数据 / IPv6 / RFC1918. 攻击者可故意破坏 import 来
        # 绕过守卫. 这里把 "guard 不可用" 与 "URL 私网" 分开上报.
        "ssrf_check_unavailable",
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


def _build_mcp_scan_blob(entry: McpCatalogEntry, block: dict[str, Any]) -> str:
    # Sprint 22-1 SEC-21-A-2: 扫描 args 字段, 镜像 skill files 全量扫描.
    # block 覆盖 entry.args: 优先用 block 的版本, 否则用 entry 的.
    args_raw = block.get("args")
    args = list(args_raw) if isinstance(args_raw, list) else list(entry.args or [])
    return " ".join(
        [
            entry.title,
            entry.description,
            entry.note,
            str(block.get("command") or ""),
            str(block.get("url") or ""),
            *[str(a) for a in args],
        ]
    )


def _check_mcp_http_url_ssrf(server_id: str, url: str) -> list[str]:
    # Audit R2-5: 子串 fallback (`host in (localhost, 127.0.0.1, 0.0.0.0)`)
    # 漏掉云元数据 / IPv6 / RFC1918, 攻击者可破坏 import 来绕过守卫.
    # 这里 hard-fail: import 失败直接拒绝安装, 不再静默降级.
    try:
        from butler.mcp.config import validate_http_url
        from butler.mcp.types import McpServerConfig
    except ImportError as exc:
        logger.error(
            "SSRF check unavailable (validate_http_url import failed); "
            "rejecting install of MCP server %r",
            server_id,
            exc_info=exc,
        )
        return ["ssrf_check_unavailable"]
    cfg = McpServerConfig(server_id=server_id, transport="http", url=url)
    err = validate_http_url(cfg)
    if err:
        return ["private_url"]
    return []


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
    issues.extend(_scan_text_blob(_build_mcp_scan_blob(entry, block)))
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
            issues.extend(_check_mcp_http_url_ssrf(entry.id, url))
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
