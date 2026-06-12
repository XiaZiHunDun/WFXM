"""Tier-1 curriculum episodes must have matching catalog skills."""

from __future__ import annotations

from pathlib import Path

from butler.dev_engine.b9_oracle_curriculum import B9_ORACLE_EPISODES
from butler.dev_engine.b9_tiers import b9_task_tier


def _missing_skills_for_tier(tier: int) -> list[str]:
    skills_root = Path(__file__).resolve().parents[1] / "butler/registry/catalog/skills"
    missing: list[str] = []
    for tid, ep in B9_ORACLE_EPISODES.items():
        if b9_task_tier(tid) != tier:
            continue
        if tid == "B9L_stuck_unsolvable":
            continue
        if not ep.skill_name:
            continue
        skill_dir = skills_root / ep.skill_name
        if not (skill_dir / "SKILL.md").is_file():
            missing.append(f"{tid} -> {ep.skill_name}")
    return missing


def test_tier1_curriculum_skills_exist():
    missing = _missing_skills_for_tier(1)
    assert not missing, f"missing skills: {missing}"


def test_tier2_curriculum_skills_exist():
    missing = _missing_skills_for_tier(2)
    assert not missing, f"missing tier2 skills: {missing}"


def test_tier2_prod_greet_skill_exists():
    skills_root = Path(__file__).resolve().parents[1] / "butler/registry/catalog/skills"
    assert (skills_root / "b9-fix-greet-return" / "SKILL.md").is_file()


def test_promoted_prod_skills_exist():
    skills_root = Path(__file__).resolve().parents[1] / "butler/registry/catalog/skills"
    for name in (
        "b9-prod-read-before-edit",
        "b9-prod-main-helpers-import",
        "b9-prod-cross-module-rename",
        "b9-prod-lingwen-demo-add",
        "b9-prod-lingwen-workflow-guard",
    ):
        assert (skills_root / name / "SKILL.md").is_file()


def test_swe_playbook_skills_exist():
    from butler.dev_engine.swe_curriculum import SWE_PLAYBOOKS

    skills_root = Path(__file__).resolve().parents[1] / "butler/registry/catalog/skills"
    missing: list[str] = []
    for iid, pb in SWE_PLAYBOOKS.items():
        if not pb.skill_name:
            continue
        if not (skills_root / pb.skill_name / "SKILL.md").is_file():
            missing.append(f"{iid} -> {pb.skill_name}")
    assert not missing, f"missing SWE skills: {missing}"
