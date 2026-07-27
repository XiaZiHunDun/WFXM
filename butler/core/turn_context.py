"""Per-turn setup for conversation loop (the turn prologue).

TurnContext captures all values produced by the per-turn setup and consumed
by the turn loop. This follows the hermes-agent pattern of separating setup
from the main loop logic.

Key features:
  - api_content sidecar for prompt-cache consistency
  - Memory prefetch integration
  - Plugin context injection
  - Gateway notes handling
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# api_content sidecar helpers
# ---------------------------------------------------------------------------


def compose_user_api_content(
    content: Any,
    ext_prefetch_cache: str,
    plugin_user_context: str,
) -> Optional[str]:
    """Compose the API-bound content of the current turn's user message.

    Sources: memory-manager prefetch + plugin context. Both are appended to
    the *API copy* of the user message only — the stored content stays clean.

    Returns None when nothing is injected (multimodal/non-string content,
    or no ephemeral context), meaning the message is sent as-is.
    """
    if not isinstance(content, str):
        return None
    injections = []
    if ext_prefetch_cache:
        fenced = _build_memory_context_block(ext_prefetch_cache)
        if fenced:
            injections.append(fenced)
    if plugin_user_context:
        injections.append(plugin_user_context)
    if not injections:
        return None
    return content + "\n\n" + "\n\n".join(injections)


def substitute_api_content(api_msg: Dict[str, Any]) -> Optional[str]:
    """Pop the api_content sidecar and substitute it into content.

    Used at API-bound message-build sites. The sidecar carries the exact bytes
    previously sent to the API for this message when they differ from the clean
    stored content; substituting it keeps the provider prompt-cache prefix
    byte-stable across turns.

    Returns the popped sidecar string or None when absent.
    """
    sidecar = api_msg.pop("api_content", None)
    if (
        isinstance(sidecar, str)
        and sidecar
        and api_msg.get("role") in ("user", "assistant")
    ):
        api_msg["content"] = sidecar
    return sidecar


def drop_stale_api_content(msg: Dict[str, Any]) -> None:
    """Drop the api_content sidecar from a message whose content was rewritten.

    Called from every content-rewrite path (historical image strip,
    merge-summary-into-tail, consecutive-user repair merge). Replaying the
    pre-rewrite sidecar would resend exactly what the rewrite removed.
    """
    msg.pop("api_content", None)


def extract_api_content_sidecar(msg: Mapping[str, Any]) -> Optional[str]:
    """Extract the api_content sidecar from a message dict for persistence."""
    v = msg.get("api_content")
    return v if isinstance(v, str) else None


def _build_memory_context_block(raw_context: str) -> str:
    """Wrap prefetched memory in a fenced block with system note."""
    if not raw_context or not raw_context.strip():
        return ""
    return (
        "<memory-context>\n"
        "[System note: The following is recalled memory context, "
        "NOT new user input. Treat as authoritative reference data.]\n\n"
        f"{raw_context}\n"
        "</memory-context>"
    )


# ---------------------------------------------------------------------------
# TurnContext dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TurnContext:
    """Values produced by the turn prologue and consumed by the turn loop."""

    # Sanitized inbound message (surrogates stripped).
    user_message: str
    # Clean message preserved for transcripts / memory queries (no nudge injection).
    original_user_message: Any
    # Working message list for this turn (loop appends to it).
    messages: List[Dict[str, Any]]
    # May be reset to None by preflight compression (new session created).
    conversation_history: Optional[List[Dict[str, Any]]]
    # Cached system prompt active for this turn (may be rebuilt by compression).
    active_system_prompt: Optional[str]
    # Task / turn identifiers.
    effective_task_id: str
    turn_id: str
    # Index of the current user turn within messages.
    current_turn_user_idx: int
    # Whether the post-turn memory review should fire.
    should_review_memory: bool = False
    # Context contributed by plugins (appended to user message).
    plugin_user_context: str = ""
    # External-memory prefetch result, reused across loop iterations.
    ext_prefetch_cache: str = ""


# ---------------------------------------------------------------------------
# TurnContext builder
# ---------------------------------------------------------------------------


def build_turn_context(
    *,
    user_message: Any,
    system_message: Optional[str],
    conversation_history: Optional[List[Dict[str, Any]]],
    task_id: Optional[str],
    session_id: str = "",
    memory_manager: Any = None,
    memory_nudge_interval: int = 0,
    valid_tool_names: set = frozenset(),
    memory_store: Any = None,
    user_turn_count: int = 0,
    turns_since_memory: int = 0,
) -> TurnContext:
    """Run the once-per-turn setup and return the loop's input context.

    Args:
        user_message: The incoming user message
        system_message: Optional system message
        conversation_history: Previous conversation messages
        task_id: Optional task ID
        session_id: Current session ID
        memory_manager: Optional memory manager for prefetch
        memory_nudge_interval: Interval for memory review nudges
        valid_tool_names: Set of valid tool names
        memory_store: Optional memory store
        user_turn_count: Current user turn count
        turns_since_memory: Turns since last memory review

    Returns:
        TurnContext with all pre-computed values for the turn
    """
    # Generate unique task_id if not provided
    effective_task_id = task_id or str(uuid.uuid4())
    turn_id = f"{session_id or 'session'}:{effective_task_id}:{uuid.uuid4().hex[:8]}"

    # Initialize conversation (copy to avoid mutating caller's list)
    messages = list(conversation_history) if conversation_history else []

    # Track user turns
    user_turn_count += 1

    # Add the current user message
    user_msg = {"role": "user", "content": user_message}
    messages.append(user_msg)
    current_turn_user_idx = len(messages) - 1

    # Preserve original user message
    original_user_message = user_message

    # Track memory nudge trigger
    should_review_memory = False
    if (
        memory_nudge_interval > 0
        and "memory" in valid_tool_names
        and memory_store
    ):
        turns_since_memory += 1
        if turns_since_memory >= memory_nudge_interval:
            should_review_memory = True
            turns_since_memory = 0

    # System prompt
    active_system_prompt = system_message

    # Notify memory providers of new turn
    if memory_manager:
        try:
            turn_msg = original_user_message if isinstance(original_user_message, str) else ""
            memory_manager.on_turn_start(user_turn_count, turn_msg)
        except Exception:
            pass

    # External memory prefetch
    ext_prefetch_cache = ""
    if memory_manager:
        try:
            query = original_user_message if isinstance(original_user_message, str) else ""
            ext_prefetch_cache = memory_manager.prefetch(query, session_id=session_id) or ""
        except Exception:
            pass

    # Plugin context (currently empty, extensible for future plugin system)
    plugin_user_context = ""

    # api_content sidecar: persist what you send
    if (
        0 <= current_turn_user_idx < len(messages)
        and messages[current_turn_user_idx].get("role") == "user"
    ):
        turn_user_msg = messages[current_turn_user_idx]
        api_content = compose_user_api_content(
            turn_user_msg.get("content", ""),
            ext_prefetch_cache,
            plugin_user_context,
        )
        if api_content is not None and api_content != turn_user_msg.get("content"):
            turn_user_msg["api_content"] = api_content

    logger.info(
        "conversation turn: session=%s task=%s turn=%s history=%d",
        session_id or "none",
        effective_task_id,
        turn_id[:16],
        len(conversation_history or []),
    )

    return TurnContext(
        user_message=user_message,
        original_user_message=original_user_message,
        messages=messages,
        conversation_history=conversation_history,
        active_system_prompt=active_system_prompt,
        effective_task_id=effective_task_id,
        turn_id=turn_id,
        current_turn_user_idx=current_turn_user_idx,
        should_review_memory=should_review_memory,
        plugin_user_context=plugin_user_context,
        ext_prefetch_cache=ext_prefetch_cache,
    )


__all__ = [
    "TurnContext",
    "build_turn_context",
    "compose_user_api_content",
    "substitute_api_content",
    "drop_stale_api_content",
    "extract_api_content_sidecar",
]