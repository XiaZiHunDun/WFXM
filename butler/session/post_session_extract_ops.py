"""Post-session extraction helpers and fail-loud item errors (P0-A / R2-7)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, Callable

from butler.core.best_effort import async_safe_best_effort, safe_best_effort

logger = logging.getLogger("butler.session.post_session")


def append_butler_profile_corpus(parts: list[str], butler_memory: Any) -> None:
    if butler_memory is None or not hasattr(butler_memory, "profile"):
        return

    def _run() -> None:
        parts.append(str(butler_memory.profile.read() or ""))

    safe_best_effort(_run, label="post_session.corpus.profile", default=None)


def append_butler_experience_corpus(parts: list[str], butler_memory: Any) -> None:
    exp = getattr(butler_memory, "experience", None) if butler_memory is not None else None
    if exp is None or not hasattr(exp, "get_recent"):
        return

    def _run() -> None:
        from butler.session.lifecycle import filter_non_conversation_experience

        for row in filter_non_conversation_experience(exp.get_recent(limit=40)):
            parts.append(str(row.get("content") or ""))

    safe_best_effort(_run, label="post_session.corpus.experience", default=None)


def append_project_memory_corpus(parts: list[str], project_memory: Any) -> None:
    if project_memory is None or not hasattr(project_memory, "get_full_context"):
        return

    def _run() -> None:
        parts.append(str(project_memory.get_full_context(max_lines=80) or ""))

    safe_best_effort(_run, label="post_session.corpus.project", default=None)


def build_existing_memory_corpus(butler_memory: Any, project_memory: Any) -> str:
    parts: list[str] = []
    append_butler_profile_corpus(parts, butler_memory)
    append_butler_experience_corpus(parts, butler_memory)
    append_project_memory_corpus(parts, project_memory)
    return "\n".join(p for p in parts if isinstance(p, str) and p.strip())


def sync_profile_vectors_safe(butler_memory: Any) -> None:
    def _run() -> None:
        butler_memory.sync_profile_vectors()

    safe_best_effort(_run, label="post_session.profile_vector_sync", default=None)


def apply_memory_update_item(
    *,
    dispatch_fn: Callable[..., bool],
    upd: dict[str, Any],
    butler_memory: Any,
    project_memory: Any,
    project_name: str,
    errors: list[str] | None,
    idx: int,
) -> bool:
    try:
        return bool(
            dispatch_fn(upd, butler_memory, project_memory, project_name)
        )
    except Exception as exc:
        logger.error("Post-session memory update %d failed", idx, exc_info=exc)
        if errors is not None:
            errors.append(f"Memory item {idx}: {exc}")
        return False


def create_skill_item(
    skill: Any,
    skill_manager: Any,
    errors: list[str] | None,
) -> int:
    if not isinstance(skill, dict) or not skill.get("name") or not skill.get("body"):
        return 0
    name = skill.get("name", "?")
    try:
        outcome = skill_manager.create(
            name=str(skill["name"]),
            description=str(skill.get("description", "")),
            triggers=skill.get("triggers", []),
            content=str(skill["body"]),
        )
        logger.info("Extracted skill: %s (%s)", name, outcome)
        return 1 if outcome in ("created", "merged", "pending") else 0
    except Exception as exc:
        logger.error(
            "Post-session skill creation failed: %s", name, exc_info=exc,
        )
        if errors is not None:
            errors.append(f"Skill {name}: {exc}")
        return 0


async def run_extraction_channel(
    *,
    extract_fn: Callable[..., Awaitable[int]],
    channel_label: str,
    result: dict[str, Any],
    updates_key: str,
    failed_key: str,
    **kwargs: Any,
) -> None:
    chan_errors: list[str] = []
    try:
        result[updates_key] = await extract_fn(errors=chan_errors, **kwargs)
    except Exception as exc:
        logger.error("%s extraction failed", channel_label, exc_info=exc)
        result["errors"].append(f"{channel_label}: {exc}")
    result[failed_key] = len(chan_errors)
    result["errors"].extend(chan_errors)


async def maybe_run_layered_post_session(
    messages: list[dict[str, Any]],
    llm_call: Any,
    result: dict[str, Any],
) -> None:
    async def _run() -> None:
        from butler.session.post_session_layered import (
            extract_layered_summary,
            post_session_layered_enabled,
        )

        if not post_session_layered_enabled():
            return
        layers = await extract_layered_summary(messages, llm_call)
        for key in ("persona", "preference", "experience"):
            result[key] = layers.get(key) or []

    await async_safe_best_effort(
        _run,
        label="post_session.layered",
        default=None,
    )
