"""Shared session boundary hooks (post-session extraction, memory sync)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


def trigger_session_end(orchestrator: Any, agent_loop: Any | None) -> None:
    """Run post-session memory/skill extraction when conversation is long enough."""
    try:
        if not agent_loop or not hasattr(agent_loop, "messages"):
            return
        if len(agent_loop.messages) <= 4:
            return

        from butler.post_session import PostSessionProcessor
        from butler.transport.auxiliary_client import auxiliary_llm_call_factory

        processor = PostSessionProcessor()
        processor.set_llm_call(auxiliary_llm_call_factory("post_session"))

        result = asyncio.run(
            processor.process(
                messages=agent_loop.messages,
                butler_memory=orchestrator.butler_memory,
                project_memory=getattr(orchestrator, "_project_memory", None),
                skill_manager=getattr(orchestrator, "_skill_manager", None),
                project_name=orchestrator.project_manager.current_project or "",
            )
        )
        if result.get("memory_updates") or result.get("skills_extracted"):
            logger.info(
                "Session end: %d memory, %d skills",
                result.get("memory_updates", 0),
                result.get("skills_extracted", 0),
            )
    except Exception as exc:
        logger.debug("Session end processing failed: %s", exc)


def sync_turn_memory(
    orchestrator: Any,
    user_msg: str,
    assistant_msg: str,
    *,
    interrupted: bool = False,
) -> None:
    """Sync one conversation turn to experience store."""
    if interrupted:
        return
    try:
        if not (user_msg and assistant_msg):
            return
        bm = orchestrator.butler_memory
        if bm and hasattr(bm, "experience") and bm.experience:
            bm.experience.add(
                project=orchestrator.project_manager.current_project or "",
                category="conversation",
                content=f"Q: {user_msg[:200]} → A: {assistant_msg[:300]}",
            )
    except Exception as exc:
        logger.debug("Memory sync skipped: %s", exc)
