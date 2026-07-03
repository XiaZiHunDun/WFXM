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
# Extended 2026-06-22: dev phase — 06-23 窗仅 B9 测评证据，延后至小规模真人试用前。
G1_04_WINDOW_START = date(2026, 6, 9)
G1_04_WINDOW_END = date(2026, 7, 31)
G1_04_MIN_FEEDBACK_FOR_CLOSURE = 1

# Triggers written by B9 / offline eval — not WeChat production usage.
G1_04_B9_EVAL_TRIGGERS = frozenset({
    "b9_live_low_pass",
    "wrong_patch_dominant",
})


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


def classify_feedback_evidence(row: dict[str, Any]) -> Literal["b9_eval", "production", "unknown"]:
    """Classify eval_feedback.jsonl row for G1-04 closure (B9 script vs production)."""
    trigger = str(row.get("trigger") or "").strip()
    if trigger in G1_04_B9_EVAL_TRIGGERS or trigger.startswith("b9_"):
        return "b9_eval"
    if trigger:
        return "production"
    return "unknown"


def _read_jsonl_between(
    path: Path,
    *,
    start_ts: float,
    end_ts: float,
) -> dict[str, Any]:
    if not path.is_file():
        return {
            "count": 0,
            "last_ts": None,
            "actions": {},
            "triggers": {},
            "evidence": {"b9_eval": 0, "production": 0, "unknown": 0},
        }
    count = 0
    last_ts: float | None = None
    actions: dict[str, int] = {}
    triggers: dict[str, int] = {}
    evidence: dict[str, int] = {"b9_eval": 0, "production": 0, "unknown": 0}
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
        trig = str(row.get("trigger") or "").strip() or "(none)"
        triggers[trig] = triggers.get(trig, 0) + 1
        kind = classify_feedback_evidence(row)
        evidence[kind] = evidence.get(kind, 0) + 1
    return {
        "count": count,
        "last_ts": last_ts,
        "actions": actions,
        "triggers": triggers,
        "evidence": evidence,
    }


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
    evidence = in_window.get("evidence") or {}
    b9_eval = int(evidence.get("b9_eval") or 0)
    production = int(evidence.get("production") or 0)
    unknown = int(evidence.get("unknown") or 0)
    feedback_in_window = int(in_window.get("count") or 0)
    pipeline_closure_ready = (
        window_complete
        and feedback_in_window >= G1_04_MIN_FEEDBACK_FOR_CLOSURE
    )
    # Strict: ≥1 production-sourced hard feedback (not B9 weekly / offline eval only).
    ot2_closure_ready = pipeline_closure_ready and production >= 1
    feedback_b9_eval_only = (
        feedback_in_window > 0
        and b9_eval == feedback_in_window
    )
    triggers = in_window.get("triggers") or {}
    from butler.ops.owner_feedback import is_owner_explicit_trigger

    feedback_owner_explicit = sum(
        int(n) for trig, n in triggers.items() if is_owner_explicit_trigger(str(trig))
    )
    window_days = (G1_04_WINDOW_END - G1_04_WINDOW_START).days + 1
    days_elapsed = max(0, (day - G1_04_WINDOW_START).days + 1) if day >= G1_04_WINDOW_START else 0
    return {
        "window_start": G1_04_WINDOW_START.isoformat(),
        "window_end": G1_04_WINDOW_END.isoformat(),
        "today": day.isoformat(),
        "window_open": window_open,
        "window_complete": window_complete,
        "window_days": window_days,
        "days_elapsed": min(days_elapsed, window_days),
        "days_remaining": max(0, days_remaining) if window_open else 0,
        "feedback_in_window": feedback_in_window,
        "feedback_count": feedback_in_window,
        "feedback_7d": int(fb_7d.get("count") or 0),
        "feedback_actions_in_window": in_window.get("actions") or {},
        "feedback_triggers_in_window": in_window.get("triggers") or {},
        "feedback_evidence_b9_eval": b9_eval,
        "feedback_evidence_production": production,
        "feedback_evidence_unknown": unknown,
        "feedback_owner_explicit": feedback_owner_explicit,
        "feedback_b9_eval_only": feedback_b9_eval_only,
        "last_feedback_ts": in_window.get("last_ts"),
        "pipeline_closure_ready": pipeline_closure_ready,
        "ot2_closure_ready": ot2_closure_ready,
        "closure_ready": ot2_closure_ready,
        "eval_feedback_path": str(fb_path),
    }


