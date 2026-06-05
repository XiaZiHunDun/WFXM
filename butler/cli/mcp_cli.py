"""CLI: ``butler mcp ...`` — MCP server and catalog subcommands.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

Extracted from ``butler/main.py`` as part of the R1-7 subcommand
registration refactor. The ``mcp`` parent + ``serve`` subcommand
were inline in the old ``_build_parser``; the catalog subcommands
were already delegated to ``butler.cli.mcp_catalog_cli``.
"""

from __future__ import annotations

import argparse


def register_mcp_parser(sub: argparse._SubParsersAction) -> None:
    """Register the ``mcp`` parent parser and its ``serve`` subcommand.

    Catalog subcommands (``add``, ``list``, ``remove``, …) are still
    delegated to ``butler.cli.mcp_catalog_cli.register_mcp_catalog_parsers``
    to keep the split non-overlapping.
    """
    from butler import main as _butler_main

    mcp = sub.add_parser("mcp", help="MCP 协议工具（需 butler-system[mcp]）")
    mcp_sub = mcp.add_subparsers(dest="mcp_cmd", required=True)
    mcp_serve = mcp_sub.add_parser(
        "serve",
        help="stdio MCP Server，暴露只读 Butler 工具供 Cursor 等客户端调用",
    )
    mcp_serve.set_defaults(func=_butler_main._cmd_mcp_serve)

    from butler.cli.mcp_catalog_cli import register_mcp_catalog_parsers

    register_mcp_catalog_parsers(mcp_sub)


def _cmd_mcp_serve(_ns: argparse.Namespace) -> int:
    from butler.mcp.server_stdio import run_stdio_server

    return run_stdio_server()
