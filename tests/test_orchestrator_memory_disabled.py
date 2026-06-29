"""R2-4: Surface memory_offline flag on orchestrator initialization failure.

Per audit R2-4 in docs/reviews/project-deep-audit-2026-06-r1to8.md:
- orchestrator._initialize_memory_provider at lines 199-210 silently
  disables the entire memory subsystem on failure with logger.warning.
  Agent continues but every recall-dependent turn returns nothing; user
  has no degraded-mode indicator and the model appears to "have no
  memory" without explanation.

Fix:
  1. logger.warning → logger.error(..., exc_info=exc) at the catch site
  2. Add orchestrator.memory_offline: bool field (default False). Set to
     True when init fails; False on success.
  3. Surface flag in collect_memory_layer_stats (memory_offline key).
  4. Render visible line in format_rag_diagnostic_lines: "记忆子系统: 离线
     (initialization failed: <class>)".
  5. Inject a warning chunk into the system prompt (via
     build_dynamic_system_reminder + _assemble_default_system_prompt) so
     the model knows to tell the user "本次对话无历史记忆".
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from butler.config import reload_butler_settings
from butler.project.manager import ProjectManager


def _reset_singletons() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


# ── 1. Exception path: ERROR + exc_info, not WARNING ──────────────────────


@pytest.mark.module_test
class TestLogLevelAndExcInfo:
    def test_init_failure_logs_error_with_exc_info(self, tmp_butler_home, caplog):
        _reset_singletons()
        caplog.set_level(logging.DEBUG, logger="butler.orchestrator")

        def _boom(_self, *a, **kw):
            raise RuntimeError("memory init blew up")

        with patch(
            "butler.memory.facade.ButlerMemoryService", side_effect=_boom
        ):
            from butler.orchestrator import ButlerOrchestrator

            with caplog.at_level(logging.DEBUG):
                orch = ButlerOrchestrator(user_id="u1", channel="test")

        error_records = [
            r
            for r in caplog.records
            if r.levelno >= logging.ERROR
            and "Butler memory provider unavailable" in r.getMessage()
        ]
        assert error_records, (
            "audit R2-4 requires the catch to escalate to ERROR, not WARNING"
        )
        rec = error_records[0]
        assert rec.exc_info is not None, (
            "audit R2-4 requires exc_info so the operator sees the traceback"
        )

        # The deprecated WARNING line must be gone.
        warning_records = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING
            and "Butler memory provider unavailable" in r.getMessage()
        ]
        assert not warning_records, (
            "R2-4 must not log at WARNING — that's the silent-disable pattern"
        )

    def test_init_failure_preserves_none_memory_provider(
        self, tmp_butler_home
    ):
        _reset_singletons()

        def _boom(_self, *a, **kw):
            raise RuntimeError("memory init blew up")

        with patch(
            "butler.memory.facade.ButlerMemoryService", side_effect=_boom
        ):
            from butler.orchestrator import ButlerOrchestrator

            orch = ButlerOrchestrator(user_id="u1", channel="test")

        assert orch.memory_provider is None


# ── 2. memory_offline flag is observable ──────────────────────────────────


@pytest.mark.module_test
class TestMemoryOfflineFlag:
    def test_init_failure_sets_memory_offline_true(self, tmp_butler_home):
        _reset_singletons()

        def _boom(_self, *a, **kw):
            raise RuntimeError("memory init blew up")

        with patch(
            "butler.memory.facade.ButlerMemoryService", side_effect=_boom
        ):
            from butler.orchestrator import ButlerOrchestrator

            orch = ButlerOrchestrator(user_id="u1", channel="test")

        assert orch.memory_offline is True

    def test_init_success_sets_memory_offline_false(self, tmp_butler_home):
        _reset_singletons()
        provider = MagicMock()

        with patch(
            "butler.memory.facade.ButlerMemoryService", return_value=provider
        ):
            from butler.orchestrator import ButlerOrchestrator

            orch = ButlerOrchestrator(user_id="u1", channel="test")

        assert orch.memory_offline is False
        assert orch.memory_provider is provider


# ── 3. /诊断 surface — collect_memory_layer_stats exposes memory_offline ─


@pytest.mark.module_test
class TestDiagnosticsSurface:
    def test_collect_stats_surfaces_memory_offline_true(self):
        from butler.memory.diagnostics import collect_memory_layer_stats

        orch = MagicMock()
        orch.memory_offline = True
        orch.butler_memory = None
        orch._project_memory = None
        # project_manager.get_current may be called; allow it to return None.
        orch.project_manager.get_current.return_value = None

        stats = collect_memory_layer_stats(orch, session_key="s-r2-4")
        assert stats.get("memory_offline") is True

    def test_collect_stats_default_memory_offline_false(self):
        from butler.memory.diagnostics import collect_memory_layer_stats

        orch = MagicMock(spec=["memory_offline", "butler_memory",
                                "_project_memory", "project_manager"])
        orch.memory_offline = False
        orch.butler_memory = None
        orch._project_memory = None
        orch.project_manager.get_current.return_value = None

        stats = collect_memory_layer_stats(orch, session_key="s-r2-4-ok")
        assert stats.get("memory_offline") is False


# ── 4. /诊断 display — format_rag_diagnostic_lines shows memory offline ───


@pytest.mark.module_test
class TestFormatRagDiagnosticShowsMemoryOffline:
    def test_format_emits_memory_offline_line(self):
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        lines = format_rag_diagnostic_lines(
            {
                "semantic_enabled": True,
                "vector_rows": 0,
                "memory_offline": True,
            }
        )
        offline = [
            ln
            for ln in lines
            if "记忆" in ln and ("离线" in ln or "offline" in ln.lower())
        ]
        assert offline, (
            "audit R2-4 requires a visible '记忆子系统: 离线' line in /诊断"
        )

    def test_format_omits_memory_offline_line_when_false(self):
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        lines = format_rag_diagnostic_lines(
            {
                "semantic_enabled": True,
                "vector_rows": 0,
                "memory_offline": False,
            }
        )
        offline = [
            ln
            for ln in lines
            if "记忆" in ln and ("离线" in ln or "offline" in ln.lower())
        ]
        assert not offline, (
            "do not emit memory_offline line when the subsystem is healthy"
        )


# ── 5. System prompt surface — model sees the warning ─────────────────────


@pytest.mark.module_test
class TestSystemPromptWarning:
    def test_dynamic_reminder_contains_offline_warning_when_offline(
        self, tmp_butler_home
    ):
        _reset_singletons()
        provider = MagicMock()

        with patch(
            "butler.memory.facade.ButlerMemoryService", return_value=provider
        ):
            from butler.orchestrator import ButlerOrchestrator

            orch = ButlerOrchestrator(user_id="u1", channel="test")
        # Force the offline flag (init succeeded; we are simulating a
        # later degradation scenario in a future fix; for R2-4 the only
        # way to set the flag is init failure).
        orch.memory_offline = True

        reminder = orch.build_dynamic_system_reminder()
        assert isinstance(reminder, str)
        assert (
            "记忆" in reminder
            and ("离线" in reminder or "offline" in reminder.lower())
        ), (
            "audit R2-4 requires the system reminder to mention memory "
            "is offline so the model can warn the user"
        )

    def test_dynamic_reminder_omits_offline_warning_when_healthy(
        self, tmp_butler_home
    ):
        _reset_singletons()
        provider = MagicMock()

        with patch(
            "butler.memory.facade.ButlerMemoryService", return_value=provider
        ):
            from butler.orchestrator import ButlerOrchestrator

            orch = ButlerOrchestrator(user_id="u1", channel="test")

        reminder = orch.build_dynamic_system_reminder()
        assert isinstance(reminder, str)
        # No offline warning in the healthy path.
        assert not (
            "记忆子系统" in reminder and "离线" in reminder
        ), (
            "healthy orchestrator must not emit the offline warning"
        )

    def test_assembled_prompt_contains_offline_warning_when_offline(
        self, tmp_butler_home
    ):
        _reset_singletons()
        provider = MagicMock()

        with patch(
            "butler.memory.facade.ButlerMemoryService", return_value=provider
        ):
            from butler.orchestrator import ButlerOrchestrator

            orch = ButlerOrchestrator(user_id="u1", channel="test")
        orch.memory_offline = True

        prompt = orch._assemble_default_system_prompt()
        assert isinstance(prompt, str)
        assert (
            "记忆" in prompt
            and ("离线" in prompt or "offline" in prompt.lower())
        ), (
            "audit R2-4 requires the system prompt to surface memory offline"
        )
