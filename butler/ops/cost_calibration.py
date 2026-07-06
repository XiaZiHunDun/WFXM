"""D4 cost model numerical calibration — persist, rollup, baseline compare.

Observation only (P-COST): does not gate scheduling or limits.
"""

from __future__ import annotations

from butler.env_parse import int_env, float_env
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


def calibration_persist_enabled() -> bool:
    return os.getenv("BUTLER_COST_CALIBRATION_PERSIST", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def default_period_days() -> int:
    try:
        return cast(int, int_env("BUTLER_COST_CALIBRATION_DAYS", 7, min=1))
    except ValueError:
        return 7


def usd_cny_rate() -> float:
    try:
        return cast(float, float_env("BUTLER_COST_USD_CNY_RATE", 7.2))
    except ValueError:
        return 7.2


def _metrics_dir() -> Path:
    from butler.config import get_butler_home

    d = get_butler_home() / "metrics"
    d.mkdir(parents=True, exist_ok=True)
    return cast(Path, d)


def events_path_for(day: date | None = None) -> Path:
    day = day or date.today()
    return _metrics_dir() / f"cost_events_{day.isoformat()}.jsonl"


def baseline_path() -> Path:
    return _metrics_dir() / "cost_baseline.json"


def append_cost_event(event: dict[str, Any]) -> None:
    """Append one cost observation event (best-effort)."""
    if not calibration_persist_enabled():
        return
    row = dict(event)
    row.setdefault("ts", time.time())
    path = events_path_for()
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.debug("cost event append skipped: %s", exc)


def record_llm_cost_event(
    *,
    input_tokens: int,
    output_tokens: int,
    model: str = "",
    session_key: str = "",
) -> None:
    from butler.ops.token_cost_diagnostics import _estimate_cost_usd

    est = _estimate_cost_usd(input_tokens, output_tokens, model=model)
    append_cost_event({
        "kind": "llm",
        "session_key": session_key,
        "input_tokens": max(0, input_tokens),
        "output_tokens": max(0, output_tokens),
        "model": model,
        "estimated_usd": est,
    })


def record_tool_cost_event(*, tool_name: str, bucket: str, session_key: str = "") -> None:
    append_cost_event({
        "kind": "tool",
        "session_key": session_key,
        "tool": tool_name,
        "bucket": bucket,
    })


@dataclass
class CostRollup:
    days: int = 7
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_usd: float = 0.0
    tool_calls_pim: int = 0
    tool_calls_dev: int = 0
    tool_calls_pm: int = 0
    tool_calls_other: int = 0
    delegate_spawns: int = 0
    event_lines: int = 0
    models: dict[str, list[int]] = field(default_factory=dict)

    @property
    def total_tool_calls(self) -> int:
        return (
            self.tool_calls_pim
            + self.tool_calls_dev
            + self.tool_calls_pm
            + self.tool_calls_other
        )

    def bucket_shares(self) -> dict[str, float]:
        total = self.total_tool_calls
        if total <= 0:
            return {"pim": 0.0, "dev": 0.0, "pm": 0.0, "other": 0.0}
        return {
            "pim": self.tool_calls_pim / total,
            "dev": self.tool_calls_dev / total,
            "pm": self.tool_calls_pm / total,
            "other": self.tool_calls_other / total,
        }

    def to_dict(self) -> dict[str, Any]:
        shares = self.bucket_shares()
        return {
            "days": self.days,
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_usd": round(self.estimated_usd, 4),
            "estimated_cny": round(self.estimated_usd * usd_cny_rate(), 2),
            "tool_calls": {
                "pim": self.tool_calls_pim,
                "dev": self.tool_calls_dev,
                "pm": self.tool_calls_pm,
                "other": self.tool_calls_other,
                "delegate": self.delegate_spawns,
                "total": self.total_tool_calls,
            },
            "bucket_share": {k: round(v, 4) for k, v in shares.items()},
            "event_lines": self.event_lines,
            "models": self.models,
        }


def rollup_period(days: int | None = None) -> CostRollup:
    """Aggregate cost events for the last N days."""
    days = days or default_period_days()
    rollup = CostRollup(days=days)
    start = date.today() - timedelta(days=days - 1)
    for offset in range(days):
        day = start + timedelta(days=offset)
        path = events_path_for(day)
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    _merge_event(rollup, row)
        except OSError as exc:
            logger.debug("rollup read skipped %s: %s", path, exc)
    return rollup


def _merge_event(rollup: CostRollup, row: dict[str, Any]) -> None:
    rollup.event_lines += 1
    kind = str(row.get("kind") or "")
    if kind == "llm":
        rollup.llm_calls += 1
        pin = int(row.get("input_tokens") or 0)
        pout = int(row.get("output_tokens") or 0)
        rollup.input_tokens += pin
        rollup.output_tokens += pout
        est = row.get("estimated_usd")
        if est is not None:
            rollup.estimated_usd += float(est)
        else:
            from butler.ops.token_cost_diagnostics import _estimate_cost_usd

            e = _estimate_cost_usd(pin, pout, model=str(row.get("model") or ""))
            if e is not None:
                rollup.estimated_usd += e
        model = str(row.get("model") or "")
        if model:
            if model not in rollup.models:
                rollup.models[model] = [0, 0]
            rollup.models[model][0] += pin
            rollup.models[model][1] += pout
    elif kind == "tool":
        bucket = str(row.get("bucket") or "other")
        tool = str(row.get("tool") or "")
        if bucket == "pim":
            rollup.tool_calls_pim += 1
        elif bucket == "dev":
            rollup.tool_calls_dev += 1
            if tool == "delegate_task":
                rollup.delegate_spawns += 1
        elif bucket == "pm":
            rollup.tool_calls_pm += 1
        else:
            rollup.tool_calls_other += 1


def load_baseline() -> dict[str, Any]:
    path = baseline_path()
    if not path.is_file():
        return {}
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("load baseline skipped: %s", exc)
        return {}


def save_baseline(data: dict[str, Any]) -> Path:
    path = baseline_path()
    data.setdefault("updated_at", datetime.now().isoformat(timespec="seconds"))
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def compare_to_baseline(rollup: CostRollup, baseline: dict[str, Any]) -> dict[str, Any]:
    """Compute deviation between Butler estimates and user-recorded bill."""
    if not baseline:
        return {"has_baseline": False}

    actual_usd = baseline.get("actual_usd")
    actual_in = int(baseline.get("actual_input_tokens") or 0)
    actual_out = int(baseline.get("actual_output_tokens") or 0)

    out: dict[str, Any] = {
        "has_baseline": True,
        "period_note": baseline.get("period_note", ""),
        "butler_estimated_usd": round(rollup.estimated_usd, 4),
        "actual_usd": actual_usd,
        "butler_input_tokens": rollup.input_tokens,
        "butler_output_tokens": rollup.output_tokens,
        "actual_input_tokens": actual_in,
        "actual_output_tokens": actual_out,
    }

    if actual_usd is not None and float(actual_usd) > 0:
        est = rollup.estimated_usd
        out["usd_deviation_pct"] = round((est - float(actual_usd)) / float(actual_usd) * 100, 1)
    if actual_in > 0:
        out["input_token_deviation_pct"] = round(
            (rollup.input_tokens - actual_in) / actual_in * 100, 1
        )
    if actual_out > 0:
        out["output_token_deviation_pct"] = round(
            (rollup.output_tokens - actual_out) / actual_out * 100, 1
        )
    return out


def format_rollup_lines(rollup: CostRollup | None = None, *, days: int | None = None) -> list[str]:
    rollup = rollup or rollup_period(days)
    if rollup.event_lines == 0 and rollup.llm_calls == 0:
        return []
    shares = rollup.bucket_shares()
    lines = [
        f"成本标定 ({rollup.days} 日汇总):",
        f"  LLM: {rollup.llm_calls} 次 · in={rollup.input_tokens:,} out={rollup.output_tokens:,}",
        f"  预估: ~${rollup.estimated_usd:.4f} (~¥{rollup.estimated_usd * usd_cny_rate():.2f})",
        (
            f"  工具: PIM {rollup.tool_calls_pim} ({shares['pim']:.0%}) · "
            f"Dev {rollup.tool_calls_dev} ({shares['dev']:.0%}) · "
            f"PM {rollup.tool_calls_pm} ({shares['pm']:.0%}) · "
            f"其他 {rollup.tool_calls_other}"
        ),
        f"  委派: {rollup.delegate_spawns} 次",
    ]
    cmp_ = compare_to_baseline(rollup, load_baseline())
    if cmp_.get("has_baseline"):
        lines.append("  账单对照:")
        if "usd_deviation_pct" in cmp_:
            lines.append(
                f"    USD 偏差: {cmp_['usd_deviation_pct']:+.1f}%"
                f" (Butler ${cmp_['butler_estimated_usd']:.4f} vs 账单 ${cmp_['actual_usd']})"
            )
        if "input_token_deviation_pct" in cmp_:
            lines.append(
                f"    输入 token 偏差: {cmp_['input_token_deviation_pct']:+.1f}%"
            )
        if "output_token_deviation_pct" in cmp_:
            lines.append(
                f"    输出 token 偏差: {cmp_['output_token_deviation_pct']:+.1f}%"
            )
        note = str(cmp_.get("period_note") or "").strip()
        if note:
            lines.append(f"    备注: {note[:120]}")
    else:
        lines.append("  账单对照: 未设基线 (butler cost set-baseline)")
    return lines


def format_cost_with_calibration(session_key: str) -> str:
    from butler.ops.cost_tracker import format_cost_summary

    parts = [format_cost_summary(session_key)]
    cal_lines = format_rollup_lines()
    if cal_lines:
        parts.append("")
        parts.extend(cal_lines)
    return "\n".join(parts)


__all__ = [
    "CostRollup",
    "append_cost_event",
    "calibration_persist_enabled",
    "compare_to_baseline",
    "format_cost_with_calibration",
    "format_rollup_lines",
    "load_baseline",
    "record_llm_cost_event",
    "record_tool_cost_event",
    "rollup_period",
    "save_baseline",
]
