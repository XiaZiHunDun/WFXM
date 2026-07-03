"""Bridge B9 seed playbooks / retrieval into production-shaped dev delegates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.dev_engine.b9_delegate_gate import (
    LINGWEN_DRILL_CATEGORY,
    LINGWEN_PROD_SAMPLE_CATEGORY,
    SWE_LIVE_CATEGORY,
)
from butler.dev_engine.b9_live_tuning import B9_LIVE_CATEGORY
from butler.dev_engine.b9_experience_retrieval import (
    TASK_RETRIEVAL_KEYWORDS,
    retrieval_keywords_for_task,
)
from butler.dev_engine.b9_live_tuning import (
    _append_b9_learning_blocks,
    build_b9_task_playbook,
)
from butler.memory.memory_scope import (
    LINGWEN1_PROJECT_ID,
    project_coding_experiences_path,
    tenant_coding_experiences_path,
)

# Dev categories that receive task→playbook bridge (not full b9-benchmark runner).
PROD_PLAYBOOK_CATEGORIES: frozenset[str] = frozenset(
    {
        LINGWEN_PROD_SAMPLE_CATEGORY,
        LINGWEN_DRILL_CATEGORY,
        "deep",
        "quick",
        "nexus-sprint",
    }
)

_SKIP_PLAYBOOK_CATEGORIES: frozenset[str] = frozenset(
    {B9_LIVE_CATEGORY, SWE_LIVE_CATEGORY}
)

LINGWEN_SAMPLE_TO_B9_TASK: dict[str, str] = {
    "lingwen1-sample-demo-import": "B9L_prod_lingwen_demo_add",
    "lingwen1-sample-constants-comment": "B9L_prod_lingwen_constants_docstring",
    "lingwen1-sample-validate-progress": "B9L_prod_lingwen_validate_progress",
}

_MIN_KEYWORD_MATCH_SCORE = 3


def _category_name(
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> str:
    return str(category or (category_meta or {}).get("category") or "").strip()


def should_apply_prod_delegate_bridge(
    *,
    role: str,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> bool:
    """Whether to inject production playbook blocks into delegate context."""
    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return False
    cat = _category_name(category, category_meta)
    if cat in _SKIP_PLAYBOOK_CATEGORIES:
        return False
    if cat in PROD_PLAYBOOK_CATEGORIES:
        return True
    return not cat


def infer_b9_task_id(
    task: str,
    context: str = "",
    *,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> str:
    """Best-effort map production delegate text → B9 task_id for playbook/retrieval."""
    blob = f"{task}\n{context}".lower()
    cat = _category_name(category, category_meta)

    for sample_id, b9_task in LINGWEN_SAMPLE_TO_B9_TASK.items():
        if sample_id in blob:
            return b9_task

    if cat == LINGWEN_DRILL_CATEGORY:
        return "B9L_prod_lingwen_demo_add"

    best_id = ""
    best_score = 0
    for task_id, keywords in TASK_RETRIEVAL_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw and kw in blob)
        if score > best_score:
            best_score = score
            best_id = task_id
    if best_score >= _MIN_KEYWORD_MATCH_SCORE:
        return best_id
    return ""


PRODUCTION_AUTO_VERIFY_LEVELS = "lint,typecheck,test"


def production_auto_verify_levels(
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> str:
    """Benchmark-aligned verify levels for production-shaped dev delegates."""
    cat = _category_name(category, category_meta)
    if cat in PROD_PLAYBOOK_CATEGORIES or not cat:
        return PRODUCTION_AUTO_VERIFY_LEVELS
    return ""


def experience_task_affinity(
    experience_id: str,
    *,
    inferred_task_id: str = "",
) -> bool | None:
    """True when selected experience aligns with inferred B9 task; None if unknown."""
    eid = (experience_id or "").strip()
    tid = (inferred_task_id or "").strip()
    if not eid or not tid:
        return None
    exp_core = eid.removeprefix("B9_EX_").removeprefix("PROD_FAIL_").lower()
    task_core = tid.removeprefix("B9L_").lower()
    if exp_core == task_core:
        return True
    if exp_core in task_core or task_core in exp_core:
        return True
    if exp_core.startswith("prod_") and task_core.startswith("prod_"):
        return exp_core.split("_", 2)[-1] == task_core.split("_", 2)[-1]
    return False


def production_delegate_keywords(
    task: str,
    context: str = "",
    *,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> list[str]:
    """Keywords for process_task — task tokens + inferred production retrieval aliases."""
    base = [w.strip().lower() for w in (task or "").split() if w.strip()]
    task_id = infer_b9_task_id(
        task,
        context,
        category=category,
        category_meta=category_meta,
    )
    if task_id:
        base.extend(retrieval_keywords_for_task(task_id))
    seen: set[str] = set()
    out: list[str] = []
    for kw in base:
        if kw and kw not in seen:
            seen.add(kw)
            out.append(kw)
    return out


def build_production_delegate_blocks(
    task: str,
    context: str = "",
    *,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> list[str]:
    """Context blocks to prepend for production dev delegates."""
    if not should_apply_prod_delegate_bridge(
        role="dev",
        category=category,
        category_meta=category_meta,
    ):
        return []

    blocks: list[str] = []
    blob = f"{task}\n{context}"
    from butler.dev_engine.prod_delegate_bridge_ops import (
        build_prod_playbook_blocks_safe,
        collect_lingwen_prod_sample_playbooks_safe,
    )

    blocks.extend(build_prod_playbook_blocks_safe(task, context))
    blocks.extend(collect_lingwen_prod_sample_playbooks_safe(blob))

    task_id = infer_b9_task_id(
        task,
        context,
        category=category,
        category_meta=category_meta,
    )
    if task_id:
        playbook = build_b9_task_playbook(task_id)
        if playbook:
            blocks.insert(
                0,
                f"## TASK PLAYBOOK (production bridge — {task_id})\n{playbook}",
            )
        learning: list[str] = []
        _append_b9_learning_blocks(learning, task_id)
        blocks.extend(learning)

    return blocks


def enrich_delegate_context_for_production(
    context: str,
    *,
    task: str,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
) -> str:
    """Prepend production bridge blocks to delegate context."""
    blocks = build_production_delegate_blocks(
        task,
        context,
        category=category,
        category_meta=category_meta,
    )
    if not blocks:
        return context
    merged = "\n\n".join([*blocks, context.strip()]) if context.strip() else "\n\n".join(blocks)
    return merged.strip()


def migrate_lingwen_experiences_to_l3(
    *,
    butler_home: Path | str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Move LingWen private B9_EX_prod_lingwen_* from L4 tenant file to project L3."""
    from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary, TheoremLibrary
    from butler.memory.memory_scope import MemoryScope, infer_default_scope
    from butler.project.manager import get_project_manager

    home = Path(butler_home).expanduser().resolve()
    l4_path = tenant_coding_experiences_path(home)
    tenant_lib = ExperienceLibrary.load_from_file(str(l4_path), theorem_lib=TheoremLibrary())

    proj = get_project_manager().get_project(LINGWEN1_PROJECT_ID)
    if proj is None or not getattr(proj, "workspace", None):
        return {
            "ok": False,
            "reason": "lingwen_project_missing",
            "project": LINGWEN1_PROJECT_ID,
        }
    workspace = Path(proj.workspace).expanduser().resolve()
    l3_path = project_coding_experiences_path(workspace)

    migrated: list[str] = []
    l3_lib = None
    if not dry_run:
        l3_lib = ExperienceLibrary.load_from_file(str(l3_path), theorem_lib=TheoremLibrary())

    for exp_id, exp in list(tenant_lib._experiences.items()):
        scope = exp.scope
        if not scope.project_id and exp_id.startswith("B9_EX_prod_lingwen"):
            scope = infer_default_scope(exp_id=exp_id, domain=exp.domain)
        is_lingwen_private = (
            scope.project_id == LINGWEN1_PROJECT_ID
            and scope.visibility == "private"
            and (
                exp_id.startswith("B9_EX_prod_lingwen")
                or "prod_lingwen" in exp_id
            )
        )
        if not is_lingwen_private:
            continue

        l3_exp = CodingExperience(
            id=exp.id,
            title=exp.title,
            domain=list(exp.domain),
            theorem_basis=set(exp.theorem_basis),
            context=exp.context,
            pattern=exp.pattern,
            benchmarks=dict(exp.benchmarks),
            validity_start=exp.validity_start,
            validity_end=exp.validity_end,
            supersedes=exp.supersedes,
            scope=MemoryScope(
                level="project",
                project_id=LINGWEN1_PROJECT_ID,
                visibility="private",
                stack_tags=("novel-factory", "content"),
                source="b9",
            ),
        )
        migrated.append(exp_id)
        if dry_run:
            continue
        tenant_lib.remove(exp_id)
        assert l3_lib is not None
        l3_lib.add(l3_exp, skip_validation=True)

    if migrated and not dry_run and l3_lib is not None:
        l3_lib.save_to_file(str(l3_path))
        tenant_lib.save_to_file(str(l4_path))

    return {
        "ok": True,
        "dry_run": dry_run,
        "migrated": migrated,
        "l3_path": str(l3_path),
        "l4_path": str(l4_path),
        "l3_count": len(migrated) if dry_run else len(migrated),
    }


__all__ = [
    "PROD_PLAYBOOK_CATEGORIES",
    "PRODUCTION_AUTO_VERIFY_LEVELS",
    "build_production_delegate_blocks",
    "enrich_delegate_context_for_production",
    "experience_task_affinity",
    "infer_b9_task_id",
    "migrate_lingwen_experiences_to_l3",
    "production_auto_verify_levels",
    "production_delegate_keywords",
    "should_apply_prod_delegate_bridge",
]
