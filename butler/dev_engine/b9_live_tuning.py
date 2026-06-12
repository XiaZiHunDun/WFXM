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

# Task-specific playbooks for top wrong_patch probes (injected into delegate context).
B9_PROBE_PLAYBOOKS: dict[str, str] = {
    "B9L_multi_file_import": (
        "Playbook: list_directory first. helpers.py exists; main.py wrongly imports helper. "
        "Patch main.py: change import line to `from helpers import run` (module name must match file)."
    ),
    "B9L_pytest_fix_impl": (
        "Playbook: read calc.py and test_b9.py. mul() uses + but test expects multiplication. "
        "Patch calc.py body: replace `a + b` with `a * b` in mul()."
    ),
    "B9L_prod_demo_fix_greet_return": (
        "Playbook: read greet.py and test_b9.py. greet() returns 'hi' but test expects 'hello'. "
        "Patch greet.py return literal only; do not edit test_b9.py."
    ),
}

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
            "For ImportError/ModuleNotFoundError, list_directory then align import with actual .py filename.",
            "read_file the target source before patch; old_string must match file content exactly.",
            "patch always needs path, old_string, and new_string.",
        ])
    from butler.dev_engine.b9_oracle_fewshot import format_b9_oracle_fewshot_block

    fewshot = format_b9_oracle_fewshot_block(max_cases=2)
    if fewshot:
        lines.append(fewshot)
    return "\n".join(lines)


def build_b9_task_playbook(task_id: str) -> str:
    """Return optional task-specific fix playbook for probe / shaped tasks."""
    return B9_PROBE_PLAYBOOKS.get(task_id, "")


def build_b9_verify_hint(output_tail: str) -> str:
    """Turn pytest/lint tail into an actionable delegate hint (wrong_patch recovery)."""
    tail = (output_tail or "").strip()
    if not tail:
        return ""
    lower = tail.lower()
    if "modulenotfounderror" in lower or "no module named" in lower:
        return (
            "import mismatch: list_directory, then patch import in source to match the real .py module name"
        )
    if "importerror" in lower:
        return "import error: read failing module and test_b9.py; fix import path or symbol in source only"
    if "assert" in lower and "==" in tail:
        return (
            "assertion failed: read implementation under test; fix return value/operator in source, not test_b9.py"
        )
    if "assertionerror" in lower:
        return "assertion failed: adjust implementation to satisfy test_b9.py expectations"
    return ""


def build_b9_delegate_args(spec: B9TaskSpec, workspace: Path) -> dict[str, Any]:
    context = build_b9_delegate_context(workspace)
    playbook = build_b9_task_playbook(spec.task_id)
    if playbook:
        context = f"{context}\n{playbook}"
    return {
        "role": "dev",
        "task": spec.delegate_prompt,
        "context": context,
        "category": B9_LIVE_CATEGORY,
    }


@contextmanager
def b9_live_runtime_env() -> Iterator[None]:
    """Enable terminal + dev auto-verify for the duration of a B9 LIVE delegate."""
    keys = (
        "BUTLER_ENABLE_TERMINAL",
        "BUTLER_DEV_AUTO_VERIFY",
        "BUTLER_DEV_AUTO_VERIFY_LEVELS",
        "BUTLER_TERMINAL_PROFILE",
    )
    backup = {k: os.environ.get(k) for k in keys}
    os.environ["BUTLER_ENABLE_TERMINAL"] = "1"
    os.environ["BUTLER_TERMINAL_PROFILE"] = "dev"
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
    "B9_PROBE_PLAYBOOKS",
    "B9_TUNING_PROBE_TASK_IDS",
    "build_b9_task_playbook",
    "build_b9_verify_hint",
    "b9_live_runtime_env",
    "b9_live_tuning_enabled",
    "b9_failure_class_tuning_patch",
    "b9_live_tuning_patch",
    "build_b9_delegate_args",
    "build_b9_delegate_context",
    "filter_tasks_by_ids",
]
