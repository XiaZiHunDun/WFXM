"""Eval quality snapshot for /诊断 and ``butler doctor`` (G1-05 / O7 / O9)."""

from __future__ import annotations

from butler.env_parse import float_env
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _butler_audit_dir() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit"


def regression_audit_path() -> Path:
    return _butler_audit_dir() / "eval_regression.jsonl"


def b9_audit_path() -> Path:
    return _butler_audit_dir() / "b9_benchmark.jsonl"


def _read_latest_jsonl(path: Path) -> dict[str, Any] | None:
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
    return last


def _fmt_ts(ts: float | int | None) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return "—"


def b9_report_to_audit_record(report: Any) -> dict[str, Any]:
    """Serialize a B9Report (or summary dict) for audit jsonl."""
    if isinstance(report, dict):
        return {**report, "ts": report.get("ts", time.time())}
    return {
        "ts": time.time(),
        "mode": getattr(report, "mode", "oracle"),
        "passed": getattr(report, "passed", 0),
        "total": getattr(report, "total", 0),
        "pass_rate": round(getattr(report, "pass_rate", 0.0), 4),
        "results": [
            r.to_dict() if hasattr(r, "to_dict") else dict(r)
            for r in getattr(report, "results", [])
        ],
    }


def append_b9_audit(report: Any) -> Path:
    path = b9_audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = b9_report_to_audit_record(report)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _min_b9_pass_rate() -> float:
    try:
        return float_env("BUTLER_EVAL_B9_PASS_RATE_MIN", 1.0)
    except ValueError:
        return 1.0


def b9_in_regression_enabled() -> bool:
    return os.getenv("BUTLER_EVAL_B9_IN_REGRESSION", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


@dataclass
class EvalQualitySnapshot:
    regression: dict[str, Any] | None = None
    b9: dict[str, Any] | None = None

    @property
    def regression_ok(self) -> bool | None:
        if not self.regression:
            return None
        return bool(self.regression.get("passed"))

    @property
    def b9_ok(self) -> bool | None:
        if not self.b9:
            return None
        rate = float(self.b9.get("pass_rate") or 0.0)
        return rate >= _min_b9_pass_rate()


def collect_eval_quality_snapshot() -> EvalQualitySnapshot:
    reg = _read_latest_jsonl(regression_audit_path())
    b9 = _read_latest_jsonl(b9_audit_path())
    if b9 is None and reg:
        # Regression gate may embed B9 in the same record.
        if reg.get("b9_total") is not None:
            b9 = {
                "ts": reg.get("ts"),
                "mode": reg.get("b9_mode", "oracle"),
                "passed": reg.get("b9_passed", 0),
                "total": reg.get("b9_total", 0),
                "pass_rate": reg.get("b9_pass_rate", 0.0),
            }
    return EvalQualitySnapshot(regression=reg, b9=b9)


def format_eval_quality_lines() -> list[str]:
    """Lines for /诊断 and doctor — last Dev/Mem/B9 benchmark snapshot."""
    snap = collect_eval_quality_snapshot()
    lines = ["开发质量 (O7/O9):"]

    reg = snap.regression
    if reg:
        dev_rate = float(reg.get("dev_pass_rate") or 0.0)
        mem_rate = float(reg.get("mem_pass_rate") or 0.0)
        gate = "通过" if reg.get("passed") else "未通过"
        lines.append(
            f"  Dev B1–B8: {reg.get('dev', '?')} ({dev_rate:.0%}) · {_fmt_ts(reg.get('ts'))}"
        )
        lines.append(
            f"  Mem MB1–MB7: {reg.get('mem', '?')} ({mem_rate:.0%})"
        )
        lines.append(f"  发版回归门: {gate}")
    else:
        lines.append("  Dev/Mem: (未记录)")
        lines.append("  提示: bash scripts/butler-eval-regression.sh")

    b9 = snap.b9
    if b9:
        rate = float(b9.get("pass_rate") or 0.0)
        mode = b9.get("mode", "oracle")
        ok = snap.b9_ok
        flag = "✓" if ok else "⚠"
        lines.append(
            f"  B9 delegate: {flag} {b9.get('passed', 0)}/{b9.get('total', 0)} "
            f"({rate:.0%}, {mode}) · {_fmt_ts(b9.get('ts'))}"
        )
        if ok is False:
            lines.append(
                f"  B9 阈值: < {_min_b9_pass_rate():.0%} "
                f"(BUTLER_EVAL_B9_PASS_RATE_MIN)"
            )
    else:
        lines.append("  B9 delegate: (未记录)")
        lines.append("  提示: bash scripts/butler-eval-llm-benchmark.sh")

    live = os.getenv("BUTLER_EVAL_LLM_BENCHMARK", "0").strip() in ("1", "true", "yes")
    lines.append(
        f"  B9 模式: {'live LLM' if live else 'oracle (CI/默认)'}"
    )
    return lines


__all__ = [
    "EvalQualitySnapshot",
    "append_b9_audit",
    "b9_audit_path",
    "b9_in_regression_enabled",
    "b9_report_to_audit_record",
    "collect_eval_quality_snapshot",
    "format_eval_quality_lines",
    "regression_audit_path",
]
