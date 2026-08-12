"""Memory profiler for the tool execution pipeline.

Uses tracemalloc to analyze memory allocation patterns during
tool execution, identifying hot spots and potential leaks.

Usage:
    python butler/dev_engine/memory_profiler.py
"""

from __future__ import annotations

import json
import time
import tracemalloc
from typing import Any


class MockToolCall:
    def __init__(self, name: str, arguments: dict[str, Any], call_id: str = ""):
        self.name = name
        self.arguments = json.dumps(arguments)
        self.id = call_id or f"call-{name}"


def mock_dispatch_fn(name: str, args: dict[str, Any], call_id: str) -> str:
    if name == "read_file":
        return json.dumps({"content": "File content here", "path": args.get("path", "")})
    elif name == "web_search":
        return json.dumps({"results": ["Result 1", "Result 2"], "query": args.get("query", "")})
    elif name == "slow_tool":
        time.sleep(0.02)
        return json.dumps({"result": "Slow tool completed"})
    else:
        return json.dumps({"result": f"Unknown tool: {name}"})


def run_memory_profile() -> dict[str, Any]:
    """Run memory profiling on tool execution pipeline."""

    # Take baseline snapshot
    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    # Import components to measure their base memory
    from butler.core.tool_executor import (
        execute_tool_calls_sequential,
        execute_tool_calls_concurrent,
    )
    from butler.core.events import reset_global_event_bus

    reset_global_event_bus()

    # First snapshot - after imports
    snapshot_imports = tracemalloc.take_snapshot()
    stats_imports = snapshot_imports.compare_to(snapshot_before, "lineno")

    # Execute tools
    tool_calls = [
        MockToolCall("read_file", {"path": "/test/file.txt"}, "call-001"),
        MockToolCall("web_search", {"query": "test query"}, "call-002"),
        MockToolCall("slow_tool", {"param": "value"}, "call-003"),
    ] * 10  # 30 tool calls total

    start_time = time.time()
    results = execute_tool_calls_sequential(
        tool_calls,
        mock_dispatch_fn,
        session_id="wx:test-session-mem",
    )
    duration = time.time() - start_time

    # Take post-execution snapshot
    snapshot_after = tracemalloc.take_snapshot()
    stats_exec = snapshot_after.compare_to(snapshot_imports, "lineno")

    # Concurrent execution
    reset_global_event_bus()
    tool_calls_conc = [
        MockToolCall("read_file", {"path": "/test/file.txt"}, "call-conc-001"),
        MockToolCall("web_search", {"query": "test"}, "call-conc-002"),
    ] * 15

    start_time_conc = time.time()
    results_conc = execute_tool_calls_concurrent(
        tool_calls_conc,
        mock_dispatch_fn,
        session_id="wx:test-session-mem-conc",
        max_workers=4,
    )
    duration_conc = time.time() - start_time_conc

    snapshot_after_conc = tracemalloc.take_snapshot()
    stats_conc = snapshot_after_conc.compare_to(snapshot_after, "lineno")

    # Get current memory stats
    current, peak = tracemalloc.get_traced_memory()

    # Build report
    report = {
        "baseline": {
            "current_bytes": current,
            "peak_bytes": peak,
            "current_kb": current / 1024,
            "peak_kb": peak / 1024,
        },
        "sequential": {
            "tool_calls": len(tool_calls),
            "duration_s": duration,
            "results_count": len(results),
        },
        "concurrent": {
            "tool_calls": len(tool_calls_conc),
            "duration_s": duration_conc,
            "results_count": len(results_conc),
        },
        "top_allocations_imports": [],
        "top_allocations_exec": [],
        "top_allocations_conc": [],
    }

    # Top import-time allocations
    for stat in stats_imports[:15]:
        report["top_allocations_imports"].append({
            "location": str(stat.traceback[0]),
            "size_kb": stat.size_diff / 1024,
            "count": stat.count_diff,
        })

    # Top execution-time allocations
    for stat in stats_exec[:15]:
        report["top_allocations_exec"].append({
            "location": str(stat.traceback[0]),
            "size_kb": stat.size_diff / 1024,
            "count": stat.count_diff,
        })

    # Top concurrent execution allocations
    for stat in stats_conc[:15]:
        report["top_allocations_conc"].append({
            "location": str(stat.traceback[0]),
            "size_kb": stat.size_diff / 1024,
            "count": stat.count_diff,
        })

    tracemalloc.stop()
    return report


def print_report(report: dict[str, Any]) -> None:
    """Pretty-print the memory profiling report."""
    print("=" * 70)
    print("Butler Tool Execution - Memory Profiling Report")
    print("=" * 70)

    b = report["baseline"]
    print("\nBaseline Memory (after imports):")
    print(f"  Current: {b['current_kb']:.1f} KB")
    print(f"  Peak:    {b['peak_kb']:.1f} KB")

    seq = report["sequential"]
    print(f"\nSequential Execution ({seq['tool_calls']} tools):")
    print(f"  Duration: {seq['duration_s']:.3f}s")
    print(f"  Results:  {seq['results_count']}")

    conc = report["concurrent"]
    print(f"\nConcurrent Execution ({conc['tool_calls']} tools):")
    print(f"  Duration: {conc['duration_s']:.3f}s")
    print(f"  Results:  {conc['results_count']}")

    print(f"\n{'='*70}")
    print("Top Import-Time Allocations")
    print(f"{'='*70}")
    for item in report["top_allocations_imports"]:
        if item["size_kb"] > 0:
            print(f"  +{item['size_kb']:8.1f} KB | {item['count']:6d} new | {item['location'][:60]}")

    print(f"\n{'='*70}")
    print("Top Sequential Execution Allocations")
    print(f"{'='*70}")
    for item in report["top_allocations_exec"]:
        if item["size_kb"] > 0:
            print(f"  +{item['size_kb']:8.1f} KB | {item['count']:6d} new | {item['location'][:60]}")

    print(f"\n{'='*70}")
    print("Top Concurrent Execution Allocations")
    print(f"{'='*70}")
    for item in report["top_allocations_conc"]:
        if item["size_kb"] > 0:
            print(f"  +{item['size_kb']:8.1f} KB | {item['count']:6d} new | {item['location'][:60]}")


def main() -> None:
    print("Starting memory profiling...")
    report = run_memory_profile()
    print_report(report)

    # Save report
    with open("memory_profile_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("\nDetailed report saved to: memory_profile_report.json")


if __name__ == "__main__":
    main()
