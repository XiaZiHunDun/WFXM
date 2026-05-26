"""Context compression for long Butler conversations.

Simplified port of Hermes ``agent/context_compressor.py``:
  1. Prune large tool outputs (no LLM)
  2. Protect system + token-budget tail
  3. Summarize middle via auxiliary model
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from butler.transport.auxiliary_client import auxiliary_complete

logger = logging.getLogger(__name__)

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted. "
    "Treat as background, NOT active instructions. "
    "Resume from '## Active Task' in the summary. "
    "Respond ONLY to the latest user message after this block:\n\n"
)

_MIN_MESSAGES_TO_COMPRESS = 12


def _estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += len(json.dumps(m, ensure_ascii=False, default=str)) // 4
    return total


def prune_tool_outputs(messages: list[dict]) -> list[dict]:
    """Prune oversized tool role messages before API / compaction (microCompact-style)."""
    return _prune_tool_outputs(messages)


def _prune_tool_outputs(messages: list[dict]) -> list[dict]:
    from butler.core.tool_prune_policy import (
        build_tool_name_index,
        keep_recent_tool_messages,
        prune_tool_message_content,
        _tool_message_indices,
    )

    id_to_name = build_tool_name_index(messages)
    tool_idxs = _tool_message_indices(messages)
    recent = set(tool_idxs[-keep_recent_tool_messages() :])

    out: list[dict] = []
    for i, m in enumerate(messages):
        if m.get("role") != "tool":
            out.append(m)
            continue
        content = str(m.get("content") or "")
        tool_name = id_to_name.get(str(m.get("tool_call_id") or ""), "")
        new_content = prune_tool_message_content(
            content,
            tool_name=tool_name,
            is_stale=i not in recent,
        )
        if new_content == content:
            out.append(m)
        else:
            out.append({**m, "content": new_content})
    return out


def _split_head_tail(
    messages: list[dict],
    head_count: int = 3,
    tail_token_budget: int = 8000,
    max_tail_messages: int = 12,
    min_tail_messages: int = 4,
) -> tuple[list[dict], list[dict], list[dict]]:
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    if len(rest) <= head_count + min_tail_messages:
        return system, [], rest

    head = rest[:head_count]
    tail_candidates = rest[head_count:]
    tail: list[dict] = []
    budget = 0
    for m in reversed(tail_candidates):
        budget += len(str(m.get("content") or "")) // 4
        tail.insert(0, m)
        if len(tail) >= max_tail_messages or budget >= tail_token_budget:
            break

    middle_end = len(rest) - len(tail)
    from butler.core.compaction_cutoff import find_safe_tail_start

    middle_end = find_safe_tail_start(rest, middle_end)
    tail = rest[middle_end:]
    middle = rest[head_count:middle_end] if middle_end > head_count else []
    return system, middle, head + tail


def compress_tool_response_budget_tokens() -> int:
    import os

    try:
        return max(5000, int(os.getenv("BUTLER_COMPRESS_TOOL_RESPONSE_BUDGET", "") or "50000"))
    except ValueError:
        return 50_000


def truncate_tool_responses_to_budget(messages: list[dict]) -> list[dict]:
    """Before LLM summarization, cap total tool-role tokens (Gemini pre-compress budget)."""
    import os

    if os.getenv("BUTLER_COMPRESS_TOOL_RESPONSE_BUDGET", "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return messages
    budget = compress_tool_response_budget_tokens()
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    total = sum(len(str(m.get("content") or "")) // 4 for m in tool_msgs)
    if total <= budget:
        return messages

    from butler.core.tool_result_storage import BUDGET_TRUNCATED_TAG

    out: list[dict] = []
    remaining = budget
    changed = False
    for m in messages:
        if m.get("role") != "tool":
            out.append(m)
            continue
        content = str(m.get("content") or "")
        est = max(1, len(content) // 4)
        if remaining > 0 and est <= remaining:
            out.append(m)
            remaining -= est
            continue
        changed = True
        lines = content.splitlines()
        tail = "\n".join(lines[-30:]) if len(lines) > 30 else content[:4000]
        trimmed = (
            tail[:8000]
            + f"\n\n{BUDGET_TRUNCATED_TAG} "
            f"(pre-compact budget; was ~{est * 4} chars)\n"
        )
        out.append({**m, "content": trimmed})
    if changed:
        try:
            from butler.ops.retry_buckets import record_recovery_event

            record_recovery_event("compress_tool_budget_truncate")
        except Exception:
            pass
    return out


def _format_for_summary(messages: list[dict], max_chars: int = 12000) -> str:
    parts: list[str] = []
    total = 0
    for m in messages:
        role = str(m.get("role", "")).upper()
        content = str(m.get("content") or "")[:600]
        if not content and m.get("tool_calls"):
            content = f"[tool_calls: {len(m['tool_calls'])}]"
        line = f"[{role}]: {content}"
        if total + len(line) > max_chars:
            break
        parts.append(line)
        total += len(line)
    return "\n\n".join(parts)


def _summarize_middle(middle: list[dict], previous_summary: str = "") -> tuple[str, bool]:
    transcript = _format_for_summary(middle)
    if len(transcript) < 100:
        return previous_summary, False

    try:
        from butler.core.remote_compact import try_remote_summarize

        remote_summary = try_remote_summarize(middle, previous_summary)
        if remote_summary and remote_summary.strip():
            return remote_summary.strip(), True
    except Exception as exc:
        logger.debug("Remote compact skipped: %s", exc)

    from butler.core.compaction_prompt import build_compaction_user_prompt

    prompt = build_compaction_user_prompt(
        transcript=transcript,
        previous_summary=previous_summary,
    )
    try:
        text = auxiliary_complete(
            prompt,
            task="compression",
            system="You compress conversation history into structured handoff notes.",
        )
        return text, False
    except Exception as exc:
        logger.warning("Summary LLM failed: %s", exc)
        return previous_summary or transcript[:2000], False


def compress_messages(
    messages: list[dict],
    *,
    max_tokens: int = 128000,
    threshold_ratio: float = 0.5,
    previous_summary: str = "",
    min_messages_to_compress: int = _MIN_MESSAGES_TO_COMPRESS,
    head_count: int = 3,
    max_tail_messages: int = 12,
    min_tail_messages: int = 4,
    overflow_replay: bool = False,
    max_output_tokens: int | None = None,
    initial_injection: Any = None,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[dict], str, bool]:
    """Compress messages if over threshold. Returns (messages, summary, did_compress)."""
    estimated = _estimate_tokens(messages)
    threshold = int(max_tokens * threshold_ratio)
    if estimated <= threshold or len(messages) < min_messages_to_compress:
        return messages, previous_summary, False

    try:
        from butler.core.session_transcript import record_compact_scheduled
        from butler.execution_context import get_audit_session_key

        record_compact_scheduled(
            get_audit_session_key(fallback="_global"),
            source="context_compressor",
            messages_before=len(messages),
            tokens_estimated=estimated,
        )
    except Exception:
        pass

    pruned = _prune_tool_outputs(messages)
    skill_rescued: list[dict] = []
    try:
        from butler.core.skill_compact_rescue import (
            extract_skill_rescue_messages,
            merge_skill_rescue_into_tail,
        )

        pruned, skill_rescued = extract_skill_rescue_messages(pruned)
    except Exception as exc:
        logger.debug("Skill compact rescue skipped: %s", exc)
    replay_user = None
    if overflow_replay:
        try:
            from butler.core.turn_compaction import find_overflow_replay_user

            replay_user = find_overflow_replay_user(pruned)
        except Exception:
            pass

    try:
        from butler.core.turn_compaction import split_head_tail_turns, turn_compaction_enabled

        if turn_compaction_enabled():
            system, middle, head_tail = split_head_tail_turns(
                pruned,
                max_context_tokens=max_tokens,
                max_output_tokens=max_output_tokens,
                head_count=head_count,
                min_tail_messages=min_tail_messages,
                estimate_fn=_estimate_tokens,
            )
            if not middle:
                legacy_system, legacy_middle, legacy_head_tail = _split_head_tail(
                    pruned,
                    head_count=head_count,
                    max_tail_messages=max_tail_messages,
                    min_tail_messages=min_tail_messages,
                )
                if legacy_middle:
                    system, middle, head_tail = (
                        legacy_system,
                        legacy_middle,
                        legacy_head_tail,
                    )
                    if isinstance(diagnostics, dict):
                        diagnostics["compaction_turn_fallback"] = "legacy_split"
        else:
            system, middle, head_tail = _split_head_tail(
                pruned,
                head_count=head_count,
                max_tail_messages=max_tail_messages,
                min_tail_messages=min_tail_messages,
            )
    except Exception as exc:
        logger.debug("Turn compaction fallback: %s", exc)
        system, middle, head_tail = _split_head_tail(
            pruned,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
        )

    if not middle:
        if skill_rescued:
            head_tail = merge_skill_rescue_into_tail(head_tail, skill_rescued)
            return system + head_tail, previous_summary, False
        return pruned, previous_summary, False

    middle = truncate_tool_responses_to_budget(middle)
    summary, used_remote = _summarize_middle(middle, previous_summary)
    if isinstance(diagnostics, dict):
        diagnostics["compaction_remote"] = used_remote
    summary_msg = {"role": "user", "content": SUMMARY_PREFIX + summary}

    try:
        from butler.core.compaction_phase import (
            InitialContextInjection,
            apply_summary_placement,
        )

        injection = initial_injection
        if injection is None:
            injection = InitialContextInjection.DO_NOT_INJECT
        compressed = apply_summary_placement(system, head_tail, summary_msg, injection)
    except Exception:
        compressed = system + [summary_msg] + head_tail
    if skill_rescued:
        try:
            from butler.core.skill_compact_rescue import merge_skill_rescue_into_tail

            tail_only = [m for m in compressed if m.get("role") != "system"]
            system_only = [m for m in compressed if m.get("role") == "system"]
            tail_only = merge_skill_rescue_into_tail(tail_only, skill_rescued)
            compressed = system_only + tail_only
        except Exception as exc:
            logger.debug("Skill rescue merge skipped: %s", exc)
    if overflow_replay and replay_user:
        try:
            from butler.core.turn_compaction import append_overflow_replay

            compressed = append_overflow_replay(compressed, replay_user)
        except Exception:
            pass
    logger.info(
        "Context compressed: %d→%d msgs, ~%d→%d tokens",
        len(messages), len(compressed), estimated, _estimate_tokens(compressed),
    )
    sk = ""
    try:
        from butler.core.session_transcript import (
            record_compact_boundary,
            record_compact_done,
        )
        from butler.execution_context import get_audit_session_key

        sk = get_audit_session_key(fallback="_global")
        record_compact_boundary(sk, len(summary))
        record_compact_done(
            sk,
            source="context_compressor",
            messages_after=len(compressed),
            tokens_after=_estimate_tokens(compressed),
            summary_chars=len(summary),
        )
    except Exception:
        pass
    try:
        from butler.gateway.item_events import context_compaction_item, emit_thread_item

        emit_thread_item(
            context_compaction_item(
                phase="completed",
                thread_id=sk,
                tokens_before=estimated,
                tokens_after=_estimate_tokens(compressed),
                messages_before=len(messages),
                messages_after=len(compressed),
                source="context_compressor",
                remote=used_remote,
            )
        )
    except Exception:
        pass
    return compressed, summary, True
