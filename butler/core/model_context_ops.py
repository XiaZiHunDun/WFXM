"""Model output token resolution (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def resolve_max_output_tokens_safe(
    orchestrator: Any,
    *,
    session_key: str,
    role: str,
) -> int | None:
    def _run() -> int | None:
        from butler.model_resolve import normalize_role, resolve_effective_model
        from butler.project.lead import gateway_loop_role

        loop_role = normalize_role(str(role or "butler").strip() or "butler")
        proj = None
        if orchestrator is not None:
            pm = getattr(orchestrator, "project_manager", None)
            if pm is not None:
                proj_name = ""
                if hasattr(pm, "resolve_active_project_name"):
                    proj_name = str(pm.resolve_active_project_name(session_key=session_key) or "")
                proj = pm.get_current(session_key=session_key) if hasattr(pm, "get_current") else None
                loop_role = gateway_loop_role(proj_name, project=proj)
        cfg = resolve_effective_model(loop_role, project=proj).config
        if cfg.max_tokens and int(cfg.max_tokens) > 0:
            return int(cfg.max_tokens)
        return None

    result = safe_best_effort(_run, label="model_context.max_output_tokens", default=None)
    return int(result) if isinstance(result, int) else None
