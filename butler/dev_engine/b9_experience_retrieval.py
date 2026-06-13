"""Production-facing retrieval aliases for B9 / SWE coding experiences."""

from __future__ import annotations

import time
from typing import Any

# Map benchmark task_id → production delegate keywords (lowercase).
TASK_RETRIEVAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "B9L_two_file_patch": ("threshold", "config", "filter", "predicate", "constant", "pytest"),
    "B9L_extract_constant": ("constant", "extract", "import", "refactor", "max_retries", "shared"),
    "B9L_test_driven_add": ("ping", "pong", "missing", "function", "import", "pytest", "implement"),
    "B9L_add_missing_method": ("get", "put", "store", "method", "dict", "class", "pytest"),
    "B9L_fix_exception_handler": ("exception", "valueerror", "bare", "except", "raise", "parser", "pytest"),
    "B9L_fix_off_by_one_loop": ("off", "by", "one", "range", "loop", "sum", "pytest"),
    "B9L_prod_no_test": ("strip", "trim", "return", "literal", "formatter", "pytest"),
    "B9L_multi_file_import": ("import", "helpers", "helper", "module", "importerror", "modulenotfound", "main"),
    "B9L_pytest_fix_impl": ("operator", "mul", "multiply", "calc", "arithmetic", "pytest"),
    "B9L_prod_demo_fix_greet_return": ("greet", "hello", "hi", "return", "literal", "verify_fail", "pytest"),
    "B9L_prod_read_state_greet": (
        "greet", "hello", "read_file", "read_state", "patch", "before", "edit", "pytest",
    ),
    "B9L_prod_main_helpers_import": (
        "main", "helpers", "helper", "import", "module", "importerror", "list_directory", "pytest",
    ),
    "B9L_prod_cross_module_rename": (
        "rename", "getdata", "get_data", "client", "pkg", "refactor", "multi_file", "pytest",
    ),
    "B9L_prod_lingwen_demo_add": (
        "lingwen", "lingwen1", "demo", "hello", "add", "operator", "subtract", "pytest", "灵文",
    ),
    "B9L_prod_lingwen_workflow_guard": (
        "lingwen", "lingwen1", "novel", "factory", "workflow", "guard", "待修复", "completed", "pytest",
    ),
    "B9L_prod_verify_fail": ("divide", "zero", "division", "verify", "pytest", "handler"),
    "B9L_prod_patch_wrong": ("patch", "wrong", "operator", "fix", "implementation", "pytest"),
    "B9L_prod_no_test": ("no", "test", "read", "only", "edit", "patch", "pytest"),
    "SWE-013": ("api", "response", "status", "http", "code", "ok", "error", "make_response"),
    "SWE-014": ("eventbus", "event", "unsubscribe", "callback", "listener", "on(", "events"),
    "SWE-015": ("priority", "queue", "pop", "heap", "min", "ordering"),
}

# Theorems injected into all B9 experiences so strict retrieval matches prod tasks.
B9_EXPERIENCE_THEOREM_BASIS: frozenset[str] = frozenset({"T01", "T04", "T03", "T10"})

# Broad benchmark experiences require task-specific anchor tokens (or inferred task match).
GENERIC_BENCHMARK_EXPERIENCE_ANCHORS: dict[str, frozenset[str]] = {
    "B9_EX_test_driven_add": frozenset(
        {"ping", "pong", "test_driven_add", "b9l_test_driven_add"},
    ),
    "B9_EX_prod_read_state_greet": frozenset(
        {"read_state", "before", "b9l_prod_read_state_greet", "prod_read_state_greet"},
    ),
}

# Low-signal tokens that alone should not unlock a B9_EX benchmark experience.
GENERIC_RETRIEVAL_TOKENS: frozenset[str] = frozenset(
    {
        "pytest",
        "test",
        "tests",
        "implement",
        "fix",
        "fixed",
        "patch",
        "edit",
        "verify",
        "failed",
        "fail",
        "run",
        "missing",
        "function",
        "import",
        "return",
        "only",
        "read",
        "wrong",
        "green",
        "assert",
        "add",
        "hello",
        "demo",
    },
)


def task_specific_anchors(b9_task: str) -> frozenset[str]:
    """Non-generic keywords for a B9L task — used as eligibility anchors."""
    kws = TASK_RETRIEVAL_KEYWORDS.get((b9_task or "").strip(), ())
    specific = {k for k in kws if k not in GENERIC_RETRIEVAL_TOKENS}
    tid = (b9_task or "").strip().lower()
    if tid:
        specific.add(tid)
        specific.add(tid.removeprefix("b9l_"))
    return frozenset(specific)


