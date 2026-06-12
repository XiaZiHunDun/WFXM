"""Tier-1 curriculum episodes must have matching catalog skills."""

from __future__ import annotations

from pathlib import Path

from butler.dev_engine.b9_oracle_curriculum import B9_ORACLE_EPISODES
from butler.dev_engine.b9_tiers import b9_task_tier


def test_tier1_curriculum_skills_exist():
    skills_root = Path(__file__).resolve().parents[1] / "butler/registry/catalog/skills"
    missing: list[str] = []
    for tid, ep in B9_ORACLE_EPISODES.items():
        if b9_task_tier(tid) != 1:
            continue
        if tid == "B9L_stuck_unsolvable":
            continue
        if not ep.skill_name:
            continue
        skill_dir = skills_root / ep.skill_name
        if not (skill_dir / "SKILL.md").is_file():
            missing.append(f"{tid} -> {ep.skill_name}")
    assert not missing, f"missing skills: {missing}"
