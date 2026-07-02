"""B9 delegate gate best-effort probes (P0-A)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def tool_safe_root_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.tools.path_safety import tool_safe_root

        return tool_safe_root()

    return safe_best_effort(_run, label="b9_delegate_gate.tool_safe_root", default=None)


def build_b9_verify_hint_safe(failure_tail: str) -> str:
    def _run() -> str:
        from butler.dev_engine.b9_live_tuning import build_b9_verify_hint

        return str(build_b9_verify_hint(failure_tail) or "")

    result = safe_best_effort(_run, label="b9_delegate_gate.verify_hint", default="")
    return str(result or "")


def is_dev_verify_exempt_safe(
    *,
    role: str,
    task: str,
    task_preview: str,
    changes: list | None,
    category_meta: dict[str, Any] | None,
) -> bool | None:
    def _run() -> bool:
        from butler.gateway.delegate_task_kind import is_dev_verify_exempt

        return bool(
            is_dev_verify_exempt(
                role=role,
                task=task,
                task_preview=task_preview,
                changes=changes,
                category_meta=category_meta,
            )
        )

    return safe_best_effort(_run, label="b9_delegate_gate.dev_verify_exempt", default=None)


def auto_verify_enabled_safe() -> bool | None:
    def _run() -> bool:
        from butler.dev_engine.dev_tools import auto_verify_enabled

        return bool(auto_verify_enabled())

    return safe_best_effort(_run, label="b9_delegate_gate.auto_verify_enabled", default=None)


def coding_strict_enabled_safe() -> bool | None:
    def _run() -> bool:
        from butler.dev_engine.dev_tools import coding_strict_enabled

        return bool(coding_strict_enabled())

    return safe_best_effort(_run, label="b9_delegate_gate.coding_strict_enabled", default=None)


def review_strict_enabled_safe() -> bool | None:
    def _run() -> bool:
        from butler.dev_engine.dev_tools import review_strict_enabled

        return bool(review_strict_enabled())

    return safe_best_effort(_run, label="b9_delegate_gate.review_strict_enabled", default=None)


def coding_strict_pilot_categories_safe() -> frozenset[str]:
    def _run() -> frozenset[str]:
        from butler.dev_engine.prod_delegate_bridge import PROD_PLAYBOOK_CATEGORIES

        return PROD_PLAYBOOK_CATEGORIES

    result = safe_best_effort(
        _run,
        label="b9_delegate_gate.pilot_categories",
        default=frozenset({"deep", "quick", "nexus-sprint"}),
    )
    if isinstance(result, frozenset):
        return result
    return frozenset({"deep", "quick", "nexus-sprint"})


def resolve_b9_workspace_tail_safe() -> Path | None:
    root = os.environ.get("BUTLER_TOOL_SAFE_ROOT", "").strip()
    if root:
        try:
            return Path(root).resolve()
        except (TypeError, ValueError, OSError):
            pass
    return tool_safe_root_workspace_safe()
