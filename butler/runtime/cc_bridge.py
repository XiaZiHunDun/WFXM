"""Claude Code CLI bridge — opt-in heavy tasks on gateway host (complements delegate_task)."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from butler.env_parse import env_truthy, int_env

logger = logging.getLogger(__name__)

_JOB_DIR_NAME = "jobs"
_QUEUE_FILE = "cc_bridge_queue.jsonl"


def cc_bridge_enabled() -> bool:
    return bool(env_truthy("BUTLER_CC_BRIDGE", default=False))


def claude_cli_path() -> str | None:
    custom = os.getenv("BUTLER_CC_CLI", "").strip()
    if custom:
        if os.path.isfile(custom):
            return custom
        return shutil.which(custom)
    return shutil.which("claude")


def cc_bridge_timeout_sec() -> int:
    return int(int_env("BUTLER_CC_BRIDGE_TIMEOUT", 900, min=60))


def _jobs_dir() -> Path:
    from butler.config import get_butler_home

    path = get_butler_home() / _JOB_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return cast(Path, path)


def _queue_path() -> Path:
    return _jobs_dir() / _QUEUE_FILE


@dataclass
class CcBridgeJob:
    job_id: str
    session_key: str
    task: str
    workspace: str
    project_name: str = ""
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    exit_code: int | None = None
    summary: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _append_job_record(job: CcBridgeJob) -> None:
    line = json.dumps(job.to_dict(), ensure_ascii=False)
    with _queue_path().open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def list_recent_jobs(session_key: str = "", *, limit: int = 5) -> list[CcBridgeJob]:
    path = _queue_path()
    if not path.is_file():
        return []
    rows: list[CcBridgeJob] = []
    sk = str(session_key or "").strip()
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if sk and str(data.get("session_key") or "") != sk:
                continue
            rows.append(CcBridgeJob(**{k: data[k] for k in CcBridgeJob.__dataclass_fields__ if k in data}))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.debug("cc_bridge list skipped: %s", exc)
        return []
    return rows[-limit:]


def _minimal_child_env() -> dict[str, str]:
    keep = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "SHELL", "TMPDIR")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["BUTLER_CC_BRIDGE_CHILD"] = "1"
    return env


def run_cc_bridge_sync(job: CcBridgeJob) -> CcBridgeJob:
    """Run ``claude -p`` in workspace; mutates and returns job."""
    cli = claude_cli_path()
    if not cli:
        job.status = "failed"
        job.error = "未找到 claude CLI（安装 Claude Code 或设 BUTLER_CC_CLI）"
        job.completed_at = time.time()
        _append_job_record(job)
        return job

    ws = Path(job.workspace)
    if not ws.is_dir():
        job.status = "failed"
        job.error = f"工作区不可用: {job.workspace}"
        job.completed_at = time.time()
        _append_job_record(job)
        return job

    argv = [cli, "-p", job.task]
    job.status = "running"
    _append_job_record(job)

    try:
        proc = subprocess.run(
            argv,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=cc_bridge_timeout_sec(),
            env=_minimal_child_env(),
        )
        job.exit_code = proc.returncode
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        blob = out or err
        job.summary = blob[:4000] if blob else "(无输出)"
        if proc.returncode == 0:
            job.status = "completed"
        else:
            job.status = "failed"
            job.error = (err or out or f"exit {proc.returncode}")[:500]
    except subprocess.TimeoutExpired:
        job.status = "failed"
        job.error = f"超时（>{cc_bridge_timeout_sec()}s）"
    except OSError as exc:
        job.status = "failed"
        job.error = str(exc)[:500]

    job.completed_at = time.time()
    _append_job_record(job)
    return job


def submit_cc_bridge_job(
    *,
    session_key: str,
    task: str,
    workspace: str,
    project_name: str = "",
    run_async: bool = True,
    on_complete: Any | None = None,
) -> CcBridgeJob:
    job = CcBridgeJob(
        job_id=uuid.uuid4().hex[:12],
        session_key=str(session_key or "").strip(),
        task=(task or "").strip(),
        workspace=str(workspace or "").strip(),
        project_name=str(project_name or "").strip(),
    )
    if not job.task:
        job.status = "failed"
        job.error = "任务摘要为空"
        job.completed_at = time.time()
        _append_job_record(job)
        return job

    if not run_async:
        return run_cc_bridge_sync(job)

    def _worker() -> None:
        from butler.runtime.cc_bridge_ops import call_on_complete_safe

        finished = run_cc_bridge_sync(job)
        if on_complete is not None:
            call_on_complete_safe(on_complete, finished)

    threading.Thread(target=_worker, name=f"cc-bridge-{job.job_id}", daemon=True).start()
    job.status = "queued"
    _append_job_record(job)
    return job


def format_cc_bridge_status(*, session_key: str = "") -> str:
    if not cc_bridge_enabled():
        return (
            "CC CLI 桥接：未启用\n"
            "开启：.env 设 BUTLER_CC_BRIDGE=1 并 restart，或\n"
            "  python3 scripts/apply-butler-env-profile.py dev-remote"
        )
    cli = claude_cli_path()
    lines = [
        "CC CLI 桥接（Claude Code）",
        f"  状态：{'就绪' if cli else '未找到 claude 命令'}",
        f"  CLI：{cli or '(PATH 中无 claude，可设 BUTLER_CC_CLI)'}",
        f"  超时：{cc_bridge_timeout_sec()}s",
        "",
        "用法：/cc-bridge <任务摘要>",
        "示例：/cc-bridge 只读检查 tests/ 目录结构并摘要",
        "",
        "与 Butler 委派分工：",
        "  · 常规改码 → 「交给开发代理…」",
        "  · 重 refactor / 长环 → /cc-bridge",
    ]
    recent = list_recent_jobs(session_key, limit=3)
    if recent:
        lines.append("")
        lines.append("最近任务：")
        for row in reversed(recent):
            mark = row.status
            preview = row.task[:60] + ("…" if len(row.task) > 60 else "")
            lines.append(f"  · [{mark}] {preview}")
    return "\n".join(lines)


def format_cc_bridge_result(job: CcBridgeJob) -> str:
    head = "✅ CC 任务完成" if job.status == "completed" else "❌ CC 任务失败"
    lines = [head, f"项目：{job.project_name or '—'}", f"任务：{job.task[:200]}"]
    if job.summary:
        lines.append("")
        lines.append(job.summary[:3500])
    if job.error:
        lines.append("")
        lines.append(f"错误：{job.error[:400]}")
    return "\n".join(lines)


def push_cc_bridge_completion(job: CcBridgeJob) -> bool:
    from butler.runtime.cc_bridge_ops import push_cc_bridge_completion_safe

    return bool(push_cc_bridge_completion_safe(job))


__all__ = [
    "CcBridgeJob",
    "cc_bridge_enabled",
    "cc_bridge_timeout_sec",
    "claude_cli_path",
    "format_cc_bridge_result",
    "format_cc_bridge_status",
    "list_recent_jobs",
    "push_cc_bridge_completion",
    "run_cc_bridge_sync",
    "submit_cc_bridge_job",
]
