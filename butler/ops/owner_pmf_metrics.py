"""Owner PMF metrics (PROD-P4-08) — opt-in product signals vs OT2 engineering."""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PENDING_FEEDBACK_FILE = "owner_pmf_pending_feedback.json"


def owner_pmf_metrics_enabled() -> bool:
    from butler.env_parse import env_truthy

    return env_truthy("BUTLER_OWNER_PMF_METRICS", default=False)


def _metrics_dir() -> Path:
    from butler.config import get_butler_home

    d = get_butler_home() / "metrics"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _jsonl_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m")
    return _metrics_dir() / f"owner_pmf_{stamp}.jsonl"


def _pending_feedback_path() -> Path:
    return _metrics_dir() / _PENDING_FEEDBACK_FILE


def append_pmf_event(
    event: str,
    *,
    session_key: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    if not owner_pmf_metrics_enabled():
        return
    row: dict[str, Any] = {
        "ts": time.time(),
        "event": str(event or "").strip(),
        "session_key": str(session_key or "").strip()[:120],
    }
    if payload:
        row.update(payload)
    path = _jsonl_path()
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("owner pmf append skipped: %s", exc)


def record_brief_view(*, session_key: str = "") -> None:
    append_pmf_event("brief", session_key=session_key)


def record_owner_feedback_pmf(*, session_key: str = "", trigger: str = "") -> None:
    append_pmf_event(
        "feedback",
        session_key=session_key,
        payload={"trigger": str(trigger or "").strip()},
    )
    _mark_feedback_pending(session_key)


def record_acceptance_card(
    report: Any,
    *,
    session_key: str = "",
) -> None:
    meta = dict((getattr(report, "structured_output", None) or {}).get("acceptance") or {})
    append_pmf_event(
        "acceptance_card",
        session_key=session_key,
        payload={
            "task_id": str(getattr(report, "task_id", "") or ""),
            "success": bool(getattr(report, "success", False)),
            "verify_passed": meta.get("verify_passed"),
            "test_configured": meta.get("test_configured"),
            "change_count": meta.get("change_count"),
        },
    )


def maybe_record_post_feedback_retry(user_text: str, *, session_key: str = "") -> None:
    """Count user retry in same session after Owner hard feedback."""
    if not owner_pmf_metrics_enabled():
        return
    sk = str(session_key or "").strip()
    if not sk:
        return
    pending = _load_pending_feedback()
    row = pending.get(sk)
    if not row:
        return
    if time.time() - float(row.get("ts") or 0) > 3600:
        pending.pop(sk, None)
        _save_pending_feedback(pending)
        return
    text = str(user_text or "").strip()
    if not text or text.startswith("/反馈"):
        return
    retry = False
    if text.startswith("/改"):
        retry = True
    else:
        from butler.ops.owner_pmf_metrics_ops import owner_edit_slash_expanded_safe

        if owner_edit_slash_expanded_safe(text):
            retry = True
    if not retry and any(k in text for k in ("交给开发", "委派开发", "delegate")):
        retry = True
    if not retry:
        return
    append_pmf_event(
        "feedback_retry",
        session_key=sk,
        payload={"after_trigger": str(row.get("trigger") or "")},
    )
    pending.pop(sk, None)
    _save_pending_feedback(pending)


def _mark_feedback_pending(session_key: str) -> None:
    sk = str(session_key or "").strip()
    if not sk:
        return
    pending = _load_pending_feedback()
    pending[sk] = {"ts": time.time()}
    _save_pending_feedback(pending)


def _load_pending_feedback() -> dict[str, dict[str, Any]]:
    path = _pending_feedback_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_pending_feedback(data: dict[str, dict[str, Any]]) -> None:
    path = _pending_feedback_path()
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    except OSError as exc:
        logger.debug("owner pmf pending feedback save skipped: %s", exc)


def _read_events(*, days: int = 7) -> list[dict[str, Any]]:
    if days <= 0:
        days = 7
    cutoff = time.time() - days * 86400
    out: list[dict[str, Any]] = []
    metrics = _metrics_dir()
    if not metrics.is_dir():
        return out
    for path in sorted(metrics.glob("owner_pmf_*.jsonl")):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if float(row.get("ts") or 0) >= cutoff:
                    out.append(row)
        except (OSError, json.JSONDecodeError):
            continue
    return out


def summarize_owner_pmf(*, days: int = 7) -> dict[str, Any]:
    """Aggregate PMF signals for weekly report."""
    events = _read_events(days=days)
    brief_days: set[str] = set()
    feedback_count = 0
    retry_count = 0
    acceptance_total = 0
    acceptance_verify_ok = 0
    acceptance_verify_fail = 0
    acceptance_unconfigured = 0

    for row in events:
        ev = str(row.get("event") or "")
        ts = float(row.get("ts") or 0)
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        if ev == "brief":
            brief_days.add(day)
        elif ev == "feedback":
            feedback_count += 1
        elif ev == "feedback_retry":
            retry_count += 1
        elif ev == "acceptance_card":
            acceptance_total += 1
            vp = row.get("verify_passed")
            if row.get("test_configured") is False:
                acceptance_unconfigured += 1
            elif vp is True:
                acceptance_verify_ok += 1
            elif vp is False:
                acceptance_verify_fail += 1

    retry_rate = (
        round(retry_count / feedback_count, 3) if feedback_count else None
    )
    verify_denom = acceptance_verify_ok + acceptance_verify_fail
    verify_pass_rate = (
        round(acceptance_verify_ok / verify_denom, 3) if verify_denom else None
    )

    return {
        "days": days,
        "event_count": len(events),
        "brief_days": len(brief_days),
        "brief_day_list": sorted(brief_days),
        "feedback_count": feedback_count,
        "feedback_retry_count": retry_count,
        "feedback_retry_rate": retry_rate,
        "acceptance_card_total": acceptance_total,
        "acceptance_verify_ok": acceptance_verify_ok,
        "acceptance_verify_fail": acceptance_verify_fail,
        "acceptance_unconfigured": acceptance_unconfigured,
        "acceptance_verify_pass_rate": verify_pass_rate,
        "enabled": owner_pmf_metrics_enabled(),
        "jsonl": str(_jsonl_path()),
    }


def format_owner_pmf_report(*, days: int = 7) -> str:
    s = summarize_owner_pmf(days=days)
    lines = [
        f"Owner PMF 周报（近 {s['days']} 天）",
        f"采集：{'开' if s['enabled'] else '关（设 BUTLER_OWNER_PMF_METRICS=1）'}",
        "",
        f"· /简报 活跃天数：{s['brief_days']}（{', '.join(s['brief_day_list'][-7:]) or '—'}）",
        f"· 验收卡：{s['acceptance_card_total']} 次"
        f"（测试✅ {s['acceptance_verify_ok']} · ❌ {s['acceptance_verify_fail']}"
        f" · 未配置 {s['acceptance_unconfigured']}）",
    ]
    if s["acceptance_verify_pass_rate"] is not None:
        lines.append(f"  验收通过率（已配置测试）：{s['acceptance_verify_pass_rate']:.0%}")
    lines.extend(
        [
            f"· /反馈：{s['feedback_count']} 次",
            f"· 反馈后同会话重试：{s['feedback_retry_count']} 次",
        ]
    )
    if s["feedback_retry_rate"] is not None:
        lines.append(f"  重试率：{s['feedback_retry_rate']:.0%}")
    lines.append("")
    lines.append(f"原始：{s['jsonl']}")
    return "\n".join(lines)


__all__ = [
    "append_pmf_event",
    "format_owner_pmf_report",
    "maybe_record_post_feedback_retry",
    "owner_pmf_metrics_enabled",
    "record_acceptance_card",
    "record_brief_view",
    "record_owner_feedback_pmf",
    "summarize_owner_pmf",
]
