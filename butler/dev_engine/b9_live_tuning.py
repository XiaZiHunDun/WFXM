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

B9_EDIT_TOOL_NAMES: frozenset[str] = frozenset({"patch", "write_file", "delete_file"})

# Task-specific playbooks (probe + Tier-1 gate tasks); injected into delegate context.
B9_TASK_PLAYBOOKS: dict[str, str] = {
    # Tier-2 probe (stretch)
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
    # Tier-1 gate (release subset)
    "B9L_test_driven_add": (
        "Playbook: read test_b9.py — needs ping() returning 'pong'. service.py is nearly empty. "
        "write_file or patch service.py: add `def ping():\\n    return 'pong'\\n`. "
        "Then run_pytest until passed=true."
    ),
    "B9L_add_missing_method": (
        "Playbook: read store.py and test_b9.py. Store has put() but no get(); put overwrites _data. "
        "Patch store.py: add __init__ with self._data={}, fix put to self._data[k]=v, add get(self,k)."
    ),
    "B9L_fix_exception_handler": (
        "Playbook: read parser.py and test_b9.py. Bare `except:` swallows ValueError; test expects raise. "
        "Patch parser.py: replace `except:\\n        return None` with `except ValueError:\\n        raise`."
    ),
    "B9L_fix_off_by_one_loop": (
        "Playbook: read loops.py and test_b9.py. sum_until(4) should be 6 (0+1+2+3). "
        "Patch loops.py: change `range(n + 1)` to `range(n)`."
    ),
    "B9L_prod_no_test": (
        "Playbook: read formatter.py and test_b9.py. label('ok') must equal 'ok' (no padding). "
        "Patch formatter.py return: add `.strip()` on the f-string result."
    ),
}

# Back-compat alias
B9_PROBE_PLAYBOOKS = B9_TASK_PLAYBOOKS

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
        "run_pytest (preferred) or `python3 -m pytest test_b9.py -q` until green.",
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

    fewshot = format_b9_oracle_fewshot_block(max_cases=3)
    if fewshot:
        lines.append(fewshot)
    return "\n".join(lines)


def _append_b9_learning_blocks(lines: list[str], task_id: str) -> None:
    try:
        from butler.dev_engine.b9_oracle_curriculum import format_curriculum_block

        block = format_curriculum_block(task_id, max_steps=4)
        if block:
            lines.append(block)
    except Exception:
        pass
    try:
        from butler.ops.b9_lessons import format_b9_lessons_block

        lessons = format_b9_lessons_block(task_id, limit=2)
        if lessons:
            lines.append(lessons)
    except Exception:
        pass


def build_b9_task_playbook(task_id: str) -> str:
    """Return optional task-specific fix playbook for probe / Tier-1 / shaped tasks."""
    return B9_TASK_PLAYBOOKS.get(task_id, "")


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
    if "importerror" in lower or "cannot import name" in lower:
        return (
            "missing symbol: read test_b9.py and target module; add the function/class "
            "or fix import — implementation must export what the test imports"
        )
    if "attributeerror" in lower and "has no attribute" in lower:
        return "missing method: read test_b9.py; add the method/attribute to the class in source"
    if "did not raise" in lower:
        return (
            "exception test: bare except swallowed the error — narrow except or re-raise ValueError "
            "so pytest.raises(ValueError) passes"
        )
    if "assert" in lower and "==" in tail:
        return (
            "assertion failed: read implementation under test; fix return value/operator in source, not test_b9.py"
        )
    if "assertionerror" in lower:
        return "assertion failed: adjust implementation to satisfy test_b9.py expectations"
    return ""


def b9_has_edit_tools(tools_used: list[str] | None) -> bool:
    tools = {str(t).strip().lower() for t in (tools_used or []) if t}
    return bool(tools & B9_EDIT_TOOL_NAMES)


def build_b9_no_edit_retry_banner(
    prior_context: str,
    *,
    failure_tail: str = "",
) -> str:
    extra = ""
    lower = (failure_tail or "").lower()
    if "cannot import name" in lower or "importerror" in lower:
        extra = (
            "\nImportError: the test imports a symbol missing from the module — "
            "write_file or patch the implementation file to define that function/class.\n"
        )
    return (
        "## NO-EDIT RETRY (mandatory)\n"
        "The previous delegate attempt only read/listed files — no patch or write_file. "
        "This benchmark cannot pass without editing source. "
        "read_file the target module, then patch or write_file now."
        f"{extra}\n\n{prior_context}"
    )


def build_b9_delegate_args(spec: B9TaskSpec, workspace: Path) -> dict[str, Any]:
    context = build_b9_delegate_context(workspace)
    extra: list[str] = []
    _append_b9_learning_blocks(extra, spec.task_id)
    playbook = build_b9_task_playbook(spec.task_id)
    if playbook:
        extra.insert(0, f"## TASK PLAYBOOK (priority — follow before generic workflow)\n{playbook}")
    if extra:
        context = "\n\n".join([*extra, context])
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
    "B9_EDIT_TOOL_NAMES",
    "B9_LIVE_CATEGORY",
    "B9_PROBE_PLAYBOOKS",
    "B9_TASK_PLAYBOOKS",
    "B9_TUNING_PROBE_TASK_IDS",
    "b9_has_edit_tools",
    "build_b9_no_edit_retry_banner",
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
