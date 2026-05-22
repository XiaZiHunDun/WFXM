"""auxiliary section loaded via ButlerSettings."""

import yaml

from butler.config import reload_butler_settings


def test_auxiliary_from_config_yaml(tmp_butler_home, monkeypatch):
    (tmp_butler_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "auxiliary": {
                    "compression": {"provider": "deepseek", "model": "deepseek-chat"},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    settings = reload_butler_settings()
    cfg = settings.get_auxiliary_task_config("compression")
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
