"""Cross-dimension assistant health — memory vs dev vs wechat (phase 4)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "memory_pass_rate": ("memory_benchmark.pass_rate",),
    "dev_pass_rate": ("dev_benchmark.pass_rate",),
    "b9_pass_rate": ("llm_benchmark.pass_rate",),
    "wechat_pass_rate": ("corpus.wechat_gateway.pass_rate", "corpus.wechat.pass_rate"),
    "tool_selection": ("tool_selection", "eval.tool_selection"),
    "delegate_routing": ("delegate_routing", "eval.delegate_routing"),
    "intent_accuracy": ("intent_accuracy", "eval.intent_accuracy"),
}


@dataclass
class AssistantHealthReport:
    lookback_hours: float = 168.0
    metrics: dict[str, float] = field(default_factory=dict)
    tensions: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        return {
            "lookback_hours": self.lookback_hours,
            "metrics": self.metrics,
            "tensions": self.tensions,
            "recommendations": self.recommendations,
            "sources": self.sources,
            "timestamp": self.timestamp,
        }


def _avg_scores_by_name(scores: list[Any]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for s in scores:
        name = getattr(s, "name", "")
        if not name:
            continue
        buckets.setdefault(name, []).append(float(getattr(s, "value", 0.0)))
    return {k: sum(v) / len(v) for k, v in buckets.items() if v}


def _pick_metric(averages: dict[str, float], key: str) -> float | None:
    for alias in _METRIC_ALIASES.get(key, (key,)):
        if alias in averages:
            return averages[alias]
    return None


def _read_audit_metric(path: Path, *fields: str) -> float | None:
    if not path.is_file():
        return None
    last: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    if not last:
        return None
    for field_name in fields:
        if field_name in last and last[field_name] is not None:
            try:
                return float(last[field_name])
            except (TypeError, ValueError):
                continue
    return None


def detect_health_tensions(metrics: dict[str, float]) -> tuple[list[str], list[str]]:
    tensions: list[str] = []
    recs: list[str] = []

    mem = metrics.get("memory_pass_rate")
    dev = metrics.get("dev_pass_rate")
    if mem is not None and dev is not None:
        if mem >= 0.7 and dev < 0.7:
            tensions.append("memory_ok_dev_low")
            recs.append("记忆召回正常但开发能力偏弱：查 delegate/B9/SWE 与 coding knowledge")
        if dev >= 0.85 and mem < 0.6:
            tensions.append("dev_ok_memory_low")
            recs.append("开发基准正常但记忆偏弱：查 MB 基准与 half-life/向量检索")

    routing = metrics.get("delegate_routing")
    if routing is None:
        routing = metrics.get("tool_selection")
    if routing is not None and routing < 0.6:
        tensions.append("delegate_routing_low")
        recs.append(
            "工具路由偏低：检查是否该 delegate 却用 terminal/write_file；"
            "跑 bash scripts/butler-eval-wechat-corpus.sh"
        )

    wechat = metrics.get("wechat_pass_rate")
    if wechat is not None and wechat < 0.9:
        tensions.append("wechat_corpus_low")
        recs.append("微信语料回归偏低：查 utterance_catalog 失败项并同步 Dataset")

    b9 = metrics.get("b9_pass_rate")
    if b9 is not None and b9 < 1.0:
        tensions.append("b9_not_perfect")
        recs.append("B9 未满分：bash scripts/butler-eval-llm-benchmark.sh（可开 LIVE）")

    if not tensions:
        recs.append("各维度无显著张力；保持周常 regression + corpus 推送")

    return tensions, recs


def collect_assistant_health(
    *,
    lookback_hours: float = 168.0,
) -> AssistantHealthReport:
    """Aggregate LangFuse scores + local audit for a unified health view."""
    report = AssistantHealthReport(lookback_hours=lookback_hours)

    try:
        from butler.ops.eval_feedback import read_recent_scores

        averages = _avg_scores_by_name(read_recent_scores(lookback_hours=lookback_hours))
        report.sources["langfuse"] = f"{len(averages)} metric names"
        for key in _METRIC_ALIASES:
            val = _pick_metric(averages, key)
            if val is not None:
                report.metrics[key] = round(val, 4)
    except Exception as exc:
        logger.debug("assistant health langfuse read skipped: %s", exc)

    try:
        from butler.config import get_butler_home
        from butler.ops.eval_diagnostics import regression_audit_path

        audit = get_butler_home() / "audit"
        if "dev_pass_rate" not in report.metrics:
            last = _read_audit_jsonl(regression_audit_path())
            if last:
                dev = float(last.get("dev_pass_rate") or 0.0)
                mem = float(last.get("mem_pass_rate") or 0.0)
                report.metrics.setdefault("dev_pass_rate", round(dev, 4))
                report.metrics.setdefault("memory_pass_rate", round(mem, 4))
                report.sources["regression_audit"] = str(regression_audit_path())
        corp = _read_audit_metric(audit / "wechat_corpus_eval.jsonl", "pass_rate")
        if corp is not None:
            report.metrics.setdefault("wechat_pass_rate", round(corp, 4))
            report.sources["wechat_corpus_audit"] = str(audit / "wechat_corpus_eval.jsonl")
    except Exception as exc:
        logger.debug("assistant health audit read skipped: %s", exc)

    report.tensions, report.recommendations = detect_health_tensions(report.metrics)
    return report


def _read_audit_jsonl(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    last = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue
    return last


def format_assistant_health_lines(report: AssistantHealthReport | None = None) -> list[str]:
    report = report or collect_assistant_health()
    lines = [f"助手全局健康 (近 {int(report.lookback_hours)}h):"]

    def _line(label: str, key: str) -> None:
        val = report.metrics.get(key)
        if val is not None:
            lines.append(f"  {label}: {val:.0%}")

    _line("记忆 MB", "memory_pass_rate")
    _line("开发 B", "dev_pass_rate")
    _line("B9 委派", "b9_pass_rate")
    _line("微信语料", "wechat_pass_rate")
    _line("工具路由", "delegate_routing")
    if report.metrics.get("tool_selection") is not None and "delegate_routing" not in report.metrics:
        _line("工具选择", "tool_selection")

    if report.tensions:
        lines.append(f"  张力: {', '.join(report.tensions)}")
        for rec in report.recommendations[:3]:
            lines.append(f"  → {rec}")
    else:
        lines.append("  张力: (无)")
    return lines


def push_assistant_health_scores(report: AssistantHealthReport) -> dict[str, Any]:
    from butler.ops.eval_bridge import EvalScore, push_scores

    scores: list[EvalScore] = []
    for key, val in report.metrics.items():
        scores.append(EvalScore(
            name=f"assistant_health.{key}",
            value=float(val),
            comment=f"tension={','.join(report.tensions) or 'none'}",
            category="assistant_health",
            metadata={"lookback_hours": report.lookback_hours},
        ))
    if report.tensions:
        scores.append(EvalScore(
            name="assistant_health.tension_count",
            value=float(len(report.tensions)),
            comment=",".join(report.tensions),
            category="assistant_health",
        ))
    push_report = push_scores(scores)
    return {"scores_pushed": push_report.scores_pushed, "tensions": report.tensions}


__all__ = [
    "AssistantHealthReport",
    "collect_assistant_health",
    "detect_health_tensions",
    "format_assistant_health_lines",
    "push_assistant_health_scores",
]
