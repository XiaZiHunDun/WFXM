"""Gateway config.yaml section + env override."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.gateway_settings import resolve_gateway_inbound_config, vision_api_host


@pytest.fixture
def butler_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    yield tmp_path
    reload_butler_settings()


def test_gateway_yaml_inbound_media(butler_home):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "gateway": {
                    "inbound_media": {
                        "enabled": True,
                        "max_chars": 2500,
                        "vision": {"endpoint": "coding_plan/vlm", "timeout_seconds": 30},
                        "speech": {"stt_provider": "local", "whisper_model": "base"},
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    gw = resolve_gateway_inbound_config()
    assert gw.max_chars == 2500
    assert gw.vision.timeout_seconds == 30.0
    assert gw.speech.whisper_model == "base"


def test_gateway_env_overrides_yaml(butler_home, monkeypatch):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"gateway": {"inbound_media": {"max_chars": 4000}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_WECHAT_MEDIA_MAX_CHARS", "1800")
    gw = resolve_gateway_inbound_config()
    assert gw.max_chars == 1800


def test_save_butler_config_preserves_gateway(butler_home):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"gateway": {"inbound_media": {"enabled": True}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    from butler.config import save_butler_config

    save_butler_config()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert "gateway" in data
    assert data["gateway"]["inbound_media"]["enabled"] is True


def test_vision_api_host_from_env(monkeypatch):
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
    monkeypatch.delenv("BUTLER_WECHAT_MINIMAX_API_HOST", raising=False)
    host = vision_api_host()
    assert "minimax" in host
