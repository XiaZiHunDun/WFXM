"""Sink expectations and weak-consistency rules for ``butler eval sync``."""

from __future__ import annotations

from typing import Any

# required=True → missing sink yields warning; langfuse never required by default
SINK_EXPECTATIONS: dict[str, dict[str, bool]] = {
    "tcr": {"audit": True, "junit": True},
    "agent_weekly": {"audit": True},
    "capability": {"audit": True},
    "regression": {"audit": True},
    "wechat_corpus": {"audit": True},
    "memory_mb": {"audit": True},
    "b9_oracle": {"audit": True},
    "deepeval_agent": {"audit": True, "deepeval": True},
    "ragas_memory": {"audit": True, "ragas": True},
}


def _ok_from_row(row: dict[str, Any] | None) -> bool | None:
    if row is None:
        return None
    if "ok" in row:
        return bool(row["ok"])
    metrics = row.get("metrics")
    if isinstance(metrics, dict) and "ok" in metrics:
        return bool(metrics["ok"])
    return None


def evaluate_sync(suite_id: str, sink_rows: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    """Return sync report with ``ok``, ``warnings``, per-sink detail."""
    expectations = SINK_EXPECTATIONS.get(suite_id, {"audit": True})
    warnings: list[str] = []
    sinks_out: dict[str, Any] = {}

    for backend_id, row in sink_rows.items():
        present = row is not None
        ok_val = _ok_from_row(row)
        sinks_out[backend_id] = {
            "present": present,
            "ok": ok_val,
            "ts": row.get("ts") if row else None,
        }

    for backend_id, required in expectations.items():
        row = sink_rows.get(backend_id)
        if required and row is None:
            warnings.append(f"missing required sink: {backend_id}")

    ok_values = [v["ok"] for v in sinks_out.values() if v.get("present") and v.get("ok") is not None]
    if len(ok_values) >= 2 and len(set(ok_values)) > 1:
        warnings.append("sink ok status mismatch across backends")

    audit_ok = sinks_out.get("audit", {}).get("ok")
    junit_ok = sinks_out.get("junit", {}).get("ok")
    if audit_ok is not None and junit_ok is not None and audit_ok != junit_ok:
        warnings.append("audit vs junit ok mismatch")

    return {
        "suite_id": suite_id,
        "ok": len(warnings) == 0,
        "warnings": warnings,
        "sinks": sinks_out,
        "expectations": expectations,
    }
