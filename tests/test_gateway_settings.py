"""Gateway config.yaml section + env override."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.gateway import queue_settings as qs
from butler.gateway_settings import (
    format_gateway_inbound_config_source_line,
    format_gateway_queue_config_source_line,
    resolve_gateway_inbound_config,
    resolve_gateway_queue_config,
    vision_api_host,
)


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


def test_save_butler_config_preserves_auxiliary(butler_home):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {"auxiliary": {"compression": {"provider": "deepseek", "model": "deepseek-chat"}}}
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    from butler.config import save_butler_config

    save_butler_config()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["auxiliary"]["compression"]["provider"] == "deepseek"


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


def test_gateway_yaml_queue(butler_home):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "gateway": {
                    "queue": {
                        "mode": "collect",
                        "cap": 12,
                        "drop": "old",
                        "collect_debounce_ms": 800,
                    }
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    q = resolve_gateway_queue_config()
    assert q.mode == "collect"
    assert q.cap == 12
    assert q.drop == "old"
    assert q.collect_debounce_ms == 800
    assert qs.default_queue_mode() == "collect"
    assert qs.queue_cap() == 12
    assert qs.queue_drop_policy() == "old"
    assert qs.collect_debounce_ms("s") == 800


def test_gateway_queue_env_overrides_yaml(butler_home, monkeypatch):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {"gateway": {"queue": {"mode": "collect", "cap": 30, "drop": "old"}}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_MODE", "steer")
    monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_CAP", "5")
    q = resolve_gateway_queue_config()
    assert q.mode == "steer"
    assert q.cap == 5
    assert q.drop == "old"


def test_save_butler_config_preserves_gateway_queue(butler_home):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "gateway": {
                    "inbound_media": {"enabled": True},
                    "queue": {"mode": "followup", "cap": 20},
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    from butler.config import save_butler_config

    save_butler_config()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["gateway"]["queue"]["cap"] == 20


def test_format_gateway_inbound_config_source_line_yaml(butler_home):
    (butler_home / "config.yaml").write_text(
        yaml.safe_dump({"gateway": {"inbound_media": {"enabled": True, "max_chars": 2500}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    line = format_gateway_inbound_config_source_line()
    assert "来源=yaml+env" in line
    assert "入站媒体: 开" in line
    assert "max_chars=2500" in line


def test_format_gateway_queue_config_source_line_yaml(butler_home):
    (butler_home / "config.yaml").write_text(
        yaml.safe_dump(
            {"gateway": {"queue": {"mode": "collect", "cap": 12, "drop": "old"}}},
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    line = format_gateway_queue_config_source_line()
    assert "来源=yaml+env" in line
    assert "mode=collect" in line
    assert "cap=12" in line
    assert "drop=old" in line
    q = resolve_gateway_queue_config()
    assert q.yaml_configured is True


def test_format_gateway_queue_config_source_line_env_default(butler_home):
    reload_butler_settings()
    line = format_gateway_queue_config_source_line()
    assert "来源=env/默认" in line
    assert resolve_gateway_queue_config().yaml_configured is False


def test_format_gateway_inbound_config_source_line_env_default(butler_home):
    reload_butler_settings()
    line = format_gateway_inbound_config_source_line()
    assert "来源=env/默认" in line


def test_gateway_inbound_yaml_configured_false_when_only_queue(butler_home):
    (butler_home / "config.yaml").write_text(
        yaml.safe_dump({"gateway": {"queue": {"mode": "collect", "cap": 10}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    gw = resolve_gateway_inbound_config()
    assert gw.yaml_configured is False
    assert "来源=env/默认" in format_gateway_inbound_config_source_line()


def test_vision_api_host_from_env(monkeypatch):
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
    monkeypatch.delenv("BUTLER_WECHAT_MINIMAX_API_HOST", raising=False)
    host = vision_api_host()
    assert "minimax" in host
