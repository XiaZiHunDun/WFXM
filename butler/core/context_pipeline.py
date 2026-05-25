"""Context compression and API message preparation for AgentLoop."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from butler.core.context_compressor import (
    _estimate_tokens,
    compress_messages,
    prune_tool_outputs,
)
from butler.core.tool_output_prune import backward_prune_tool_outputs
from butler.core.post_compact_cleanup import apply_post_compact_anchors, run_post_compact_cleanup
from butler.core.hygiene_preflight import run_hygiene_preflight
from butler.core.loop_types import LoopConfig
from butler.core.message_repair import repair_message_sequence, repair_tool_arguments
from butler.core.tool_pair_repair import repair_tool_pairs
from butler.core.message_sanitize import (
    drop_thinking_only_assistants,
    sanitize_api_messages,
)

logger = logging.getLogger(__name__)


@dataclass
class ContextPipeline:
    """Compress conversation history and prepare messages for the LLM API."""

    config: LoopConfig
    compression_summary: str = ""
    consecutive_compact_failures: int = 0
    _attached_loop: Any | None = None

    def estimate_tokens(self, messages: list[dict]) -> int:
        return _estimate_tokens(messages)

    def compress_context(
        self,
        messages: list[dict],
        *,
        threshold_ratio: float = 0.5,
        min_messages_to_compress: int = 12,
        head_count: int = 3,
        max_tail_messages: int = 12,
        min_tail_messages: int = 4,
        overflow_replay: bool = False,
        diagnostics: dict[str, Any] | None = None,
    ) -> list[dict]:
        session_key = ""
        try:
            from butler.execution_context import get_audit_session_key

            session_key = get_audit_session_key(fallback="")
        except Exception:
            pass
        if session_key and len(messages) >= min_messages_to_compress:
            try:
                from butler.core.compaction_checkpoint import capture_checkpoint
                from butler.core.session_todos import count_open_todos, session_todos_enabled

                open_n = (
                    count_open_todos(session_key)
                    if session_todos_enabled()
                    else 0
                )
                capture_checkpoint(
                    session_key,
                    open_todos=open_n,
                    compression_summary=self.compression_summary,
                    max_iterations=self.config.max_iterations,
                )
                if self._attached_loop is not None:
                    from butler.core.compaction_checkpoint import capture_from_loop

                    capture_from_loop(
                        session_key,
                        loop=self._attached_loop,
                        compression_summary=self.compression_summary,
                    )
            except Exception as exc:
                logger.debug("Compaction checkpoint pre-capture: %s", exc)

        injection = None
        if isinstance(diagnostics, dict):
            try:
                from butler.core.compaction_phase import (
                    record_compaction_diagnostics,
                    resolve_compaction_context,
                )

                iteration = int(diagnostics.get("compaction_turn_iteration") or 0)
                reactive = bool(diagnostics.get("reactive_context_compact"))
                phase, injection, reason = resolve_compaction_context(
                    iteration=max(1, iteration),
                    explicit_turn=bool(diagnostics.get("compaction_explicit_turn")),
                    reactive=reactive,
                )
                record_compaction_diagnostics(
                    diagnostics, phase=phase, reason=reason, injection=injection
                )
            except Exception:
                injection = None

        compressed, summary, did = compress_messages(
            messages,
            max_tokens=self.config.max_context_tokens,
            threshold_ratio=threshold_ratio,
            previous_summary=self.compression_summary,
            min_messages_to_compress=min_messages_to_compress,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
            max_output_tokens=getattr(self.config, "max_output_tokens", None),
            overflow_replay=overflow_replay,
            initial_injection=injection,
            diagnostics=diagnostics,
        )
        if did and summary:
            self.compression_summary = summary
            self.consecutive_compact_failures = 0
            skip_anchor = False
            if isinstance(diagnostics, dict):
                try:
                    from butler.core.compaction_phase import (
                        CompactionPhase,
                        should_skip_post_compact_reanchor,
                    )

                    skip_anchor = should_skip_post_compact_reanchor(diagnostics)
                except Exception:
                    skip_anchor = False
            if not skip_anchor:
                compressed = apply_post_compact_anchors(compressed, diagnostics)
            if session_key and isinstance(diagnostics, dict):
                try:
                    from butler.core.compaction_checkpoint import restore_into_diagnostics

                    restore_into_diagnostics(session_key, diagnostics)
                except Exception as exc:
                    logger.debug("Compaction checkpoint restore: %s", exc)
        return compressed

    def prepare_messages_for_api(
        self,
        messages: list[dict],
        *,
        pre_llm_transform: Callable[[list[dict]], list[dict]] | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> list[dict]:
        from butler.core.tool_result_storage import enforce_message_tool_budget
        from butler.execution_context import get_audit_session_key

        prepared = enforce_message_tool_budget(
            list(messages),
            session_key=get_audit_session_key(fallback="_global"),
        )
        prepared = prune_tool_outputs(prepared)
        prepared = backward_prune_tool_outputs(prepared)
        try:
            from butler.core.tool_output_masking import apply_unified_tool_masking

            prepared = apply_unified_tool_masking(prepared)
        except Exception as exc:
            logger.debug("Unified tool masking skipped: %s", exc)
        diag: dict[str, Any] = diagnostics if isinstance(diagnostics, dict) else {}
        try:
            from butler.core.preemptive_compact import (
                ContextPrecheckOverflow,
                apply_preemptive_pipeline,
                preemptive_compact_enabled,
            )

            if preemptive_compact_enabled():
                prepared, decision = apply_preemptive_pipeline(
                    prepared,
                    max_context_tokens=self.config.max_context_tokens,
                    estimate_tokens=self.estimate_tokens,
                    compress=self.compress_context,
                    diagnostics=diag or None,
                )
                if decision.route == "overflow_fail":
                    raise ContextPrecheckOverflow(
                        decision.message,
                        estimated=decision.estimated_tokens,
                        threshold=decision.threshold_tokens,
                    )
        except ContextPrecheckOverflow:
            raise
        except Exception as exc:
            logger.debug("Preemptive compact skipped: %s", exc)
        if diag is not None:
            diag.setdefault("session_key", get_audit_session_key(fallback="_global"))
        prepared = self.compress_context(prepared, diagnostics=diag or None)
        prepared, _ = repair_message_sequence(prepared)
        prepared, _ = repair_tool_pairs(prepared, diagnostics=diag or None)
        repair_tool_arguments(prepared)
        prepared, _ = sanitize_api_messages(prepared)
        prepared, _ = drop_thinking_only_assistants(prepared)
        if pre_llm_transform:
            prepared = pre_llm_transform(prepared)
        ephemeral = ""
        if diag:
            ephemeral = str(diag.get("ephemeral_system") or "").strip()
        if ephemeral:
            prepared = _inject_ephemeral_system(prepared, ephemeral)
        return prepared

    def hygiene_compress_if_needed(
        self,
        messages: list[dict],
        diagnostics: dict[str, Any],
        *,
        threshold_ratio: float = 0.85,
        hard_message_limit: int = 400,
        max_output_tokens: int | None = None,
    ) -> tuple[bool, list[dict]]:
        """Run gateway preflight compression; return (compressed, updated_messages)."""
        snapshot = list(messages)
        result = run_hygiene_preflight(
            snapshot,
            max_context_tokens=self.config.max_context_tokens,
            diagnostics=diagnostics,
            estimate_tokens=self.estimate_tokens,
            compress=self.compress_context,
            threshold_ratio=threshold_ratio,
            hard_message_limit=hard_message_limit,
            consecutive_compact_failures=self.consecutive_compact_failures,
            max_output_tokens=max_output_tokens,
        )
        self.consecutive_compact_failures = int(
            diagnostics.get("context_compact_consecutive_failures", 0) or 0
        )
        if not result.compressed:
            return False, messages

        anchored = run_post_compact_cleanup(diagnostics, messages=result.messages) or result.messages
        logger.info(
            "Gateway hygiene compressed %d->%d messages (~%d tokens, threshold=%d)",
            len(messages),
            len(anchored),
            diagnostics.get("hygiene_estimated_tokens", 0),
            diagnostics.get("hygiene_threshold_tokens", 0),
        )
        return True, anchored


def _inject_ephemeral_system(messages: list[dict], banner: str) -> list[dict]:
    if not banner.strip():
        return messages
    block = f"{banner.strip()}\n\n(本段为 ephemeral 执行提示，不写入用户消息。)"
    out = list(messages)
    for i, msg in enumerate(out):
        if isinstance(msg, dict) and msg.get("role") == "system":
            prev = str(msg.get("content") or "")
            out[i] = {**msg, "content": f"{prev}\n\n{block}".strip() if prev else block}
            return out
    out.insert(0, {"role": "system", "content": block})
    return out
