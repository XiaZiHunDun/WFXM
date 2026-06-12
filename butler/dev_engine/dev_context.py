"""Code-aware context management — relevance scoring and focused window.

Formal model from v4-dev-engine-theory.md §5.3 DD2/DD4:
  Edit → affected_files → Verify → inject_diagnostics(context)
  DevState injected into LLM context for structured reporting.
"""

from __future__ import annotations

import os
from pathlib import Path

from butler.dev_engine.dev_state import DevState


def dev_state_context_block(state: DevState) -> str:
    """Generate a context block summarizing current DevState for LLM injection."""
    lines = [
        "<dev-engine-state>",
        f"phase: {state.phase.value}",
        f"iteration: {state.iteration}/{state.max_iterations}",
        f"fix_rounds: {state.fix_count}/{state.max_fix_rounds}",
    ]

    if state.edit_history:
        lines.append(f"edits: {len(state.edit_history)} operations")
        for e in state.edit_history[-3:]:
            lines.append(f"  - {e.operation} {e.path}")

    if state.verify_result.status.value != "UNKNOWN":
        lines.append(f"verify: {state.verify_result.status.value}")
        if state.verify_result.diagnostics:
            lines.append(f"  errors: {state.verify_result.error_count}")
            for d in state.verify_result.diagnostics[:5]:
                lines.append(f"  - {d.file}:{d.line} [{d.severity.value}] {d.message}")

    if state.search_context:
        lines.append(f"search_hits: {len(state.search_context)}")
        for h in state.search_context[:3]:
            lines.append(f"  - {h.path}:{h.range_start} (rel={h.relevance:.1f})")

    ck = state.coding_knowledge
    if ck.mode:
        lines.append(f"coding_knowledge_mode: {ck.mode}")
        if ck.activated_theorem_ids:
            lines.append(f"activated_theorems: {', '.join(ck.activated_theorem_ids)}")
        if ck.activated_elements:
            lines.append(f"activated_elements: {', '.join(ck.activated_elements)}")
        if ck.experience_id:
            lines.append(f"experience: {ck.experience_title} ({ck.experience_id})")
        if ck.violated_theorems:
            lines.append(f"⚠ violated_theorems: {', '.join(ck.violated_theorems)}")

    ctx = getattr(state, "_coding_knowledge_ctx", None)
    if ctx is not None:
        try:
            from butler.dev_engine.coding_knowledge import format_coding_guidance_block

            max_cases = 6
            try:
                from butler.ops.eval_config_overrides import effective_coding_guidance_max_cases

                max_cases = effective_coding_guidance_max_cases(6)
            except Exception:
                pass
            guidance = format_coding_guidance_block(ctx, max_cases=max_cases)
            if guidance.strip():
                lines.append(guidance)
            try:
                from butler.dev_engine.b9_oracle_fewshot import format_b9_oracle_fewshot_block

                fewshot = format_b9_oracle_fewshot_block(max_cases=2)
                if fewshot:
                    lines.append(fewshot)
            except Exception:
                pass
        except Exception as exc:
            import logging
            logging.getLogger(__name__).debug("coding guidance block skipped: %s", exc)

    lines.append("</dev-engine-state>")
    return "\n".join(lines)


def compute_file_relevance(
    file_path: str,
    state: DevState,
    workspace: Path,
) -> float:
    """Score a file's relevance to the current development task.

    Higher scores → more likely to be included in focused context.
    """
    score = 0.0

    for edit in state.edit_history:
        if _paths_match(edit.path, file_path, workspace):
            score += 2.0

    for hit in state.search_context:
        if _paths_match(hit.path, file_path, workspace):
            score += hit.relevance

    for diag in state.diagnostics:
        if _paths_match(diag.file, file_path, workspace):
            score += 1.5

    return min(score, 10.0)


def select_focused_files(
    state: DevState,
    workspace: Path,
    *,
    max_files: int = 10,
) -> list[str]:
    """Select the most relevant files for context injection."""
    candidates: dict[str, float] = {}

    for edit in state.edit_history:
        candidates[edit.path] = candidates.get(edit.path, 0) + 2.0

    for hit in state.search_context:
        full = str(workspace / hit.path) if not os.path.isabs(hit.path) else hit.path
        candidates[full] = candidates.get(full, 0) + hit.relevance

    for diag in state.diagnostics:
        if diag.file:
            full = str(workspace / diag.file) if not os.path.isabs(diag.file) else diag.file
            candidates[full] = candidates.get(full, 0) + 1.5

    sorted_files = sorted(candidates.items(), key=lambda x: x[1], reverse=True)
    return [f for f, _ in sorted_files[:max_files]]


def _paths_match(a: str, b: str, workspace: Path) -> bool:
    """Check if two paths refer to the same file (handles relative/absolute)."""
    try:
        pa = Path(a)
        pb = Path(b)
        if not pa.is_absolute():
            pa = workspace / pa
        if not pb.is_absolute():
            pb = workspace / pb
        return pa.resolve() == pb.resolve()
    except (OSError, ValueError):
        return a == b
