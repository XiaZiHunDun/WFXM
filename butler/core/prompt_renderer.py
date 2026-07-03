"""Prompt rendering helpers (LlamaFactory / 主线 K P1 subset)."""

from __future__ import annotations

from typing import Any

from butler.core.system_reminder import wrap_system_reminder
import logging


logger = logging.getLogger(__name__)

def anchor_sections(sections: dict[str, str]) -> str:
    """Render named sections as markdown headings."""
    parts: list[str] = []
    for title, body in sections.items():
        t = str(title or "").strip()
        b = str(body or "").strip()
        if not b:
            continue
        if t:
            parts.append(f"## {t}\n{b}")
        else:
            parts.append(b)
    return "\n\n".join(parts)


def render_system(
    static_body: str,
    *,
    dynamic_sections: dict[str, str] | None = None,
    use_reminder_wrapper: bool = False,
) -> tuple[str, str | None]:
    """Return (system_prompt, user_side_reminder_or_none)."""
    system = str(static_body or "").rstrip()
    dynamic = dynamic_sections or {}
    if not dynamic:
        return system, None
    anchored = anchor_sections(dynamic)
    if use_reminder_wrapper:
        return system, wrap_system_reminder(anchored)
    if anchored:
        return f"{system}\n\n{anchored}", None
    return system, None


def render_orchestrator_turn(
    orchestrator: Any,
    *,
    for_role: str = "default",
    use_static_reminder: bool = False,
) -> tuple[str, str | None]:
    """Build system + optional user reminder from a Butler orchestrator."""
    from butler.core.prompt_renderer_ops import static_system_reminder_enabled_safe

    use_static_reminder = static_system_reminder_enabled_safe(
        default=use_static_reminder,
    )
    if use_static_reminder:
        static = orchestrator.build_static_system_prompt()
        reminder_body = orchestrator.build_dynamic_system_reminder(for_role=for_role)
        return static, reminder_body or None
    assemble = getattr(orchestrator, "_assemble_default_system_prompt", None)
    if callable(assemble):
        return assemble(for_role=for_role), None
    return orchestrator.build_system_prompt(), None


__all__ = ["anchor_sections", "render_orchestrator_turn", "render_system"]
