"""Seed L4/L3 production playbooks for delegate rescue, path errors, read_state."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from butler.dev_engine.b9_experience_retrieval import B9_EXPERIENCE_THEOREM_BASIS


@dataclass(frozen=True)
class ProdPlaybookSeed:
    experience_id: str
    title: str
    domain: tuple[str, ...]
    pattern: str
    retrieval_keywords: tuple[str, ...]
    trigger_keywords: tuple[str, ...]


PROD_PLAYBOOK_SEEDS: tuple[ProdPlaybookSeed, ...] = (
    ProdPlaybookSeed(
        experience_id="PROD_PLAYBOOK_delegate_rescue",
        title="Production delegate rescue (verify → patch → re-test)",
        domain=("prod", "playbook", "delegate", "rescue"),
        pattern=(
            "When verify/pytest fails after an edit:\n"
            "1. Read output_tail / failing assertion; do not guess.\n"
            "2. read_file the implementation under test before patch.\n"
            "3. Smallest patch to fix implementation (not tests).\n"
            "4. Re-run pytest; repeat until green or escalate with evidence.\n"
            "5. Lead summary: what failed, what changed, verify status."
        ),
        retrieval_keywords=(
            "verify_fail",
            "pytest",
            "assert",
            "patch",
            "fix",
            "rescue",
            "delegate",
            "output_tail",
        ),
        trigger_keywords=(
            "verify",
            "pytest",
            "失败",
            "assert",
            "fix",
            "green",
            "test fail",
        ),
    ),
    ProdPlaybookSeed(
        experience_id="PROD_PLAYBOOK_path_error",
        title="Workspace-relative paths (no repo prefix)",
        domain=("prod", "playbook", "path", "workspace"),
        pattern=(
            "Sub-agents run with cwd = project workspace root.\n"
            "- Use docs/foo.md, novel-factory/workflow_state.json — never LingWen1/docs/…\n"
            "- File not found: check path is relative to workspace, not monorepo root prefix.\n"
            "- In delegate task/context, repeat the relative path explicitly."
        ),
        retrieval_keywords=(
            "path",
            "workspace",
            "lingwen1/",
            "file not found",
            "docs/",
            "relative",
            "prefix",
        ),
        trigger_keywords=(
            "lingwen1/",
            "file not found",
            "path",
            "docs/",
            "workspace",
            "找不到",
            "前缀",
        ),
    ),
    ProdPlaybookSeed(
        experience_id="PROD_PLAYBOOK_read_state",
        title="READ_STATE before patch/write",
        domain=("prod", "playbook", "read_state"),
        pattern=(
            "Before patch or write_file on existing code:\n"
            "1. read_file the target module (and related imports if needed).\n"
            "2. Satisfy READ_STATE_REQUIRED — do not patch from memory.\n"
            "3. After edit, run pytest or project dev.test_command."
        ),
        retrieval_keywords=(
            "read_state",
            "read_file",
            "before",
            "patch",
            "write_file",
            "edit",
        ),
        trigger_keywords=(
            "read_state",
            "read_file",
            "before edit",
            "patch",
            "write_file",
            "先读",
        ),
    ),
)


def _seed_to_experience(seed: ProdPlaybookSeed) -> Any:
    from butler.dev_engine.coding_knowledge import CodingExperience
    from butler.memory.memory_scope import MemoryScope

    kw = ",".join(seed.retrieval_keywords)
    return CodingExperience(
        id=seed.experience_id,
        title=seed.title,
        domain=list(seed.domain),
        theorem_basis=set(B9_EXPERIENCE_THEOREM_BASIS),
        context=f"{seed.title}; keywords: {', '.join(seed.retrieval_keywords[:12])}",
        pattern=seed.pattern[:2000],
        benchmarks={
            "playbook": "prod_seed",
            "retrieval_keywords": kw,
            "trigger_keywords": ",".join(seed.trigger_keywords),
        },
        validity_start=time.time(),
        validity_end=time.time() + 365 * 86400,
        scope=MemoryScope(level="tenant", visibility="shared", source="prod_playbook"),
    )


def match_prod_playbook_triggers(task: str, context: str = "") -> list[ProdPlaybookSeed]:
    blob = f"{task}\n{context}".lower()
    matched: list[ProdPlaybookSeed] = []
    for seed in PROD_PLAYBOOK_SEEDS:
        if any(kw.lower() in blob for kw in seed.trigger_keywords):
            matched.append(seed)
    return matched


def build_prod_playbook_blocks(task: str, context: str = "") -> list[str]:
    blocks: list[str] = []
    for seed in match_prod_playbook_triggers(task, context):
        blocks.append(
            f"## PROD PLAYBOOK ({seed.experience_id})\n{seed.pattern.strip()}",
        )
    return blocks


def seed_prod_playbooks(
    *,
    butler_home: Any = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Upsert PROD_PLAYBOOK_* experiences into tenant L4 coding_experiences."""
    from butler.config import get_butler_home
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary
    from butler.memory.memory_scope import tenant_coding_experiences_path

    home = butler_home or get_butler_home()
    l4_path = tenant_coding_experiences_path(home)
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(str(l4_path), theorem_lib=tlib)

    added: list[str] = []
    updated: list[str] = []
    for seed in PROD_PLAYBOOK_SEEDS:
        exp = _seed_to_experience(seed)
        existing = xlib.get(seed.experience_id)
        if existing is not None:
            xlib.remove(seed.experience_id)
            updated.append(seed.experience_id)
        else:
            added.append(seed.experience_id)
        if dry_run:
            continue
        xlib.add(exp, skip_validation=True)

    if not dry_run:
        xlib.save_to_file(str(l4_path))

    return {
        "ok": True,
        "dry_run": dry_run,
        "l4_path": str(l4_path),
        "added": added,
        "updated": updated,
        "total": len(PROD_PLAYBOOK_SEEDS),
    }


def verify_prod_playbook_retrieval() -> dict[str, Any]:
    """Smoke: seeded playbooks match experience search keywords."""
    from butler.dev_engine.coding_knowledge import ExperienceLibrary, TheoremLibrary
    from butler.config import get_butler_home
    from butler.memory.memory_scope import tenant_coding_experiences_path

    l4_path = tenant_coding_experiences_path(get_butler_home())
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary.load_from_file(str(l4_path), theorem_lib=tlib)

    checks: list[dict[str, Any]] = []
    ok = True
    probes = (
        ("verify pytest failed patch", "PROD_PLAYBOOK_delegate_rescue"),
        ("lingwen1 docs file not found path", "PROD_PLAYBOOK_path_error"),
        ("read_file before patch edit", "PROD_PLAYBOOK_read_state"),
    )
    for query, expected_id in probes:
        kws = {w.strip().lower() for w in query.split() if w.strip()}
        hits = xlib.search(
            kws,
            set(B9_EXPERIENCE_THEOREM_BASIS),
            strict_coverage=False,
        )
        ids = [h.id for h in hits]
        hit = expected_id in ids
        checks.append({"query": query, "expected": expected_id, "hit": hit, "top": ids[:3]})
        ok = ok and hit

    block_probe = build_prod_playbook_blocks(
        "fix verify_fail pytest assert in greet",
        "path LingWen1/docs missing",
    )
    blocks_ok = len(block_probe) >= 2

    return {"ok": ok and blocks_ok, "checks": checks, "block_count": len(block_probe)}


__all__ = [
    "PROD_PLAYBOOK_SEEDS",
    "build_prod_playbook_blocks",
    "match_prod_playbook_triggers",
    "seed_prod_playbooks",
    "verify_prod_playbook_retrieval",
]
