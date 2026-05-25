"""Sprint Codex-C2: remote compact, transcript fork/memory, thread_item events."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from butler.core.remote_compact import (
    _extract_summary_from_response,
    _messages_to_compact_input,
    remote_compact_enabled,
    try_remote_summarize,
)
from butler.core.transcript_fork import fork_transcript_at_user_message
from butler.gateway.item_events import SCHEMA, context_compaction_item, thread_item_event
from butler.gateway.item_event_sink import recent_thread_items, record_thread_item
from butler.memory.transcript_memory_pipeline import (
    transcript_rows_to_messages,
    transcript_memory_enabled,
)


def test_remote_compact_disabled_by_default():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BUTLER_REMOTE_COMPACT", None)
    assert remote_compact_enabled() is False
    assert try_remote_summarize([{"role": "user", "content": "x" * 200}]) is None


def test_extract_summary_from_compaction_output():
    data = {
        "output": [
            {"type": "message", "role": "user", "content": "hi"},
            {"type": "compaction", "encrypted_content": "SUMMARY TEXT"},
        ]
    }
    assert _extract_summary_from_response(data) == "SUMMARY TEXT"


def test_messages_to_compact_input():
    items = _messages_to_compact_input(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ]
    )
    assert len(items) == 2
    assert items[0]["type"] == "message"


def test_transcript_fork_at_second_user():
    with tempfile.TemporaryDirectory() as tmp:
        sk = "test_fork_sk"
        from butler.config import get_butler_home

        with patch.object(
            type(get_butler_home()),
            "__call__",
            side_effect=lambda: Path(tmp),
        ):
            pass

        from butler.core import session_transcript as st

        home = Path(tmp)
        with patch("butler.core.session_transcript.get_butler_home", return_value=home):
            with patch("butler.core.transcript_fork.transcript_path", wraps=st.transcript_path):
                path = home / "sessions" / st._safe_segment(sk) / "transcript.jsonl"
                path.parent.mkdir(parents=True, exist_ok=True)
                lines = [
                    json.dumps({"type": "user", "ts": "1", "content_preview": "u1"}),
                    json.dumps({"type": "assistant", "ts": "2", "content_preview": "a1"}),
                    json.dumps({"type": "user", "ts": "3", "content_preview": "u2"}),
                    json.dumps({"type": "assistant", "ts": "4", "content_preview": "a2"}),
                ]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")

                with patch("butler.core.transcript_fork.transcript_path", return_value=path):
                    result = fork_transcript_at_user_message(sk, keep_from_user_index=2)

        assert result.get("ok") is True
        assert result.get("dropped_lines") == 2
        out_lines = path.read_text(encoding="utf-8").splitlines()
        assert out_lines[0].find("transcript_fork") >= 0 or json.loads(out_lines[0]).get("type") == "transcript_fork"
        assert any("u2" in ln for ln in out_lines)


def test_transcript_rows_to_messages():
    rows = [
        {"type": "user", "content_preview": "hello"},
        {"type": "assistant", "content_preview": "hi"},
        {"type": "compact_done"},
    ]
    msgs = transcript_rows_to_messages(rows)
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"


def test_thread_item_event_schema():
    ev = context_compaction_item(
        phase="completed",
        thread_id="sk1",
        tokens_before=100,
        tokens_after=40,
        remote=True,
    )
    d = ev.to_dict()
    assert d["kind"] == "thread_item"
    assert d.get("schema") == SCHEMA
    assert d.get("payload", {}).get("remote") is True


def test_item_event_sink_ring():
    record_thread_item(thread_item_event("message", phase="started", thread_id="t1"))
    items = recent_thread_items(5)
    assert len(items) >= 1
    assert items[-1]["kind"] == "thread_item"


def test_transcript_memory_env_gate():
    with patch.dict(os.environ, {"BUTLER_TRANSCRIPT_MEMORY": "0"}, clear=False):
        from butler.memory.transcript_memory_pipeline import extract_memory_from_transcript

        out = extract_memory_from_transcript("sk")
    assert out.get("ok") is False
    assert out.get("error") == "transcript_memory_disabled"
