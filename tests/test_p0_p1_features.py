"""Tests for P0/P1 feature implementations:
- WeChat file auto-parsing (inbound_media document detection)
- Inbound queue persistence (JSONL-backed durable queue)
- Session summary injection (context continuity)
- Reminder tools (set/list/cancel/poll)
- Git push approval gate
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── #1 WeChat file auto-parsing ──────────────────────────────


class TestInboundMediaDocuments:
    def test_is_document_path_pdf(self):
        from butler.gateway.inbound_media import _is_document_path

        assert _is_document_path("/tmp/file.pdf", "application/pdf") is True

    def test_is_document_path_docx(self):
        from butler.gateway.inbound_media import _is_document_path

        assert _is_document_path("/tmp/file.docx", "application/vnd.openxml") is True

    def test_is_document_path_image_false(self):
        from butler.gateway.inbound_media import _is_document_path

        assert _is_document_path("/tmp/file.jpg", "image/jpeg") is False

    def test_pair_media_detects_documents(self):
        from butler.gateway.inbound_media import _pair_media
        from butler.gateway.platforms.types import MessageEvent, MessageType

        event = MessageEvent(
            text="",
            message_type=MessageType.DOCUMENT,
            media_urls=["/tmp/file.pdf", "/tmp/img.jpg"],
            media_types=["application/pdf", "image/jpeg"],
        )
        images, voices, documents = _pair_media(event)
        assert len(documents) == 1
        assert documents[0] == "/tmp/file.pdf"
        assert len(images) == 1

    @patch("butler.gateway.inbound_media.inbound_media_enabled", return_value=True)
    def test_build_inbound_user_text_with_document(self, _mock_enabled):
        from butler.gateway.inbound_media import build_inbound_user_text
        from butler.gateway.platforms.types import MessageEvent, MessageType

        event = MessageEvent(
            text="这是合同文件",
            message_type=MessageType.DOCUMENT,
            media_urls=["/tmp/contract.pdf"],
            media_types=["application/pdf"],
        )
        with patch("butler.tools.document_reader.convert_document") as mock_convert:
            mock_convert.return_value = {"ok": True, "format": "pdf", "chars": 500, "text": "合同正文内容"}
            result = build_inbound_user_text(event)
            assert "微信文件" in result
            assert "合同正文内容" in result


# ── #2 Inbound queue persistence ─────────────────────────────


class TestQueuePersistence:
    def test_persist_enqueue_and_restore(self, tmp_path):
        from butler.gateway.message_queue import (
            QueuedInbound,
            _persist_enqueue,
            restore_persisted_queue,
            _QUEUES,
            _LOCK,
        )

        with patch("butler.gateway.message_queue._queue_persist_enabled", return_value=True), \
             patch("butler.gateway.message_queue._queue_persist_dir", return_value=tmp_path):
            item = QueuedInbound(
                text="测试消息",
                priority="next",
                platform="wechat",
                persist_id="test123",
            )
            _persist_enqueue("wechat:user1:proj", item)

            jsonl_files = list(tmp_path.glob("*.jsonl"))
            assert len(jsonl_files) == 1

            safe_key = jsonl_files[0].stem
            with _LOCK:
                _QUEUES.pop(safe_key, None)

            restored = restore_persisted_queue()
            assert restored == 1

            with _LOCK:
                bucket = _QUEUES.get(safe_key)
                assert bucket is not None
                assert len(bucket) == 1
                assert bucket[0].text == "测试消息"
                _QUEUES.pop(safe_key, None)

    def test_persist_remove(self, tmp_path):
        from butler.gateway.message_queue import (
            QueuedInbound,
            _persist_enqueue,
            _persist_remove,
        )

        with patch("butler.gateway.message_queue._queue_persist_enabled", return_value=True), \
             patch("butler.gateway.message_queue._queue_persist_dir", return_value=tmp_path):
            item = QueuedInbound(text="msg1", priority="next", persist_id="aaa111")
            _persist_enqueue("sk1", item)
            _persist_remove("sk1", "aaa111")

            jsonl_files = list(tmp_path.glob("*.jsonl"))
            assert len(jsonl_files) == 0 or jsonl_files[0].read_text().strip() == ""

    def test_persist_clear(self, tmp_path):
        from butler.gateway.message_queue import (
            QueuedInbound,
            _persist_enqueue,
            _persist_clear,
        )

        with patch("butler.gateway.message_queue._queue_persist_enabled", return_value=True), \
             patch("butler.gateway.message_queue._queue_persist_dir", return_value=tmp_path):
            item = QueuedInbound(text="msg", priority="next", persist_id="bbb222")
            _persist_enqueue("sk2", item)
            _persist_clear("sk2")

            assert not list(tmp_path.glob("*.jsonl"))


# ── #5 Session summary injection ─────────────────────────────


class TestSessionSummaryInjection:
    def test_inject_with_summary_file(self, tmp_path):
        from butler.gateway.message_handler import _inject_previous_session_summary

        summary = {
            "session_id": "prev-001",
            "project": "butler",
            "turns": 15,
            "persona": ["喜欢简洁回复"],
            "preference": [],
            "experience": ["微信网关调优"],
        }
        butler_dir = tmp_path / ".butler"
        butler_dir.mkdir(exist_ok=True)
        (butler_dir / "session_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False), encoding="utf-8"
        )

        mock_loop = MagicMock()
        mock_loop._messages = []

        mock_project = MagicMock()
        mock_project.workspace = str(tmp_path)

        _inject_previous_session_summary(mock_loop, mock_project)

        assert len(mock_loop._messages) == 1
        msg = mock_loop._messages[0]
        assert msg["role"] == "system"
        assert "上次会话摘要" in msg["content"]
        assert "butler" in msg["content"]
        assert "微信网关调优" in msg["content"]

    def test_inject_without_summary_file(self, tmp_path):
        from butler.gateway.message_handler import _inject_previous_session_summary

        mock_loop = MagicMock()
        mock_loop._messages = []

        mock_project = MagicMock()
        mock_project.workspace = str(tmp_path)

        _inject_previous_session_summary(mock_loop, mock_project)
        assert len(mock_loop._messages) == 0


# ── #6 Reminder tools ────────────────────────────────────────


class TestReminderTools:
    def test_set_reminder(self, tmp_path):
        from butler.tools.reminder import tool_set_reminder

        with patch("butler.tools.reminder._reminders_dir", return_value=tmp_path):
            result = json.loads(tool_set_reminder(message="开会", when="30分钟"))
            assert result["ok"] is True
            assert result["message"] == "开会"
            assert "id" in result
            assert "due" in result

    def test_set_reminder_absolute_time(self, tmp_path):
        from butler.tools.reminder import tool_set_reminder

        with patch("butler.tools.reminder._reminders_dir", return_value=tmp_path):
            result = json.loads(tool_set_reminder(message="吃饭", when="23:59"))
            assert result["ok"] is True

    def test_set_reminder_bad_time(self, tmp_path):
        from butler.tools.reminder import tool_set_reminder

        with patch("butler.tools.reminder._reminders_dir", return_value=tmp_path):
            result = json.loads(tool_set_reminder(message="test", when="昨天"))
            assert result["ok"] is False

    def test_list_reminders(self, tmp_path):
        from butler.tools.reminder import tool_set_reminder, tool_list_reminders

        with patch("butler.tools.reminder._reminders_dir", return_value=tmp_path):
            tool_set_reminder(message="r1", when="1小时")
            tool_set_reminder(message="r2", when="2小时")
            result = json.loads(tool_list_reminders())
            assert result["ok"] is True
            assert result["pending"] == 2

    def test_cancel_reminder(self, tmp_path):
        from butler.tools.reminder import tool_set_reminder, tool_cancel_reminder, tool_list_reminders

        with patch("butler.tools.reminder._reminders_dir", return_value=tmp_path):
            created = json.loads(tool_set_reminder(message="cancel me", when="1天"))
            rid = created["id"]
            cancel_result = json.loads(tool_cancel_reminder(reminder_id=rid))
            assert cancel_result["ok"] is True

            remaining = json.loads(tool_list_reminders())
            assert remaining["pending"] == 0

    def test_poll_due_reminders(self, tmp_path):
        from butler.tools.reminder import tool_set_reminder, poll_due_reminders

        with patch("butler.tools.reminder._reminders_dir", return_value=tmp_path):
            tool_set_reminder(message="overdue", when="1秒")
            time.sleep(1.5)
            fired = poll_due_reminders()
            assert len(fired) == 1
            assert fired[0]["message"] == "overdue"
            assert fired[0]["status"] == "fired"

    def test_parse_relative_time(self):
        from butler.tools.reminder import _parse_relative_time

        assert _parse_relative_time("30分钟") == 1800
        assert _parse_relative_time("2小时") == 7200
        assert _parse_relative_time("1天") == 86400
        assert _parse_relative_time("5min") == 300
        assert _parse_relative_time("随便") is None

    def test_register_reminder_tools(self):
        from butler.tools.reminder import register_reminder_tools

        registered = {}

        def mock_register(name, **kw):
            registered[name] = kw

        register_reminder_tools(mock_register)
        assert "set_reminder" in registered
        assert "list_reminders" in registered
        assert "cancel_reminder" in registered


# ── #9 Git push approval gate ─────────────────────────────────


class TestGitPush:
    def test_push_disabled(self):
        from butler.tools.git_tools import _tool_git_push

        with patch.dict(os.environ, {"BUTLER_ENABLE_GIT": "1", "BUTLER_ENABLE_GIT_WRITE": "1"}):
            with patch.dict(os.environ, {"BUTLER_ENABLE_GIT_PUSH": ""}, clear=False):
                result = json.loads(_tool_git_push())
                assert result.get("code") == "GIT_PUSH_DISABLED"

    def test_push_force_blocked(self):
        from butler.tools.git_tools import _tool_git_push

        with patch.dict(os.environ, {
            "BUTLER_ENABLE_GIT": "1",
            "BUTLER_ENABLE_GIT_WRITE": "1",
            "BUTLER_ENABLE_GIT_PUSH": "1",
        }):
            result = json.loads(_tool_git_push(force=True))
            assert result.get("code") == "GIT_FORCE_PUSH_BLOCKED"

    def test_push_protected_branch(self):
        from butler.tools.git_tools import _tool_git_push

        with patch.dict(os.environ, {
            "BUTLER_ENABLE_GIT": "1",
            "BUTLER_ENABLE_GIT_WRITE": "1",
            "BUTLER_ENABLE_GIT_PUSH": "1",
        }):
            with patch("butler.tools.git_tools._resolve_git_workdir", return_value=(Path("/tmp"), None)):
                result = json.loads(_tool_git_push(branch="main"))
                assert result.get("code") == "GIT_PROTECTED_BRANCH"

    def test_push_requires_approval(self):
        from butler.tools.git_tools import _tool_git_push

        with patch.dict(os.environ, {
            "BUTLER_ENABLE_GIT": "1",
            "BUTLER_ENABLE_GIT_WRITE": "1",
            "BUTLER_ENABLE_GIT_PUSH": "1",
        }):
            with patch("butler.tools.git_tools._resolve_git_workdir", return_value=(Path("/tmp"), None)), \
                 patch("butler.tools.git_tools._run_git", return_value={"stdout": "feature-x\n", "exit_code": 0}), \
                 patch("butler.tools.terminal_approval.check_approval", return_value=False):
                result = json.loads(_tool_git_push())
                assert result.get("code") == "PUSH_REQUIRES_APPROVAL"


# ── #3 Outbox replay ─────────────────────────────────────────


class TestOutboxReplay:
    def test_replay_pending_outbox_empty(self):
        from butler.gateway.runner import _replay_pending_outbox

        _replay_pending_outbox([])

    def test_replay_pending_outbox_with_entries(self):
        from butler.gateway.runner import _replay_pending_outbox

        mock_adapter = MagicMock()
        mock_adapter.send_text = MagicMock()

        with patch("butler.gateway.durable_outbox.durable_outbox_enabled", return_value=True), \
             patch("butler.gateway.durable_outbox.list_pending_outbox", return_value=[
                 {"id": "e1", "chat_id": "user1", "text": "hello"},
             ]), \
             patch("butler.gateway.durable_outbox.mark_outbox_sent") as mock_mark:
            _replay_pending_outbox([mock_adapter])
            mock_adapter.send_text.assert_called_once_with("user1", "hello")
            mock_mark.assert_called_once_with("e1")
