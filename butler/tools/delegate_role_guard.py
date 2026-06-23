"""Enforce user-specified delegate role on Lead projects (override docs→content drift)."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.tools.delegate_phases import DelegateRunState

logger = logging.getLogger(__name__)

_DEV_SIGNALS: tuple[re.Pattern[str], ...] = (
    re.compile(r"role\s*[=:]\s*dev\b", re.I),
    re.compile(r"委派\s*开发", re.I),
    re.compile(r"开发代理", re.I),
    re.compile(r"交给\s*开发", re.I),
    re.compile(r"禁止(用|使用)?\s*content", re.I),
    re.compile(r"不要(用|使用)?\s*content", re.I),
    re.compile(r"禁止\s*内容代理", re.I),
)

_CONTENT_SIGNALS: tuple[re.Pattern[str], ...] = (
    re.compile(r"role\s*[=:]\s*content\b", re.I),
    re.compile(r"委派\s*内容", re.I),
    re.compile(r"内容代理", re.I),
    re.compile(r"交给\s*content", re.I),
    re.compile(r"禁止(用|使用)?\s*dev\b", re.I),
    re.compile(r"不要(用|使用)?\s*dev\b", re.I),
    re.compile(r"禁止\s*开发代理", re.I),
)


def _normalize_role(role: str) -> str:
    return str(role or "").replace("_agent", "").strip().lower()


def _user_query_head(text: str) -> str:
    """Parse only the user-facing lines; ignore trailing Skill/Memory injections."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    for marker in (
        "## 相关知识",
        "## Related knowledge",
        "### `",
        "<!-- butler-skill",
    ):
        idx = raw.find(marker)
        if idx > 0:
            return raw[:idx].strip()
    return raw


def user_explicit_delegate_role(user_text: str) -> str | None:
    """Return ``dev`` / ``content`` / ``review`` when user pinned a role, else None."""
    text = _user_query_head(user_text)
    if not text:
        return None
    dev_hit = any(p.search(text) for p in _DEV_SIGNALS)
    content_hit = any(p.search(text) for p in _CONTENT_SIGNALS)
    # Explicit role= params in user head — dev before review (Skill blocks may mention review)
    if re.search(r"role\s*[=:]\s*dev\b", text, re.I):
        return "dev"
    if re.search(r"role\s*[=:]\s*content\b", text, re.I):
        return "content"
    if re.search(r"role\s*[=:]\s*review\b", text, re.I):
        return "review"
    if dev_hit and not content_hit:
        return "dev"
    if content_hit and not dev_hit:
        return "content"
    return None


def _turn_user_text() -> str:
    from butler.tools.network_search_policy import _turn_user_query

    text = _turn_user_query()
    if text:
        return text
    try:
        from butler.core.session_epoch import last_user_query_in_epoch
        from butler.execution_context import get_current_session_key

        sk = str(get_current_session_key() or "").strip()
        if sk:
            q = last_user_query_in_epoch(sk)
            if q:
                return q
    except Exception as exc:
        logger.debug("turn user text from epoch skipped: %s", exc)
    return ""


def _explicit_role_from_state(state: "DelegateRunState") -> str | None:
    blob = "\n".join(
        part
        for part in (
            state.task or "",
            state.context or "",
            state.original_context or "",
        )
        if part
    )
    return user_explicit_delegate_role(blob)


def _is_lead_turn() -> bool:
    try:
        from butler.execution_context import get_current_orchestrator
        from butler.project.lead import is_lead_project

        orch = get_current_orchestrator()
        if orch is None:
            return False
        proj = orch.project_manager.get_current()
        if proj is None:
            return False
        name = str(getattr(proj, "name", "") or "")
        return bool(name) and is_lead_project(name, project=proj)
    except Exception as exc:
        logger.debug("lead turn check skipped: %s", exc)
        return False


def apply_user_role_override(state: "DelegateRunState") -> bool:
    """If user pinned role=dev/content on a Lead turn, override model-chosen role."""
    if int(getattr(state, "depth", 0) or 0) > 0:
        return False
    if not _is_lead_turn():
        return False
    explicit = user_explicit_delegate_role(_turn_user_text())
    if not explicit:
        explicit = _explicit_role_from_state(state)
    if not explicit:
        return False
    current = _normalize_role(state.role)
    if current == explicit:
        return False
    logger.info(
        "Lead delegate role override: %s -> %s (user explicit)",
        current or "?",
        explicit,
    )
    state.role = explicit
    note = (
        f"[role_override] 用户明确要求 role={explicit}；"
        f"已覆盖 Lead 默认路由（原 role={current or '?'}）。"
    )
    ctx = str(state.context or "").strip()
    state.context = f"{ctx}\n\n{note}".strip() if ctx else note
    return True


__all__ = ["apply_user_role_override", "user_explicit_delegate_role"]
