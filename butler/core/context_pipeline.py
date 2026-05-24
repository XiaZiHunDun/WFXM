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
from butler.core.post_compact_cleanup import run_post_compact_cleanup
from butler.core.hygiene_preflight import run_hygiene_preflight
from butler.core.loop_types import LoopConfig
from butler.core.message_repair import repair_message_sequence, repair_tool_arguments
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
    ) -> list[dict]:
        compressed, summary, did = compress_messages(
            messages,
            max_tokens=self.config.max_context_tokens,
            threshold_ratio=threshold_ratio,
            previous_summary=self.compression_summary,
            min_messages_to_compress=min_messages_to_compress,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
        )
        if did and summary:
            self.compression_summary = summary
            self.consecutive_compact_failures = 0
        return compressed

    def prepare_messages_for_api(
        self,
        messages: list[dict],
        *,
        pre_llm_transform: Callable[[list[dict]], list[dict]] | None = None,
    ) -> list[dict]:
        prepared = prune_tool_outputs(list(messages))
        prepared = self.compress_context(prepared)
        prepared, _ = repair_message_sequence(prepared)
        repair_tool_arguments(prepared)
        prepared, _ = sanitize_api_messages(prepared)
        prepared, _ = drop_thinking_only_assistants(prepared)
        if pre_llm_transform:
            prepared = pre_llm_transform(prepared)
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

        run_post_compact_cleanup(diagnostics)
        logger.info(
            "Gateway hygiene compressed %d->%d messages (~%d tokens, threshold=%d)",
            len(messages),
            len(result.messages),
            diagnostics.get("hygiene_estimated_tokens", 0),
            diagnostics.get("hygiene_threshold_tokens", 0),
        )
        return True, result.messages
