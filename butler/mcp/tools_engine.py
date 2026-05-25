"""ToolsEngine subset — FC support check + enable filter (LobeHub / 主线 J P2)."""

from __future__ import annotations

import logging
from typing import Any

from butler.env_parse import env_truthy
from butler.transport.model_capabilities import get_provider_capabilities

logger = logging.getLogger(__name__)


def tools_engine_enabled() -> bool:
    return env_truthy("BUTLER_TOOLS_ENGINE", default=True)


def model_supports_function_calling(provider: str, model: str = "") -> bool:
    """Return False only when explicitly disabled via env."""
    if env_truthy("BUTLER_TOOLS_ENGINE_FORCE_OFF", default=False):
        return False
    cap = get_provider_capabilities(provider)
    if cap.get("function_calling") is False:
        return False
    m = str(model or "").lower()
    if m.endswith("-instruct-only") or "no-tools" in m:
        return False
    return True


def filter_tools_for_model(
    tools: list[dict],
    *,
    provider: str,
    model: str = "",
) -> tuple[list[dict], dict[str, Any]]:
    """Drop tool schemas when model cannot use function calling."""
    diag: dict[str, Any] = {"tools_engine_input": len(tools)}
    working = list(tools)
    try:
        from butler.mcp.tools_manifest import filter_tools_by_mcp_ssot

        working, manifest_diag = filter_tools_by_mcp_ssot(working)
        diag.update(manifest_diag)
    except Exception as exc:
        logger.debug("ToolsEngine manifest merge skipped: %s", exc)

    if not tools_engine_enabled():
        diag["tools_engine_skipped"] = True
        return working, diag
    if model_supports_function_calling(provider, model):
        diag["tools_engine_fc"] = True
        return working, diag
    logger.info("ToolsEngine: FC disabled for %s/%s — %d tools omitted", provider, model, len(working))
    diag["tools_engine_fc"] = False
    diag["tools_engine_dropped"] = len(working)
    return [], diag


__all__ = [
    "filter_tools_for_model",
    "model_supports_function_calling",
    "tools_engine_enabled",
]
