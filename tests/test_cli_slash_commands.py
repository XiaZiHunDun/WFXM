"""Tests for butler.cli.slash_commands."""

from __future__ import annotations

import pytest

from butler.cli.slash_commands import (
    build_slash_completer,
    is_known_slash_command,
    normalize_slash_token,
)


@pytest.mark.module_test
class TestSlashRegistry:
    @pytest.mark.parametrize(
        "cmd",
        ["/help", "/status", "/health", "/诊断", "/new", "/quit", "/q"],
    )
    def test_known_commands(self, cmd):
        assert is_known_slash_command(cmd)

    def test_unknown_command(self):
        assert not is_known_slash_command("/not-a-command")

    @pytest.mark.parametrize(
        "cmd",
        ["/记忆待审", "/记忆图谱", "/批准记忆", "/拒绝记忆"],
    )
    def test_memory_slash_commands(self, cmd):
        assert is_known_slash_command(cmd)

    def test_model_with_args_is_known_prefix(self):
        assert is_known_slash_command("/model butler minimax/M2.7")

    def test_normalize_aliases(self):
        assert normalize_slash_token("/q") == "quit"
        assert normalize_slash_token("/诊断") == "health"


@pytest.mark.module_test
def test_slash_completer_yields_help():
    completer = build_slash_completer()
    from prompt_toolkit.document import Document

    doc = Document("/he", cursor_position=3)
    completions = list(completer.get_completions(doc, None))
    assert any("/help" in c.text for c in completions)
