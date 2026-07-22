"""Integration tests for effects/with_retry in tool dispatch pipeline."""

from __future__ import annotations

import pytest

from butler.tools.registry import dispatch_tool
from butler.tools.registry_invoke_ops import NO_RETRY_TOOLS


class TestRetryIntegration:
    def test_retry_on_network_error(self):
        """Test that a tool raising OSError is retried and succeeds on second attempt."""
        counter = [0]

        def flaky_tool(*, retry_count: int = 0) -> str:
            counter[0] += 1
            if counter[0] < 2:
                raise OSError("Network error")
            return "Success"

        from butler.tools.registry import _REGISTRY

        try:
            _REGISTRY["__test_retry_tool__"] = type('ToolEntry', (), {
                'handler': flaky_tool,
                'schema': {'name': '__test_retry_tool__', 'parameters': {}}
            })

            result = dispatch_tool("__test_retry_tool__", {"retry_count": 0})

            assert counter[0] == 2, f"Expected 2 attempts but got {counter[0]}"
            assert "Success" in result

        finally:
            _REGISTRY.pop("__test_retry_tool__", None)

    def test_no_retry_on_non_network_error(self):
        """Test that a tool raising ValueError is NOT retried."""
        counter = [0]

        def failing_tool(*, value: str = "") -> str:
            counter[0] += 1
            raise ValueError("Invalid value")

        from butler.tools.registry import _REGISTRY

        try:
            _REGISTRY["__test_no_retry_tool__"] = type('ToolEntry', (), {
                'handler': failing_tool,
                'schema': {'name': '__test_no_retry_tool__', 'parameters': {}}
            })

            result = dispatch_tool("__test_no_retry_tool__", {"value": "test"})

            assert counter[0] == 1, f"Expected 1 attempt but got {counter[0]}"
            assert "error" in result.lower()

        finally:
            _REGISTRY.pop("__test_no_retry_tool__", None)

    def test_retry_exhausted_returns_error(self):
        """Test that when retries are exhausted, an error is returned."""
        counter = [0]

        def always_failing_tool() -> str:
            counter[0] += 1
            raise ConnectionError("Always fails")

        from butler.tools.registry import _REGISTRY

        try:
            _REGISTRY["__test_exhausted_tool__"] = type('ToolEntry', (), {
                'handler': always_failing_tool,
                'schema': {'name': '__test_exhausted_tool__', 'parameters': {}}
            })

            result = dispatch_tool("__test_exhausted_tool__", {})

            assert counter[0] == 2, f"Expected 2 attempts but got {counter[0]}"
            assert "error" in result.lower()

        finally:
            _REGISTRY.pop("__test_exhausted_tool__", None)

    def test_no_retry_for_side_effect_tools(self):
        """Test that tools in NO_RETRY_TOOLS are NOT retried even on network error."""
        counter = [0]

        def flaky_side_effect_tool(*, content: str = "") -> str:
            counter[0] += 1
            raise OSError("Network error")

        from butler.tools.registry_invoke_ops import invoke_registered_tool_handler

        result = invoke_registered_tool_handler(
            name="write_file",
            args={"content": "test"},
            call_args={"content": "test"},
            handler=flaky_side_effect_tool,
            started_at=0.0,
            finalize_result=lambda n, a, r, **k: str(r),
            apply_hooks=lambda n, a, r, **k: r,
        )

        assert counter[0] == 1, f"Expected 1 attempt (no retry) but got {counter[0]}"
        assert "error" in result.lower()

    def test_no_retry_tools_contains_side_effect_tools(self):
        """Verify NO_RETRY_TOOLS contains expected side-effect tools."""
        side_effect_tools = {
            "write_file",
            "patch",
            "delete_file",
            "terminal",
            "opencode_task",
            "delegate_task",
            "run_workflow",
        }
        assert side_effect_tools.issubset(NO_RETRY_TOOLS), \
            f"NO_RETRY_TOOLS missing expected tools: {side_effect_tools - NO_RETRY_TOOLS}"