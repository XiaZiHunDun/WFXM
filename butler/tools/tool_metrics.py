"""Tool performance metrics — collection and reporting.

Tracks tool call statistics including:
- Call count and success rate
- Average duration
- Cache hit rate
- Error patterns
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


class ToolMetrics:
    """Collects and reports tool performance metrics."""
    
    def __init__(self):
        self._metrics: dict[str, dict[str, Any]] = defaultdict(self._default_metric)
        self._lock = threading.Lock()
        self._session_start = time.time()
    
    def _default_metric(self) -> dict[str, Any]:
        """Default metric structure for a new tool."""
        return {
            "call_count": 0,
            "success_count": 0,
            "error_count": 0,
            "total_duration_ms": 0,
            "min_duration_ms": float("inf"),
            "max_duration_ms": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "duplicate_blocks": 0,
            "errors": defaultdict(int),  # error_type → count
        }
    
    def record(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool,
        cache_hit: bool = False,
        error_type: str | None = None,
    ) -> None:
        """Record a tool call outcome.
        
        Args:
            tool_name: Name of the tool
            duration_ms: Duration in milliseconds
            success: Whether the call succeeded
            cache_hit: Whether result was from cache
            error_type: Error type if failed
        """
        with self._lock:
            m = self._metrics[tool_name]
            m["call_count"] += 1
            m["total_duration_ms"] += duration_ms
            m["min_duration_ms"] = min(m["min_duration_ms"], duration_ms)
            m["max_duration_ms"] = max(m["max_duration_ms"], duration_ms)
            
            if success:
                m["success_count"] += 1
            else:
                m["error_count"] += 1
                if error_type:
                    m["errors"][error_type] += 1
            
            if cache_hit:
                m["cache_hits"] += 1
            else:
                m["cache_misses"] += 1
    
    def record_duplicate_block(self, tool_name: str) -> None:
        """Record a duplicate call block."""
        with self._lock:
            m = self._metrics[tool_name]
            m["duplicate_blocks"] += 1
    
    def get_tool_stats(self, tool_name: str) -> dict[str, Any]:
        """Get statistics for a specific tool."""
        with self._lock:
            m = self._metrics.get(tool_name)
            if not m:
                return {}
            
            call_count = m["call_count"]
            if call_count == 0:
                return {"tool_name": tool_name, "call_count": 0}
            
            success_rate = m["success_count"] / call_count
            avg_duration = m["total_duration_ms"] / call_count
            cache_total = m["cache_hits"] + m["cache_misses"]
            cache_hit_rate = m["cache_hits"] / cache_total if cache_total > 0 else 0
            
            return {
                "tool_name": tool_name,
                "call_count": call_count,
                "success_count": m["success_count"],
                "error_count": m["error_count"],
                "success_rate": round(success_rate, 4),
                "avg_duration_ms": round(avg_duration, 2),
                "min_duration_ms": round(m["min_duration_ms"], 2) if m["min_duration_ms"] != float("inf") else 0,
                "max_duration_ms": round(m["max_duration_ms"], 2),
                "cache_hits": m["cache_hits"],
                "cache_misses": m["cache_misses"],
                "cache_hit_rate": round(cache_hit_rate, 4),
                "duplicate_blocks": m["duplicate_blocks"],
                "errors": dict(m["errors"]),
            }
    
    def get_all_stats(self) -> dict[str, Any]:
        """Get statistics for all tools."""
        with self._lock:
            tools = {}
            for tool_name in self._metrics:
                tools[tool_name] = self.get_tool_stats(tool_name)
            
            # Overall summary
            total_calls = sum(m["call_count"] for m in self._metrics.values())
            total_success = sum(m["success_count"] for m in self._metrics.values())
            total_errors = sum(m["error_count"] for m in self._metrics.values())
            total_cache_hits = sum(m["cache_hits"] for m in self._metrics.values())
            
            session_duration = time.time() - self._session_start
            
            return {
                "session_duration_seconds": round(session_duration, 2),
                "total_tools": len(self._metrics),
                "total_calls": total_calls,
                "total_success": total_success,
                "total_errors": total_errors,
                "overall_success_rate": round(total_success / total_calls, 4) if total_calls > 0 else 0,
                "total_cache_hits": total_cache_hits,
                "overall_cache_hit_rate": round(total_cache_hits / total_calls, 4) if total_calls > 0 else 0,
                "tools": tools,
            }
    
    def get_top_tools(self, by: str = "call_count", limit: int = 10) -> list[dict[str, Any]]:
        """Get top tools by a metric."""
        with self._lock:
            stats = [(name, self.get_tool_stats(name)) for name in self._metrics]
            stats.sort(key=lambda x: x[1].get(by, 0), reverse=True)
            return [s[1] for s in stats[:limit]]
    
    def get_slowest_tools(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get slowest tools by average duration."""
        with self._lock:
            stats = [(name, self.get_tool_stats(name)) for name in self._metrics]
            stats.sort(key=lambda x: x[1].get("avg_duration_ms", 0), reverse=True)
            return [s[1] for s in stats[:limit]]
    
    def get_error_prone_tools(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get tools with most errors."""
        with self._lock:
            stats = [(name, self.get_tool_stats(name)) for name in self._metrics]
            stats.sort(key=lambda x: x[1].get("error_count", 0), reverse=True)
            return [s[1] for s in stats[:limit]]
    
    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._metrics.clear()
            self._session_start = time.time()


class ToolCallRecorder:
    """Records tool calls with timing."""
    
    def __init__(self, metrics: ToolMetrics | None = None):
        self._metrics = metrics or get_tool_metrics()
        self._start_time: float | None = None
        self._tool_name: str | None = None
    
    def start(self, tool_name: str) -> None:
        """Start recording a tool call."""
        self._tool_name = tool_name
        self._start_time = time.time()
    
    def end(
        self,
        success: bool = True,
        cache_hit: bool = False,
        error_type: str | None = None,
    ) -> None:
        """End recording and submit metrics."""
        if self._start_time is None or self._tool_name is None:
            return
        
        duration_ms = (time.time() - self._start_time) * 1000
        self._metrics.record(
            self._tool_name,
            duration_ms,
            success,
            cache_hit,
            error_type,
        )
        
        self._start_time = None
        self._tool_name = None


# Singleton
_metrics: ToolMetrics | None = None


def get_tool_metrics() -> ToolMetrics:
    """Get the singleton metrics instance."""
    global _metrics
    if _metrics is None:
        _metrics = ToolMetrics()
    return _metrics


def record_tool_call(
    tool_name: str,
    duration_ms: float,
    success: bool,
    cache_hit: bool = False,
    error_type: str | None = None,
) -> None:
    """Convenience function to record a tool call."""
    get_tool_metrics().record(tool_name, duration_ms, success, cache_hit, error_type)