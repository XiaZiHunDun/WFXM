"""R1-10 layering seam: tools → gateway reverse imports decoupled.

Audit source: docs/reviews/project-deep-audit-2026-06-r1to8.md §R1-10 [H]

The v4 architecture puts ``butler/tools/`` below ``butler/gateway/`` in the
dependency graph. 5 tool modules historically lazy-imported gateway state:

  - tools/config_tools.py:50        owner_gate (is_gateway_owner, owner_required_message)
  - tools/registry_tools.py:121     owner_gate
  - tools/builtin_impl.py:98        outbound_bridge (get_gateway_bridge_optional)
  - tools/builtin_impl.py:129       completion_notify (try_push_workflow_failure)
  - tools/delegate_impl.py:220      outbound_bridge
  - tools/delegate_impl.py:252      outbound_bridge
  - tools/multimodal_tools.py:40    minimax_image_gen (LLM provider)
  - tools/multimodal_tools.py:65    minimax_tts (LLM provider)

The fix routes owner/bridge/completion through a new seam in
``butler.execution_context`` and moves the LLM-provider modules to
``butler/transport/multimodal/``. The seam mirrors the R1-3 / R1-9
``EventsSink`` / ``MetricsSink`` Protocol pattern but stays lightweight
(thin shims over the back-compat gateway module + duck-typed orchestrator
hook for future per-orchestrator policy).

This file asserts:

  1. The new seam helpers exist and behave per spec.
  2. The orchestrator duck-typed ``is_owner`` / ``gateway_bridge`` accessors
     take precedence when an orchestrator is bound.
  3. The back-compat fallback to ``butler.gateway.*`` still works when no
     orchestrator is bound (CLI / unit tests).
  4. None of the 5 audited tools files contain a top-level or
     function-local ``from butler.gateway`` import (only the minimax_*
     back-compat shim location is allowed in multimodal_tools, and only
     via the new transport path).
  5. The minimax_* modules have moved to ``butler/transport/multimodal/``
     and the old gateway paths are re-export shims.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pathlib

import pytest

from butler.execution_context import (
    get_current_orchestrator,
    use_execution_context,
)


# ── Files under audit (R1-10 reverse imports) ───────────────────────────

_TOOLS_FILES_UNDER_AUDIT = (
    "butler/tools/config_tools.py",
    "butler/tools/registry_tools.py",
    "butler/tools/multimodal_tools.py",
    "butler/tools/builtin_impl.py",
    "butler/tools/delegate_impl.py",
)

# multimodal_tools is allowed to import minimax_* via the new transport
# path.  Owner / outbound / completion modules MUST NOT appear in any
# tools file (the seam is the only allowed path).
_FORBIDDEN_GATEWAY_MODULES_IN_TOOLS = (
    "butler.gateway.owner_gate",
    "butler.gateway.outbound_bridge",
    "butler.gateway.completion_notify",
)

# minimax_image_gen / minimax_tts may NOT be imported via the gateway
# path from tools (multimodal_tools must use the transport path).  vlm
# stays in gateway so is not listed here.
_FORBIDDEN_MINIMAX_PATHS_IN_TOOLS = (
    "butler.gateway.minimax_image_gen",
    "butler.gateway.minimax_tts",
)


def _offending_imports(source: str) -> list[tuple[str, int]]:
    """Return (module, lineno) for every ``from butler.gateway`` import in source."""
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "butler.gateway" or module.startswith("butler.gateway."):
                offenders.append((module, node.lineno))
    return offenders


def _offending_modules(source: str, targets: tuple[str, ...]) -> list[tuple[str, int]]:
    """Return (module, lineno) for every import whose module starts with any target prefix."""
    tree = ast.parse(source)
    offenders: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        module = ""
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith(targets):
                    offenders.append((alias.name, node.lineno))
            continue
        for target in targets:
            if module == target or module.startswith(target + "."):
                offenders.append((module, node.lineno))
                break
    return offenders


# ── Seam contract: helpers must exist on butler.execution_context ──────


@pytest.mark.module_test
class TestSeamHelpersExported:
    """The seam helpers must be importable from butler.execution_context."""

    def test_is_current_turn_owner_callable(self):
        from butler.execution_context import is_current_turn_owner

        assert callable(is_current_turn_owner)

    def test_get_current_turn_bridge_callable(self):
        from butler.execution_context import get_current_turn_bridge

        assert callable(get_current_turn_bridge)

    def test_try_push_current_turn_workflow_failure_callable(self):
        from butler.execution_context import try_push_current_turn_workflow_failure

        assert callable(try_push_current_turn_workflow_failure)

    def test_owner_required_message_helper(self):
        from butler.execution_context import owner_required_message

        assert callable(owner_required_message)
        assert isinstance(owner_required_message(), str)
        assert owner_required_message()  # non-empty


# ── Seam contract: is_current_turn_owner behaviour ─────────────────────


@pytest.mark.unit
class TestIsCurrentTurnOwner:
    """R1-10 seam behaviour: orchestrator.is_owner wins; back-compat fallback otherwise."""

    def setup_method(self):
        from butler.gateway import owner_gate as og

        self._saved_og_state = {
            "BUTLER_ENV": og.os.environ.get("BUTLER_ENV", ""),
            "BUTLER_PROJECT_CREATE_OPEN": og.os.environ.get(
                "BUTLER_PROJECT_CREATE_OPEN", ""
            ),
            "BUTLER_OWNER_WECHAT_ID": og.os.environ.get("BUTLER_OWNER_WECHAT_ID", ""),
        }

    def teardown_method(self):
        from butler.gateway import owner_gate as og

        for k, v in self._saved_og_state.items():
            if v:
                og.os.environ[k] = v
            else:
                og.os.environ.pop(k, None)

    def test_no_orchestrator_no_allowlist_returns_false(self, monkeypatch):
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_ENV", raising=False)

        from butler.execution_context import is_current_turn_owner

        # Make sure no orchestrator is bound (default in unit tests).
        assert get_current_orchestrator() is None
        assert is_current_turn_owner(platform="wechat", external_id="anyone") is False

    def test_no_orchestrator_dev_bypass_returns_true(self, monkeypatch):
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        monkeypatch.delenv("BUTLER_ENV", raising=False)

        from butler.execution_context import is_current_turn_owner

        assert is_current_turn_owner(platform="wechat", external_id="x") is True

    def test_no_orchestrator_allowlist_match(self, monkeypatch):
        monkeypatch.setenv("WECHAT_ALLOWED_USERS", "alice,bob")
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_ENV", raising=False)

        from butler.execution_context import is_current_turn_owner

        assert is_current_turn_owner(platform="wechat", external_id="alice") is True
        assert is_current_turn_owner(platform="wechat", external_id="charlie") is False

    def test_orchestrator_is_owner_takes_precedence(self):
        """When orchestrator exposes ``is_owner()``, the seam must use it.

        This is the duck-typed hook the wider contract reserves for future
        per-orchestrator policy / per-tenant overrides.
        """
        calls: list[dict] = []

        def _is_owner(*, platform, external_id=None, session_key=""):
            calls.append(
                {
                    "platform": platform,
                    "external_id": external_id,
                    "session_key": session_key,
                }
            )
            return True

        # Set is_owner on the instance dict (not via class) so the seam's
        # ``__dict__``-based duck-typed check sees it as an explicit
        # override and not an auto-created MagicMock attribute.
        orch_stub = type("_O", (), {})()
        orch_stub.__dict__["is_owner"] = _is_owner

        from butler.execution_context import is_current_turn_owner

        with use_execution_context(orch_stub, session_key="wechat:cid:p"):
            assert (
                is_current_turn_owner(
                    platform="wechat", external_id="cid", session_key="wechat:cid:p"
                )
                is True
            )
        assert calls == [
            {
                "platform": "wechat",
                "external_id": "cid",
                "session_key": "wechat:cid:p",
            }
        ]

    def test_orchestrator_is_owner_false_overrides_allowlist(self, monkeypatch):
        """Orchestrator hook wins even when allowlist would have matched."""
        monkeypatch.setenv("WECHAT_ALLOWED_USERS", "alice")
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_ENV", raising=False)

        def _is_owner(*, platform, external_id=None, session_key=""):
            return False

        orch_stub = type("_O", (), {})()
        orch_stub.__dict__["is_owner"] = _is_owner

        from butler.execution_context import is_current_turn_owner

        with use_execution_context(orch_stub):
            assert is_current_turn_owner(platform="wechat", external_id="alice") is False

    def test_orchestrator_without_is_owner_falls_through(self, monkeypatch):
        """Orchestrator present but no ``is_owner`` attribute → back-compat path."""
        monkeypatch.setenv("WECHAT_ALLOWED_USERS", "alice")
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_ENV", raising=False)

        orch_stub = type("_O", (), {})()
        # no is_owner attribute

        from butler.execution_context import is_current_turn_owner

        with use_execution_context(orch_stub):
            assert is_current_turn_owner(platform="wechat", external_id="alice") is True


# ── Seam contract: get_current_turn_bridge behaviour ────────────────────


@pytest.mark.unit
class TestGetCurrentTurnBridge:
    """R1-10 seam: orchestrator.gateway_bridge wins; else gateway singleton."""

    def test_no_orchestrator_returns_gateway_singleton(self, monkeypatch):
        from butler.gateway.outbound_bridge import set_current_bridge
        from butler.execution_context import get_current_turn_bridge

        sentinel = object()
        # Set a thread-local bridge that get_gateway_bridge_optional returns
        set_current_bridge(sentinel)  # type: ignore[arg-type]
        try:
            assert get_current_turn_bridge() is sentinel
        finally:
            set_current_bridge(None)

    def test_orchestrator_gateway_bridge_wins(self):
        class _BridgeStub:
            pass

        orch_bridge = _BridgeStub()
        orch_stub = type("_O", (), {})()
        orch_stub.__dict__["gateway_bridge"] = orch_bridge

        from butler.execution_context import get_current_turn_bridge
        from butler.gateway.outbound_bridge import set_current_bridge

        thread_bridge = object()
        set_current_bridge(thread_bridge)  # type: ignore[arg-type]
        try:
            with use_execution_context(orch_stub):
                assert get_current_turn_bridge() is orch_bridge
        finally:
            set_current_bridge(None)

    def test_orchestrator_none_bridge_falls_through(self):
        orch_stub = type("_O", (), {})()
        orch_stub.__dict__["gateway_bridge"] = None

        from butler.execution_context import get_current_turn_bridge
        from butler.gateway.outbound_bridge import set_current_bridge

        sentinel = object()
        set_current_bridge(sentinel)  # type: ignore[arg-type]
        try:
            with use_execution_context(orch_stub):
                assert get_current_turn_bridge() is sentinel
        finally:
            set_current_bridge(None)


# ── Seam contract: try_push_current_turn_workflow_failure ───────────────


@pytest.mark.unit
class TestTryPushCurrentTurnWorkflowFailure:
    """Thin wrapper — uses the current turn's bridge."""

    def test_is_callable(self):
        from butler.execution_context import try_push_current_turn_workflow_failure

        assert callable(try_push_current_turn_workflow_failure)

    def test_returns_bool(self):
        from butler.execution_context import try_push_current_turn_workflow_failure

        # No orchestrator bound, no thread bridge — gateway fallback returns
        # False (no bridge to push to).
        result = try_push_current_turn_workflow_failure(
            workflow_name="demo",
            error=RuntimeError("boom"),
            session_key="sess",
        )
        assert isinstance(result, bool)
        assert result is False


