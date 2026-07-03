"""Butler settings load/save best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

_PRESERVED_CONFIG_KEYS = (
    "gateway",
    "memory",
    "context",
    "auxiliary",
    "embedding",
    "llm_fallback",
    "remote_compact",
)


def load_preserved_config_keys_safe(path: Path) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("config yaml root must be a mapping")
        preserved: dict[str, Any] = {}
        for key in _PRESERVED_CONFIG_KEYS:
            if key in raw:
                preserved[key] = raw[key]
        return preserved

    result = safe_best_effort(
        _run,
        label="config.preserve_keys",
        default={},
    )
    return result if isinstance(result, dict) else {}


def merge_secrets_into_settings_safe(instance: Any) -> None:
    def _run() -> None:
        from butler.config_secrets import merge_secrets_into_settings

        merge_secrets_into_settings(instance)

    safe_best_effort(_run, label="config.merge_secrets", default=None)
