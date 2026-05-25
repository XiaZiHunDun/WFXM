"""Parse scalar metrics from harness / runtime stdout (METRIC name=value)."""

from __future__ import annotations

import re
from typing import Any

_METRIC_LINE = re.compile(
    r"^(?:METRIC)\s+([a-zA-Z0-9_.-]+)\s*=\s*([^\s#]+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_METRIC_VALUE = re.compile(
    r"^metric_value\s*=\s*([^\s#]+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_METRIC_NAME_HINT = re.compile(
    r"^metric_name\s*=\s*([a-zA-Z0-9_.-]+)\s*$",
    re.MULTILINE | re.IGNORECASE,
)


def _parse_float(raw: str) -> float | None:
    s = str(raw or "").strip().rstrip(",")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_metrics_from_text(text: str) -> list[dict[str, Any]]:
    """Return [{metric_name, metric_value}, ...] in document order."""
    blob = str(text or "")
    if not blob.strip():
        return []

    default_name = ""
    mname = _METRIC_NAME_HINT.search(blob)
    if mname:
        default_name = mname.group(1).strip()

    out: list[dict[str, Any]] = []
    for match in _METRIC_LINE.finditer(blob):
        name = match.group(1).strip()
        val = _parse_float(match.group(2))
        if name and val is not None:
            out.append({"metric_name": name, "metric_value": val})

    if not out:
        for match in _METRIC_VALUE.finditer(blob):
            val = _parse_float(match.group(1))
            if val is not None:
                name = default_name or "metric_value"
                out.append({"metric_name": name, "metric_value": val})
                break

    return out


def primary_metric(
    text: str,
    *,
    default_name: str = "score",
) -> dict[str, Any] | None:
    rows = parse_metrics_from_text(text)
    if rows:
        return rows[0]
    return None


__all__ = ["parse_metrics_from_text", "primary_metric"]
