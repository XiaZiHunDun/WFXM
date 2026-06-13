"""G1/G2 gap register — read-only boundary observability for /诊断 and ops scripts."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

BoundaryStatus = Literal["ok", "warn", "info", "manual", "deferred"]

# G1-04 OT2 passive observation window (pilot-log §G1, gap register 2026-06-09).
G1_04_WINDOW_START = date(2026, 6, 9)
G1_04_WINDOW_END = date(2026, 6, 23)
G1_04_MIN_FEEDBACK_FOR_CLOSURE = 1


@dataclass
class BoundaryObservation:
    gap_id: str
    status: BoundaryStatus
    summary: str
    detail: str = ""

    def line(self, *, verbose: bool = False) -> str:
        icon = {
            "ok": "✓",
            "warn": "⚠",
            "info": "·",
            "manual": "☐",
            "deferred": "⏸",
        }.get(self.status, "·")
        text = f"  {icon} {self.gap_id}: {self.summary}"
        if verbose and self.detail:
            text += f" — {self.detail}"
        return text


def _read_jsonl_stats(path: Path, *, since_seconds: float | None = None) -> dict[str, Any]:
    if not path.is_file():
        return {"count": 0, "last_ts": None}
    count = 0
    last_ts: float | None = None
    cutoff = time.time() - since_seconds if since_seconds else None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = row.get("ts")
        try:
            ts_f = float(ts) if ts is not None else None
        except (TypeError, ValueError):
            ts_f = None
        if cutoff is not None and ts_f is not None and ts_f < cutoff:
            continue
        count += 1
        if ts_f is not None:
            last_ts = ts_f if last_ts is None else max(last_ts, ts_f)
    return {"count": count, "last_ts": last_ts}


def _window_epoch_bounds() -> tuple[float, float]:
    start = datetime(
        G1_04_WINDOW_START.year,
        G1_04_WINDOW_START.month,
        G1_04_WINDOW_START.day,
        tzinfo=timezone.utc,
    ).timestamp()
    end = datetime(
        G1_04_WINDOW_END.year,
        G1_04_WINDOW_END.month,
        G1_04_WINDOW_END.day,
        23,
        59,
        59,
        tzinfo=timezone.utc,
    ).timestamp()
    return start, end


def _read_jsonl_between(
    path: Path,
    *,
    start_ts: float,
    end_ts: float,
) -> dict[str, Any]:
    if not path.is_file():
        return {"count": 0, "last_ts": None, "actions": {}}
    count = 0
    last_ts: float | None = None
    actions: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = row.get("ts")
        try:
            ts_f = float(ts) if ts is not None else None
        except (TypeError, ValueError):
            ts_f = None
        if ts_f is None or ts_f < start_ts or ts_f > end_ts:
            continue
        count += 1
        last_ts = ts_f if last_ts is None else max(last_ts, ts_f)
        act = str(row.get("action") or "unknown")
        actions[act] = actions.get(act, 0) + 1
    return {"count": count, "last_ts": last_ts, "actions": actions}


def g1_04_observation_window_status(
    *,
    butler_home: Path | str | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """G1-04 OT2 window progress for ops scripts and /诊断."""
    from butler.config import get_butler_home

    home = Path(butler_home or get_butler_home()).expanduser().resolve()
    day = today or date.today()
    days_remaining = (G1_04_WINDOW_END - day).days
    window_open = G1_04_WINDOW_START <= day <= G1_04_WINDOW_END
    window_complete = day > G1_04_WINDOW_END
    start_ts, end_ts = _window_epoch_bounds()
    fb_path = home / "audit" / "eval_feedback.jsonl"
    in_window = _read_jsonl_between(fb_path, start_ts=start_ts, end_ts=end_ts)
    fb_7d = _read_jsonl_stats(fb_path, since_seconds=7 * 86400)
    closure_ready = (
        window_complete
        and int(in_window.get("count") or 0) >= G1_04_MIN_FEEDBACK_FOR_CLOSURE
    )
    return {
        "window_start": G1_04_WINDOW_START.isoformat(),
        "window_end": G1_04_WINDOW_END.isoformat(),
        "today": day.isoformat(),
        "window_open": window_open,
        "window_complete": window_complete,
        "days_remaining": max(0, days_remaining) if window_open else 0,
        "feedback_in_window": int(in_window.get("count") or 0),
        "feedback_7d": int(fb_7d.get("count") or 0),
        "feedback_actions_in_window": in_window.get("actions") or {},
        "last_feedback_ts": in_window.get("last_ts"),
        "closure_ready": closure_ready,
        "eval_feedback_path": str(fb_path),
    }


def _g1_04_detail(*, fb_7d: dict[str, Any], window: dict[str, Any]) -> str:
    parts = [
        f"窗 {G1_04_WINDOW_START.strftime('%m-%d')}→{G1_04_WINDOW_END.strftime('%m-%d')}",
    ]
    if window.get("window_open"):
        parts.append(f"剩 {window.get('days_remaining', 0)}d")
    elif window.get("window_complete"):
        parts.append("窗已结束")
    parts.append(f"窗内 {window.get('feedback_in_window', 0)} 条")
    if fb_7d.get("count"):
        parts.append(f"最近 {_fmt_age(fb_7d.get('last_ts'))}")
    if window.get("closure_ready"):
        parts.append("可结案")
    return " · ".join(parts)


def _fmt_age(ts: float | None) -> str:
    if ts is None:
        return "无记录"
    age_h = (time.time() - ts) / 3600.0
    if age_h < 1:
        return f"{int(age_h * 60)} 分钟前"
    if age_h < 48:
        return f"{age_h:.1f} 小时前"
    return f"{age_h / 24:.1f} 天前"


def collect_boundary_observations() -> list[BoundaryObservation]:
    """Snapshot signals for open G1/G2 backlog items (no live LLM)."""
    from butler.config import get_butler_home

    home = get_butler_home()
    out: list[BoundaryObservation] = []

    # ── G1 ──
    try:
        from butler.ops.cost_calibration import load_baseline

        baseline = load_baseline()
        if baseline:
            note = str(baseline.get("period_note") or "")[:40]
            out.append(BoundaryObservation(
                "G1-02",
                "ok",
                f"成本基线已设 ({note or '有 actual_usd'})",
                "butler cost report 可看偏差",
            ))
        else:
            out.append(BoundaryObservation(
                "G1-02",
                "warn",
                "成本基线未设",
                "butler cost set-baseline",
            ))
    except Exception as exc:
        out.append(BoundaryObservation("G1-02", "info", f"成本基线: 不可用 ({exc})"))

    fb_path = home / "audit" / "eval_feedback.jsonl"
    fb = _read_jsonl_stats(fb_path, since_seconds=7 * 86400)
    g1_window = g1_04_observation_window_status(butler_home=home)
    if fb["count"]:
        out.append(BoundaryObservation(
            "G1-04",
            "ok",
            f"OT2 硬反馈审计 {fb['count']} 条/7d",
            _g1_04_detail(fb_7d=fb, window=g1_window),
        ))
    elif g1_window.get("window_open"):
        out.append(BoundaryObservation(
            "G1-04",
            "info",
            "OT2 硬反馈审计暂无",
            _g1_04_detail(fb_7d=fb, window=g1_window),
        ))
    else:
        out.append(BoundaryObservation(
            "G1-04",
            "warn" if not g1_window.get("closure_ready") else "info",
            "OT2 观测窗已结束但证据不足" if not g1_window.get("closure_ready") else "OT2 观测窗已结束",
            _g1_04_detail(fb_7d=fb, window=g1_window),
        ))

    out.append(BoundaryObservation(
        "G1-06",
        "ok",
        "入站媒体真机已验",
        "M-img/M-voice 2026-06-10 pilot-log",
    ))
    out.append(BoundaryObservation(
        "G1-08",
        "deferred",
        "新书态探针已搁置",
        "灵文试点；开新书时再验 dual-playbook",
    ))

    # ── G2 ──
    try:
        from butler.core.compaction_prompt import PII_EXCLUSION_RULE

        active = "PRIVACY" in PII_EXCLUSION_RULE
        out.append(BoundaryObservation(
            "G2-01",
            "ok" if active else "warn",
            "压缩 PII_EXCLUSION_RULE 已注入" if active else "PII 规则缺失",
            "边界已接受；pii_clearable 已接",
        ))
    except Exception as exc:
        out.append(BoundaryObservation("G2-01", "info", f"PII 缓解: ({exc})"))

    try:
        from butler.runtime import push_queue
        from butler.runtime.notify import rate_limit_drain_wait_seconds

        pending = push_queue.count_pending_pushes()
        wait_s = rate_limit_drain_wait_seconds()
        if pending and wait_s > 0:
            out.append(BoundaryObservation(
                "G2-02",
                "deferred",
                f"推送队列 {pending} 条 · 限流冷却 ~{wait_s:.0f}s",
                "冷却后 drain-push",
            ))
        elif pending:
            out.append(BoundaryObservation(
                "G2-02",
                "info",
                f"推送队列 {pending} 条待送达",
                "drain-push 或 push-drain.timer（缓解已验 2026-06-10）",
            ))
        else:
            out.append(BoundaryObservation("G2-02", "ok", "推送队列空"))
    except Exception as exc:
        out.append(BoundaryObservation("G2-02", "info", f"推送队列: ({exc})"))

    out.append(BoundaryObservation(
        "G2-03",
        "ok",
        "P-PIM live 94%/92% (2026-06-09)",
        "50 条×2 provider ≥85%；ε 为诚实边界，发版前可复跑",
    ))

    try:
        from butler.tools import pim_schema as ps

        out.append(BoundaryObservation(
            "G2-04",
            "ok",
            "PIM 字段截断",
            f"边界已接受 memo≤{ps.MAX_MEMO_CONTENT_LEN} reminder≤{ps.MAX_REMINDER_MESSAGE_LEN}",
        ))
    except Exception as exc:
        out.append(BoundaryObservation("G2-04", "info", f"PIM 截断: ({exc})"))

    out.append(BoundaryObservation(
        "G2-05",
        "ok",
        "TenantStore 单文件 atomic_write",
        "边界已接受；崩溃窗口为诚实边界",
    ))

    provider = os.getenv("BUTLER_EMBEDDING_PROVIDER", "local")
    semantic = os.getenv("BUTLER_SEMANTIC_MEMORY", "0").strip() in ("1", "true", "yes")
    out.append(BoundaryObservation(
        "G2-06",
        "ok" if semantic else "warn",
        f"嵌入 provider={provider} semantic={int(semantic)}",
        "边界已接受；Recall@3: butler doctor",
    ))

    lf = os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in ("1", "true", "yes")
    hf = os.getenv("BUTLER_EVAL_HARD_FEEDBACK", "1").strip() in ("1", "true", "yes")
    out.append(BoundaryObservation(
        "G2-07",
        "ok",
        f"LangFuse={'开' if lf else '关'} · 硬反馈={'开' if hf else '关'}",
        "边界已接受；无 LangFuse 时读本地 audit",
    ))

    strict = os.getenv("BUTLER_CODING_STRICT", "0").strip() in ("1", "true", "yes")
    if strict:
        out.append(BoundaryObservation(
            "G2-08",
            "warn",
            "CA4 strict env=1（生产未接线）",
            "与默认相同：AUTO_VERIFY 软检查；硬阻断待理论分析 G2-08",
        ))
    else:
        out.append(BoundaryObservation(
            "G2-08",
            "ok",
            "CA4 advisory（默认关 strict）",
            "AUTO_VERIFY 软检查已接；硬阻断未实现，登记册保持现状",
        ))

    try:
        from butler.ops.eval_diagnostics import collect_eval_quality_snapshot

        snap = collect_eval_quality_snapshot()
        mem_rate = None
        if snap.regression:
            mem_rate = float(snap.regression.get("mem_pass_rate") or 0.0)
        if mem_rate is not None:
            ok = mem_rate >= 0.7
            out.append(BoundaryObservation(
                "G2-09",
                "ok" if ok else "warn",
                f"Mem 基准 {mem_rate:.0%}",
                "边界已接受；写后索引 MB1 见 memory_benchmark",
            ))
        else:
            out.append(BoundaryObservation(
                "G2-09",
                "info",
                "Mem 基准未记录",
                "butler-eval-regression.sh",
            ))
    except Exception as exc:
        out.append(BoundaryObservation("G2-09", "info", f"Mem 基准: ({exc})"))

    return out


def format_boundary_observability_lines(*, verbose: bool = False) -> list[str]:
    obs = collect_boundary_observations()
    if not obs:
        return []
    lines = ["诚实边界观测 (G1/G2):"]
    # WeChat /诊断: show warns/deferred/manual first, then ok (capped)
    priority = [o for o in obs if o.status in ("warn", "deferred", "manual")]
    rest = [o for o in obs if o.status not in ("warn", "deferred", "manual")]
    shown = priority + rest[: max(0, 10 - len(priority))]
    for o in shown:
        lines.append(o.line(verbose=verbose))
    hidden = len(obs) - len(shown)
    if hidden > 0:
        lines.append(f"  … 另有 {hidden} 项 (butler-gap-observability.sh)")
    return lines


def boundary_observability_summary() -> dict[str, Any]:
    obs = collect_boundary_observations()
    return {
        "total": len(obs),
        "warn": sum(1 for o in obs if o.status == "warn"),
        "deferred": sum(1 for o in obs if o.status == "deferred"),
        "manual": sum(1 for o in obs if o.status == "manual"),
        "g1_04_window": g1_04_observation_window_status(),
        "items": [
            {"id": o.gap_id, "status": o.status, "summary": o.summary, "detail": o.detail}
            for o in obs
        ],
    }


__all__ = [
    "BoundaryObservation",
    "G1_04_MIN_FEEDBACK_FOR_CLOSURE",
    "G1_04_WINDOW_END",
    "G1_04_WINDOW_START",
    "boundary_observability_summary",
    "collect_boundary_observations",
    "format_boundary_observability_lines",
    "g1_04_observation_window_status",
]
