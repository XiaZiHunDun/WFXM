"""Owner surface best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def pending_delegate_line_safe(session_key: str) -> str:
    def _run() -> str:
        from butler.runtime.task_store import list_recent_tasks

        for row in list_recent_tasks(session_key, limit=5):
            status = str(row.get("status") or "")
            if status not in ("running", "pending", "queued"):
                continue
            role = str(row.get("role") or "dev")
            tid = str(row.get("task_id") or "")[:12]
            preview = str(row.get("task_preview") or row.get("task") or "")[:40]
            tail = f" {preview}…" if preview else ""
            return f"委派进行中：{role} ({tid}){tail} → /任务 /详细"
        return ""

    result = safe_best_effort(_run, label="owner_surface.pending_delegate", default="")
    return result if isinstance(result, str) else ""


def project_todos_brief_safe(ws: Path) -> str | None:
    def _run() -> str | None:
        from butler.ops.butler_inbox_ops import project_todos_info_safe

        open_n, samples = project_todos_info_safe(ws)
        if open_n:
            sample = samples[0] if samples else ""
            extra = f"（例：{sample}）" if sample else ""
            return f"· 项目待办 {open_n} 项{extra} → /项目待办"
        return "· 项目待办：无未完成项"

    return safe_best_effort(_run, label="owner_surface.project_todos", default=None)


def outbound_brief_line_safe(*, session_key: str = "", chat_id: str = "") -> str | None:
    def _run() -> str | None:
        from butler.gateway.completion_telemetry import (
            completion_push_stats,
            push_queue_pending_count,
        )
        from butler.gateway.durable_outbox import outbox_counts
        from butler.gateway.owner_surface import _health_icon

        key = str(chat_id or session_key or "").strip()
        counts = outbox_counts(chat_id=key)
        pending_outbox = int(counts.get("pending") or 0)
        failed_outbox = int(counts.get("failed") or 0)
        pending_queue = push_queue_pending_count(chat_id=key)
        stats = completion_push_stats(key)
        failed_push = int(stats.get("failed") or 0)
        if failed_outbox > 0:
            return (
                f"出站：{_health_icon(False)} "
                f"有 {failed_outbox} 条发送失败 → 运维见 wechat-gateway-ops · /诊断 详细"
            )
        if pending_outbox > 3 or pending_queue > 3:
            total = max(pending_outbox, pending_queue)
            return (
                f"出站：{_health_icon(False, warn=True)} "
                f"待发约 {total} 条 → 稍候或 /诊断 详细"
            )
        if failed_push > 0:
            return (
                f"出站：{_health_icon(False, warn=True)} "
                f"本轮推送失败 {failed_push} 次 → /诊断 详细"
            )
        return None

    return safe_best_effort(_run, label="owner_surface.outbound", default=None)


def degradation_brief_line_safe(
    orchestrator: Any,
    *,
    session_key: str = "",
    health: dict | None = None,
) -> str | None:
    def _run() -> str | None:
        from butler.gateway.owner_surface import _health_icon
        from butler.ops.degradation_registry import refresh_degradations_for_owner_brief

        body = refresh_degradations_for_owner_brief(
            orchestrator,
            session_key=str(session_key or "").strip(),
            health=health,
        )
        if not body:
            return None
        return body.replace("降级：", f"降级：{_health_icon(False, warn=True)} ", 1)

    return safe_best_effort(_run, label="owner_surface.degradation", default=None)


def runtime_jobs_lines_safe(workspace: Path) -> list[str]:
    def _run() -> list[str]:
        import yaml

        jobs_path = workspace / "runtime" / "jobs.yaml"
        if not jobs_path.is_file():
            return []
        data = yaml.safe_load(jobs_path.read_text(encoding="utf-8")) or {}
        jobs = data.get("jobs") or []
        if not isinstance(jobs, list):
            return []
        enabled = [j for j in jobs if isinstance(j, dict) and j.get("enabled", True)]
        if not enabled:
            return ["· 定时任务：均已关闭"]
        names = [str(j.get("id") or j.get("description") or "?")[:40] for j in enabled[:4]]
        extra = len(enabled) - len(names)
        tail = f" 等 {len(enabled)} 个" if extra > 0 else f" {len(enabled)} 个"
        return [f"· 定时任务{tail}：{', '.join(names)}"]

    result = safe_best_effort(_run, label="owner_surface.runtime_jobs", default=[])
    return result if isinstance(result, list) else []
