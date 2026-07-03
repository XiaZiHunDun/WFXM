"""Experience selection telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def experience_task_affinity_safe(
    experience_id: str,
    *,
    inferred_task_id: str = "",
) -> bool | None:
    eid = str(experience_id or "").strip()
    tid = str(inferred_task_id or "").strip()
    if not eid or not tid:
        return None

    def _run() -> bool:
        from butler.dev_engine.prod_delegate_bridge import experience_task_affinity

        return bool(experience_task_affinity(eid, inferred_task_id=tid))

    result = safe_best_effort(
        _run,
        label="experience_telemetry.task_affinity",
        default=None,
    )
    if result is None:
        return None
    return bool(result)


def infer_b9_task_id_safe(preview: str) -> str:
    def _run() -> str:
        from butler.dev_engine.prod_delegate_bridge import infer_b9_task_id

        return str(infer_b9_task_id(preview) or "")

    result = safe_best_effort(
        _run,
        label="experience_telemetry.infer_task_id",
        default="",
    )
    return str(result or "")


def record_experience_lifecycle_safe(
    *,
    experience_id: str,
    action: str,
    success: bool,
    session_key: str = "",
    task_preview: str = "",
    role: str = "dev",
) -> None:
    def _run() -> None:
        from butler.ops.experience_selection_telemetry import record_experience_lifecycle

        record_experience_lifecycle(
            experience_id=experience_id,
            action=action,
            success=success,
            session_key=session_key,
            task_preview=task_preview,
            role=role,
        )

    safe_best_effort(_run, label="experience_telemetry.lifecycle", default=None)