# ── Layering contract: tools must not import from butler.gateway ────────


@pytest.mark.module_test
@pytest.mark.parametrize("rel_path", _TOOLS_FILES_UNDER_AUDIT)
def test_tools_file_does_not_import_forbidden_gateway_module(rel_path: str):
    """No tools file may import owner_gate / outbound_bridge / completion_notify."""
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    offenders = _offending_modules(text, _FORBIDDEN_GATEWAY_MODULES_IN_TOOLS)
    assert not offenders, (
        f"{rel_path} still imports from {', '.join(_FORBIDDEN_GATEWAY_MODULES_IN_TOOLS)}; "
        "R1-10 layering violation. Offending imports: "
        + ", ".join(f"{mod}:{ln}" for mod, ln in offenders)
    )


@pytest.mark.module_test
@pytest.mark.parametrize("rel_path", _TOOLS_FILES_UNDER_AUDIT)
def test_tools_file_does_not_import_minimax_via_gateway(rel_path: str):
    """minimax_image_gen / minimax_tts must come from butler.transport, not butler.gateway."""
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    offenders = _offending_modules(text, _FORBIDDEN_MINIMAX_PATHS_IN_TOOLS)
    assert not offenders, (
        f"{rel_path} still imports minimax_* from butler.gateway; "
        "R1-10 says minimax_* lives in butler/transport/multimodal/. Offending: "
        + ", ".join(f"{mod}:{ln}" for mod, ln in offenders)
    )


