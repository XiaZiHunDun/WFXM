"""Resolve model context window / output limits for context budgeting."""

from __future__ import annotations

from typing import Any
import logging


logger = logging.getLogger(__name__)

def resolve_max_output_tokens(
    orchestrator: Any,
    *,
    session_key: str = "",
    role: str = "butler",
) -> int | None:
    """Return configured max_tokens for the active loop role, if set."""
    try:
        from butler.model_resolve import normalize_role, resolve_effective_model

        loop_role = normalize_role(str(role or "butler").strip() or "butler")
        proj = None
        if orchestrator is not None:
            pm = getattr(orchestrator, "project_manager", None)
            if pm is not None:
                proj_name = ""
                if hasattr(pm, "resolve_active_project_name"):
                    proj_name = str(
                        pm.resolve_active_project_name(session_key=session_key) or ""
                    )
                from butler.project.lead import gateway_loop_role

                proj = pm.get_current(session_key=session_key) if hasattr(pm, "get_current") else None
                loop_role = gateway_loop_role(proj_name, project=proj)
        cfg = resolve_effective_model(loop_role, project=proj).config
        if cfg.max_tokens and int(cfg.max_tokens) > 0:
            return int(cfg.max_tokens)
    except Exception as exc:
        logger.debug("resolve max output tokens skipped: %s", exc)
    return None
