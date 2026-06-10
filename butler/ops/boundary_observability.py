"""G1/G2 gap register — read-only boundary observability for /诊断 and ops scripts."""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

BoundaryStatus = Literal["ok", "warn", "info", "manual", "deferred"]


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
    if fb["count"]:
        out.append(BoundaryObservation(
            "G1-04",
            "ok",
            f"OT2 硬反馈审计 {fb['count']} 条/7d",
            f"最近 {_fmt_age(fb['last_ts'])}",
        ))
    else:
        out.append(BoundaryObservation(
            "G1-04",
            "info",
            "OT2 硬反馈审计暂无",
            "生产运行后观测 eval_feedback.jsonl",
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
        "items": [
            {"id": o.gap_id, "status": o.status, "summary": o.summary, "detail": o.detail}
            for o in obs
        ],
    }


__all__ = [
    "BoundaryObservation",
    "boundary_observability_summary",
    "collect_boundary_observations",
    "format_boundary_observability_lines",
]
