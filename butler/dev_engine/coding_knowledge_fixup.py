"""Re-activate coding knowledge after verify_fail (FIX phase, P1)."""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_VERIFY_KEYWORDS = frozenset(
    {
        "verify",
        "verify_fail",
        "pytest",
        "assert",
        "assertion",
        "failed",
        "error",
        "test",
    }
)


def keywords_from_verify_fail(verify_result: Any, *, extra: list[str] | None = None) -> list[str]:
    """Build retrieval keywords from verify diagnostics and output tail."""
    tokens: list[str] = []
    for diag in getattr(verify_result, "diagnostics", None) or []:
        for field in (getattr(diag, "message", ""), getattr(diag, "rule", ""), getattr(diag, "source", "")):
            tokens.extend(_tokenize(str(field or "")))
    tokens.extend(_tokenize(str(getattr(verify_result, "output_tail", "") or "")))
    for kw in extra or []:
        tokens.extend(_tokenize(kw))
    for kw in _VERIFY_KEYWORDS:
        tokens.append(kw)
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        if tok and tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out[:48]


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{1,}", text) if len(t) > 1]


def reactivate_coding_knowledge_on_verify_fail(state: Any) -> dict[str, Any]:
    """Re-run process_task after verify_fail and refresh DevState guidance."""
    verify_result = getattr(state, "verify_result", None)
    if verify_result is None or getattr(verify_result, "passed", False):
        return {"reactivated": False, "reason": "verify_passed"}

    base_keywords = list(getattr(state, "_delegate_keywords", None) or [])
    extra = [str(getattr(state, "task_description", "") or "")]
    keywords = keywords_from_verify_fail(verify_result, extra=extra)
    for kw in base_keywords:
        if kw and kw not in keywords:
            keywords.append(kw)

    try:
        from butler.dev_engine.coding_knowledge import (
            TheoremLibrary,
            process_task,
        )
        from butler.memory.memory_scope import load_delegate_experience_library

        from butler.config import get_butler_home

        project_id = str(getattr(state, "_delegate_project_id", "") or "")
        stack_tags = getattr(state, "_delegate_stack_tags", None) or frozenset()
        inferred_task_id = str(getattr(state, "_inferred_task_id", "") or "")
        project = getattr(state, "_delegate_project", None)

        tlib = TheoremLibrary()
        xlib = load_delegate_experience_library(
            butler_home=get_butler_home(),
            project=project,
            theorem_lib=tlib,
        )
        try:
            from butler.ops.eval_config_overrides import effective_coding_knowledge_strict

            strict = effective_coding_knowledge_strict(True)
        except Exception:
            strict = True

        prev_id = ""
        ck = getattr(state, "coding_knowledge", None)
        if ck is not None:
            prev_id = str(getattr(ck, "experience_id", "") or "")

        ctx = process_task(
            keywords,
            tlib,
            xlib,
            strict_experience=strict,
            project_id=project_id,
            stack_tags=stack_tags,
            inferred_task_id=inferred_task_id,
        )

        if ck is not None:
            ck.mode = ctx.mode
            ck.activated_theorem_ids = sorted(ctx.activated_theorems.keys())
            ck.activated_elements = [e.value for e in ctx.activated_elements]
            if ctx.selected_experience is not None:
                ck.experience_id = ctx.selected_experience.id
                ck.experience_title = ctx.selected_experience.title
            else:
                ck.experience_id = ""
                ck.experience_title = ""

        state._coding_knowledge_ctx = ctx
        state._coding_knowledge_theorems = ctx.activated_theorems
        count = int(getattr(state, "_coding_knowledge_reactivation_count", 0) or 0) + 1
        state._coding_knowledge_reactivation_count = count

        new_id = ctx.selected_experience.id if ctx.selected_experience else ""
        if new_id and new_id != prev_id:
            try:
                from butler.ops.experience_selection_telemetry import record_experience_selection

                record_experience_selection(
                    session_key=str(getattr(state, "_delegate_session_key", "") or ""),
                    task_preview=str(getattr(state, "task_description", "") or "")[:300],
                    experience_id=new_id,
                    experience_mode=ctx.mode,
                    keywords=keywords[:24],
                    role="dev",
                    inferred_task_id=inferred_task_id,
                    selection_phase="fix_reactivation",
                )
            except Exception:
                pass

        return {
            "reactivated": True,
            "experience_id": new_id,
            "experience_mode": ctx.mode,
            "keywords": keywords[:12],
            "reactivation_count": count,
            "experience_changed": bool(new_id and new_id != prev_id),
        }
    except Exception as exc:
        logger.debug("coding knowledge fixup skipped: %s", exc)
        return {"reactivated": False, "reason": str(exc)}


__all__ = [
    "keywords_from_verify_fail",
    "reactivate_coding_knowledge_on_verify_fail",
]
