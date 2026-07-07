"""Network route manifest load / golden-case helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from butler.core.best_effort import safe_best_effort


def load_yaml_dict_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("manifest root is not a dict")
        return data

    result = safe_best_effort(
        _run,
        label="network_route_verify.load_yaml",
        default=None,
    )
    return result if isinstance(result, dict) else None


def run_policy_golden_case_safe(
    run_case: Any,
    *,
    case_name: str,
) -> str | None:
    try:
        run_case()
        return None
    except Exception as exc:
        return f"{case_name}: {exc}"
