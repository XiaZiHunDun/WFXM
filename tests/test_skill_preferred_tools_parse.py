"""SkillManager parses preferred_tools from frontmatter."""

from __future__ import annotations

from pathlib import Path

from butler.skills.manager import SkillManager


def test_parse_preferred_tools_from_file(tmp_path: Path):
    skill_dir = tmp_path / "skills"
    skill_dir.mkdir()
    (skill_dir / "demo.md").write_text(
        """---
name: demo
description: d
triggers: [x]
preferred_tools:
  - read_file
  - delegate_task
---
body
""",
        encoding="utf-8",
    )
    mgr = SkillManager(skill_dir)
    listed = mgr.list_skills()
    assert listed[0]["preferred_tools"] == ["read_file", "delegate_task"]
    full = mgr.get_skill("demo")
    assert full is not None
    assert full["preferred_tools"] == ["read_file", "delegate_task"]
