"""CLI probe for web_search — same code path as gateway tool dispatch."""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

from butler.tools.web_search import (
    _proxy_configured,
    _search_strategies,
    _total_budget,
    _try_direct_with_proxy,
    tool_web_search,
    web_search_enabled,
)


def run_probe(query: str = "AI写作助手 竞品", max_results: int = 3) -> dict[str, Any]:
    proxy_vars = {
        k: os.environ.get(k, "")
        for k in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
        )
        if str(os.environ.get(k) or "").strip()
    }
    started = time.monotonic()
    raw = tool_web_search(query=query, max_results=max_results)
    elapsed = round(time.monotonic() - started, 2)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"raw": raw}
    results = payload.get("results") if isinstance(payload, dict) else None
    return {
        "ok": bool(isinstance(results, list) and len(results) > 0),
        "enabled": web_search_enabled(),
        "proxy_configured": _proxy_configured(),
        "try_direct": _try_direct_with_proxy(),
        "strategies": _search_strategies(),
        "budget_seconds": _total_budget(),
        "elapsed_seconds": elapsed,
        "proxy_env": proxy_vars,
        "result_count": len(results) if isinstance(results, list) else 0,
        "first_url": (results[0].get("url") if isinstance(results, list) and results else ""),
        "message": payload.get("message") if isinstance(payload, dict) else "",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Probe Butler web_search (gateway-equivalent env)")
    p.add_argument("--query", default="AI写作助手 竞品")
    p.add_argument("--max-results", type=int, default=3)
    args = p.parse_args(argv)
    out = run_probe(query=str(args.query), max_results=int(args.max_results))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
