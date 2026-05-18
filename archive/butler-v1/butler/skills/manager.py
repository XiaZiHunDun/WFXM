"""SkillManager — runtime skill creation, editing, deletion, and merging.

Provides lifecycle management with automatic similarity detection and
consolidation on create. Supports project vs global skill directories.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from pathlib import Path
from typing import Any

from butler.skills.consolidator import SkillConsolidator
from butler.skills.loader import SkillLoader
from butler.skills.similarity import SkillSimilarity
from butler.skills.usage import UsageTracker

logger = logging.getLogger(__name__)

VALID_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9._-]*$')
MAX_NAME_LEN = 64
MAX_DESC_LEN = 1024


def _render_skill_md(
    name: str,
    description: str,
    triggers: list[str],
    tools: list[str],
    body: str,
    scope: str,
) -> str:
    """Render a SKILL.md file from components."""
    lines = ["---"]
    lines.append(f"name: {name}")
    lines.append(f"description: {description}")
    if triggers:
        lines.append("triggers:")
        for t in triggers:
            lines.append(f"  - \"{t}\"")
    if tools:
        lines.append("tools:")
        for t in tools:
            lines.append(f"  - {t}")
    lines.append(f"scope: {scope}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


class SkillManager:
    """Manages skill lifecycle with similarity detection and auto-merge."""

    def __init__(
        self,
        skill_loader: SkillLoader,
        similarity: SkillSimilarity,
        consolidator: SkillConsolidator,
        usage_tracker: UsageTracker,
    ):
        self._loader = skill_loader
        self._similarity = similarity
        self._consolidator = consolidator
        self._usage = usage_tracker

    def _validate_name(self, name: str) -> str | None:
        if not name:
            return "Name is required."
        if len(name) > MAX_NAME_LEN:
            return f"Name too long (max {MAX_NAME_LEN} chars)."
        if not VALID_NAME_RE.match(name):
            return "Name must be kebab-case (lowercase letters, digits, hyphens, dots)."
        return None

    def _skills_base_dir(self, scope: str) -> Path | None:
        if scope == "global":
            return self._loader.global_skills_dir
        return self._loader.project_skills_dir

    def _resolve_archive_root(self, skill_dir: Path) -> Path:
        return skill_dir.parent / ".archive"

    def _get_existing_skills_as_dicts(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "triggers": s.triggers,
                "tools": s.tools,
                "body": s.body,
                "scope": s.scope,
            }
            for s in self._loader.list_skills(scope="all")
        ]

    async def create(
        self,
        name: str,
        description: str,
        triggers: list[str] | None,
        tools: list[str] | None,
        body: str,
        scope: str = "project",
        source: str = "manual",
    ) -> dict[str, Any]:
        error = self._validate_name(name)
        if error:
            return {"success": False, "error": error}
        if not description:
            return {"success": False, "error": "Description is required."}
        if len(description) > MAX_DESC_LEN:
            return {"success": False, "error": f"Description too long (max {MAX_DESC_LEN})."}
        if not body:
            return {"success": False, "error": "Body is required."}

        if scope not in ("project", "global"):
            return {"success": False, "error": "scope must be 'project' or 'global'."}

        base = self._skills_base_dir(scope)
        if base is None:
            return {"success": False, "error": f"No skills directory configured for scope '{scope}'."}

        new_skill: dict[str, Any] = {
            "name": name,
            "description": description,
            "triggers": triggers or [],
            "tools": tools or [],
            "body": body,
            "scope": scope,
        }

        existing = self._get_existing_skills_as_dicts()
        similar_results = await self._similarity.find_similar(new_skill, existing)

        if similar_results:
            similar_skills: list[dict[str, Any]] = []
            for r in similar_results:
                for s in existing:
                    if s["name"] == r.skill_name:
                        similar_skills.append(s)
                        break

            all_skills = [new_skill] + similar_skills
            merge_result = await self._consolidator.merge(all_skills)

            if merge_result.success and merge_result.merged_skill:
                merged = merge_result.merged_skill

                for s in similar_skills:
                    self._archive_skill(s["name"])

                self._write_skill(
                    merged["name"],
                    merged["description"],
                    merged["triggers"],
                    merged["tools"],
                    merged["body"],
                    scope=scope,
                )
                self._loader.reload()
                self._usage.on_merge(
                    merged["name"],
                    [s["name"] for s in similar_skills],
                    source="merged",
                )

                return {
                    "success": True,
                    "action": "merged",
                    "name": merged["name"],
                    "scope": scope,
                    "merged_from": [s["name"] for s in all_skills],
                    "message": f"Merged {len(all_skills)} similar skills into '{merged['name']}'.",
                }
            logger.warning("Merge failed: %s. Creating as standalone.", merge_result.error)

        if self._loader.get_skill(name):
            return {"success": False, "error": f"Skill '{name}' already exists. Use 'edit' to modify."}

        self._write_skill(name, description, triggers, tools, body, scope=scope)
        self._loader.reload()
        self._usage.on_create(name, source=source)

        return {
            "success": True,
            "action": "created",
            "name": name,
            "scope": scope,
            "message": f"Skill '{name}' created successfully.",
        }

    async def edit(
        self,
        name: str,
        description: str | None = None,
        triggers: list[str] | None = None,
        tools: list[str] | None = None,
        body: str | None = None,
    ) -> dict[str, Any]:
        skill = self._loader.get_skill(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found."}

        new_desc = description if description is not None else skill.description
        new_triggers = triggers if triggers is not None else skill.triggers
        new_tools = tools if tools is not None else skill.tools
        new_body = body if body is not None else skill.body

        self._write_skill(
            name, new_desc, new_triggers, new_tools, new_body, scope=skill.scope,
        )
        self._loader.reload()

        return {"success": True, "action": "edited", "name": name, "message": f"Skill '{name}' updated."}

    async def delete(self, name: str) -> dict[str, Any]:
        skill = self._loader.get_skill(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found."}

        self._archive_skill(name)
        self._loader.reload()
        self._usage.on_delete(name)

        return {"success": True, "action": "deleted", "name": name, "message": f"Skill '{name}' archived and removed."}

    async def patch(self, name: str, old_text: str, new_text: str) -> dict[str, Any]:
        skill = self._loader.get_skill(name)
        if not skill:
            return {"success": False, "error": f"Skill '{name}' not found."}
        if not old_text:
            return {"success": False, "error": "old_text is required for patch."}

        if old_text not in skill.body:
            return {"success": False, "error": f"old_text not found in skill '{name}'."}

        new_body = skill.body.replace(old_text, new_text, 1)
        self._write_skill(
            name, skill.description, skill.triggers, skill.tools, new_body, scope=skill.scope,
        )
        self._loader.reload()

        return {"success": True, "action": "patched", "name": name, "message": f"Skill '{name}' patched."}

    def _write_skill(
        self,
        name: str,
        description: str,
        triggers: list[str] | None,
        tools: list[str] | None,
        body: str,
        scope: str,
    ) -> None:
        base = self._skills_base_dir(scope)
        if base is None:
            raise ValueError(f"No directory for scope {scope}")
        skill_dir = base / name.replace("-", "_")
        skill_dir.mkdir(parents=True, exist_ok=True)
        content = _render_skill_md(
            name, description, list(triggers or []), list(tools or []), body, scope,
        )
        (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")

    def _archive_skill(self, name: str) -> None:
        skill = self._loader.get_skill(name)
        if not skill or not skill.path:
            return
        skill_path = Path(skill.path)
        skill_dir = skill_path.parent
        if not skill_dir.exists():
            return
        archive_dir = self._resolve_archive_root(skill_dir)
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_name = f"{name}_{int(time.time())}"
        dest = archive_dir / archive_name
        shutil.move(str(skill_dir), str(dest))
        logger.info("Archived skill '%s' -> %s", name, dest)
