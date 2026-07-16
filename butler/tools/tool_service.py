"""Unified tool service — integrates experience, taxonomy, discovery, optimization, and metrics.

This is the main entry point for intelligent tool selection and management.

Usage:
    from butler.tools.tool_service import ToolService
    
    service = ToolService()
    
    # Get tool recommendations
    recommendations = service.recommend_tools("read a python file")
    
    # Execute with optimization
    result, meta = service.execute_tool("read_file", {"path": "test.py"})
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from butler.tools.experience_selector import (
    ExperienceBasedToolSelector,
    ToolRecommendation,
    get_tool_selector,
)
from butler.tools.tool_call_optimizer import ToolCallOptimizer, get_tool_optimizer
from butler.tools.tool_discovery import ToolDiscovery, get_tool_discovery
from butler.tools.tool_metrics import ToolMetrics, get_tool_metrics, ToolCallRecorder
from butler.tools.tool_taxonomy import (
    TOOL_TAXONOMY,
    get_domains_for_tool,
    get_recommended_tools,
    get_tool_info,
)

logger = logging.getLogger(__name__)


class ToolService:
    """Unified tool service combining all tool intelligence features."""
    
    def __init__(self):
        self._selector = get_tool_selector()
        self._discovery = get_tool_discovery()
        self._optimizer = get_tool_optimizer()
        self._metrics = get_tool_metrics()
    
    # ─── Tool Recommendation ───
    
    def recommend_tools(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Get tool recommendations for a query.
        
        Combines experience-based, taxonomy-based, and semantic discovery.
        
        Args:
            query: User query or task description
            top_k: Maximum number of recommendations
            
        Returns:
            List of tool recommendation dicts
        """
        recommendations: dict[str, dict[str, Any]] = {}
        
        # 1. Experience-based selection
        exp_recs = self._selector.select_tools(query, top_k=top_k * 2)
        for rec in exp_recs:
            recommendations[rec.tool_name] = {
                "tool_name": rec.tool_name,
                "score": rec.score,
                "source": rec.source,
                "success_rate": rec.success_rate,
                "domains": get_domains_for_tool(rec.tool_name),
            }
        
        # 2. Semantic discovery
        sem_recs = self._discovery.discover(query, top_k=top_k * 2, threshold=0.25)
        for rec in sem_recs:
            tool_name = rec["tool_name"]
            if tool_name in recommendations:
                # Boost existing recommendation
                recommendations[tool_name]["score"] += rec["similarity"] * 0.3
            else:
                recommendations[tool_name] = {
                    "tool_name": tool_name,
                    "score": rec["similarity"],
                    "source": "semantic",
                    "success_rate": 0,
                    "domains": get_domains_for_tool(tool_name),
                }
        
        # 3. Taxonomy fallback
        tax_tools = get_recommended_tools(query, top_k=top_k)
        for tool_name in tax_tools:
            if tool_name not in recommendations:
                recommendations[tool_name] = {
                    "tool_name": tool_name,
                    "score": 0.2,
                    "source": "taxonomy",
                    "success_rate": 0,
                    "domains": get_domains_for_tool(tool_name),
                }
        
        # Sort and return
        sorted_recs = sorted(
            recommendations.values(),
            key=lambda r: r["score"],
            reverse=True
        )
        return sorted_recs[:top_k]
    
    def recommend_for_domain(self, domain_id: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Get tool recommendations for a specific domain."""
        from butler.tools.tool_taxonomy import get_tools_by_domain
        
        tools = get_tools_by_domain(domain_id)
        return [
            {
                "tool_name": tool,
                "score": 0.5,
                "source": "domain_taxonomy",
                "success_rate": 0,
                "domains": [domain_id],
                **get_tool_info(tool),
            }
            for tool in tools[:top_k]
        ]
    
    # ─── Tool Execution ───
    
    def execute_tool(
        self,
        tool_name: str,
        args: dict[str, Any],
        handler: Callable[[], str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Execute a tool call with optimization and metrics.
        
        Args:
            tool_name: Name of the tool
            args: Tool arguments
            handler: Function to call (if None, looks up in registry)
            
        Returns:
            Tuple of (result, metadata)
        """
        recorder = ToolCallRecorder(self._metrics)
        recorder.start(tool_name)
        
        cache_hit = False
        
        try:
            if self._optimizer.should_cache(tool_name):
                cached = self._optimizer.check_cache(tool_name, args)
                if cached is not None:
                    cache_hit = True
                    recorder.end(success=True, cache_hit=True)
                    return cached, {"cached": True, "duration_ms": 0}
            
            if self._optimizer.should_dedup(tool_name):
                if self._optimizer.check_duplicate(tool_name, args):
                    self._metrics.record_duplicate_block(tool_name)
                    recorder.end(success=False, error_type="DUPLICATE_BLOCKED")
                    return '{"ok": false, "code": "DUPLICATE_BLOCKED"}', {"blocked": True}
            
            if handler is None:
                from butler.tools.registry import dispatch_tool
                result = dispatch_tool(tool_name, args)
            else:
                result = handler()
            
            if self._optimizer.should_cache(tool_name):
                self._optimizer.set_cache(tool_name, args, result)
            
            recorder.end(success=True, cache_hit=False)
            return result, {"cached": False}
        
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            recorder.end(success=False, error_type=type(e).__name__)
            raise
    
    # ─── Statistics & Monitoring ───
    
    def get_stats(self) -> dict[str, Any]:
        """Get comprehensive tool statistics."""
        return {
            "metrics": self._metrics.get_all_stats(),
            "optimizer": self._optimizer.get_stats(),
        }
    
    def get_tool_report(self, tool_name: str) -> dict[str, Any]:
        """Get a detailed report for a specific tool."""
        stats = self._metrics.get_tool_stats(tool_name)
        info = get_tool_info(tool_name)
        similar = self._discovery.get_similar_tools(tool_name, top_k=5)
        
        return {
            **stats,
            **info,
            "similar_tools": similar,
        }
    
    def get_performance_report(self) -> dict[str, Any]:
        """Get a performance summary report."""
        stats = self._metrics.get_all_stats()
        
        return {
            "session_summary": {
                "duration_seconds": stats["session_duration_seconds"],
                "total_calls": stats["total_calls"],
                "success_rate": stats["overall_success_rate"],
                "cache_hit_rate": stats["overall_cache_hit_rate"],
            },
            "top_by_calls": self._metrics.get_top_tools(by="call_count"),
            "slowest": self._metrics.get_slowest_tools(),
            "most_errors": self._metrics.get_error_prone_tools(),
        }
    
    # ─── Learning ───
    
    def record_usage(self, tool_name: str, query: str, success: bool) -> None:
        """Record a tool usage for learning."""
        self._selector.record_tool_usage(tool_name, query, success)
    
    def refresh_discovery(self) -> None:
        """Refresh semantic discovery (after tool changes)."""
        self._discovery.refresh()
    
    def clear_cache(self) -> None:
        """Clear all cached tool results."""
        self._optimizer.clear_cache()


# Singleton
_service: ToolService | None = None


def get_tool_service() -> ToolService:
    """Get the singleton tool service instance."""
    global _service
    if _service is None:
        _service = ToolService()
    return _service


def recommend_tools(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """Convenience function to get tool recommendations."""
    return get_tool_service().recommend_tools(query, top_k)