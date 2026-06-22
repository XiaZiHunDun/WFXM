"""G1-12 network route manifest policy verify."""

from __future__ import annotations

import pytest

from butler.tools.network_route_verify import (
    load_network_route_manifest,
    run_policy_golden_cases,
)


@pytest.mark.unit
def test_network_route_manifest_loaded():
    manifest = load_network_route_manifest()
    assert manifest is not None
    assert len(manifest.golden_cases) >= 5


@pytest.mark.unit
def test_policy_golden_cases_all_pass():
    manifest = load_network_route_manifest()
    assert manifest is not None
    report = run_policy_golden_cases(manifest)
    assert report.ok, report.errors


@pytest.mark.unit
def test_evaluate_handler_tool_route_order():
    from butler.tools.network_route_verify import (
        HandlerRouteCase,
        evaluate_handler_tool_route,
    )

    case = HandlerRouteCase(
        name="order",
        user_text="x",
        web_search_before_firecrawl_search=True,
    )
    errors, _ = evaluate_handler_tool_route(
        ["mcp_firecrawl_firecrawl_search", "web_search"],
        "ok",
        case,
    )
    assert errors
    errors2, _ = evaluate_handler_tool_route(
        ["web_search", "mcp_firecrawl_firecrawl_search"],
        "ok",
        case,
    )
    assert not errors2


@pytest.mark.unit
def test_evaluate_handler_tool_route_strict_requires_preferred():
    from butler.tools.network_route_verify import (
        HandlerRouteCase,
        evaluate_handler_tool_route,
    )

    case = HandlerRouteCase(
        name="search",
        user_text="搜竞品",
        prefer_tools_any=("web_search",),
    )
    errors, warnings = evaluate_handler_tool_route([], "无工具", case, strict=True)
    assert errors
    assert not warnings
    errors2, warnings2 = evaluate_handler_tool_route(
        ["web_search"],
        "有结果",
        case,
        strict=True,
    )
    assert not errors2


@pytest.mark.unit
def test_evaluate_handler_tool_route_strict_allows_direct_reply():
    from butler.tools.network_route_verify import (
        HandlerRouteCase,
        evaluate_handler_tool_route,
    )

    case = HandlerRouteCase(
        name="todoist",
        user_text="列项目",
        prefer_tools_any=("mcp_todoist_lst_projects",),
        expect_reply_any=("项目",),
        allow_empty_tools=True,
    )
    errors, _ = evaluate_handler_tool_route([], "Todoist 共有 3 个项目", case, strict=True)
    assert not errors


@pytest.mark.unit
def test_handler_manifest_loaded():
    manifest = load_network_route_manifest()
    assert manifest is not None
    assert len(manifest.handler_cases) >= 2
