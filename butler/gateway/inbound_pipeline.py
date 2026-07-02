"""Declarative inbound message pipeline (D-L1-2).

Converts the imperative phase-call chain in ``handle_message`` into a
registered step list.  Each step is a ``InboundStep`` — a named guard /
transform / gate that the pipeline runner executes in order.

Three step types:

* **guard**   — may block (return ``str``); pipeline stops on block.
* **transform** — may rewrite text; returns ``(new_text, block_or_None)``.
* **gate**    — side-effect only (e.g. MCP profile); always continues.

The pipeline is configured once at handler init, and can be inspected
or extended at runtime (e.g. for testing or plugin hooks).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler

logger = logging.getLogger(__name__)


class StepKind(str, Enum):
    GUARD = "guard"
    TRANSFORM = "transform"
    GATE = "gate"


@dataclass(frozen=True)
class InboundStep:
    """A single inbound pipeline step."""

    name: str
    kind: StepKind
    run: Callable[..., Any]
    enabled: Callable[[], bool] = field(default=lambda: True)


@dataclass
class InboundTurnContext:
    """Mutable per-turn state threaded through the pipeline."""

    handler: "ButlerMessageHandler"
    text: str
    session_key: str
    platform: str
    external_id: str | None
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """Outcome of running the inbound pipeline."""

    text: str
    blocked: bool = False
    block_reply: str = ""
    stopped_at: str = ""
    step_timings: dict[str, float] = field(default_factory=dict)


def run_inbound_pipeline(
    steps: list[InboundStep],
    ctx: InboundTurnContext,
) -> PipelineResult:
    """Execute all registered inbound steps in order.

    For each step:
    - **guard**: call ``step.run(ctx)`` → ``Optional[str]``.
      If non-None, pipeline blocks with that reply.
    - **transform**: call ``step.run(ctx)`` → ``(new_text, block_or_None)``.
      If ``block`` is non-None, pipeline blocks. Otherwise ``ctx.text``
      is updated to ``new_text``.
    - **gate**: call ``step.run(ctx)`` → ignored. Pipeline always continues.

    Returns a ``PipelineResult`` with the (possibly rewritten) text,
    block status, and per-step timing diagnostics.
    """
    timings: dict[str, float] = {}
    from butler.gateway.inbound_pipeline_ops import run_inbound_step

    for step in steps:
        if not step.enabled():
            continue
        t0 = time.perf_counter()
        if step.kind == StepKind.GUARD:
            block = run_inbound_step(step.name, lambda: step.run(ctx))
            elapsed = time.perf_counter() - t0
            timings[step.name] = round(elapsed * 1000, 2)
            if block is not None:
                return PipelineResult(
                    text=ctx.text,
                    blocked=True,
                    block_reply=block,
                    stopped_at=step.name,
                    step_timings=timings,
                )
        elif step.kind == StepKind.TRANSFORM:
            result = run_inbound_step(step.name, lambda: step.run(ctx))
            elapsed = time.perf_counter() - t0
            timings[step.name] = round(elapsed * 1000, 2)
            if isinstance(result, tuple) and len(result) == 2:
                new_text, block = result
                if block is not None:
                    return PipelineResult(
                        text=ctx.text,
                        blocked=True,
                        block_reply=block,
                        stopped_at=step.name,
                        step_timings=timings,
                    )
                ctx.text = new_text
            elif isinstance(result, str):
                ctx.text = result
        elif step.kind == StepKind.GATE:
            run_inbound_step(step.name, lambda: step.run(ctx))
            elapsed = time.perf_counter() - t0
            timings[step.name] = round(elapsed * 1000, 2)

    return PipelineResult(text=ctx.text, step_timings=timings)


def build_default_inbound_pipeline() -> list[InboundStep]:
    """Build the default inbound guard pipeline (D-L1-2 declarative config).

    Each step wraps the corresponding phase function from
    ``message_pipelines.py``, adapting it to the ``InboundTurnContext``
    carrier.
    """
    from butler.gateway import message_pipelines as mp

    def _guard_io(ctx: InboundTurnContext) -> Optional[str]:
        return mp._phase_apply_io_guardrail(ctx.text)

    def _guard_human_gate(ctx: InboundTurnContext) -> Optional[str]:
        return mp._phase_apply_human_gate(
            ctx.text, ctx.session_key,
            platform=ctx.platform, external_id=ctx.external_id,
        )

    def _transform_injection_guard(ctx: InboundTurnContext) -> tuple[str, Optional[str]]:
        return mp._phase_apply_injection_guard(ctx.text, ctx.session_key)

    def _guard_injection_llm(ctx: InboundTurnContext) -> Optional[str]:
        return mp._phase_apply_injection_llm(ctx.text, ctx.session_key)

    def _guard_bot_loop(ctx: InboundTurnContext) -> Optional[str]:
        return mp._phase_apply_bot_loop_guard(
            ctx.text, ctx.session_key, external_id=ctx.external_id,
        )

    def _guard_two_phase(ctx: InboundTurnContext) -> Optional[str]:
        return mp._phase_apply_two_phase_confirm(
            ctx.text, ctx.session_key,
            platform=ctx.platform, external_id=ctx.external_id,
        )

    def _guard_prequeue_interrupt(ctx: InboundTurnContext) -> Optional[str]:
        return mp._phase_apply_prequeue_interrupt(ctx.text, ctx.session_key, handler=ctx.handler)

    def _transform_pre_dispatch(ctx: InboundTurnContext) -> tuple[str, Optional[str]]:
        rewritten = mp._phase_apply_pre_dispatch_rewrites(
            ctx.text, ctx.session_key, platform=ctx.platform,
        )
        if rewritten == "":
            return "", "drop"
        if rewritten is not None:
            return rewritten, None
        return ctx.text, None

    def _gate_mcp_profile(ctx: InboundTurnContext) -> None:
        mp._phase_apply_mcp_profile(ctx.text, ctx.session_key)

    return [
        InboundStep("io_guardrail", StepKind.GUARD, _guard_io),
        InboundStep("human_gate", StepKind.GUARD, _guard_human_gate),
        InboundStep("injection_guard", StepKind.TRANSFORM, _transform_injection_guard),
        InboundStep("injection_llm", StepKind.GUARD, _guard_injection_llm),
        InboundStep("bot_loop_guard", StepKind.GUARD, _guard_bot_loop),
        InboundStep("two_phase_confirm", StepKind.GUARD, _guard_two_phase),
        InboundStep("prequeue_interrupt", StepKind.GUARD, _guard_prequeue_interrupt),
        InboundStep("mcp_profile", StepKind.GATE, _gate_mcp_profile),
        InboundStep("pre_dispatch_rewrite", StepKind.TRANSFORM, _transform_pre_dispatch),
    ]
