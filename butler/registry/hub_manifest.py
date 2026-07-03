"""Hub / remote catalog manifest checks (市场 manifest 子集)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


@dataclass
class HubManifestReport:
    ok: bool
    catalog_integrity_ok: bool = True
    catalog_errors: list[str] = field(default_factory=list)
    remote_entries: int = 0
    remote_scan_blocks: int = 0
    remote_issues: list[str] = field(default_factory=list)


def hub_manifest_check_enabled() -> bool:
    return env_truthy("BUTLER_HUB_MANIFEST_CHECK", default=True)


def verify_hub_manifest() -> HubManifestReport:
    """Bundled catalog SHA + optional remote MCP catalog pre-scan."""
    report = HubManifestReport(ok=True)
    if not hub_manifest_check_enabled():
        return report

    from butler.registry.hub_manifest_ops import (
        scan_remote_catalog_entries_safe,
        verify_catalog_integrity_safe,
    )

    ok, errors = verify_catalog_integrity_safe()
    report.catalog_integrity_ok = ok
    report.catalog_errors = list(errors)
    if not ok:
        report.ok = False

    if not os.getenv("BUTLER_MCP_CATALOG_URLS", "").strip():
        return report

    entry_count, block_count, issues = scan_remote_catalog_entries_safe()
    report.remote_entries = entry_count
    report.remote_scan_blocks = block_count
    report.remote_issues.extend(issues)
    if block_count:
        report.ok = False

    return report


def format_hub_manifest_report(report: HubManifestReport) -> str:
    lines = [
        f"Registry manifest: {'OK' if report.ok else 'ISSUES'}",
        f"  catalog integrity: {'OK' if report.catalog_integrity_ok else 'FAIL'}",
    ]
    for err in report.catalog_errors[:6]:
        lines.append(f"    • {err}")
    if report.remote_entries:
        lines.append(f"  remote catalog entries: {report.remote_entries}")
        if report.remote_scan_blocks:
            lines.append(f"  remote blocked: {report.remote_scan_blocks}")
    for issue in report.remote_issues[:8]:
        lines.append(f"    • {issue}")
    if not os.getenv("BUTLER_MCP_CATALOG_URLS", "").strip():
        lines.append("  remote: (BUTLER_MCP_CATALOG_URLS unset)")
    return "\n".join(lines)


__all__ = [
    "HubManifestReport",
    "format_hub_manifest_report",
    "hub_manifest_check_enabled",
    "verify_hub_manifest",
]
