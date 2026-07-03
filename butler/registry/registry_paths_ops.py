"""Registry path resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort
from butler.tenant import DEFAULT_TENANT, normalize_tenant_id


def resolve_tenant_id_safe() -> str:
    def _run() -> str:
        from butler.config import load_settings

        return normalize_tenant_id(load_settings().default_tenant)

    result = safe_best_effort(
        _run,
        label="registry_paths.resolve_tenant",
        default=DEFAULT_TENANT,
    )
    return str(result) if result else DEFAULT_TENANT
