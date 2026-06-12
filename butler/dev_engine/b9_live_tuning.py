"""B9 LIVE delegate tuning — prompts, overrides, and probe task sets."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from butler.dev_engine.b9_types import B9TaskSpec

# Top failure probes (wrong_patch / prod-shaped).
B9_TUNING_PROBE_TASK_IDS: tuple[str, ...] = (
    "B9L_multi_file_import",
    "B9L_pytest_fix_impl",
    "B9L_prod_demo_fix_greet_return",
)

B9_LIVE_CATEGORY = "b9-benchmark"

_DELEGATE_RESCUE_PATCH: dict[str, Any] = {
    "dev_max_fix_rounds": 4,
    "delegate_max_iterations": 32,
    "dev_auto_verify_levels": "lint,typecheck,test",
}


def b9_live_tuning_enabled() -> bool:
    raw = os.getenv("BUTLER_B9_LIVE_TUNING", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def b9_live_tuning_patch() -> dict[str, Any]:
    """Eval override patch applied during B9 LIVE runs (merged with persisted overrides)."""
    if not b9_live_tuning_enabled():
        return {}
    from butler.ops.eval_config_overrides import load_overrides

    patch = dict(_DELEGATE_RESCUE_PATCH)
    data = load_overrides()
    for key in (
        "dev_max_fix_rounds",
        "delegate_max_iterations",
        "dev_auto_verify_levels",
        "coding_knowledge_strict_experience",
        "coding_guidance_max_cases",
        "b9_enhanced_delegate_context",
    ):
        if key in data and data[key] is not None:
            patch[key] = data[key]
    patch["dev_max_fix_rounds"] = max(
        int(patch.get("dev_max_fix_rounds") or _DELEGATE_RESCUE_PATCH["dev_max_fix_rounds"]),
        _DELEGATE_RESCUE_PATCH["dev_max_fix_rounds"],
    )
    patch["delegate_max_iterations"] = max(
        int(patch.get("delegate_max_iterations") or _DELEGATE_RESCUE_PATCH["delegate_max_iterations"]),
        _DELEGATE_RESCUE_PATCH["delegate_max_iterations"],
    )
    return patch


def b9_failure_class_tuning_patch() -> dict[str, Any]:
    """Probe variant: rescue floors + coding guidance + enhanced delegate context."""
    patch = b9_live_tuning_patch()
    patch.update({
        "coding_knowledge_strict_experience": True,
        "coding_guidance_max_cases": 8,
        "b9_enhanced_delegate_context": True,
        "dev_auto_verify_levels": "lint,typecheck,test",
    })
    return patch


def build_b9_delegate_context(workspace: Path) -> str:
    from butler.ops.eval_config_overrides import effective_b9_enhanced_delegate_context

    ws = workspace.resolve()
    lines = [
        f"B9 benchmark workspace (project-bound). All edits under: {ws}",
        "Workflow: read test_b9.py → patch/write source → "
        "`python3 -m pytest test_b9.py -q` via terminal until green.",
        "Do not claim done before pytest passes.",
    ]
    if effective_b9_enhanced_delegate_context():
        lines.extend([
            "After each edit, auto-verify injects pytest/lint feedback — fix before claiming done.",
            "If pytest shows assert X == Y, fix implementation so X equals Y (never edit the test).",
            "For ImportError/ModuleNotFoundError, fix imports or rename modules consistently.",
            "patch always needs path, old_string, and new_string.",
        ])
    return "\n".join(lines)


def build_b9_delegate_args(spec: B9TaskSpec, workspace: Path) -> dict[str, Any]:
    return {
        "role": "dev",
        "task": spec.delegate_prompt,
        "context": build_b9_delegate_context(workspace),
        "category": B9_LIVE_CATEGORY,
    }


@contextmanager
def b9_live_runtime_env() -> Iterator[None]:
    """Enable terminal + dev auto-verify for the duration of a B9 LIVE delegate."""
    keys = (
        "BUTLER_ENABLE_TERMINAL",
        "BUTLER_DEV_AUTO_VERIFY",
        "BUTLER_DEV_AUTO_VERIFY_LEVELS",
    )
    backup = {k: os.environ.get(k) for k in keys}
    os.environ["BUTLER_ENABLE_TERMINAL"] = "1"
    os.environ["BUTLER_DEV_AUTO_VERIFY"] = "1"
    if not os.environ.get("BUTLER_DEV_AUTO_VERIFY_LEVELS", "").strip():
        os.environ["BUTLER_DEV_AUTO_VERIFY_LEVELS"] = "lint,test"
    try:
        yield
    finally:
        for k, v in backup.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def filter_tasks_by_ids(
    tasks: list[B9TaskSpec],
    task_ids: tuple[str, ...] | list[str],
) -> list[B9TaskSpec]:
    wanted = set(task_ids)
    return [t for t in tasks if t.task_id in wanted]


__all__ = [
    "B9_LIVE_CATEGORY",
    "B9_TUNING_PROBE_TASK_IDS",
    "b9_live_runtime_env",
    "b9_live_tuning_enabled",
    "b9_failure_class_tuning_patch",
    "b9_live_tuning_patch",
    "build_b9_delegate_args",
    "build_b9_delegate_context",
    "filter_tasks_by_ids",
]
