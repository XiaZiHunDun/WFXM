"""Tests for butler.runtime.delegate_job — async path, failure, and push scenarios."""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from butler.runtime.delegate_job import (
    DelegateJob,
    DelegatePushTarget,
    build_async_delegate_tool_result,
    push_delegate_completion,
)


class TestBuildAsyncDelegateToolResult:
    def test_basic_fields(self):
        raw = build_async_delegate_tool_result(
            task_id="tid-1",
            child_session_key="child-1",
            role="dev",
            task_preview="fix tests",
        )
        payload = json.loads(raw)
        assert payload["success"] is True
        assert payload["background"] is True
        assert payload["async"] is True
        assert payload["task_id"] == "tid-1"
        assert payload["child_session_key"] == "child-1"
        assert "fix tests" in payload["task_preview"]

    def test_category_included(self):
        raw = build_async_delegate_tool_result(
            task_id="tid-2",
            child_session_key="child-2",
            role="content",
            task_preview="write",
            category="novel",
        )
        payload = json.loads(raw)
        assert payload["category"] == "novel"

    def test_task_preview_truncated(self):
        raw = build_async_delegate_tool_result(
            task_id="tid-3",
            child_session_key="c3",
            role="dev",
            task_preview="x" * 500,
        )
        payload = json.loads(raw)
        assert len(payload["task_preview"]) <= 200


class TestPushDelegateCompletion:
    def test_disabled_returns_false(self):
        with patch(
            "butler.gateway.completion_notify.delegate_completion_enabled",
            return_value=False,
        ):
            assert push_delegate_completion(MagicMock()) is False

    def test_bridge_notify(self):
        report = MagicMock()
        bridge = MagicMock()
        with (
            patch(
                "butler.gateway.completion_notify.delegate_completion_enabled",
                return_value=True,
            ),
            patch(
                "butler.gateway.completion_notify.build_report_push_text",
                return_value="text",
            ),
        ):
            result = push_delegate_completion(report, bridge=bridge)
        assert result is True
        bridge.notify_delegate_finished.assert_called_once_with(report)

    def test_bridge_exception_falls_through(self):
        report = MagicMock()
        bridge = MagicMock()
        bridge.notify_delegate_finished.side_effect = RuntimeError("boom")

        with (
            patch(
                "butler.gateway.completion_notify.delegate_completion_enabled",
                return_value=True,
            ),
            patch(
                "butler.gateway.completion_notify.build_report_push_text",
                return_value="text",
            ),
            patch(
                "butler.runtime.notify.push_runtime_message",
                return_value=True,
            ) as mock_push,
        ):
            result = push_delegate_completion(report, bridge=bridge)
        assert result is True
        mock_push.assert_called_once()

    def test_async_push_target(self):
        import asyncio

        loop = asyncio.new_event_loop()
        target = DelegatePushTarget(adapter=MagicMock(), chat_id="c1", loop=loop)
        report = MagicMock()

        with (
            patch(
                "butler.gateway.completion_notify.delegate_completion_enabled",
                return_value=True,
            ),
            patch(
                "butler.gateway.completion_notify.build_report_push_text",
                return_value="text",
            ),
            patch(
                "butler.gateway.completion_notify.deliver_completion_push",
            ) as mock_deliver,
        ):
            result = push_delegate_completion(
                report,
                push_target=target,
                use_async_push=True,
            )
        assert result is True
        loop.close()


class TestRunDelegateJob:
    def test_failure_calls_finalize(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()

        agent = MagicMock()
        agent.run.side_effect = RuntimeError("agent exploded")
        orch = MagicMock()

        job = DelegateJob(
            agent=agent,
            orch=orch,
            user_msg="do stuff",
            raw_user_msg="do stuff",
            role="dev",
            task="do stuff",
            session_key="sess-1",
            child_session_key="child-1",
            task_id="tid-fail",
        )

        with (
            patch("butler.gateway.outbound_bridge.set_current_bridge"),
            patch("butler.execution_context.use_execution_context"),
            patch("butler.runtime.delegate_registry.register_delegate_loop"),
            patch("butler.runtime.delegate_registry.unregister_delegate_loop"),
            patch("butler.core.delegate_semaphore.release_delegate_slot") as mock_release,
            patch(
                "butler.tools.registry._finalize_delegate_failure"
            ) as mock_fail,
        ):
            from butler.runtime.delegate_job import run_delegate_job

            run_delegate_job(job)

        mock_fail.assert_called_once()
        assert mock_fail.call_args.kwargs["task_id"] == "tid-fail"
        mock_release.assert_called_once_with("sess-1")

    def test_success_path_caches_report(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()

        @dataclass
        class FakeResult:
            final_response: str = "done"
            messages: list = None
            status: MagicMock = None
            iterations: int = 1
            tool_calls_made: int = 2
            total_tokens: int = 100
            elapsed_seconds: float = 1.5

            def __post_init__(self):
                if self.messages is None:
                    self.messages = []
                if self.status is None:
                    self.status = MagicMock(value="completed")

        agent = MagicMock()
        agent.run.return_value = FakeResult()
        orch = MagicMock()

        job = DelegateJob(
            agent=agent,
            orch=orch,
            user_msg="do stuff",
            raw_user_msg="do stuff",
            role="dev",
            task="do stuff",
            session_key="sess-2",
            child_session_key="child-2",
            task_id="tid-ok",
        )

        with (
            patch("butler.gateway.outbound_bridge.set_current_bridge"),
            patch("butler.execution_context.use_execution_context"),
            patch("butler.runtime.delegate_registry.register_delegate_loop"),
            patch("butler.runtime.delegate_registry.unregister_delegate_loop"),
            patch("butler.core.delegate_semaphore.release_delegate_slot"),
            patch("butler.session.lifecycle.sync_turn_memory"),
            patch(
                "butler.tools.registry._extract_changes_from_messages",
                return_value=[],
            ),
            patch(
                "butler.tools.registry._extract_issues_from_messages",
                return_value=[],
            ),
            patch(
                "butler.tools.registry._delegate_task_succeeded",
                return_value=True,
            ),
            patch("butler.tools.registry._run_subagent_stop_hooks"),
            patch(
                "butler.runtime.delegate_job._try_attach_diff_summary",
            ),
            patch(
                "butler.runtime.delegate_job.push_delegate_completion",
            ),
            patch("butler.report.cache_report") as mock_cache,
            patch("butler.runtime.task_store.complete_task") as mock_complete,
            patch("butler.core.session_transcript.record_generic_event"),
        ):
            from butler.runtime.delegate_job import run_delegate_job

            run_delegate_job(job)

        mock_cache.assert_called_once()
        report = mock_cache.call_args.args[0]
        assert report.success is True
        mock_complete.assert_called_once()
