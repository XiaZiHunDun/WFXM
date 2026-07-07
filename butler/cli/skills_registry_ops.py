"""Best-effort helpers for skills CLI (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def default_tenant_id_safe() -> str:
    def _run() -> str:
        from butler.config import load_settings

        return str(load_settings().default_tenant)

    result = safe_best_effort(_run, label="skills_registry.tenant_id", default="default")
    return str(result or "default")


def run_skill_install_cli(
    svc: Any,
    *,
    identifier: str,
    name_override: str,
    force: bool,
    confirmed: bool,
) -> tuple[int, str, Any | None]:
    """Return (exit_code, user_message, install_record)."""
    try:
        rec = svc.install(
            identifier,
            name_override=name_override,
            force=force,
            confirmed=confirmed,
        )
        return 0, "", rec
    except Exception as exc:
        from butler.registry.registry_errors import InstallConfirmationRequired

        if isinstance(exc, InstallConfirmationRequired):
            h = exc.hit
            return (
                2,
                (
                    f"需要确认安装 [{h.source}/{h.trust}]: {h.name}\n"
                    f"  id: {h.identifier}\n"
                    f"重试: butler skills install {h.identifier} --yes"
                ),
                None,
            )
        if isinstance(exc, ValueError):
            return 1, f"安装失败: {exc}", None
        raise
