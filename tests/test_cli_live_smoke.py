"""Live CLI smoke: real ``butler chat`` / ``exec`` against MiniMax (or configured provider).

Skipped by default (``pyproject`` ``-m 'not live_llm'``). Run explicitly:

    BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=... PYTHONPATH=. \\
        pytest -m live_llm tests/test_cli_live_smoke.py -v

Optional: ``BUTLER_SMOKE_MINIMAX_MODEL=MiniMax-M2.7-highspeed`` to override model.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from butler.config import get_butler_settings, reload_butler_settings
from butler.main import _cmd_exec
from butler.transport.providers import get_provider
from tests.cli_harness import (
    assert_no_ansi_artifacts,
    assert_welcome_banner,
    run_live_scripted_chat,
)
from tests.test_real_api_smoke import _require_smoke_enabled


pytestmark = pytest.mark.live_llm


def _require_minimax_for_cli() -> None:
    _require_smoke_enabled()
    profile = get_provider("minimax")
    if profile is None:
        pytest.skip("minimax provider profile missing")
    if not profile.resolve_api_key():
        pytest.skip(f"set one of {profile.env_vars} for CLI live smoke")
    reload_butler_settings()
    settings = get_butler_settings()
    mc = settings.get_model_config("butler")
    provider = (mc.provider or settings.default_provider or "minimax").strip().lower()
    if provider != "minimax":
        pytest.skip(
            f"butler role resolves to {provider}/{mc.model}, not minimax — "
            "configure minimax for butler or set BUTLER_SMOKE_MINIMAX_MODEL"
        )
    model_override = os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "").strip()
    if model_override:
        from butler.config import ModelConfig

        settings.set_runtime_model_override(
            "butler", ModelConfig(provider="minimax", model=model_override)
        )


def test_live_cli_chat_one_turn_minimax(tmp_butler_home):
    """Scripted ``butler chat``: welcome → one user turn → /quit (real MiniMax)."""
    _require_minimax_for_cli()
    run = run_live_scripted_chat(
        [
            "请只回复这一行英文，不要其它内容：cli-smoke-ok",
            "/quit",
        ],
        patch_sync_memory=True,
    )

    assert run.exit_code == 0
    assert_welcome_banner(run.output)
    assert run.user_messages == [
        "请只回复这一行英文，不要其它内容：cli-smoke-ok",
    ]
    assert "<think>" not in run.output.lower()
    assert "Memory extraction failed" not in run.output
    assert "can't be used in 'await'" not in run.output
    assert_no_ansi_artifacts(run.output)
    # Model may add punctuation; require token substring.
    assert "cli-smoke-ok" in run.output.lower() or "cli smoke ok" in run.output.lower()
    assert "╭" in run.output  # Rich assistant panel rendered


def test_live_cli_slash_commands_no_extra_llm_turns(tmp_butler_home):
    """Slash-only session should not call the agent loop for normal messages."""
    _require_minimax_for_cli()
    run = run_live_scripted_chat(
        ["/help", "/status", "/quit"],
        patch_sync_memory=True,
    )

    assert run.exit_code == 0
    assert run.user_messages == []
    assert "/projects" in run.output
    assert "Butler 状态" in run.output or "管家" in run.output


def test_live_cli_new_after_turn_minimax(tmp_butler_home):
    """``/new`` after a real turn: no post-session async errors."""
    _require_minimax_for_cli()
    run = run_live_scripted_chat(
        [
            "用一句话说你好",
            "/new",
            "/quit",
        ],
        patch_sync_memory=True,
    )

    assert run.exit_code == 0
    assert "已清空本轮对话上下文" in run.output
    assert "Memory extraction failed" not in run.output
    assert "Skill extraction failed" not in run.output


def test_live_cli_exec_one_shot_minimax(tmp_butler_home, capsys):
    """``butler exec`` one-shot with real MiniMax."""
    _require_minimax_for_cli()
    with patch(
        "butler.transport.auxiliary_client.auxiliary_complete",
        return_value='{"updates": []}',
    ):
        with patch("butler.main._sync_memory"):
            code = _cmd_exec(
                SimpleNamespace(
                    message="请只回复：exec-smoke-ok",
                )
            )

    assert code == 0
    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    assert "<think>" not in combined
    assert "exec-smoke-ok" in combined or "exec smoke" in combined


def test_cli_live_smoke_skipped_without_flag(monkeypatch):
    monkeypatch.delenv("BUTLER_RUN_REAL_API_SMOKE", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _require_smoke_enabled()
