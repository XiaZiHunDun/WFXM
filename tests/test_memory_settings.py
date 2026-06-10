"""Memory config.yaml section + env override (Phase B2)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.memory.memory_caps import memory_index_caps
from butler.memory.semantic_config import (
    hybrid_vector_weight,
    semantic_memory_enabled,
)
from butler.memory_settings import format_memory_config_source_line, resolve_memory_config


@pytest.fixture
def butler_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    yield tmp_path
    reload_butler_settings()


def test_memory_yaml_semantic_and_hybrid(butler_home, monkeypatch):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "memory": {
                    "semantic_enabled": True,
                    "hybrid": {"vector_weight": 0.7},
                    "index": {"max_lines": 150, "max_bytes": 12000},
                    "ranking": {"half_life_days": 14, "access_boost": 0.2},
                    "search_limit": 12,
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.delenv("BUTLER_SEMANTIC_MEMORY", raising=False)
    monkeypatch.delenv("BUTLER_VECTOR_HYBRID_WEIGHT", raising=False)
    monkeypatch.delenv("BUTLER_MEMORY_MAX_LINES", raising=False)
    cfg = resolve_memory_config()
    assert cfg.semantic_enabled is True
    assert cfg.vector_hybrid_weight == 0.7
    assert cfg.search_limit == 12
    assert cfg.max_lines == 150
    assert cfg.half_life_days == 14.0
    assert semantic_memory_enabled() is True
    assert hybrid_vector_weight() == 0.7
    caps = memory_index_caps()
    assert caps["max_lines"] == 150
    assert caps["max_bytes"] == 12000


def test_memory_env_overrides_yaml(butler_home, monkeypatch):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"memory": {"semantic_enabled": True, "hybrid": {"vector_weight": 0.9}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
    monkeypatch.setenv("BUTLER_VECTOR_HYBRID_WEIGHT", "0.3")
    cfg = resolve_memory_config()
    assert cfg.semantic_enabled is False
    assert cfg.vector_hybrid_weight == 0.3


def test_save_butler_config_preserves_memory(butler_home):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"memory": {"semantic_enabled": True, "search_limit": 10}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    from butler.config import save_butler_config

    save_butler_config()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["memory"]["search_limit"] == 10


def test_format_memory_config_source_line_yaml(butler_home):
    (butler_home / "config.yaml").write_text(
        yaml.safe_dump({"memory": {"semantic_enabled": True}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    line = format_memory_config_source_line()
    assert "来源=yaml+env" in line
    assert "向量=开" in line
