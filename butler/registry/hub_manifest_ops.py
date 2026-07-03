"""Hub manifest check best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def verify_catalog_integrity_safe() -> tuple[bool, list[str]]:
    try:
        from butler.registry.catalog_integrity import verify_catalog_integrity

        ok, errors = verify_catalog_integrity()
        return bool(ok), list(errors)
    except Exception as exc:
        return False, [str(exc)]


def scan_remote_catalog_entries_safe() -> tuple[int, int, list[str]]:
    """Return ``(entry_count, block_count, issues)``."""
    try:
        from butler.registry.install_scan import pre_install_scan_mcp
        from butler.registry.mcp_catalog_remote import load_remote_catalog_entries
        from butler.registry.mcp_install import _entry_to_server_block

        entries = load_remote_catalog_entries()
        issues: list[str] = []
        blocks = 0
        for entry in entries[:24]:
            block = _entry_to_server_block(entry, {})
            scan = pre_install_scan_mcp(entry, block)
            if scan.verdict == "block":
                blocks += 1
                issues.append(f"{entry.id}: {','.join(scan.issues[:4])}")
            elif scan.issues:
                issues.append(f"{entry.id}: warn {scan.issues[0]}")
        return len(entries), blocks, issues
    except Exception as exc:
        logger.debug("hub manifest remote scan: %s", exc)
        return 0, 0, [f"remote_load: {exc}"]
