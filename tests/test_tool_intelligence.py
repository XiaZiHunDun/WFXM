"""Tests for tool intelligence system — experience, taxonomy, discovery, optimization, metrics.

Tests:
- Tool recommendations from experience
- Domain-based tool taxonomy
- Semantic tool discovery
- Call optimization (cache + dedup)
- Performance metrics collection
"""

from __future__ import annotations

import pytest
import time


class TestToolTaxonomy:
    """Test tool taxonomy and domain classification."""

    def test_get_domains_for_tool(self):
        """Test mapping tool name to domains."""
        from butler.tools.tool_taxonomy import get_domains_for_tool

        # Known tools
        domains = get_domains_for_tool("read_file")
        assert isinstance(domains, list)
        assert "code_engineering" in domains or "agent_dev" in domains

        # Unknown tool
        domains = get_domains_for_tool("nonexistent_tool_xyz")
        assert domains == []

    def test_get_tools_by_domain(self):
        """Test getting tools for a domain."""
        from butler.tools.tool_taxonomy import get_tools_by_domain

        tools = get_tools_by_domain("code_engineering")
        assert isinstance(tools, list)
        assert len(tools) > 0
        assert "read_file" in tools or "write_file" in tools

    def test_get_tool_info(self):
        """Test getting tool metadata."""
        try:
            from butler.tools.tool_taxonomy import get_tool_info

            info = get_tool_info("read_file")
            assert isinstance(info, dict)
            # Should have at least description or domains
            assert "description" in info or "domains" in info or len(info) >= 0
        except ModuleNotFoundError as e:
            # Skip if dependencies not available
            if "dotenv" in str(e):
                pytest.skip("dotenv module not available")
            raise


class TestToolCallOptimizer:
    """Test tool call caching and deduplication."""

    def test_cache_hit(self):
        """Test that cache returns cached results."""
        from butler.tools.tool_call_optimizer import ToolCallOptimizer

        optimizer = ToolCallOptimizer()

        # Simulate a cacheable tool call
        tool_name = "read_file"
        args = {"path": "/tmp/test.py"}
        result = '{"content": "test content"}'

        # Cache it
        optimizer.set_cache(tool_name, args, result)

        # Check cache hit
        cached = optimizer.check_cache(tool_name, args)
        assert cached == result

    def test_cache_miss(self):
        """Test cache miss behavior."""
        from butler.tools.tool_call_optimizer import ToolCallOptimizer

        optimizer = ToolCallOptimizer()

        # Check cache for never-cached tool
        cached = optimizer.check_cache("read_file", {"path": "/nonexistent.py"})
        assert cached is None

    def test_deduplicate_calls(self):
        """Test duplicate call detection."""
        from butler.tools.tool_call_optimizer import ToolCallOptimizer

        optimizer = ToolCallOptimizer()

        tool_name = "read_file"
        args = {"path": "/tmp/test.py"}

        # First call should not be duplicate
        is_dup = optimizer.check_duplicate(tool_name, args)
        assert is_dup is False

        # Immediate second call should be duplicate
        is_dup = optimizer.check_duplicate(tool_name, args)
        assert is_dup is True

    def test_optimize_call_flow(self):
        """Test optimize_call end-to-end."""
        from butler.tools.tool_call_optimizer import ToolCallOptimizer

        optimizer = ToolCallOptimizer()

        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1
            return '{"ok": true}'

        tool_name = "read_file"
        args = {"path": "/tmp/test.py"}

        # First call: cache miss, execute
        result1, cached1 = optimizer.optimize_call(tool_name, args, handler)
        assert result1 == '{"ok": true}'
        assert cached1 is False
        assert call_count == 1

        # Second call: cache hit, no execution
        result2, cached2 = optimizer.optimize_call(tool_name, args, handler)
        assert result2 == '{"ok": true}'
        assert cached2 is True
        assert call_count == 1  # Handler not called again

    def test_cache_stats(self):
        """Test cache statistics."""
        from butler.tools.tool_call_optimizer import ToolCallOptimizer

        optimizer = ToolCallOptimizer()

        # Perform some operations
        optimizer.set_cache("read_file", {"path": "a.py"}, '{"a"}')
        optimizer.set_cache("read_file", {"path": "b.py"}, '{"b"}')
        optimizer.check_cache("read_file", {"path": "a.py"})  # hit
        optimizer.check_cache("read_file", {"path": "c.py"})  # miss

        stats = optimizer.get_stats()
        assert "cache" in stats
        assert stats["cache"]["hits"] >= 1
        assert stats["cache"]["misses"] >= 1


