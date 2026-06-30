"""Review findings persistence — reflection + experience candidates."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.review_ports import DevReviewView, ReviewFinding
from butler.core.review_context_adapter import max_severity

logger = logging.getLogger(__name__)


def review_closure_write_enabled() -> bool:
    try:
        from butler.core.reflection_closure import reflection_closure_enabled

        if not reflection_closure_enabled():
            return False
    except Exception:
        return False
    try:
        from butler.env_parse import env_truthy

        return env_truthy("BUTLER_REFLECTION_CLOSURE_WRITE", default=False) or env_truthy(
            "BUTLER_REFLEXION_WRITE_EXPERIENCE", default=False
        )
    except Exception:
        return False


def maybe_persist_review_closure(
    view: DevReviewView,
    *,
    session_key: str = "",
    source: str = "dev_review",
) -> None:
    if view.passed:
        return
    errors = [f for f in view.findings if f.severity == "error"]
    if not errors and not view.findings:
        return
    top = errors[0] if errors else view.findings[0]
    cause = f"{top.rule_id}: {top.message}"[:400]
    try:
        from butler.core.reflection_closure import maybe_persist_reflect_closure

        maybe_persist_reflect_closure(
            trigger="review_fail",
            cause=cause,
            strategy="address_review_findings",
            detail=f"findings={len(view.findings)}",
            session_key=session_key,
            source=source,
        )
    except Exception as exc:
        logger.debug("review closure persist skipped: %s", exc)


def maybe_queue_experience_candidate(
    view: DevReviewView,
    *,
    task_preview: str = "",
    project: str = "",
) -> None:
    """Best-effort coding experience candidate from review findings."""
    if not review_closure_write_enabled() or view.passed:
        return
    errors = [f for f in view.findings if f.severity == "error"]
    if not errors:
        return
    lines = [f"- [{f.rule_id}] {f.message}"[:200] for f in errors[:4]]
    content = "Review findings:\n" + "\n".join(lines)
    try:
        from butler.config import get_butler_home
        from butler.memory.memory_scope import coding_experiences_save_path

        path = coding_experiences_save_path(project=project or None)
        row = {
            "title": f"review:{errors[0].rule_id}",
            "content": content[:800],
            "tags": ["review", errors[0].rule_id],
            "source": "dev_review",
            "task_preview": (task_preview or "")[:200],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        import json

        pending = get_butler_home() / "experiences" / "review_candidates.jsonl"
        pending.parent.mkdir(parents=True, exist_ok=True)
        with pending.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("review experience candidate skipped: %s", exc)


def summarize_review_for_delegate(view: DevReviewView) -> dict[str, Any]:
    return {
        "passed": view.passed,
        "findings_count": len(view.findings),
        "severity_max": max_severity(view.findings),
        "suggestions": list(view.suggestions[:6]),
        "top_findings": [
            {
                "rule_id": f.rule_id,
                "severity": f.severity,
                "file": f.file,
                "message": f.message[:160],
            }
            for f in view.findings[:6]
        ],
    }


def nexus_sprint_review_handoff(category: str = "") -> str:
    if str(category or "").strip() != "nexus-sprint":
        return ""
    return (
        "\n\n## 建议下一步\n"
        "实现完成后请委派审查：`delegate_task role=review category=nexus-micro`，"
        "或运行 workflow `dev-qa-loop`。"
    )
