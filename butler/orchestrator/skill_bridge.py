"""Skill router rebuild and context injection (ENG-12)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

from butler.skills.router import SkillRouter

logger = logging.getLogger(__name__)


def project_workspace(orch: ButlerOrchestrator) -> Path | None:
    p = orch.project_manager.get_current()
    return p.workspace if p else None


def rebuild_skill_router(orch: ButlerOrchestrator) -> None:
    from butler.orchestrator.templates import combined_skill_manager
    from butler.tenant import resolve_tenant_for_project

    tid = resolve_tenant_for_project(
        orch.project_manager.get_current(),
        orch._settings,
    )
    mgr = combined_skill_manager(
        orch._settings,
        project_workspace(orch),
        tenant_id=tid,
    )
    orch._skill_manager = mgr
    payloads = mgr.list_skills()
    orch._skill_router = SkillRouter(
        payloads,
        content_loader=mgr.get_skill,
        batch_content_loader=mgr.get_skills,
    )


def build_skill_injection_sections(
    matched: list[dict[str, Any]],
    *,
    header_note: str,
) -> list[str]:
    sections: list[str] = [
        "## 相关知识（Butler Skill）",
        "",
        header_note,
    ]
    for sk in matched:
        content = str(sk.get("content") or "").strip()
        if not content:
            continue
        name = sk.get("name", "skill")
        score = sk.get("match_score")
        hdr = f"### `{name}`" + (f" (相关性 {score})" if score is not None else "")
        if sk.get("_trust_warn"):
            hdr += " [hub/社区 — 未验证]"
        sections.append(hdr)
        sections.append(content)
    return sections


def inject_skill_context(
    orch: ButlerOrchestrator,
    task_description: str,
    top_k: int = 3,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> str:
    """Augment user text with skill bodies (experience-first policy via injection_policy)."""
    if not task_description.strip():
        if diagnostics is not None:
            diagnostics["skill_context_injected"] = False
            diagnostics["skill_matches"] = []
        return task_description
    if orch._skill_router is None:
        if diagnostics is not None:
            diagnostics["skill_context_injected"] = False
            diagnostics["skill_matches"] = []
        return task_description

    from butler.skills.injection_policy import resolve_skill_injection

    decision = resolve_skill_injection(
        orch, task_description, diagnostics=diagnostics
    )
    if diagnostics is not None:
        diagnostics["skill_injection_reason"] = decision.reason

    router_note = (
        "> 以下内容来自与本任务相关的 Butler 技能（未验证参考），仅作上下文参考。"
    )
    ref_note = (
        "> 以下 Skill 由经验层 `skill:<名>` 指针点名加载（未验证参考）。"
    )

    if decision.skip:
        if diagnostics is not None:
            diagnostics["skill_context_injected"] = False
            diagnostics["skill_matches"] = []
        return task_description

    matched: list[dict[str, Any]] = []
    if decision.skill_names:
        manager = orch._skill_manager
        if manager is None:
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_matches"] = []
            return task_description
        loaded = manager.get_skills(list(decision.skill_names))
        for name in decision.skill_names:
            sk = loaded.get(name)
            if sk:
                matched.append({**sk, "match_score": None})
        header_note = ref_note
    else:
        matched = orch._skill_router.match(task_description, top_k=top_k)
        header_note = router_note

    if not matched:
        if diagnostics is not None:
            diagnostics["skill_context_injected"] = False
            diagnostics["skill_matches"] = []
        return task_description
    if diagnostics is not None:
        diagnostics["skill_matches"] = [
            str(sk.get("name")) for sk in matched if sk.get("name")
        ]

    sections = build_skill_injection_sections(matched, header_note=header_note)
    if len(sections) == 3:
        if diagnostics is not None:
            diagnostics["skill_context_injected"] = False
            diagnostics["skill_empty_matches"] = [
                str(sk.get("name")) for sk in matched if sk.get("name")
            ]
        return task_description

    sections.append("")
    sections.append(task_description.strip())
    if diagnostics is not None:
        diagnostics["skill_context_injected"] = True
    return "\n".join(sections).strip()


__all__ = [
    "build_skill_injection_sections",
    "inject_skill_context",
    "project_workspace",
    "rebuild_skill_router",
]
