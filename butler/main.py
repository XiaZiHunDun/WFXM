#!/usr/bin/env python3
"""Butler CLI entry point — thin orchestrator.

R1-7 refactor: this module is now a thin dispatch layer. Subcommand
registration and per-command logic live in ``butler/cli/<area>_cli.py``
modules (chat_cli, projects_cli, memory_cli, runtime_cli, gateway_cli,
mcp_cli, plus the pre-existing registry_cli / sessions_cli /
skills_registry / workflow_cli / experiment_cli / prompt_eval_cli /
provider_presets_cli / secrets_cli). Slash commands are dispatched by
``butler.cli.slash_dispatch``.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

from butler.cli.chat_cli import register_chat_parser
from butler.cli.cost_cli import register_cost_parser
from butler.cli.doctor import cmd_doctor
from butler.cli.eval_cli import register_eval_parser
from butler.cli.experiment_cli import register_experiment_parser
from butler.cli.gateway_cli import register_gateway_parser
from butler.cli.mcp_cli import register_mcp_parser
from butler.cli.memory_cli import register_memory_parser
from butler.cli.onboard_cli import register_onboard_parser
from butler.cli.projects_cli import register_projects_parser
from butler.cli.prompt_eval_cli import register_prompt_eval_parser
from butler.cli.provider_presets_cli import register_provider_presets_parser
from butler.cli.registry_cli import register_registry_parser
from butler.cli.runtime_cli import register_runtime_parser
from butler.cli.secrets_cli import register_secrets_subparser
from butler.cli.sessions_cli import register_sessions_subparser
from butler.cli.skills_registry import register_skills_parser
from butler.cli.transcript_cli import register_transcript_parser
from butler.cli.workflow_cli import register_workflow_subparser
from butler.env_parse import init_dotenv
from butler.logging_config import configure_logging

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_parser() -> argparse.ArgumentParser:
    """Build the top-level ``butler`` argument parser.

    R1-7 refactor: this is a thin orchestrator that delegates to
    per-area ``register_xxx_parser(sub)`` helpers. Adding a new
    subcommand is a single ``register_xxx_parser(sub)`` call in the
    appropriate ``butler.cli.<area>_cli`` module.
    """
    p = argparse.ArgumentParser(
        prog="butler",
        description="Butler v4 — AI 管家系统（自建 Agent Loop 架构）",
    )
    sub = p.add_subparsers(dest="command", required=True)

    _register_per_area_parsers(sub)
    _register_preexisting_parsers(sub)

    sub.add_parser(
        "doctor",
        help="静态安全配置审计（OpenClaw doctor 子集，只读）",
    ).set_defaults(func=_cmd_doctor)

    return p


def _register_per_area_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Per-area registrations (R1-7 extraction targets)."""
    register_chat_parser(sub)
    register_cost_parser(sub)
    register_onboard_parser(sub)
    register_projects_parser(sub)
    register_memory_parser(sub)
    register_runtime_parser(sub)
    register_gateway_parser(sub)
    register_mcp_parser(sub)


def _register_preexisting_parsers(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Pre-existing delegations — keep them here so the orchestrator
    surface is the single point of truth for "what does `butler` do?"."""
    register_eval_parser(sub)
    register_skills_parser(sub)
    register_workflow_subparser(sub)
    register_experiment_parser(sub)
    register_sessions_subparser(sub)
    register_transcript_parser(sub)
    register_prompt_eval_parser(sub)
    register_provider_presets_parser(sub)
    register_registry_parser(sub)
    register_secrets_subparser(sub)


def _cmd_doctor(ns: argparse.Namespace) -> int:
    return int(cmd_doctor(ns))


def main(argv: Sequence[str] | None = None) -> None:
    init_dotenv()
    configure_logging()
    args = _build_parser().parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


# ---------------------------------------------------------------------------
# Backward-compat re-exports
#
# R1-7 moved the per-area command logic into ``butler.cli.<area>_cli``.
# Existing tests and the cli_harness import these private names from
# ``butler.main``; we re-export them here so the import surface stays
# stable. New code should import from the per-area modules directly.
# ---------------------------------------------------------------------------

# chat + exec + interactive loop
from butler.cli.chat_cli import (  # noqa: E402
    _cmd_chat,
    _cmd_exec,
    _run_interactive_chat,
)

# project subcommands
from butler.cli.projects_cli import (  # noqa: E402
    _cmd_create,
    _cmd_project_preflight,
    _cmd_project_register,
    _cmd_projects,
    _cmd_projects_refresh,
    _create_slug_from_ns,
)

# memory subcommands
from butler.cli.memory_cli import (  # noqa: E402
    _cmd_memory_reindex,
    _cmd_memory_search,
    _cmd_memory_seed,
)

# runtime subcommands
from butler.cli.runtime_cli import (  # noqa: E402
    _cmd_runtime_approve,
    _cmd_runtime_drain_push,
    _cmd_runtime_due,
    _cmd_runtime_list,
    _cmd_runtime_run,
)

# gateway + wechat-setup
from butler.cli.gateway_cli import (  # noqa: E402
    _cmd_gateway,
    _cmd_wechat_setup,
    _merge_wechat_env_file,
    _print_wechat_setup_success,
)

# mcp serve (the catalog subcommands live in mcp_catalog_cli)
from butler.cli.mcp_cli import _cmd_mcp_serve  # noqa: E402

# slash dispatcher + session helpers
from butler.cli.slash_dispatch import (  # noqa: E402
    _handle_slash_command,
    _sync_memory,
    _trigger_session_end,
)


if __name__ == "__main__":
    main()
