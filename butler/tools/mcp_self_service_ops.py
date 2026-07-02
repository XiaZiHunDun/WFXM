"""MCP self-service tool helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def tool_json_loud(run: Callable[[], str]) -> str:
    try:
        return run()
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)[:300]})


def resolve_project_workspace_safe() -> Path | None:
    def _run() -> Path | None:
        from butler.tools.project_todos import _get_workspace

        return _get_workspace()

    result = safe_best_effort(_run, label="mcp_self_service.workspace", default=None)
    return result if isinstance(result, Path) else None


def attach_post_install_verify_safe(payload: dict[str, Any], sid: str, workspace: Path | None) -> None:
    def _run() -> None:
        from butler.mcp.extension_manifest import get_manifest_by_server_id
        from butler.mcp.extension_verify import (
            format_post_install_verify_hint,
            verify_for_server_id,
            write_verify_cache,
        )

        manifest = get_manifest_by_server_id(sid, workspace)
        if manifest is None:
            return
        report = verify_for_server_id(sid, workspace=workspace, run_golden=False)
        if report is None:
            return
        write_verify_cache({manifest.id: report})
        payload["extension_verify"] = format_post_install_verify_hint(report, manifest)

    safe_best_effort(_run, label="mcp_self_service.post_install_verify", default=None)