def _experience_task_affinity_match(
    experience_id: str,
    *,
    inferred_task_id: str,
    benchmarks: dict[str, Any] | None,
) -> bool:
    tid = (inferred_task_id or "").strip()
    if tid:
        try:
            from butler.dev_engine.prod_delegate_bridge import experience_task_affinity

            if experience_task_affinity(experience_id, inferred_task_id=tid):
                return True
        except Exception:
            pass
    b9_task = str((benchmarks or {}).get("b9_task") or "").strip()
    return bool(tid and b9_task and b9_task == tid)


def experience_retrieval_eligible(
    experience_id: str,
    *,
    normalized_keywords: set[str],
    inferred_task_id: str = "",
    benchmarks: dict[str, Any] | None = None,
) -> bool:
    """Filter over-broad benchmark experiences (e.g. test_driven_add on greet tasks)."""
    if experience_id.startswith("PROD_FAIL_"):
        return True
    if _experience_task_affinity_match(
        experience_id,
        inferred_task_id=inferred_task_id,
        benchmarks=benchmarks,
    ):
        return True

    b9_task = str((benchmarks or {}).get("b9_task") or "").strip()
    manual = GENERIC_BENCHMARK_EXPERIENCE_ANCHORS.get(experience_id)
    if manual:
        return bool(normalized_keywords & manual)

    if experience_id.startswith("B9_EX_") and b9_task:
        specific = task_specific_anchors(b9_task)
        if specific:
            return bool(normalized_keywords & specific)

    if experience_id.startswith("B9_EX_") and not b9_task:
        return True

    if experience_id.startswith("B9_EX_"):
        return False

    return True


FAILURE_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "verify_fail": ("pytest", "assert", "verify", "test", "failed", "green"),
    "patch_wrong": ("patch", "wrong", "assert", "implementation", "fix", "operator"),
    "no_test": ("pytest", "test", "missing", "verify", "run"),
    "no_edit": ("read", "patch", "write_file", "edit", "implement"),
    "wrong_patch": ("patch", "wrong", "assert", "fix"),
    "tool_wrong": ("tool", "terminal", "read_file", "patch"),
    "read_state": ("read_file", "read_state", "before", "edit", "patch"),
    "verify_failed": ("verify", "pytest", "failed", "test"),
    "other_fail": ("fix", "delegate", "pytest"),
}


def retrieval_keywords_for_task(
    task_id: str,
    *,
    classification: str = "",
    extra: list[str] | None = None,
) -> list[str]:
    """Collect lowercase keywords for experience retrieval / context enrichment."""
    keys: list[str] = []
    tid = (task_id or "").strip()
    if tid in TASK_RETRIEVAL_KEYWORDS:
        keys.extend(TASK_RETRIEVAL_KEYWORDS[tid])
    cls = (classification or "").strip().lower()
    if cls in FAILURE_CLASS_KEYWORDS:
        keys.extend(FAILURE_CLASS_KEYWORDS[cls])
    if extra:
        keys.extend(str(x).lower() for x in extra if x)
    # stable dedupe
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        k = k.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def apply_retrieval_benchmarks(
    benchmarks: dict[str, str],
    task_id: str,
    *,
    classification: str = "",
    extra: list[str] | None = None,
) -> dict[str, str]:
    """Attach retrieval_keywords to benchmarks for ExperienceLibrary.search."""
    merged = dict(benchmarks)
    kws = retrieval_keywords_for_task(task_id, classification=classification, extra=extra)
    if kws:
        merged["retrieval_keywords"] = ",".join(kws)
    return merged


def enrich_b9_experience_context(task_id: str, *, classification: str = "") -> str:
    """Human-readable context line so keyword search hits production phrasing."""
    kws = retrieval_keywords_for_task(task_id, classification=classification)
    if not kws:
        return task_id
    return f"{task_id}; production keywords: {', '.join(kws[:16])}"


def experience_retrieval_rank_bonus(
    *,
    experience_id: str,
    normalized_keywords: set[str],
    inferred_task_id: str = "",
    project_id: str = "",
    benchmarks: dict[str, Any] | None = None,
    scope_level: str = "",
    scope_project_id: str = "",
    scope_source: str = "",
    domain: list[str] | None = None,
) -> int:
    """Boost prod/L3/task-aligned experiences in search ranking."""
    bonus = 0
    tid = (inferred_task_id or "").strip()
    if tid:
        try:
            from butler.dev_engine.prod_delegate_bridge import experience_task_affinity

            if experience_task_affinity(experience_id, inferred_task_id=tid):
                bonus += 100
        except Exception:
            pass
    b9_task = str((benchmarks or {}).get("b9_task") or "").strip()
    if tid and b9_task == tid:
        bonus += 80
    if project_id and scope_project_id == project_id:
        bonus += 40
    if scope_level == "project":
        bonus += 10
    if scope_source == "prod_failure":
        bonus += 25
    eid_lower = experience_id.lower()
    domains = [str(d).lower() for d in (domain or [])]
    if "prod" in eid_lower or "prod_shaped" in domains:
        bonus += 15
    return bonus


