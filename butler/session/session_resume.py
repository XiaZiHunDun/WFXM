"""Session resume mechanism — restore session state from persistence.

Supports:
1. Session state loading from SQLite
2. ConversationState reconstruction
3. Recovery validation
4. Auto-resume workflow integration
"""

from __future__ import annotations

import logging
from typing import Any

from butler.core.conversation_state import ConversationState
from butler.session.session_store import get_session_store

logger = logging.getLogger(__name__)


def resume_session(session_id: str) -> ConversationState | None:
    """Resume a session from persisted state.

    Returns a reconstructed ConversationState or None if:
    - Session not found
    - State data is corrupted
    - Session was destroyed
    """
    store = get_session_store()
    session_info = store.get_session_info(session_id)

    if not session_info:
        logger.warning("Session %s not found in store", session_id)
        return None

    state = session_info.get("state")
    if state == "destroyed":
        logger.warning("Session %s is destroyed, cannot resume", session_id)
        return None

    state_data = store.load(session_id)
    if not state_data:
        logger.error("Failed to load state data for session %s", session_id)
        return None

    try:
        conversation_state = ConversationState.deserialize(state_data)
        logger.info("Successfully resumed session %s", session_id)
        return conversation_state
    except Exception as exc:
        logger.error("Failed to deserialize session %s: %s", session_id, exc)
        return None


def can_resume(session_id: str) -> bool:
    """Check if a session can be resumed."""
    store = get_session_store()
    session_info = store.get_session_info(session_id)

    if not session_info:
        return False

    state = session_info.get("state")
    if state in ("destroyed",):
        return False

    state_data = store.load(session_id)
    if not state_data:
        return False

    try:
        ConversationState.deserialize(state_data)
        return True
    except Exception:
        return False


def get_resume_info(session_id: str) -> dict[str, Any]:
    """Get detailed resume information for a session."""
    store = get_session_store()
    session_info = store.get_session_info(session_id)

    if not session_info:
        return {
            "session_id": session_id,
            "can_resume": False,
            "error": "Session not found",
        }

    state = session_info.get("state")
    if state == "destroyed":
        return {
            "session_id": session_id,
            "can_resume": False,
            "error": "Session was destroyed",
            "state": state,
            "ended_at": session_info.get("ended_at"),
        }

    state_data = store.load(session_id)
    if not state_data:
        return {
            "session_id": session_id,
            "can_resume": False,
            "error": "State data corrupted",
            "state": state,
        }

    try:
        conversation_state = ConversationState.deserialize(state_data)
        return {
            "session_id": session_id,
            "can_resume": True,
            "state": state,
            "conversation_goal": conversation_state.conversation_goal,
            "current_task_summary": conversation_state.current_task_summary,
            "turn_count": len(conversation_state.turn_summaries),
            "chapter_count": len(conversation_state.chapter_summaries),
            "files_modified_count": len(conversation_state.files_modified),
            "created_at": session_info.get("created_at"),
            "updated_at": session_info.get("updated_at"),
            "last_active_at": session_info.get("last_active_at"),
        }
    except Exception as exc:
        return {
            "session_id": session_id,
            "can_resume": False,
            "error": f"Deserialize failed: {exc}",
            "state": state,
        }


def save_for_resume(session_id: str, conversation_state: ConversationState, state: str = "running", reason: str = "") -> bool:
    """Save conversation state for potential resume."""
    try:
        store = get_session_store()
        serialized = conversation_state.serialize()
        store.save(session_id, serialized, state=state, reason=reason)
        logger.info("Saved session %s for resume (state: %s)", session_id, state)
        return True
    except Exception as exc:
        logger.error("Failed to save session %s for resume: %s", session_id, exc)
        return False
