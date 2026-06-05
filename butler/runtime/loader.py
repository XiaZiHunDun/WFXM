"""Load projects/*/runtime/jobs.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from butler.io.safe_load import (
    quarantine_corrupt_file,
    record_state_file_corruption,
)
from butler.runtime.schema import ApprovalConfig, JobDef, JobsFile, NotifyConfig

logger = logging.getLogger(__name__)


def _jobs_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / "runtime" / "jobs.yaml"


def load_jobs_file(workspace: Path) -> JobsFile | None:
    path = _jobs_path(workspace)
    if not path.is_file():
        return None
    # Audit R2-19: corrupt jobs.yaml used to silently fall back to no
    # jobs. We do the parse inline (rather than going through
    # safe_load_yaml) so we can preserve the original "empty file →
    # JobsFile(jobs=[])" contract via ``or {}`` while still routing
    # corruption through the forensic + diagnostics pipeline via
    # quarantine_corrupt_file / record_state_file_corruption.
    try:
        text = path.read_text(encoding="utf-8")
        raw = yaml.safe_load(text) or {}
    except (OSError, yaml.YAMLError) as exc:
        backup = quarantine_corrupt_file(path)
        logger.warning(
            "Corrupt jobs.yaml %s, renamed to %s: %s",
            path, backup or "<rename-failed>", exc,
            exc_info=exc,
        )
        record_state_file_corruption("runtime_jobs", path, str(exc), backup)
        return None
    if not isinstance(raw, dict):
        return None

    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    jobs_raw = raw.get("jobs") or []
    jobs: list[JobDef] = []
    for item in jobs_raw:
        if not isinstance(item, dict):
            continue
        jid = str(item.get("id") or "").strip()
        if not jid:
            continue
        notify_raw = item.get("notify") if isinstance(item.get("notify"), dict) else {}
        appr_raw = item.get("approval") if isinstance(item.get("approval"), dict) else {}
        cmd = item.get("command") or []
        if isinstance(cmd, str):
            cmd = [cmd]
        cmd_list = [str(c) for c in cmd if str(c).strip()]
        jobs.append(
            JobDef(
                id=jid,
                description=str(item.get("description") or ""),
                mode=str(item.get("mode") or "readonly"),
                enabled=bool(item.get("enabled", True)),
                schedule=str(item.get("schedule") or "").strip(),
                command=cmd_list,
                handler=str(item.get("handler") or "").strip(),
                timeout_seconds=int(
                    item.get("timeout_seconds")
                    or defaults.get("timeout_seconds")
                    or 900
                ),
                notify=NotifyConfig(
                    on_success=bool(notify_raw.get("on_success", True)),
                    on_failure=bool(notify_raw.get("on_failure", True)),
                    max_summary_chars=int(
                        notify_raw.get("max_summary_chars")
                        or defaults.get("max_summary_chars")
                        or 1200
                    ),
                ),
                approval=ApprovalConfig(
                    required=bool(appr_raw.get("required", True)),
                    expires_hours=int(appr_raw.get("expires_hours") or 48),
                ),
            )
        )
    return JobsFile(
        version=int(raw.get("version") or 1),
        project=str(raw.get("project") or ""),
        defaults=defaults,
        jobs=jobs,
    )


def find_job(workspace: Path, job_id: str) -> JobDef | None:
    jf = load_jobs_file(workspace)
    if jf is None:
        return None
    key = (job_id or "").strip()
    for job in jf.jobs:
        if job.id == key:
            return job
    return None


def list_jobs(workspace: Path, *, enabled_only: bool = False) -> list[JobDef]:
    jf = load_jobs_file(workspace)
    if jf is None:
        return []
    jobs = jf.jobs
    if enabled_only:
        jobs = [j for j in jobs if j.enabled]
    return jobs
