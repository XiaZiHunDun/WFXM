"""Registry slash-command helpers (P0-A)."""

from __future__ import annotations

import time
from typing import Any

from butler.core.best_effort import safe_best_effort


def default_registry_tenant_id() -> str:
    def _run() -> str:
        from butler.config import load_settings

        return load_settings().default_tenant

    return (
        safe_best_effort(
            _run,
            label="registry_handlers.tenant_id",
            default="default",
        )
        or "default"
    )


def install_skill_or_pending(
    svc: Any,
    identifier: str,
    *,
    platform: str,
    external_id: str | None,
    session_key: str,
    append_followup: Any,
) -> str:
    try:
        rec = svc.install(identifier)
    except Exception as exc:
        from butler.registry.registry_errors import InstallConfirmationRequired

        if isinstance(exc, InstallConfirmationRequired):
            h = exc.hit
            from butler.registry.install_pending import (
                PendingSkillInstall,
                format_pending_prompt,
                save_pending,
            )

            save_pending(
                PendingSkillInstall(
                    identifier=h.identifier,
                    name=h.name,
                    description=h.description,
                    source=h.source,
                    trust=h.trust,
                    session_key=session_key,
                    platform=platform,
                    external_id=external_id or "",
                    requested_at=time.time(),
                )
            )
            return format_pending_prompt(h.name, h.identifier, h.source, h.trust)
        if isinstance(exc, ValueError):
            return f"安装失败: {exc}"
        raise
    warn = "（community 源）" if rec.trust == "community" else ""
    return append_followup(
        svc,
        identifier,
        f"已安装技能 {rec.name}（{rec.install_path}，{rec.scan_verdict}）{warn}",
        record=rec,
    )
