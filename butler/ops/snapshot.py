"""Lightweight ops snapshot (no Prometheus) for /诊断."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
import logging


logger = logging.getLogger(__name__)

def _workspace_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _gateway_log_path() -> Path:
    return _workspace_root() / "logs" / "butler-gateway.log"


def _runtime_log_path() -> Path:
    return _workspace_root() / "logs" / "butler-runtime.log"


def _file_stats(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False}
    st = path.stat()
    age_h = round((time.time() - st.st_mtime) / 3600, 1)
    return {
        "exists": True,
        "size_mb": round(st.st_size / (1024 * 1024), 2),
        "age_hours": age_h,
    }


def _systemd_timer_rows(pattern: str) -> list[str]:
    try:
        proc = subprocess.run(
            [
                "systemctl",
                "--user",
                "list-timers",
                pattern,
                "--no-pager",
                "--no-legend",
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return lines[:5]


def _recent_runtime_failures(limit: int = 5) -> list[dict[str, Any]]:
    root = get_butler_home() / "runtime" / "runs"
    if not root.is_dir():
        return []
    rows: list[tuple[float, dict[str, Any]]] = []
    for path in root.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("success") is not False:
            continue
        rows.append((path.stat().st_mtime, data))
    rows.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for _, data in rows[:limit]:
        out.append(
            {
                "project": data.get("project"),
                "job_id": data.get("job_id"),
                "finished_at": data.get("finished_at"),
            }
        )
    return out


def collect_ops_snapshot() -> dict[str, Any]:
    """Aggregate local ops signals (read-only)."""
    env_flags = {
        "runtime_enabled": os.getenv("BUTLER_RUNTIME_ENABLED", "1"),
        "runtime_push": os.getenv("BUTLER_RUNTIME_PUSH", "1"),
        "semantic_memory": os.getenv("BUTLER_SEMANTIC_MEMORY", "0"),
        "queue_prefetch": os.getenv("BUTLER_QUEUE_PREFETCH", "0"),
        "wechat_dev_smoke": os.getenv("BUTLER_WECHAT_DEV_SMOKE", "0"),
        "terminal": os.getenv("BUTLER_ENABLE_TERMINAL", "0"),
        "git": os.getenv("BUTLER_ENABLE_GIT", "0"),
        "git_write": os.getenv("BUTLER_ENABLE_GIT_WRITE", "0"),
    }
    failure_streaks: list[dict[str, Any]] = []
    try:
        from butler.runtime.failure_tracker import list_active_streaks

        failure_streaks = list_active_streaks()
    except Exception as exc:
        logger.debug("collect ops snapshot skipped: %s", exc)
    return {
        "gateway_log": _file_stats(_gateway_log_path()),
        "runtime_log": _file_stats(_runtime_log_path()),
        "timers": _systemd_timer_rows("butler-*"),
        "recent_runtime_failures": _recent_runtime_failures(),
        "failure_streaks": failure_streaks,
        "env": env_flags,
    }


def format_ops_diagnostic_lines() -> list[str]:
    snap = collect_ops_snapshot()
    lines = ["运维快照:"]
    gw = snap.get("gateway_log") or {}
    if gw.get("exists"):
        lines.append(
            f"  网关日志: {gw.get('size_mb')} MB, "
            f"最近修改 {gw.get('age_hours')}h 前"
        )
    else:
        lines.append("  网关日志: (无文件)")
    rt = snap.get("runtime_log") or {}
    if rt.get("exists"):
        lines.append(
            f"  runtime 日志: {rt.get('size_mb')} MB, "
            f"最近修改 {rt.get('age_hours')}h 前"
        )
    timers = snap.get("timers") or []
    if timers:
        lines.append(f"  systemd timer: {len(timers)} 条活跃")
        for t in timers[:3]:
            lines.append(f"    {t}")
    fails = snap.get("recent_runtime_failures") or []
    if fails:
        lines.append(f"  近期 runtime 失败: {len(fails)} 条")
        for f in fails[:3]:
            lines.append(
                f"    {f.get('project')}/{f.get('job_id')} @ {f.get('finished_at')}"
            )
    streaks = snap.get("failure_streaks") or []
    if streaks:
        lines.append(f"  连续失败跟踪: {len(streaks)} 项")
        for s in streaks[:3]:
            lines.append(
                f"    {s.get('project')}/{s.get('job_id')}: {s.get('streak')} 次"
            )
    env = snap.get("env") or {}
    lines.append(
        "  能力开关: "
        f"runtime={env.get('runtime_enabled')} "
        f"push={env.get('runtime_push')} "
        f"语义记忆={env.get('semantic_memory')} "
        f"prefetch={env.get('queue_prefetch')}"
    )
    lines.append(
        "  开发工具(网关): "
        f"terminal={env.get('terminal')} "
        f"git={env.get('git')} "
        f"git_write={env.get('git_write')} "
        f"dev_smoke={env.get('wechat_dev_smoke')}"
    )
    return lines
