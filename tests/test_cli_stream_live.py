"""Live stream mode tests for butler.cli.stream (phase A)."""

from __future__ import annotations

import pytest

from butler.cli.session_ui import ChatSessionUI
from butler.core.agent_loop import LoopStatus
from tests.cli_harness import (
    capture_console,
    count_substring,
    make_loop_result,
    rendered_text,
)


@pytest.mark.module_test
class TestLiveStreamRenderer:
    def test_on_delta_emits_complete_lines(self):
        console, buf = capture_console()
        from butler.cli.stream import StreamRenderer

        stream = StreamRenderer(console, title="莎丽", mode="live")
        stream.on_delta("第一行\n第二")
        stream.on_delta("行\n")
        stream.flush()

        text = rendered_text(buf)
        assert "第一行" in text
        assert "第二行" in text
        assert stream.streamed_live
        assert stream.lines_emitted >= 2

    def test_boundary_closes_box_before_tools(self):
        console, buf = capture_console()
        from butler.cli.stream import StreamRenderer

        stream = StreamRenderer(console, title="莎丽", mode="live")
        stream.on_delta("段落一\n")
        stream.on_boundary()
        stream.on_delta("段落二\n")
        stream.flush()
        text = rendered_text(buf)
        assert text.count("╰") >= 1
        assert "段落一" in text
        assert "段落二" in text

    def test_finish_turn_skips_duplicate_panel_when_streamed(self):
        console, buf = capture_console()
        from butler.cli.stream import StreamRenderer

        ui = ChatSessionUI(console, stream_title="莎丽")
        stream = StreamRenderer(console, title="莎丽", mode="live")
        stream.on_delta("你好！\n")
        stream.flush()
        ui.finish_turn(make_loop_result("你好！"), stream)
        text = rendered_text(buf)
        assert count_substring(text, "你好！") == 1
        assert "╭" in text

    def test_live_mode_wraps_long_lines_without_newlines(self):
        console, buf = capture_console()
        from butler.cli.stream import StreamRenderer

        stream = StreamRenderer(console, title="莎丽", mode="live")
        stream.on_delta("a" * 200)
        stream.flush()
        text = rendered_text(buf)
        assert stream.lines_emitted >= 2
        assert "a" in text

    def test_buffer_mode_uses_panel_on_finish(self):
        from tests.cli_harness import finish_turn_capture

        out = finish_turn_capture(
            stream_chunks=["缓冲模式"],
            final_response="缓冲模式",
            title="莎丽",
        )
        assert "缓冲模式" in out