def backfill_b9_experience_retrieval(*, xlib_path: str | None = None) -> dict[str, Any]:
    """Rewrite B9_EX_* / B9_FAIL_* entries with retrieval_keywords on disk."""
    import os

    from butler.config import get_butler_home
    from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary, TheoremLibrary

    path = xlib_path or os.path.join(get_butler_home(), "coding_experiences.json")
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(path, theorem_lib=tlib)
    updated = 0
    for exp_id, exp in list(xlib._experiences.items()):
        if not exp_id.startswith("B9_"):
            continue
        task_id = str(exp.benchmarks.get("b9_task") or "")
        if not task_id:
            if exp_id.startswith("B9_EX_"):
                task_id = "B9L_" + exp_id.replace("B9_EX_", "", 1)
            elif exp_id.startswith("B9_FAIL_"):
                slug = exp_id.replace("B9_FAIL_", "", 1)
                task_id = f"SWE-{slug.replace('swe_', '')}" if slug.startswith("swe_") else f"B9L_{slug}"
        classification = str(exp.benchmarks.get("failure_class") or "")
        if "failure" in exp.domain and not classification:
            classification = next((d for d in exp.domain if d not in ("b9", "failure")), "")
        new_benchmarks = apply_retrieval_benchmarks(
            dict(exp.benchmarks),
            task_id,
            classification=classification,
        )
        new_context = enrich_b9_experience_context(task_id, classification=classification)
        new_basis = set(exp.theorem_basis) | set(B9_EXPERIENCE_THEOREM_BASIS)
        if (
            new_benchmarks == exp.benchmarks
            and new_context == exp.context
            and new_basis == set(exp.theorem_basis)
        ):
            continue
        xlib._experiences[exp_id] = CodingExperience(
            id=exp.id,
            title=exp.title,
            domain=exp.domain,
            theorem_basis=new_basis,
            context=new_context,
            pattern=exp.pattern,
            benchmarks=new_benchmarks,
            validity_start=exp.validity_start,
            validity_end=exp.validity_end,
            supersedes=exp.supersedes,
        )
        updated += 1
    if updated:
        xlib.save_to_file(path)
    total_b9 = sum(1 for eid in xlib._experiences if eid.startswith("B9_"))
    created = _seed_missing_prod_experiences(xlib, path)
    return {"updated": updated, "created": created, "path": path, "total_b9": total_b9}


def _seed_missing_prod_experiences(xlib: Any, path: str) -> int:
    """Ensure B9_EX_* rows exist for prod-shaped task aliases (minimal pattern)."""
    from butler.dev_engine.coding_knowledge import CodingExperience

    created = 0
    prod_tasks = (
        "B9L_prod_demo_fix_greet_return",
        "B9L_prod_read_state_greet",
        "B9L_prod_main_helpers_import",
        "B9L_prod_cross_module_rename",
        "B9L_prod_lingwen_demo_add",
        "B9L_prod_lingwen_workflow_guard",
        "B9L_prod_verify_fail",
        "B9L_prod_patch_wrong",
        "B9L_prod_no_test",
    )
    for task_id in prod_tasks:
        exp_id = f"B9_EX_{task_id.replace('B9L_', '')}"
        if xlib.get(exp_id) is not None:
            continue
        kws = retrieval_keywords_for_task(task_id)
        if not kws:
            continue
        pattern = f"Production-shaped B9 task {task_id}. Keywords: {', '.join(kws[:8])}."
        exp = CodingExperience(
            id=exp_id,
            title=f"B9 prod template {task_id}",
            domain=["b9", "prod_shaped", "pytest"],
            theorem_basis=set(B9_EXPERIENCE_THEOREM_BASIS),
            context=enrich_b9_experience_context(task_id),
            pattern=pattern,
            benchmarks=apply_retrieval_benchmarks({"b9_task": task_id}, task_id),
            validity_start=time.time(),
            validity_end=time.time() + 365 * 86400,
        )
        if xlib.add(exp, skip_validation=True)[0]:
            created += 1
    if created:
        xlib.save_to_file(path)
    return created
