"""Load network search routing manifest and run policy golden cases (G1-12)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_MANIFEST_NAME = "network-search-routes.yaml"


@dataclass(frozen=True)
class RouteGoldenCase:
    name: str
    user_text: str
    tool: str
    expect_code: str | None
    prereq_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class HandlerRouteCase:
    name: str
    user_text: str
    forbid_tools: tuple[str, ...] = ()
    expect_tools_any: tuple[str, ...] = ()
    prefer_tools_any: tuple[str, ...] = ()
    web_search_before_firecrawl_search: bool = False
    expect_reply_any: tuple[str, ...] = ()
    allow_empty_tools: bool = False


@dataclass(frozen=True)
class NetworkRouteManifest:
    title: str
    path: Path
    golden_cases: tuple[RouteGoldenCase, ...] = ()
    handler_cases: tuple[HandlerRouteCase, ...] = ()
    verify_phrases: tuple[str, ...] = ()
    probe_query: str = "AI写作助手 竞品"
    probe_max_results: int = 3


def _routing_roots(workspace: Path | str | None = None) -> list[Path]:
    ws = Path(workspace or Path.cwd()).expanduser().resolve()
    roots: list[Path] = []
    for base in (ws / ".butler" / "routing", Path.home() / ".butler" / "routing"):
        if base.is_dir():
            roots.append(base)
    return roots


def load_network_route_manifest(workspace: Path | str | None = None) -> NetworkRouteManifest | None:
    for root in _routing_roots(workspace):
        path = root / _MANIFEST_NAME
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        cases: list[RouteGoldenCase] = []
        for row in data.get("golden_cases") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            tool = str(row.get("tool") or "").strip()
            if not name or not tool:
                continue
            raw_code = row.get("expect_code")
            expect_code = None if raw_code in (None, "null", "") else str(raw_code).strip()
            prereq = row.get("prereq_tools") or []
            cases.append(
                RouteGoldenCase(
                    name=name,
                    user_text=str(row.get("user_text") or "").strip(),
                    tool=tool,
                    expect_code=expect_code,
                    prereq_tools=tuple(str(x).strip() for x in prereq if str(x).strip()),
                )
            )
        phrases = data.get("verify_phrases") or []
        probe = data.get("probe") or {}
        handler_cases: list[HandlerRouteCase] = []
        for row in data.get("handler_cases") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            text = str(row.get("user_text") or "").strip()
            if not name or not text:
                continue
            handler_cases.append(
                HandlerRouteCase(
                    name=name,
                    user_text=text,
                    forbid_tools=tuple(
                        str(x).strip() for x in (row.get("forbid_tools") or []) if str(x).strip()
                    ),
                    expect_tools_any=tuple(
                        str(x).strip()
                        for x in (row.get("expect_tools_any") or [])
                        if str(x).strip()
                    ),
                    prefer_tools_any=tuple(
                        str(x).strip()
                        for x in (row.get("prefer_tools_any") or [])
                        if str(x).strip()
                    ),
                    web_search_before_firecrawl_search=bool(
                        row.get("web_search_before_firecrawl_search")
                    ),
                    expect_reply_any=tuple(
                        str(x).strip()
                        for x in (row.get("expect_reply_any") or [])
                        if str(x).strip()
                    ),
                    allow_empty_tools=bool(row.get("allow_empty_tools")),
                )
            )
        return NetworkRouteManifest(
            title=str(data.get("title") or "network-search-routes").strip(),
            path=path,
            golden_cases=tuple(cases),
            handler_cases=tuple(handler_cases),
            verify_phrases=tuple(str(p) for p in phrases if str(p).strip()),
            probe_query=str(probe.get("query") or "AI写作助手 竞品").strip(),
            probe_max_results=int(probe.get("max_results") or 3),
        )
    return None


@dataclass
class RouteVerifyReport:
    ok: bool
    cases: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    probe_ok: bool | None = None


@dataclass
class HandlerRouteReport:
    ok: bool
    cases: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_firecrawl_search_tool_name(name: str) -> bool:
    from butler.tools.network_search_policy import is_firecrawl_search_tool

    return is_firecrawl_search_tool(name)


def evaluate_handler_tool_route(
    tools: list[str],
    reply: str,
    case: HandlerRouteCase,
    *,
    strict: bool = False,
) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for tool in case.forbid_tools:
        if tool in tools:
            errors.append(f"forbidden tool used: {tool}")
    if case.expect_tools_any and not case.allow_empty_tools:
        if not any(t in tools for t in case.expect_tools_any):
            errors.append(f"expected tools any of {case.expect_tools_any}, got {tools}")
    if case.prefer_tools_any and not any(t in tools for t in case.prefer_tools_any):
        direct_reply_ok = bool(
            case.allow_empty_tools
            and case.expect_reply_any
            and any(x in reply for x in case.expect_reply_any)
        )
        if strict and not direct_reply_ok:
            errors.append(
                f"strict: required tools any of {case.prefer_tools_any}, got {tools}"
            )
        elif not strict:
            warnings.append(f"preferred tools missing {case.prefer_tools_any}, got {tools}")
    if case.web_search_before_firecrawl_search:
        fc_names = [t for t in tools if _is_firecrawl_search_tool_name(t)]
        if fc_names:
            if "web_search" not in tools:
                errors.append("firecrawl search used without web_search in turn")
            else:
                ws_idx = tools.index("web_search")
                if any(tools.index(t) < ws_idx for t in fc_names):
                    errors.append("firecrawl search before web_search in turn order")
    if case.expect_reply_any and not any(x in reply for x in case.expect_reply_any):
        errors.append(f"reply missing any of {case.expect_reply_any}")
    return errors, warnings


def run_policy_golden_cases(
    manifest: NetworkRouteManifest,
    *,
    gate_enabled: bool = True,
) -> RouteVerifyReport:
    import butler.tools.network_search_policy as nsp
    from butler.tools.network_search_policy import (
        check_network_search_tool_block,
        record_network_search_tool,
        turn_network_search_scope,
    )

    report = RouteVerifyReport(ok=True)
    orig_gate = nsp._web_search_in_current_toolset
    if gate_enabled:
        nsp._web_search_in_current_toolset = lambda: True  # type: ignore[method-assign]

    try:
        for case in manifest.golden_cases:
            entry: dict[str, Any] = {"name": case.name, "tool": case.tool}
            try:
                with turn_network_search_scope(case.user_text):
                    for prereq in case.prereq_tools:
                        record_network_search_tool(prereq)
                    block = check_network_search_tool_block(case.tool, {})
                code = None if block is None else str(block.get("code") or "")
                entry["code"] = code
                if case.expect_code != code:
                    msg = f"{case.name}: expected {case.expect_code!r}, got {code!r}"
                    report.errors.append(msg)
                    entry["ok"] = False
                    report.ok = False
                else:
                    entry["ok"] = True
            except Exception as exc:
                entry["ok"] = False
                entry["error"] = str(exc)[:200]
                report.errors.append(f"{case.name}: {exc}")
                report.ok = False
            report.cases.append(entry)
    finally:
        nsp._web_search_in_current_toolset = orig_gate  # type: ignore[method-assign]

    return report


def run_web_search_probe(manifest: NetworkRouteManifest) -> tuple[bool, dict[str, Any]]:
    from butler.tools.web_search_probe import run_probe

    out = run_probe(query=manifest.probe_query, max_results=manifest.probe_max_results)
    return bool(out.get("ok")), out
