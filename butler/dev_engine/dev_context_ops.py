"""Dev context block best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def append_coding_guidance_blocks_safe(lines: list[str], ctx: Any) -> None:
    def _run() -> None:
        from butler.dev_engine.coding_knowledge import format_coding_guidance_block

        max_cases = effective_coding_guidance_max_cases_safe(6)
        guidance = format_coding_guidance_block(ctx, max_cases=max_cases)
        if guidance.strip():
            lines.append(guidance)
        fewshot = format_b9_oracle_fewshot_block_safe()
        if fewshot:
            lines.append(fewshot)

    safe_best_effort(_run, label="dev_context.coding_guidance", default=None)


def effective_coding_guidance_max_cases_safe(default: int) -> int:
    def _run() -> int:
        from butler.ops.eval_config_overrides import effective_coding_guidance_max_cases

        return int(effective_coding_guidance_max_cases(default))

    result = safe_best_effort(
        _run,
        label="dev_context.guidance_max_cases",
        default=default,
    )
    return int(result) if isinstance(result, int) else default


def format_b9_oracle_fewshot_block_safe() -> str:
    def _run() -> str:
        from butler.dev_engine.b9_oracle_fewshot import format_b9_oracle_fewshot_block

        return str(format_b9_oracle_fewshot_block(max_cases=2) or "")

    result = safe_best_effort(
        _run,
        label="dev_context.b9_fewshot",
        default="",
    )
    return str(result or "")