@pytest.mark.module_test
@pytest.mark.parametrize("rel_path", _TOOLS_FILES_UNDER_AUDIT)
def test_tools_file_no_butler_gateway_text(rel_path: str):
    """Source-text fallback: no tools file may contain a `from butler.gateway` string.

    Catches REPL drift / partial edits where AST analysis might pass but
    a stale import string remains.
    """
    text = pathlib.Path(rel_path).read_text(encoding="utf-8")
    assert "from butler.gateway" not in text, (
        f"{rel_path} still contains a `from butler.gateway` import; "
        "R1-10 layering violation is not fully fixed."
    )


# ── Back-compat: gateway.owner_gate / outbound_bridge / completion_notify ─


@pytest.mark.module_test
class TestBackCompatModulesStillImportable:
    """Other code (gateway commands, tests) imports from butler.gateway.*.

    The R1-10 hard constraint: those modules MUST stay importable with
    unchanged public symbols.
    """

    @pytest.mark.parametrize(
        "module, symbols",
        [
            ("butler.gateway.owner_gate", ("is_gateway_owner", "owner_required_message")),
            (
                "butler.gateway.outbound_bridge",
                (
                    "get_gateway_bridge_optional",
                    "get_current_bridge",
                    "set_current_bridge",
                    "GatewayOutboundBridge",
                ),
            ),
            (
                "butler.gateway.completion_notify",
                ("try_push_workflow_failure",),
            ),
        ],
    )
    def test_module_exports_unchanged(self, module: str, symbols: tuple[str, ...]):
        mod = importlib.import_module(module)
        for name in symbols:
            assert hasattr(mod, name), f"{module}.{name} disappeared after R1-10"


