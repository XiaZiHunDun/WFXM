"""R1-7 ``butler/main.py`` god-module split — backward-compat guard.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

The 1340-line ``butler.main`` carried three god methods / functions:

* ``_build_parser`` (lines 999-1316, 317 non-blank lines) — 22 inline
  ``sub.add_parser`` calls; adding a new subcommand required editing
  the main.py monolith.
* ``_handle_slash_command`` (lines 261-503, 242 non-blank lines) —
  one if/elif chain for every slash command; no per-command isolation.
* ``_run_interactive_chat`` (lines 24-228, 205 non-blank lines) — a
  monolith of the entire interactive loop, not in audit scope but
  visible in the same file and explicitly required by the R1-7 wider
  contract to be reduced.

The audit's recommendation was to register sub-commands into per-area
``butler/cli/<area>_cli.py`` modules (each with ``def
register_xxx_parser(sub)``), and to refactor the slash dispatcher to
reuse the ``CommandDef`` style. This test module asserts the
post-split contract:

1. **Backward compat**: every private symbol the existing tests
   import from ``butler.main`` must remain reachable.
2. **Size contract (R1-5.2 / R1-6 lesson)**: every top-level
   function in ``butler.main`` and the new per-area CLI modules must
   be a thin orchestrator under 50 source lines.
3. **Subcommand count**: all 22 originally-inline subparsers must
   still register through the orchestrator (none lost during the
   re-bucketing).
4. **Behavioral smoke**: ``butler --help`` exits 0 and the
   top-level subcommands are discoverable.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import subprocess
import sys
from pathlib import Path

import pytest

# -- paths ----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "butler" / "main.py"
CLI_DIR = REPO_ROOT / "butler" / "cli"

NEW_CLI_MODULES = [
    "butler.cli.chat_cli",
    "butler.cli.projects_cli",
    "butler.cli.memory_cli",
    "butler.cli.runtime_cli",
    "butler.cli.gateway_cli",
    "butler.cli.mcp_cli",
    "butler.cli.slash_dispatch",
]


# -- 1. Backward compat: every symbol the existing test suite imports
#       from butler.main must stay reachable. If a re-export goes
#       missing, the import in test_main_cli / test_butler_v4 / etc.
#       will fail loudly. We assert the surface here so the failure
#       is local to this contract test.

MAIN_PUBLIC_BACKCOMPAT = [
    # public-ish symbols
    "main",
    "_build_parser",
    # back-compat re-exports for tests/cli_harness that import these
    # private names from butler.main. Moving them to per-area modules
    # is fine as long as we re-export.
    "_cmd_chat",
    "_cmd_exec",
    "_cmd_projects",
    "_cmd_projects_refresh",
    "_cmd_create",
    "_cmd_project_register",
    "_cmd_project_preflight",
    "_create_slug_from_ns",
    "_cmd_memory_search",
    "_cmd_memory_reindex",
    "_cmd_runtime_list",
    "_cmd_runtime_run",
    "_cmd_runtime_due",
    "_cmd_runtime_drain_push",
    "_cmd_runtime_approve",
    "_cmd_gateway",
    "_cmd_wechat_setup",
    "_merge_wechat_env_file",
    "_print_wechat_setup_success",
    "_cmd_mcp_serve",
    "_cmd_doctor",
    # interactive chat + slash handler
    "_run_interactive_chat",
    "_handle_slash_command",
    "_sync_memory",
    "_trigger_session_end",
]


# -- 2. Subcommand count: the 22 inline ``sub.add_parser`` calls in
#       the pre-R1-7 _build_parser must all still be reachable.
#       We assert each name shows up in the post-split parser.

EXPECTED_TOP_LEVEL_SUBCOMMANDS = [
    # inline ones (R1-7 audit target)
    "chat",
    "projects",
    "create",
    "project",  # parent
    "exec",
    "gateway",
    "wechat-setup",
    "memory",  # parent
    "memory-reindex",
    "runtime",  # parent
    "mcp",  # parent
    "doctor",
    # delegated ones (R1-7 refactor keeps the delegations intact)
    "skills",
    "workflow",
    "experiment",
    "sessions",
    "prompt",
    "provider",
    "registry",
    "secrets",
]


# =============================================================================
# Test classes
# =============================================================================


@pytest.mark.unit
class TestSplitModulesExist:
    @pytest.mark.parametrize("modname", NEW_CLI_MODULES)
    def test_new_cli_module_loads(self, modname: str):
        mod = importlib.import_module(modname)
        assert mod is not None

    def test_main_still_imports(self):
        mod = importlib.import_module("butler.main")
        assert mod is not None


@pytest.mark.unit
class TestBackwardCompatSymbols:
    @pytest.mark.parametrize("name", MAIN_PUBLIC_BACKCOMPAT)
    def test_symbol_still_in_main(self, name: str):
        mod = importlib.import_module("butler.main")
        assert hasattr(mod, name), (
            f"butler.main.{name} disappeared after R1-7 split; "
            "either move the function to its per-area module AND "
            "re-export it, or keep the symbol inline."
        )


@pytest.mark.unit
class TestMainTopLevelFunctionSizes:
    """Every top-level function in butler/main.py must be a thin
    orchestrator under 50 source lines after the R1-7 split.

    The audit's wider contract explicitly states:
        "After your refactor, main.py should have NO top-level
         function > 50L"
    """

    @pytest.mark.parametrize(
        "name",
        [
            "_build_parser",
            "_handle_slash_command",
            "_run_interactive_chat",
            "_cmd_exec",
            "main",
        ],
    )
    def test_thinned_top_level_function(self, name: str):
        mod = importlib.import_module("butler.main")
        assert hasattr(mod, name), f"butler.main.{name} missing"
        fn = getattr(mod, name)
        src = inspect.getsource(fn)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"butler.main.{name} is {len(body_lines)} non-blank lines; "
            f"R1-7 size contract requires < 50. Split into phase helpers."
        )

    def test_every_top_level_function_under_50_lines(self):
        """AST sweep across all top-level functions in main.py.

        Catches any future top-level function that regresses past
        50L even if the test parametrize list above drifts.
        """
        tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
        offenders: list[tuple[str, int]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # AST reports physical line span; we want non-blank body lines.
                src_lines = [
                    ln
                    for ln in MAIN_PY.read_text(encoding="utf-8").splitlines()[
                        node.lineno - 1 : node.end_lineno
                    ]
                    if ln.strip()
                ]
                if len(src_lines) >= 50:
                    offenders.append((node.name, len(src_lines)))
        assert not offenders, (
            "Top-level functions in butler/main.py still over 50L after R1-7: "
            + ", ".join(f"{n}={sz}L" for n, sz in offenders)
        )


@pytest.mark.unit
class TestNewCliModuleFunctionSizes:
    """Every top-level function in the new per-area CLI modules must
    be under 50 source lines. The R1-7 contract elevates this from
    a recommendation to a hard cap."""

    @pytest.mark.parametrize("modname", NEW_CLI_MODULES)
    def test_every_top_level_function_under_50_lines(self, modname: str):
        path = CLI_DIR / f"{modname.rsplit('.', 1)[-1]}.py"
        assert path.is_file(), f"{path} missing"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        src_text = path.read_text(encoding="utf-8")
        offenders: list[tuple[str, int]] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # skip the register_xxx_parser top-level if it is exactly
                # the audit's recommended thin orchestrator pattern
                body = src_text.splitlines()[node.lineno - 1 : node.end_lineno]
                body = [ln for ln in body if ln.strip()]
                if len(body) >= 50:
                    offenders.append((node.name, len(body)))
        assert not offenders, (
            f"Functions in {modname} over 50L: "
            + ", ".join(f"{n}={sz}L" for n, sz in offenders)
        )


@pytest.mark.unit
class TestSubcommandCountContract:
    """All originally-inline subparsers must still be reachable in
    the post-split parser."""

    @pytest.mark.parametrize("name", EXPECTED_TOP_LEVEL_SUBCOMMANDS)
    def test_top_level_subcommand_registered(self, name: str):
        from butler.main import _build_parser

        parser = _build_parser()
        # ``choice`` is a dict of subparser names if available, else
        # fall back to the help-text scan.
        try:
            sub_action = next(
                a for a in parser._actions if a.dest == "command"
            )
            available = set(sub_action.choices.keys())  # type: ignore[attr-defined]
        except (StopIteration, AttributeError):
            available = set()
        assert name in available, (
            f"subcommand {name!r} missing from post-R1-7 parser. "
            f"Available: {sorted(available)}"
        )

    def test_inline_add_parser_count_at_most_orchestrator(self):
        """_build_parser should be a thin orchestrator with very few
        inline ``add_parser`` calls. Most subparsers are registered
        via ``register_xxx_parser(sub)`` helpers in per-area modules.
        The pre-split parser had 22 inline ``add_parser`` calls; the
        post-split parser should have far fewer (we leave a small
        allow-list for any that the orchestrator wires up itself)."""
        from butler.main import _build_parser

        # Patch out the delegations so we can count only the orchestrator's
        # own inline add_parser calls. We do this by inspecting the source
        # and excluding calls inside register_xxx_parser function bodies.
        src = inspect.getsource(_build_parser)
        tree = ast.parse(src)
        inline_calls = 0
        for sub in tree.body:
            if isinstance(sub, ast.FunctionDef) and sub.name == "_build_parser":
                for n in ast.walk(sub):
                    if isinstance(n, ast.Call) and isinstance(
                        n.func, ast.Attribute
                    ) and n.func.attr == "add_parser":
                        inline_calls += 1
        # Pre-split was 22. Post-split target: at most a handful
        # (the delegations are now function calls, not inline).
        assert inline_calls <= 2, (
            f"_build_parser has {inline_calls} inline add_parser calls; "
            f"R1-7 split should have moved them to per-area modules."
        )


@pytest.mark.unit
class TestHelpSmoke:
    """`butler --help` must still work end-to-end after the split."""

    def test_butler_help_exits_zero(self):
        env = os.environ.copy()
        # suppress noisy loggers
        env.setdefault("BUTLER_LOG_LEVEL", "ERROR")
        result = subprocess.run(
            ["butler", "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        assert result.returncode == 0, (
            f"`butler --help` failed: rc={result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_butler_help_lists_top_level_subcommands(self):
        env = os.environ.copy()
        env.setdefault("BUTLER_LOG_LEVEL", "ERROR")
        result = subprocess.run(
            ["butler", "--help"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        out = result.stdout
        for name in ("chat", "projects", "create", "exec", "doctor"):
            assert name in out, (
                f"`butler --help` output missing subcommand {name!r}\n"
                f"full output: {out}"
            )

    def test_missing_subcommand_exits_nonzero(self):
        env = os.environ.copy()
        env.setdefault("BUTLER_LOG_LEVEL", "ERROR")
        result = subprocess.run(
            ["butler"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        assert result.returncode != 0, (
            "`butler` with no subcommand should fail (argparse required=True)"
        )


@pytest.mark.unit
class TestDispatcherShape:
    """The new _handle_slash_command in main.py must dispatch through
    the slash_dispatch module — it should not contain per-command
    logic inline."""

    def test_main_handle_slash_is_thin(self):
        from butler.main import _handle_slash_command

        src = inspect.getsource(_handle_slash_command)
        body_lines = [ln for ln in src.splitlines() if ln.strip()]
        assert len(body_lines) < 50, (
            f"butler.main._handle_slash_command is {len(body_lines)}L; "
            f"R1-7 split should move per-command logic to slash_dispatch."
        )

    def test_slash_dispatch_module_exports_dispatcher(self):
        mod = importlib.import_module("butler.cli.slash_dispatch")
        assert hasattr(mod, "dispatch_slash_command"), (
            "butler.cli.slash_dispatch must export dispatch_slash_command"
        )

    def test_local_slash_registry_has_handlers(self):
        """Each per-area CLI module that needs slash-command support
        should have registered its handlers in slash_dispatch."""
        mod = importlib.import_module("butler.cli.slash_dispatch")
        reg = getattr(mod, "_SLASH_REGISTRY", None)
        assert reg is not None, (
            "butler.cli.slash_dispatch must expose _SLASH_REGISTRY for "
            "back-compat lookups"
        )
        # We expect at least the high-traffic commands to be there.
        canonical_names = {name for name in reg.keys()}
        assert "/help" in canonical_names, "/help handler missing"
        assert "/projects" in canonical_names, "/projects handler missing"
        assert "/status" in canonical_names, "/status handler missing"
        assert "/switch" in canonical_names, "/switch handler missing"
        assert "/model" in canonical_names, "/model handler missing"
        assert "/new" in canonical_names, "/new handler missing"
        assert "/workflow" in canonical_names, "/workflow handler missing"
