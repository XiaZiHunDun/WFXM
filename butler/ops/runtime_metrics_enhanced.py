"""Runtime metrics enhancements.

Provides additional metrics for observability:
1. Tool execution metrics (latency, success/fail, cache hits)
2. Memory operation metrics (recall, write, index)
3. Session lifecycle metrics
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_metrics_registry: Dict[str, Any] = defaultdict(lambda: {"count": 0, "sum": 0.0, "min": float("inf"), "max": 0.0})


def increment_counter(name: str, value: int = 1) -> None:
    """Increment a counter metric."""
    entry = _metrics_registry[name]
    entry["count"] += value


def record_value(name: str, value: float) -> None:
    """Record a value for histogram/summary metrics."""
    entry = _metrics_registry[name]
    entry["count"] += 1
    entry["sum"] += value
    entry["min"] = min(entry["min"], value)
    entry["max"] = max(entry["max"], value)


def record_latency(name: str, start_time: float) -> float:
    """Record latency in milliseconds. Returns the latency."""
    latency_ms = (time.time() - start_time) * 1000
    record_value(name, latency_ms)
    return latency_ms


def get_metric(name: str) -> Dict[str, Any]:
    """Get metric value."""
    entry = _metrics_registry.get(name, {"count": 0, "sum": 0.0, "min": 0.0, "max": 0.0})
    result = dict(entry)
    if result["count"] > 0:
        result["avg"] = result["sum"] / result["count"]
    else:
        result["avg"] = 0.0
    return result


def get_all_metrics() -> Dict[str, Dict[str, Any]]:
    """Get all metrics."""
    return {name: get_metric(name) for name in _metrics_registry}


def reset_metrics() -> None:
    """Reset all metrics."""
    _metrics_registry.clear()


@dataclass
class ToolExecutionMetrics:
    """Metrics for tool execution."""

    tool_name: str
    call_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    cache_hit_count: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        return self.success_count / max(1, self.call_count)

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hit_count / max(1, self.call_count)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency_ms / max(1, self.call_count)


_tool_metrics: Dict[str, ToolExecutionMetrics] = {}


def record_tool_call(
    tool_name: str,
    success: bool,
    latency_ms: float,
    cache_hit: bool = False,
) -> None:
    """Record a tool call."""
    increment_counter("tool.calls.total")
    if success:
        increment_counter("tool.calls.success")
    else:
        increment_counter("tool.calls.fail")
    if cache_hit:
        increment_counter("tool.calls.cache_hit")

    if tool_name not in _tool_metrics:
        _tool_metrics[tool_name] = ToolExecutionMetrics(tool_name=tool_name)

    m = _tool_metrics[tool_name]
    m.call_count += 1
    if success:
        m.success_count += 1
    else:
        m.fail_count += 1
    if cache_hit:
        m.cache_hit_count += 1
    m.total_latency_ms += latency_ms


def get_tool_metrics(tool_name: str) -> Optional[ToolExecutionMetrics]:
    """Get metrics for a specific tool."""
    return _tool_metrics.get(tool_name)


def get_all_tool_metrics() -> Dict[str, ToolExecutionMetrics]:
    """Get metrics for all tools."""
    return dict(_tool_metrics)


@dataclass
class MemoryOperationMetrics:
    """Metrics for memory operations."""

    recall_count: int = 0
    recall_hit_count: int = 0
    write_count: int = 0
    index_count: int = 0
    total_latency_ms: float = 0.0

    @property
    def recall_hit_rate(self) -> float:
        return self.recall_hit_count / max(1, self.recall_count)


_memory_metrics = MemoryOperationMetrics()


def record_memory_recall(hit: bool, latency_ms: float) -> None:
    """Record a memory recall operation."""
    _memory_metrics.recall_count += 1
    if hit:
        _memory_metrics.recall_hit_count += 1
    _memory_metrics.total_latency_ms += latency_ms
    increment_counter("memory.recall")
    if hit:
        increment_counter("memory.recall_hit")


def record_memory_write(latency_ms: float) -> None:
    """Record a memory write operation."""
    _memory_metrics.write_count += 1
    _memory_metrics.total_latency_ms += latency_ms
    increment_counter("memory.write")


def get_memory_metrics() -> MemoryOperationMetrics:
    """Get memory operation metrics."""
    return _memory_metrics


def get_metrics_summary() -> Dict[str, Any]:
    """Get a summary of all metrics."""
    return {
        "tools": {
            name: {
                "call_count": m.call_count,
                "success_rate": round(m.success_rate, 3),
                "cache_hit_rate": round(m.cache_hit_rate, 3),
                "avg_latency_ms": round(m.avg_latency_ms, 1),
            }
            for name, m in get_all_tool_metrics().items()
        },
        "memory": {
            "recall_count": _memory_metrics.recall_count,
            "recall_hit_rate": round(_memory_metrics.recall_hit_rate, 3),
            "write_count": _memory_metrics.write_count,
        },
        "counters": {k: v["count"] for k, v in get_all_metrics().items() if v["count"] > 0},
    }


__all__ = [
    "increment_counter",
    "record_value",
    "record_latency",
    "get_metric",
    "get_all_metrics",
    "reset_metrics",
    "ToolExecutionMetrics",
    "record_tool_call",
    "get_tool_metrics",
    "get_all_tool_metrics",
    "MemoryOperationMetrics",
    "record_memory_recall",
    "record_memory_write",
    "get_memory_metrics",
    "get_metrics_summary",
]