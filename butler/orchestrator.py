"""Butler Orchestrator — bridges Butler product layer with Hermes AIAgent engine.

Provides:
- Butler-scoped system prompt injection (project context, memory, model config)
- Project-aware agent spawning via hermes delegate_task
- Report collection from delegated tasks
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.config import ButlerSettings, get_butler_settings, get_model_config
from butler.memory import ButlerMemory, ProjectMemory
from butler.project_manager import get_project_manager
from butler.skills.manager import SkillManager
from butler.skills.router import SkillRouter

logger = logging.getLogger(__name__)

_ROLE_ALIASES: dict[str, str] = {
    "dev": "dev_agent",
    "content": "content_agent",
    "review": "review_agent",
}


def _normalize_butler_role(role: str) -> str:
    key = (role or "").strip().lower()
    return _ROLE_ALIASES.get(key, role)


def _template_path() -> Path:
    return Path(__file__).resolve().parent / "prompts" / "butler_system.md"


def _format_project_list(settings: ButlerSettings) -> str:
    pm = get_project_manager()
    names = sorted(p.name for p in pm.list_projects())
    if not names:
        return f"(无 — 在 {settings.projects_dir} 下创建 project.yaml)"
    return ", ".join(names)


def _format_skill_summaries(skills: list[dict[str, Any]], max_items: int = 20) -> str:
    if not skills:
        return "(尚无技能文件 — 可在 ~/.butler/skills 或项目 `.butler/skills` 中添加)"
    lines: list[str] = []
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


def _combined_skill_manager(settings: ButlerSettings, project_workspace: Path | None) -> SkillManager:
    """Project-local skills override Butler-global skills with the same name."""
    global_dir = settings.butler_home / "skills"
    global_dir.mkdir(parents=True, exist_ok=True)
    if project_workspace is None:
        return SkillManager(skills_dir=global_dir, global_skills_dir=None)
    proj_skills = Path(project_workspace).expanduser().resolve() / ".butler" / "skills"
    proj_skills.mkdir(parents=True, exist_ok=True)
    return SkillManager(skills_dir=proj_skills, global_skills_dir=global_dir)


class ButlerOrchestrator:
    """Bridge Butler configuration and memories into Hermes ``AIAgent`` kwargs."""

    def __init__(self, user_id: str = "owner", channel: str = "cli") -> None:
        self.user_id = user_id
        self.channel = channel
        self._settings = get_butler_settings()
        self.butler_memory = ButlerMemory(self._settings.butler_home)
        self.project_manager = get_project_manager()
        self._project_memory: ProjectMemory | None = None
        self._skill_router: SkillRouter | None = None
        self._skill_manager: SkillManager | None = None
        self._reload_project_memory()
        self._rebuild_skill_router()
        self.project_manager.on_switch(self._pm_switch)

    def _pm_switch(self, old_project: str, new_project: str) -> None:
        self.on_project_switch(old_project, new_project)

    def _reload_project_memory(self) -> None:
        proj = self.project_manager.get_current()
        if proj is None:
            self._project_memory = None
        else:
            self._project_memory = ProjectMemory(proj.workspace)

    def _rebuild_skill_router(self) -> None:
        mgr = _combined_skill_manager(self._settings, self._project_workspace())
        self._skill_manager = mgr
        payloads: list[dict[str, Any]] = []
        for meta in mgr.list_skills():
            full = mgr.get_skill(str(meta.get("name", "")))
            if full:
                payloads.append(full)
        self._skill_router = SkillRouter(payloads)

    def _project_workspace(self) -> Path | None:
        p = self.project_manager.get_current()
        return p.workspace if p else None

    def _model_credentials(self, role: str) -> dict[str, Any]:
        mc = get_model_config(role)
        prov_name = (mc.provider or self._settings.default_provider or "").strip()
        pc = self._settings.providers.get(prov_name) if prov_name else None
        api_key = getattr(pc, "api_key", "") or "" if pc else ""
        base_url = getattr(pc, "base_url", "") or "" if pc else ""
        model = (mc.model or (getattr(pc, "model", "") or "")) if pc else mc.model or ""
        out: dict[str, Any] = {
            "provider": prov_name or None,
            "model": model or "",
            "api_key": api_key,
            "base_url": base_url,
        }
        if mc.max_tokens is not None:
            out["max_tokens"] = mc.max_tokens
        return out

    def build_memory_context(self, *, for_role: str = "default") -> str:
        current = self.project_manager.current_project or ""
        chunks: list[str] = []

        bm = self.butler_memory.get_system_context(current)
        chunks.append(bm)

        if self._project_memory is not None:
            pm_txt = self._project_memory.get_context_for_agent(for_role)
            chunks.append(f"## 当前项目记忆\n{pm_txt}")

        return "\n\n".join(c for c in chunks if c and str(c).strip())

    def build_system_prompt(self) -> str:
        template = _template_path()
        try:
            body = template.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Butler system template missing at %s", template)
            body = ""

        current = self.project_manager.current_project or "(未选择)"
        project_list = _format_project_list(self._settings)

        mc = get_model_config("butler")
        prov = mc.provider or self._settings.default_provider or ""
        parts_model = [
            f"- Provider: `{prov or 'unset'}`",
            f"- Model: `{mc.model or 'unset'}`",
        ]
        if mc.temperature is not None:
            parts_model.append(f"- Temperature: `{mc.temperature}`")
        if mc.max_tokens is not None:
            parts_model.append(f"- Max tokens: `{mc.max_tokens}`")
        model_block = "\n".join(parts_model)

        skills_block = "(技能管理器不可用)"
        if self._skill_manager is not None:
            skills_block = _format_skill_summaries(self._skill_manager.list_skills())

        memory_ctx = self.build_memory_context(for_role="default")

        placeholders = {
            "butler_name": self._settings.butler_name,
            "owner_name": self._settings.owner_name,
            "current_project": current,
            "project_list": project_list,
            "memory_context": memory_ctx,
            "butler_model": model_block,
            "skill_summaries": skills_block,
        }

        rendered = body
        for k, v in placeholders.items():
            rendered = rendered.replace("{" + k + "}", v)

        appendix = (
            "\n\n## Butler 模型\n"
            f"{model_block}\n\n"
            "## 可用技能概要\n"
            f"{skills_block}"
        )
        return rendered.rstrip() + appendix

    def get_agent_kwargs(self) -> dict[str, Any]:
        """Return kwargs to configure Hermes ``AIAgent``."""
        mc = self._model_credentials("butler")
        return {
            "model": mc.get("model", ""),
            "provider": mc.get("provider"),
            "base_url": mc.get("base_url") or "",
            "api_key": mc.get("api_key") or "",
            "max_tokens": mc.get("max_tokens"),
            "user_id": self.user_id,
            "platform": self.channel,
            "ephemeral_system_prompt": self.build_system_prompt(),
        }

    def get_project_agent_kwargs(self, role: str) -> dict[str, Any]:
        """Return kwargs for project-level agents (dev/content/review)."""
        r = _normalize_butler_role(role)
        proj = self.project_manager.get_current()
        if proj is None:
            mcreds = self._model_credentials(r)
            extra_prompt = (
                "## Butler 项目上下文\n"
                "当前未选择 Butler 项目 — 使用全局模型配置。"
            )
        else:
            resolved = proj.resolve_model(r)
            prov_name = (resolved.provider or self._settings.default_provider or "").strip()
            pc = self._settings.providers.get(prov_name) if prov_name else None
            api_key = getattr(pc, "api_key", "") or "" if pc else ""
            base_url = getattr(pc, "base_url", "") or "" if pc else ""
            model = (resolved.model or (getattr(pc, "model", "") or "")) if pc else resolved.model or ""
            mcreds = {
                "provider": prov_name or None,
                "model": model or "",
                "api_key": api_key,
                "base_url": base_url,
            }
            if resolved.max_tokens is not None:
                mcreds["max_tokens"] = resolved.max_tokens

            proj_mem = ProjectMemory(proj.workspace)
            mem_txt = proj_mem.get_context_for_agent(r)
            extra_prompt = (
                f"## Butler 项目: {proj.name}\n"
                f"{proj.description}\n\n"
                f"工作区路径: `{proj.workspace}`\n\n"
                f"### 项目记忆\n{mem_txt}"
            )

        return {
            "model": mcreds.get("model", ""),
            "provider": mcreds.get("provider"),
            "base_url": mcreds.get("base_url") or "",
            "api_key": mcreds.get("api_key") or "",
            "max_tokens": mcreds.get("max_tokens"),
            "user_id": self.user_id,
            "platform": self.channel,
            "ephemeral_system_prompt": extra_prompt,
        }

    def on_project_switch(self, old_project: str, new_project: str) -> None:
        logger.debug(
            "Butler project switched: %r -> %r",
            old_project,
            new_project,
        )
        self._reload_project_memory()
        self._rebuild_skill_router()

    def inject_skill_context(self, task_description: str, top_k: int = 3) -> str:
        """Augment ``task_description`` with bodies from :class:`~butler.skills.router.SkillRouter`."""
        if not task_description.strip():
            return task_description
        if self._skill_router is None:
            return task_description
        matched = self._skill_router.match(task_description, top_k=top_k)
        if not matched:
            return task_description

        sections: list[str] = [
            "## 相关知识（Butler Skill）",
            "",
            "> 以下内容来自与本任务相关的 Butler 技能，仅作上下文参考。",
        ]
        for sk in matched:
            name = sk.get("name", "skill")
            score = sk.get("match_score")
            hdr = f"### `{name}`" + (f" (相关性 {score})" if score is not None else "")
            sections.append(hdr)
            sections.append(str(sk.get("content") or "").strip())

        sections.append("")
        sections.append(task_description.strip())
        return "\n".join(sections).strip()


__all__ = ["ButlerOrchestrator"]
