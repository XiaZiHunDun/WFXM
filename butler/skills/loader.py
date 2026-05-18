"""Skill loader — reads SKILL.md files from project and global directories."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    body: str = ""
    path: str = ""
    scope: str = "project"  # "project" | "global"


def _parse_yaml_frontmatter(text: str) -> tuple[dict, str]:
    """Parse simple YAML frontmatter from SKILL.md (no PyYAML dependency)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    yaml_block = text[3:end].strip()
    body = text[end + 4:].strip()

    meta: dict = {}
    current_key = ""
    current_list: list[str] | None = None

    for line in yaml_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- ") and current_list is not None:
            val = stripped[2:].strip().strip('"').strip("'")
            current_list.append(val)
            continue

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")

            if current_key and current_list is not None:
                meta[current_key] = current_list

            if val:
                meta[key] = val
                current_key = ""
                current_list = None
            else:
                current_key = key
                current_list = []

    if current_key and current_list is not None:
        meta[current_key] = current_list

    return meta, body


class SkillLoader:
    """Loads skills from project and global directories."""

    def __init__(
        self,
        project_skills_dir: Path | None = None,
        global_skills_dir: Path | None = None,
    ):
        self._project_dir = project_skills_dir
        self._global_dir = global_skills_dir
        self._skills: dict[str, SkillInfo] = {}
        self.load_skills()

    @property
    def project_skills_dir(self) -> Path | None:
        return self._project_dir

    @property
    def global_skills_dir(self) -> Path | None:
        return self._global_dir

    def load_skills(self) -> None:
        self._skills.clear()
        if self._global_dir:
            self._scan_dir(self._global_dir, scope="global")
        if self._project_dir:
            self._scan_dir(self._project_dir, scope="project")

    def _scan_dir(self, directory: Path, scope: str) -> None:
        if not directory.exists():
            return
        for child in sorted(directory.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                text = skill_file.read_text(encoding="utf-8")
                meta, body = _parse_yaml_frontmatter(text)
                name = meta.get("name", child.name)
                tm = meta.get("triggers")
                tm_list = [str(t) for t in tm] if isinstance(tm, list) else []
                tl = meta.get("tools")
                tl_list = [str(t) for t in tl] if isinstance(tl, list) else []
                skill = SkillInfo(
                    name=name,
                    description=meta.get("description", ""),
                    triggers=tm_list,
                    tools=tl_list,
                    body=body,
                    path=str(skill_file),
                    scope=str(meta.get("scope", scope)),
                )
                self._skills[name] = skill
            except Exception as e:
                logger.warning("Failed to load skill '%s': %s", child.name, e)

    def reload(self) -> None:
        self.load_skills()

    def get_skill(self, name: str) -> Optional[SkillInfo]:
        return self._skills.get(name)

    def list_skills(self, scope: str = "all") -> list[SkillInfo]:
        if scope == "all":
            return list(self._skills.values())
        return [s for s in self._skills.values() if s.scope == scope]

    def skill_names(self) -> list[str]:
        return list(self._skills.keys())

    def build_skill_summary(self) -> str:
        """Build a concise skill summary for system prompt injection."""
        if not self._skills:
            return ""
        lines = ["## 可用 Skills"]
        for skill in self._skills.values():
            trigger_str = ", ".join(skill.triggers[:3]) if skill.triggers else ""
            line = f"- **{skill.name}**: {skill.description}"
            if trigger_str:
                line += f" (触发: {trigger_str})"
            lines.append(line)
        return "\n".join(lines)
