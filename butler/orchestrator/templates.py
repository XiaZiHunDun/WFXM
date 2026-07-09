"""System prompt templates and formatting helpers (ENG-12)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.config import ButlerSettings
from butler.project.manager import get_project_manager
from butler.skills.manager import SkillManager

logger = logging.getLogger(__name__)

# mtime+size-keyed cache — auto-invalidates on file change.
_TEMPLATE_CACHE: dict[tuple[str, int, int], str] = {}

_ROLE_ALIASES: dict[str, str] = {
    "dev": "dev_agent",
    "content": "content_agent",
    "review": "review_agent",
}


def read_template_cached(path: Path) -> str:
    """Read template file with mtime+size cache."""
    try:
        st = path.stat()
    except OSError as exc:
        logger.debug("Could not stat template %s: %s", path, exc)
        return ""
    key = (str(path), st.st_mtime_ns, st.st_size)
    cached = _TEMPLATE_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        body = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    _TEMPLATE_CACHE[key] = body
    return body


def normalize_butler_role(role: str) -> str:
    key = (role or "").strip().lower()
    return _ROLE_ALIASES.get(key, role)


def _prompts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "prompts"


def template_path() -> Path:
    return _prompts_dir() / "butler_system.md"


def lead_template_path() -> Path:
    return _prompts_dir() / "lingwen_lead_system.md"


def format_project_list(settings: ButlerSettings) -> str:
    pm = get_project_manager()
    projects = sorted(pm.list_projects(), key=lambda p: p.name)
    if not projects:
        return f"(无 — 在 {settings.projects_dir} 下创建 project.yaml)"
    parts: list[str] = []
    for p in projects:
        slug = p.workspace.name
        parts.append(f"{p.name} (目录 {slug}/)")
    return ", ".join(parts)


def format_skill_summaries(skills: list[dict[str, Any]], max_items: int = 20) -> str:
    if not skills:
        return "(尚无技能文件 — 可在 ~/.butler/tenants/<tenant>/skills 或项目 `.butler/skills` 中添加)"
    lines: list[str] = []
    from butler.orchestrator.templates_ops import skill_summary_disclaimer_lines_safe

    lines.extend(skill_summary_disclaimer_lines_safe())
    for sk in skills[:max_items]:
        name = sk.get("name", "")
        desc = (sk.get("description") or "").strip()
        triggers = sk.get("triggers") or []
        trig = ", ".join(str(t) for t in triggers[:5])
        if trig:
            lines.append(f"- **{name}**: {desc} (triggers: {trig})")
        else:
            lines.append(f"- **{name}**: {desc}")
    if len(skills) > max_items:
        lines.append(f"... 另有 {len(skills) - max_items} 条技能未列出")
    return "\n".join(lines)


def combined_skill_manager(
    settings: ButlerSettings,
    project_workspace: Path | None,
    *,
    tenant_id: str,
) -> SkillManager:
    """Project-local skills override tenant-global skills with the same name."""
    from butler.tenant import tenant_skills_dir

    global_dir = tenant_skills_dir(settings.butler_home, tenant_id)
    global_dir.mkdir(parents=True, exist_ok=True)
    if project_workspace is None:
        mgr = SkillManager(skills_dir=global_dir, global_skills_dir=None)
        from butler.skills.fusion_wiring import wire_skill_manager_fusion

        wire_skill_manager_fusion(mgr)
        return mgr
    proj_skills = Path(project_workspace).expanduser().resolve() / ".butler" / "skills"
    proj_skills.mkdir(parents=True, exist_ok=True)
    mgr = SkillManager(skills_dir=proj_skills, global_skills_dir=global_dir)
    from butler.skills.fusion_wiring import wire_skill_manager_fusion

    wire_skill_manager_fusion(mgr)
    return mgr


__all__ = [
    "combined_skill_manager",
    "format_project_list",
    "format_skill_summaries",
    "lead_template_path",
    "normalize_butler_role",
    "read_template_cached",
    "template_path",
]
