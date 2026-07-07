"""Marketplace compatibility best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from butler.core.best_effort import safe_best_effort


def load_mcp_server_ids_safe() -> set[str]:
    def _run() -> set[str]:
        from butler.registry.paths import default_mcp_config_path

        path = default_mcp_config_path()
        if not path.is_file():
            return set()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        servers = data.get("servers") if isinstance(data, dict) else None
        if not isinstance(servers, dict):
            return set()
        return {str(k) for k in servers.keys()}

    result = safe_best_effort(
        _run,
        label="marketplace_compat.mcp_server_ids",
        default=set(),
    )
    return set(result) if isinstance(result, set) else set()


def tenant_skill_stub_path_safe(*, tenant_id: str, skill_name: str) -> Path | None:
    def _run() -> Path:
        from butler.registry.paths import skills_root

        tenant_stub = skills_root(tenant_id=tenant_id) / f"{skill_name}.md"
        if not tenant_stub.is_file():
            raise ValueError("tenant skill stub missing")
        return tenant_stub

    result = safe_best_effort(
        _run,
        label="marketplace_compat.tenant_skill_stub",
        default=None,
    )
    return result if isinstance(result, Path) else None
