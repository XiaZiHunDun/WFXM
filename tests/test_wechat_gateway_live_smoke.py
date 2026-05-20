"""P3: Optional live LLM smoke for Butler gateway (WeChat code path, no iLink HTTP).

Skipped by default (``not live_llm``). Run explicitly:

    BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=... PYTHONPATH=. \\
        pytest -m live_llm tests/test_wechat_gateway_live_smoke.py -v
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from butler.config import ModelConfig, get_butler_settings, reload_butler_settings
from butler.gateway.message_handler import ButlerMessageHandler
from butler.tenant import tenant_memory_dir
from butler.transport.providers import get_provider
from tests.test_real_api_smoke import _require_smoke_enabled

pytestmark = pytest.mark.live_llm

GW_SMOKE_TOKEN = "gw-smoke-ok"
PROFILE_NICK = "主公LIVEP3"


def _require_minimax_for_gateway() -> None:
    _require_smoke_enabled()
    profile = get_provider("minimax")
    if profile is None:
        pytest.skip("minimax provider profile missing")
    if not profile.resolve_api_key():
        pytest.skip(f"set one of {profile.env_vars} for gateway live smoke")
    reload_butler_settings()
    settings = get_butler_settings()
    mc = settings.get_model_config("butler")
    provider = (mc.provider or settings.default_provider or "minimax").strip().lower()
    if provider != "minimax":
        pytest.skip(f"butler role is {provider}, configure minimax for gateway live smoke")
    model_override = os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "").strip()
    if model_override:
        settings.set_runtime_model_override(
            "butler", ModelConfig(provider="minimax", model=model_override)
        )


def _write_owner_profile(butler_home, entries: list[str]) -> None:
    mem_dir = tenant_memory_dir(butler_home, "default")
    mem_dir.mkdir(parents=True, exist_ok=True)
    (mem_dir / "profile.json").write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.mark.live_llm
def test_live_gateway_one_turn_minimax(tmp_butler_home, tmp_path, monkeypatch):
    """Real MiniMax via gateway message_handler (one user turn)."""
    _require_minimax_for_gateway()
    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))

    from tests.test_gateway_handler import _reset_singletons

    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    sk = "wechat:live-smoke"

    with patch("butler.session_lifecycle.sync_turn_memory", return_value={}):
        out = handler.handle_message(
            f"请只回复这一行英文，不要其它内容：{GW_SMOKE_TOKEN}",
            session_key=sk,
            platform="wechat",
        )

    assert out
    assert "<think>" not in out.lower()
    lowered = out.lower()
    assert GW_SMOKE_TOKEN in lowered or GW_SMOKE_TOKEN.replace("-", " ") in lowered


@pytest.mark.live_llm
def test_live_gateway_owner_profile_nickname(tmp_butler_home, tmp_path, monkeypatch):
    """With profile.json set, ask how Butler addresses the owner (real LLM)."""
    _require_minimax_for_gateway()
    _write_owner_profile(
        tmp_butler_home,
        [f"称呼：{PROFILE_NICK}；微信回复宜短。"],
    )
    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))

    from tests.test_gateway_handler import _reset_singletons

    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    sk = "wechat:live-profile"

    handler.handle_message("/新对话", session_key=sk, platform="wechat")
    with patch("butler.session_lifecycle.sync_turn_memory", return_value={}):
        out = handler.handle_message(
            "用一句话说明你会怎么称呼我（只答称呼，不要解释）。",
            session_key=sk,
            platform="wechat",
        )

    assert PROFILE_NICK in out or "主公" in out


def test_live_gateway_smoke_skipped_without_flag(monkeypatch):
    monkeypatch.delenv("BUTLER_RUN_REAL_API_SMOKE", raising=False)
    with pytest.raises(pytest.skip.Exception):
        _require_smoke_enabled()
