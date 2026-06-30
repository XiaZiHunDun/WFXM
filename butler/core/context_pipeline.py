"""Context compression and API message preparation for AgentLoop."""

from __future__ import annotations

import logging
import weakref
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class LoopContext(Protocol):
    """Minimal interface that ContextPipeline needs from AgentLoop."""

    @property
    def client(self) -> Any: ...

    @property
    def config(self) -> Any: ...

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


def apply_tool_prune_pipeline(messages: list[dict]) -> list[dict]:
    """Forward micro prune + backward volume prune (prepare_messages_for_api order)."""
    out = prune_tool_outputs(list(messages))
    return backward_prune_tool_outputs(out)


@dataclass
class ContextPipeline:
    """Compress conversation history and prepare messages for the LLM API."""

    config: LoopConfig
    compression_summary: str = ""
    consecutive_compact_failures: int = 0
    _attached_loop_ref: Any = field(default=None, repr=False)

    @property
    def _attached_loop(self) -> LoopContext | None:
        ref = self._attached_loop_ref
        if ref is None:
            return None
        if isinstance(ref, weakref.ref):
            return ref()
        return ref

    @_attached_loop.setter
    def _attached_loop(self, value: LoopContext | None) -> None:
        if value is None:
            self._attached_loop_ref = None
        else:
            try:
                self._attached_loop_ref = weakref.ref(value)
            except TypeError:
                logger.warning(
                    "Cannot create weakref for %s; loop diagnostics will be unavailable",
                    type(value).__name__,
                )
                self._attached_loop_ref = None

    def attach_loop(self, loop: LoopContext) -> None:
        """Public API: attach a loop context (stored as a weakref)."""
        self._attached_loop = loop

    def detach_loop(self) -> None:
        """Public API: clear the attached loop reference."""
        self._attached_loop = None

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
        except Exception as exc:
            logger.debug("compress context skipped: %s", exc)
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
        if did and summary is not None:
            from butler.core.compaction_context_adapter import (
                apply_compaction_view_to_diagnostics,
                to_loop_compaction_view,
            )

            view = to_loop_compaction_view(summary, source="compress_messages")
            apply_compaction_view_to_diagnostics(view, diagnostics)
            self.compression_summary = view.content
            self.consecutive_compact_failures = 0
            skip_anchor = False
            if isinstance(diagnostics, dict):
                try:
                    from butler.core.compaction_phase import (
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
        from butler.core.pipeline_steps import PipelineStep, run_pipeline_steps
        from butler.core.tool_result_storage import (
            apply_inject_once_policy,
            enforce_message_tool_budget,
        )
        from butler.execution_context import get_audit_session_key

        sk = get_audit_session_key(fallback="_global")
        diag: dict[str, Any] = diagnostics if isinstance(diagnostics, dict) else {}
        pipeline = self

        def _inject_once(msgs: list[dict]) -> list[dict]:
            out = list(msgs)
            apply_inject_once_policy(out, session_key=sk)
            return enforce_message_tool_budget(out, session_key=sk)

        def _prune(msgs: list[dict]) -> list[dict]:
            return apply_tool_prune_pipeline(msgs)

        def _mask(msgs: list[dict]) -> list[dict]:
            try:
                from butler.core.tool_output_masking import apply_unified_tool_masking

                return apply_unified_tool_masking(list(msgs))
            except Exception as exc:
                logger.debug("Unified tool masking skipped: %s", exc)
                return list(msgs)

        def _inline_compress_step(msgs: list[dict]) -> list[dict]:
            try:
                from butler.core.inline_tool_compress import compress_inline_tool_messages

                return compress_inline_tool_messages(list(msgs))
            except Exception as exc:
                logger.debug("Inline tool compress skipped: %s", exc)
                return list(msgs)

        def _model_transform(msgs: list[dict]) -> list[dict]:
            try:
                from butler.core.context_transform_registry import apply_model_transforms

                loop = getattr(pipeline, "_attached_loop", None)
                client = getattr(loop, "client", None) if loop else None
                if client is None:
                    return list(msgs)
                provider = str(getattr(client, "provider_name", "") or "")
                model = str(getattr(client, "model", "") or "")
                return apply_model_transforms(
                    list(msgs),
                    provider=provider,
                    model=model,
                    diagnostics=diag or None,
                )
            except Exception as exc:
                logger.debug("Model transform skipped: %s", exc)
                return list(msgs)

        def _preemptive(msgs: list[dict]) -> list[dict]:
            try:
                from butler.core.preemptive_compact import (
                    ContextPrecheckOverflow,
                    apply_preemptive_pipeline,
                    preemptive_compact_enabled,
                )

                if not preemptive_compact_enabled():
                    return list(msgs)
                out, decision = apply_preemptive_pipeline(
                    list(msgs),
                    max_context_tokens=pipeline.config.max_context_tokens,
                    estimate_tokens=pipeline.estimate_tokens,
                    compress=pipeline.compress_context,
                    diagnostics=diag or None,
                )
                if decision.route == "overflow_fail":
                    raise ContextPrecheckOverflow(
                        decision.message,
                        estimated=decision.estimated_tokens,
                        threshold=decision.threshold_tokens,
                    )
                return out
            except ContextPrecheckOverflow:
                raise
            except Exception as exc:
                logger.debug("Preemptive compact skipped: %s", exc)
                return list(msgs)

        def _compress(msgs: list[dict]) -> list[dict]:
            if diag is not None:
                diag.setdefault("session_key", get_audit_session_key(fallback="_global"))
            return pipeline.compress_context(list(msgs), diagnostics=diag or None)

        def _repair(msgs: list[dict]) -> list[dict]:
            out, _ = repair_message_sequence(list(msgs))
            out, _ = repair_tool_pairs(out, diagnostics=diag or None)
            repair_tool_arguments(out)
            out, _ = sanitize_api_messages(out)
            out, _ = drop_thinking_only_assistants(out)
            try:
                from butler.core.message_context_adapter import annotate_api_message_boundary

                annotate_api_message_boundary(out, diag or None, source="prepare_messages")
            except Exception as exc:
                logger.debug("API message ACL skipped: %s", exc)
            return out

        steps = [
            PipelineStep("inject_once", _inject_once),
            PipelineStep("prune_tools", _prune),
            PipelineStep("mask_tools", _mask),
            PipelineStep("inline_tool_compress", _inline_compress_step),
            PipelineStep("model_transform", _model_transform),
            PipelineStep("preemptive_compact", _preemptive),
            PipelineStep("compress", _compress),
            PipelineStep("repair_sanitize", _repair),
        ]
        prepared = run_pipeline_steps(list(messages), steps, diagnostics=diag or None)
        if pre_llm_transform:
            prepared = pre_llm_transform(prepared)
        ephemeral = str(diag.get("ephemeral_system") or "").strip() if diag else ""
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
        snapshot = apply_tool_prune_pipeline(messages)
        if snapshot is not messages:
            diagnostics["hygiene_pruned_before_compact"] = True
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
            if diagnostics.get("hygiene_pruned_before_compact"):
                return False, snapshot
            return False, messages

        anchored = run_post_compact_cleanup(diagnostics, messages=result.messages) or result.messages
        before_tokens = self.estimate_tokens(messages)
        anchored_tokens = self.estimate_tokens(anchored)
        if anchored_tokens >= before_tokens:
            diagnostics["post_compact_anchor_skipped_bloat"] = True
            anchored = result.messages
        else:
            diagnostics["post_compact_anchor_applied"] = True
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
