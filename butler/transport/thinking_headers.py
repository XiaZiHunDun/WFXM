"""Provider-specific thinking / beta API headers (主线 G 深化)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from butler.transport.model_capabilities import model_supports_thinking
from butler.transport.thinking_protocol import thinking_protocol_enabled

logger = logging.getLogger(__name__)

# (provider, model_substring) → anthropic-beta header value (empty = skip)
_DEFAULT_MATRIX: list[tuple[str, str, str]] = [
    ("anthropic", "", "interleaved-thinking-2025-05-14"),
    ("anthropic", "claude-opus-4", "interleaved-thinking-2025-05-14"),
    ("anthropic", "claude-sonnet-4", "interleaved-thinking-2025-05-14"),
]


def _load_env_matrix() -> list[tuple[str, str, str]]:
    raw = os.getenv("BUTLER_THINKING_BETA_MATRIX", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    rows: list[tuple[str, str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        prov = str(item.get("provider") or "").strip().lower()
        model = str(item.get("model_contains") or item.get("model") or "").strip().lower()
        beta = str(item.get("anthropic_beta") or item.get("beta") or "").strip()
        if prov and beta:
            rows.append((prov, model, beta))
    return rows


def resolve_thinking_beta_value(*, provider: str, model: str = "") -> str:
    """Return anthropic-beta header value or empty string."""
    if not thinking_protocol_enabled():
        return ""
    if not model_supports_thinking(provider, model):
        return ""
    override = os.getenv("BUTLER_THINKING_BETA_HEADER", "").strip()
    if override:
        return override
    prov = str(provider or "").strip().lower()
    mlow = str(model or "").strip().lower()
    matrix = _load_env_matrix() or _DEFAULT_MATRIX
    best = ""
    best_len = -1
    for p, substr, beta in matrix:
        if p != prov:
            continue
        if substr and substr not in mlow:
            continue
        key_len = len(substr)
        if key_len >= best_len:
            best_len = key_len
            best = beta
    return best


def merge_thinking_request_kwargs(
    api_kwargs: dict[str, Any],
    *,
    provider: str,
    model: str = "",
) -> dict[str, Any]:
    """Attach ``extra_headers`` for Anthropic thinking beta when configured."""
    beta = resolve_thinking_beta_value(provider=provider, model=model)
    if not beta:
        return api_kwargs
    out = dict(api_kwargs)
    headers = dict(out.get("extra_headers") or {})
    headers["anthropic-beta"] = beta
    out["extra_headers"] = headers
    return out


__all__ = [
    "merge_thinking_request_kwargs",
    "resolve_thinking_beta_value",
]
