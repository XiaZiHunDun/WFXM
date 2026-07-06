"""Read-only index of skills under projects/*/skills/ in the repo."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from butler.registry.skill_sources.base import SkillSource
from butler.registry.skill_sources.github import _name_from_frontmatter
from butler.registry.skill_types import SkillBundle, SkillSearchHit

logger = logging.getLogger(__name__)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _parse_identifier(identifier: str) -> tuple[str, str] | None:
    ident = identifier.strip()
    if ident.startswith("project:"):
        ident = ident[8:]
    if "/" not in ident:
        return None
    project, skill = ident.split("/", 1)
    project = project.strip()
    skill = skill.strip()
    if not project or not skill:
        return None
    return project, skill


def _normalize_id(project: str, skill: str) -> str:
    return f"project:{project}/{skill}"


def _iter_project_skills() -> list[tuple[str, str, Path]]:
    root = _repo_root() / "projects"
    if not root.is_dir():
        return []
    rows: list[tuple[str, str, Path]] = []
    for proj_dir in sorted(root.iterdir()):
        if not proj_dir.is_dir() or proj_dir.name.startswith("."):
            continue
        skills_dir = proj_dir / "skills"
        if not skills_dir.is_dir():
            continue
        project = proj_dir.name
        for md in sorted(skills_dir.glob("*.md")):
            if md.name.startswith("."):
                continue
            rows.append((project, md.stem, md))
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if skill_md.is_file():
                rows.append((project, skill_dir.name, skill_md))
    return rows


def _description_from_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return ""
    if text.startswith("---"):
        end = text.find("\n---", 4)
        if end > 0:
            for line in text[4:end].splitlines():
                if line.strip().lower().startswith("description:"):
                    return line.split(":", 1)[1].strip()[:500]
    return ""


class ProjectSource(SkillSource):  # type: ignore[misc]
    """Repo project skills — search/inspect/fetch from local tree (trust=builtin)."""

    @property
    def source_id(self) -> str:
        return "project"

    def search(self, query: str, *, limit: int = 20) -> list[SkillSearchHit]:
        q = query.strip().lower()
        hits: list[SkillSearchHit] = []
        for project, skill, path in _iter_project_skills():
            desc = _description_from_file(path)
            if q and q not in project.lower() and q not in skill.lower() and q not in desc.lower():
                continue
            hits.append(
                SkillSearchHit(
                    name=skill,
                    description=desc or f"Project skill in {project}",
                    source=self.source_id,
                    identifier=_normalize_id(project, skill),
                    trust="builtin",
                    tags=["project"],
                    extra={"project": project, "path": str(path.relative_to(_repo_root()))},
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def inspect(self, identifier: str) -> SkillSearchHit | None:
        parsed = _parse_identifier(identifier)
        if not parsed:
            return None
        project, skill = parsed
        for proj, name, path in _iter_project_skills():
            if proj == project and name == skill:
                return SkillSearchHit(
                    name=name,
                    description=_description_from_file(path),
                    source=self.source_id,
                    identifier=_normalize_id(project, skill),
                    trust="builtin",
                    extra={"project": project, "path": str(path.relative_to(_repo_root()))},
                )
        return None

    def fetch(self, identifier: str) -> SkillBundle | None:
        parsed = _parse_identifier(identifier)
        if not parsed:
            return None
        project, skill = parsed
        for proj, name, path in _iter_project_skills():
            if proj != project or name != skill:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                return None
            skill_name = _name_from_frontmatter(text) or name
            skill_name = re.sub(r"[^a-z0-9._-]+", "-", skill_name.lower())[:64]
            files: dict[str, str] = {"SKILL.md": text}
            if path.parent.name == skill and path.parent.parent.name == "skills":
                for extra in path.parent.rglob("*"):
                    if not extra.is_file() or extra == path:
                        continue
                    if not extra.name.lower().endswith((".md", ".txt", ".json", ".yaml", ".yml")):
                        continue
                    rel = extra.relative_to(path.parent).as_posix()
                    try:
                        files[rel] = extra.read_text(encoding="utf-8")
                    except OSError:
                        continue
            return SkillBundle(
                name=skill_name,
                files=files,
                source=self.source_id,
                identifier=_normalize_id(project, skill),
                trust="builtin",
                metadata={"project": project, "path": str(path)},
            )
        return None