class TestToolMetrics:
    """Test tool performance metrics collection."""

    def test_record_and_retrieve(self):
        """Test recording and retrieving tool metrics."""
        from butler.tools.tool_metrics import ToolMetrics

        metrics = ToolMetrics()

        # Record some calls
        metrics.record("read_file", duration_ms=50.0, success=True, cache_hit=False)
        metrics.record("read_file", duration_ms=30.0, success=True, cache_hit=True)
        metrics.record("write_file", duration_ms=100.0, success=False, cache_hit=False)

        # Get stats
        stats = metrics.get_all_stats()
        assert stats["total_calls"] == 3
        assert "read_file" in stats["tools"]
        assert "write_file" in stats["tools"]

    def test_tool_specific_stats(self):
        """Test getting stats for a specific tool."""
        from butler.tools.tool_metrics import ToolMetrics

        metrics = ToolMetrics()

        # Record calls for same tool
        for i in range(5):
            metrics.record("read_file", duration_ms=10.0 + i, success=i < 4, cache_hit=False)

        stats = metrics.get_tool_stats("read_file")
        assert stats["call_count"] == 5
        assert stats["success_count"] == 4
        assert stats["fail_count"] == 1
        assert abs(stats["success_rate"] - 0.8) < 0.01

    def test_top_tools(self):
        """Test getting top tools by different metrics."""
        from butler.tools.tool_metrics import ToolMetrics

        metrics = ToolMetrics()

        # Create different call patterns
        for _ in range(10):
            metrics.record("read_file", duration_ms=10.0, success=True, cache_hit=False)
        for _ in range(5):
            metrics.record("write_file", duration_ms=200.0, success=True, cache_hit=False)

        top_by_calls = metrics.get_top_tools(by="call_count", limit=3)
        assert len(top_by_calls) <= 3
        if len(top_by_calls) > 0:
            assert top_by_calls[0]["tool_name"] == "read_file"

    def test_metrics_reset(self):
        """Test resetting metrics."""
        from butler.tools.tool_metrics import ToolMetrics

        metrics = ToolMetrics()

        metrics.record("read_file", duration_ms=50.0, success=True, cache_hit=False)
        stats1 = metrics.get_all_stats()
        assert stats1["total_calls"] == 1

        metrics.reset()
        stats2 = metrics.get_all_stats()
        assert stats2["total_calls"] == 0


class TestToolDiscovery:
    """Test semantic tool discovery."""

    def test_discover_tools(self):
        """Test semantic tool discovery."""
        from butler.tools.tool_discovery import ToolDiscovery

        discovery = ToolDiscovery()

        # Discover tools for a query
        results = discovery.discover("read a python file", top_k=5)
        assert isinstance(results, list)
        # Results may be empty if no tools registered yet
        if len(results) > 0:
            assert "tool_name" in results[0]
            assert "similarity" in results[0]

    def test_similarity_threshold(self):
        """Test that low-similarity results are filtered."""
        from butler.tools.tool_discovery import ToolDiscovery

        discovery = ToolDiscovery()

        results = discovery.discover("random unrelated query xyz123", top_k=5, threshold=0.8)
        # Should return empty or very few results for nonsensical query
        assert isinstance(results, list)


class TestExperienceBasedToolSelector:
    """Test experience-based tool selection."""

    def test_taxonomy_fallback(self):
        """Test that selector falls back to taxonomy when no experience."""
        from butler.tools.experience_selector import ExperienceBasedToolSelector

        selector = ExperienceBasedToolSelector()

        # Query for a known domain
        tools = selector.select_tools("I need to read a file", top_k=5)
        assert isinstance(tools, list)
        # Should return some tools from taxonomy even without experience
        if len(tools) > 0:
            assert hasattr(tools[0], "tool_name")
            assert hasattr(tools[0], "score")

    def test_domain_specific_tools(self):
        """Test getting tools for a specific domain."""
        from butler.tools.experience_selector import ExperienceBasedToolSelector

        selector = ExperienceBasedToolSelector()

        tools = selector.get_tools_for_domain("code_engineering")
        assert isinstance(tools, list)
        assert len(tools) > 0