# ── Move: minimax_image_gen / minimax_tts live in transport/multimodal/ ─


@pytest.mark.module_test
class TestMinimaxTransportMove:
    """The audit R1-10 second pattern: minimax_* → butler/transport/multimodal/."""

    def test_transport_multimodal_package_exists(self):
        mod = importlib.import_module("butler.transport.multimodal")
        module_file = pathlib.Path(mod.__file__).resolve()  # type: ignore[arg-type]
        assert module_file.parent.name == "multimodal"
        assert module_file.parent.parent.name == "transport"

    def test_minimax_image_gen_lives_in_transport(self):
        from butler.transport.multimodal import minimax_image_gen

        module_file = pathlib.Path(minimax_image_gen.__file__).resolve()
        assert module_file.parent.name == "multimodal"
        assert module_file.parent.parent.name == "transport"
        assert hasattr(minimax_image_gen, "generate_image")
        assert callable(minimax_image_gen.generate_image)

    def test_minimax_tts_lives_in_transport(self):
        from butler.transport.multimodal import minimax_tts

        module_file = pathlib.Path(minimax_tts.__file__).resolve()
        assert module_file.parent.name == "multimodal"
        assert module_file.parent.parent.name == "transport"
        assert hasattr(minimax_tts, "synthesize_speech")
        assert callable(minimax_tts.synthesize_speech)

    def test_old_gateway_path_is_back_compat_shim(self):
        """butler.gateway.minimax_image_gen / minimax_tts re-export the new location."""
        import butler.gateway.minimax_image_gen as old_image
        import butler.transport.multimodal.minimax_image_gen as new_image
        import butler.gateway.minimax_tts as old_tts
        import butler.transport.multimodal.minimax_tts as new_tts

        # Old path is a thin shim — it must re-export the same callable.
        assert old_image.generate_image is new_image.generate_image
        assert old_tts.synthesize_speech is new_tts.synthesize_speech