def format_owner_g1_04_brief_lines() -> list[str]:
    """Owner-tier OT2 observation block for /诊断 brief."""
    w = g1_04_observation_window_status()
    lines = ["OT2 观测（G1-04）"]
    if w.get("window_open"):
        lines.append(f"  观测窗剩 {w.get('days_remaining', 0)} 天（至 {w.get('window_end', '?')}）")
    elif w.get("window_complete"):
        lines.append("  观测窗已结束")
    else:
        lines.append("  观测窗未开始")

    total = int(w.get("feedback_in_window") or 0)
    owner_x = int(w.get("feedback_owner_explicit") or 0)
    prod = int(w.get("feedback_evidence_production") or 0)
    b9 = int(w.get("feedback_evidence_b9_eval") or 0)
    auto_prod = max(0, prod - owner_x)
    lines.append(
        f"  窗内 {total} 条：Owner显式 {owner_x} · 自动生产 {auto_prod} · B9 {b9}"
    )

    if w.get("ot2_closure_ready"):
        closure = "可结案（含生产证据）"
    elif w.get("window_complete") and w.get("feedback_b9_eval_only"):
        closure = "仅 B9 证据，勿当 OT2 已证"
    elif w.get("window_complete"):
        closure = "窗满，待复核 eval_feedback"
    elif owner_x < 1:
        closure = "窗未满；建议用 /反馈 记录纠正"
    else:
        closure = "窗未满；已有 Owner 反馈"
    lines.append(f"  结案状态：{closure}")
    return lines


def _g1_04_detail(*, fb_7d: dict[str, Any], window: dict[str, Any]) -> str:
    parts = [
        f"窗 {G1_04_WINDOW_START.strftime('%m-%d')}→{G1_04_WINDOW_END.strftime('%m-%d')}",
    ]
    if window.get("window_open"):
        parts.append(f"剩 {window.get('days_remaining', 0)}d")
    elif window.get("window_complete"):
        parts.append("窗已结束")
    parts.append(f"窗内 {window.get('feedback_in_window', 0)} 条")
    prod = int(window.get("feedback_evidence_production") or 0)
    b9 = int(window.get("feedback_evidence_b9_eval") or 0)
    if b9:
        parts.append(f"B9测评 {b9}")
    if prod:
        parts.append(f"生产 {prod}")
    if window.get("feedback_b9_eval_only"):
        parts.append("仅B9证据")
    if fb_7d.get("count"):
        parts.append(f"最近 {_fmt_age(fb_7d.get('last_ts'))}")
    if window.get("ot2_closure_ready"):
        parts.append("可结案(生产证据)")
    elif window.get("pipeline_closure_ready"):
        parts.append("可管线结案")
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
    from butler.ops.boundary_observability_ops import observe_g1_02_cost_baseline

    out.append(observe_g1_02_cost_baseline())

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
        if g1_window.get("feedback_b9_eval_only") and g1_window.get("feedback_in_window"):
            out.append(BoundaryObservation(
                "G1-04",
                "info",
                f"OT2 窗内 {g1_window.get('feedback_in_window')} 条（仅 B9 测评）",
                _g1_04_detail(fb_7d=fb, window=g1_window),
            ))
        else:
            out.append(BoundaryObservation(
                "G1-04",
                "info",
                "OT2 硬反馈审计暂无" if not g1_window.get("feedback_in_window") else (
                    f"OT2 硬反馈 {g1_window.get('feedback_in_window')} 条/窗"
                ),
                _g1_04_detail(fb_7d=fb, window=g1_window),
            ))
    else:
        if g1_window.get("ot2_closure_ready"):
            summary = "OT2 观测窗已结束（含生产硬反馈）"
            status: BoundaryStatus = "info"
        elif g1_window.get("pipeline_closure_ready"):
            summary = "OT2 窗已结束（仅 B9 测评证据，OT2 未证）"
            status = "warn"
        else:
            summary = "OT2 观测窗已结束但 feedback 不足"
            status = "warn"
        out.append(BoundaryObservation(
            "G1-04",
            status,
            summary,
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
    from butler.ops.boundary_observability_ops import (
        observe_g2_01_pii_rule,
        observe_g2_02_push_queue,
        observe_g2_04_pim_truncation,
        observe_g2_09_mem_benchmark,
    )

    out.append(observe_g2_01_pii_rule())
    out.append(observe_g2_02_push_queue())

    out.append(BoundaryObservation(
        "G2-03",
        "ok",
        "P-PIM live 94%/92% (2026-06-09)",
        "50 条×2 provider ≥85%；ε 为诚实边界，发版前可复跑",
    ))

    out.append(observe_g2_04_pim_truncation())

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
            "CA4 strict=1 pilot 已接",
            "生产 pilot 类别定理违例 → CODING_STRICT_GATE；默认 strict=0 advisory",
        ))
    else:
        out.append(BoundaryObservation(
            "G2-08",
            "ok",
            "CA4 advisory（默认关 strict）",
            "AUTO_VERIFY 软检查已接；strict=1 时 pilot 类别硬阻断可选",
        ))

    out.append(observe_g2_09_mem_benchmark())

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
    "G1_04_B9_EVAL_TRIGGERS",
    "G1_04_MIN_FEEDBACK_FOR_CLOSURE",
    "G1_04_WINDOW_END",
    "G1_04_WINDOW_START",
    "boundary_observability_summary",
    "classify_feedback_evidence",
    "collect_boundary_observations",
    "format_boundary_observability_lines",
    "format_owner_g1_04_brief_lines",
    "g1_04_observation_window_status",
]
