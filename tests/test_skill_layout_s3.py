"""S3: directory skill layout — runtime glob + project sync alignment."""

from __future__ import annotations

from pathlib import Path

import yaml

from butler.skills.layout import (
    iter_skill_entry_paths,
    project_skills_sync_issues,
    sync_skills_tree,
)
from butler.skills.manager import SkillManager


def test_iter_skill_entry_paths_flat_and_orphan(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    (root / "flat.md").write_text("---\nname: flat\n---\n", encoding="utf-8")
    (root / "with-stub").mkdir()
    (root / "with-stub" / "SKILL.md").write_text("---\nname: with-stub\n---\n", encoding="utf-8")
    (root / "with-stub.md").write_text(
        "---\nname: with-stub\ninstall_type: directory\ncontent_path: with-stub/SKILL.md\n---\n",
        encoding="utf-8",
    )
    (root / "orphan").mkdir()
    (root / "orphan" / "SKILL.md").write_text("---\nname: orphan\n---\n", encoding="utf-8")

    entries = list(iter_skill_entry_paths(root))
    paths = {e.path.name: e.layout for e in entries}
    assert paths["flat.md"] == "flat"
    assert paths["with-stub.md"] == "flat"
    assert paths["SKILL.md"] == "directory_orphan"
    assert sum(1 for e in entries if e.name_hint == "orphan") == 1


def test_sync_skills_tree_directory_writes_stub(tmp_path: Path):
    src = tmp_path / "skills"
    dest = tmp_path / ".butler" / "skills"
    src.mkdir()
    sub = src / "pdf-tool"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "---\nname: pdf-tool\ndescription: PDF\ntriggers: [pdf]\n"
        "preferred_tools: [read_file]\n---\n\nBody\n",
        encoding="utf-8",
    )
    (sub / "reference.md").write_text("# ref\n", encoding="utf-8")

    actions = sync_skills_tree(src, dest)
    assert any("pdf-tool" in a for a in actions)
    stub = dest / "pdf-tool.md"
    assert stub.is_file()
    fm = yaml.safe_load(stub.read_text(encoding="utf-8").split("---")[1])
    assert fm.get("install_type") == "directory"
    assert (dest / "pdf-tool" / "SKILL.md").is_file()
    assert (dest / "pdf-tool" / "reference.md").is_file()

    mgr = SkillManager(dest)
    listed = mgr.list_skills()
    assert listed[0]["name"] == "pdf-tool"
    assert listed[0].get("triggers") == ["pdf"]
    assert listed[0].get("preferred_tools") == ["read_file"]
    skill = mgr.get_skill("pdf-tool")
    assert skill is not None
    assert "Body" in skill["content"]


def test_orphan_directory_skill_loads_without_stub(tmp_path: Path):
    root = tmp_path / "skills"
    root.mkdir()
    sub = root / "orphan-skill"
    sub.mkdir()
    (sub / "SKILL.md").write_text(
        "---\nname: orphan-skill\ndescription: o\ntriggers: [x]\n---\n\nOrphan body\n",
        encoding="utf-8",
    )
    mgr = SkillManager(root)
    assert mgr.get_skill("orphan-skill") is not None
    summaries = mgr.list_skills()
    assert summaries[0]["triggers"] == ["x"]


def test_project_skills_sync_issues_directory_missing(tmp_path: Path):
    git = tmp_path / "skills"
    git.mkdir()
    sub = git / "dir-skill"
    sub.mkdir()
    (sub / "SKILL.md").write_text("---\nname: dir-skill\n---\n", encoding="utf-8")
    issues = project_skills_sync_issues(tmp_path)
    assert any("dir-skill" in i and "缺同步" in i for i in issues)
