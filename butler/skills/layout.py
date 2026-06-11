"""Skill directory layout: flat ``name.md`` vs registry directory stub (S3).

Runtime loads skills via :func:`iter_skill_entry_paths` — top-level ``*.md``
(stub or flat) plus orphan ``<name>/SKILL.md`` when no ``<name>.md`` exists.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterator

import yaml

logger = logging.getLogger(__name__)

SKILL_MD_NAMES: tuple[str, ...] = ("SKILL.md", "skill.md")
_ALLOWED_SYNC_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml")


@dataclass(frozen=True)
class SkillEntryPath:
    """A skill file the runtime should load."""

    path: Path
    layout: str  # flat | directory_stub | directory_orphan
    name_hint: str


def _skill_md_in_dir(directory: Path) -> Path | None:
    for name in SKILL_MD_NAMES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return None


def iter_skill_entry_paths(skills_dir: Path) -> Iterator[SkillEntryPath]:
    """Yield load paths under a single skills root (flat glob + directory orphans)."""
    root = Path(skills_dir)
    if not root.is_dir():
        return

    stub_stems: set[str] = set()
    for md in sorted(root.glob("*.md")):
        if md.name.startswith("."):
            continue
        stub_stems.add(md.stem.lower())
        yield SkillEntryPath(path=md, layout="flat", name_hint=md.stem)

    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        if sub.name.lower() in stub_stems:
            continue
        inner = _skill_md_in_dir(sub)
        if inner is not None:
            yield SkillEntryPath(
                path=inner,
                layout="directory_orphan",
                name_hint=sub.name,
            )


def directory_content_rel(name: str, skill_rel: str = "SKILL.md") -> str:
    rel = skill_rel.replace("\\", "/").lstrip("/")
    return f"{name}/{rel}"


def build_directory_stub_md(
    name: str,
    *,
    description: str = "",
    content_rel: str | None = None,
    extra_fm: dict | None = None,
) -> str:
    """Build top-level stub frontmatter for a directory skill install/sync."""
    rel = content_rel or directory_content_rel(name)
    fm: dict = {
        "name": name,
        "description": (description or f"Directory skill ({rel})")[:1024],
        "install_type": "directory",
        "content_path": rel,
        "version": 1,
        "created": date.today().isoformat(),
    }
    if extra_fm:
        for key, val in extra_fm.items():
            if key not in fm and val is not None:
                fm[key] = val
    body = (
        f"Directory skill stub. Content: `{rel}`.\n"
        "Synced or registry-installed; runtime resolves inner SKILL.md.\n"
    )
    yaml_text = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{yaml_text}\n---\n{body}"


def write_directory_stub(
    skills_root: Path,
    name: str,
    *,
    description: str = "",
    content_rel: str | None = None,
) -> Path:
    stub = skills_root / f"{name}.md"
    stub.write_text(
        build_directory_stub_md(name, description=description, content_rel=content_rel),
        encoding="utf-8",
    )
    return stub


def _copy_tree_allowed_files(src_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in sorted(src_dir.rglob("*")):
        if not item.is_file():
            continue
        rel = item.relative_to(src_dir).as_posix()
        if ".." in rel.split("/"):
            continue
        if not item.name.lower().endswith(_ALLOWED_SYNC_SUFFIXES):
            continue
        target = dest_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, target)


def sync_skills_tree(src: Path, dest: Path) -> list[str]:
    """Sync git ``skills/`` tree to runtime ``.butler/skills/`` (flat + directory)."""
    src_root = Path(src).expanduser().resolve()
    dest_root = Path(dest).expanduser().resolve()
    if not src_root.is_dir():
        return [f"源目录不存在: {src_root}"]

    dest_root.mkdir(parents=True, exist_ok=True)
    actions: list[str] = []

    for md in sorted(src_root.glob("*.md")):
        if md.name.startswith("."):
            continue
        target = dest_root / md.name
        shutil.copy2(md, target)
        actions.append(f"flat: {md.name}")

    for sub in sorted(src_root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        inner = _skill_md_in_dir(sub)
        if inner is None:
            continue
        name = sub.name
        dest_sub = dest_root / name
        _copy_tree_allowed_files(sub, dest_sub)
        inner_rel = inner.relative_to(sub).as_posix()
        content_rel = directory_content_rel(name, inner_rel)
        desc = ""
        try:
            text = inner.read_text(encoding="utf-8")
            if text.startswith("---"):
                end = text.find("\n---", 4)
                if end > 0:
                    fm = yaml.safe_load(text[4:end]) or {}
                    if isinstance(fm, dict):
                        desc = str(fm.get("description") or "")[:1024]
        except OSError:
            pass
        write_directory_stub(
            dest_root,
            name,
            description=desc,
            content_rel=content_rel,
        )
        actions.append(f"directory: {name}/ → {name}.md + {name}/")

    return actions


def project_skills_sync_issues(workspace: Path) -> list[str]:
    """Detect git ``skills/`` vs ``.butler/skills/`` drift (flat + directory)."""
    ws = Path(workspace).expanduser().resolve()
    git_dir = ws / "skills"
    runtime_dir = ws / ".butler" / "skills"
    if not git_dir.is_dir():
        return []

    issues: list[str] = []

    def _mtime_stale(src: Path, dest: Path) -> bool:
        try:
            return src.stat().st_mtime > dest.stat().st_mtime + 1.0
        except OSError:
            return False

    for src in sorted(git_dir.glob("*.md")):
        if src.name.startswith("."):
            continue
        dest = runtime_dir / src.name
        if not dest.is_file():
            issues.append(f"  缺同步: {src.name}（skills/ → .butler/skills/）")
            continue
        if _mtime_stale(src, dest):
            issues.append(f"  可能过期: {src.name}（git 源较新，请跑 sync 脚本）")

    for sub in sorted(git_dir.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        inner = _skill_md_in_dir(sub)
        if inner is None:
            continue
        name = sub.name
        stub = runtime_dir / f"{name}.md"
        dest_inner = runtime_dir / name / inner.relative_to(sub).as_posix()
        if not stub.is_file() or not dest_inner.is_file():
            issues.append(
                f"  缺同步: {name}/（目录型 skill → {name}.md + {name}/）"
            )
            continue
        if _mtime_stale(inner, dest_inner) or _mtime_stale(inner, stub):
            issues.append(
                f"  可能过期: {name}/（git 源较新，请跑 sync 脚本）"
            )

    return issues


__all__ = [
    "SKILL_MD_NAMES",
    "SkillEntryPath",
    "build_directory_stub_md",
    "directory_content_rel",
    "iter_skill_entry_paths",
    "project_skills_sync_issues",
    "sync_skills_tree",
    "write_directory_stub",
]