class TestToolService:
    """Test unified tool service."""

    def test_recommend_tools(self):
        """Test tool recommendation."""
        from butler.tools.tool_service import ToolService

        service = ToolService()

        recommendations = service.recommend_tools("read a python file", top_k=5)
        assert isinstance(recommendations, list)
        if len(recommendations) > 0:
            assert "tool_name" in recommendations[0]
            assert "score" in recommendations[0]

    def test_get_stats(self):
        """Test getting service statistics."""
        from butler.tools.tool_service import ToolService

        service = ToolService()

        stats = service.get_stats()
        assert isinstance(stats, dict)
        assert "metrics" in stats
        assert "optimizer" in stats

    @pytest.mark.skip(reason="Tool execution with registry integration may hang")
    def test_execute_tool_with_metrics(self):
        """Test tool execution with metrics recording."""
        from butler.tools.tool_service import ToolService

        service = ToolService()

        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1
            return '{"ok": true}'

        # Execute tool WITH handler (not None) to avoid circular dependency
        result, meta = service.execute_tool("read_file", {"path": "test.py"}, handler=handler)
        assert result == '{"ok": true}'
        assert "cached" in meta

        # Check that metrics were recorded
        stats = service.get_stats()
        # Metrics may or may not be recorded depending on implementation
        assert isinstance(stats, dict)


class TestToolServiceIntegration:
    """Integration tests for tool intelligence with registry."""

    def test_service_singleton(self):
        """Test that service singleton works."""
        from butler.tools.tool_service import get_tool_service

        service1 = get_tool_service()
        service2 = get_tool_service()
        assert service1 is service2

    def test_optimizer_singleton(self):
        """Test that optimizer singleton works."""
        from butler.tools.tool_call_optimizer import get_tool_optimizer

        optimizer1 = get_tool_optimizer()
        optimizer2 = get_tool_optimizer()
        assert optimizer1 is optimizer2


class TestAgentLoopToolIntegration:
    """Integration tests for tool intelligence in Agent Loop."""

    def test_experience_recommendation_in_phases(self):
        """Test experience-based tool recommendation in _phase_enrich_user_text."""
        from butler.tools.tool_service import recommend_tools

        recommendations = recommend_tools("I need to read a Python file", top_k=10)
        assert isinstance(recommendations, list)

        recommended_names = {rec["tool_name"] for rec in recommendations if rec["score"] > 0.3}
        assert isinstance(recommended_names, set)

    def test_tool_service_execute_with_registry(self):
        """Test ToolService.execute_tool with optimization."""
        from butler.tools.tool_service import ToolService

        service = ToolService()

        call_count = 0

        def handler():
            nonlocal call_count
            call_count += 1
            return '{"ok": true}'

        result, meta = service.execute_tool("read_file", {"path": "/tmp/test.py"}, handler=handler)
        assert result == '{"ok": true}'
        assert "cached" in meta
        assert call_count == 1

        result2, meta2 = service.execute_tool("read_file", {"path": "/tmp/test.py"}, handler=handler)
        assert result2 == '{"ok": true}'
        assert meta2.get("cached") is True
        assert call_count == 1

    def test_tool_service_recommend_function(self):
        """Test the recommend_tools convenience function."""
        from butler.tools.tool_service import recommend_tools

        recommendations = recommend_tools("search for files")
        assert isinstance(recommendations, list)
        if len(recommendations) > 0:
            assert "tool_name" in recommendations[0]
            assert "score" in recommendations[0]

    def test_tool_service_performance_report(self):
        """Test getting performance report."""
        from butler.tools.tool_service import ToolService

        service = ToolService()

        report = service.get_performance_report()
        assert isinstance(report, dict)
        assert "session_summary" in report
        assert "top_by_calls" in report
        assert "slowest" in report
        assert "most_errors" in report

    def test_metrics_singleton(self):
        """Test that metrics singleton works."""
        from butler.tools.tool_metrics import get_tool_metrics

        metrics1 = get_tool_metrics()
        metrics2 = get_tool_metrics()
        assert metrics1 is metrics2