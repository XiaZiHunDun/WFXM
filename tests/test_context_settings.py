"""Context config.yaml section + env override."""

from __future__ import annotations

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.context_settings import (
    format_context_config_source_line,
    resolve_context_config,
)
from butler.core import context_budget, instruction_walkup, turn_token_budget
from butler.core import tool_output_prune, tool_prune_policy


@pytest.fixture
def butler_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    yield tmp_path
    reload_butler_settings()


def test_context_yaml_budget(butler_home, monkeypatch):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "context": {
                    "budget": {
                        "output_reserve": 18_000,
                        "compact_reserve": 10_000,
                    }
                }
            },
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.delenv("BUTLER_CONTEXT_OUTPUT_RESERVE", raising=False)
    monkeypatch.delenv("BUTLER_CONTEXT_COMPACT_RESERVE", raising=False)
    cfg = resolve_context_config()
    assert cfg.yaml_configured is True
    assert cfg.budget.output_reserve == 18_000
    assert cfg.budget.compact_reserve == 10_000
    assert context_budget.get_output_reserve_tokens() == 18_000
    eff = context_budget.get_effective_context_window(128_000)
    auto = context_budget.get_auto_compact_threshold(128_000)
    assert eff == 128_000 - 18_000
    assert auto == eff - 10_000


def test_context_env_overrides_yaml(butler_home, monkeypatch):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"context": {"budget": {"output_reserve": 25_000}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.setenv("BUTLER_CONTEXT_OUTPUT_RESERVE", "15000")
    assert resolve_context_config().budget.output_reserve == 15_000


def test_context_turn_budget_and_tool_prune_yaml(butler_home, monkeypatch):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "context": {
                    "turn_budget": {"max_iterations": 45, "default": 300_000},
                    "tool_prune": {"keep_recent": 6, "backward_minimum": 15_000},
                    "instruction_walkup": {"max_files": 2, "enabled": False},
                }
            },
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.delenv("BUTLER_TURN_BUDGET_MAX_ITERATIONS", raising=False)
    monkeypatch.delenv("BUTLER_TOOL_PRUNE_KEEP_RECENT", raising=False)
    monkeypatch.delenv("BUTLER_TOOL_PRUNE_BACKWARD_MINIMUM", raising=False)
    monkeypatch.delenv("BUTLER_INSTRUCTION_WALKUP", raising=False)
    cfg = resolve_context_config()
    assert cfg.turn_budget.max_iterations == 45
    assert cfg.turn_budget.default_tokens == 300_000
    assert cfg.tool_prune.keep_recent == 6
    assert cfg.tool_prune.backward_minimum == 15_000
    assert cfg.instruction_walkup.max_files == 2
    assert cfg.instruction_walkup.enabled is False
    assert tool_prune_policy.keep_recent_tool_messages() == 6
    assert tool_output_prune.prune_minimum_chars() == 15_000
    assert not instruction_walkup.walkup_enabled()


def test_format_context_config_source_line_yaml(butler_home, monkeypatch):
    (butler_home / "config.yaml").write_text(
        yaml.safe_dump({"context": {"budget": {"compact_reserve": 11_000}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    monkeypatch.delenv("BUTLER_CONTEXT_COMPACT_RESERVE", raising=False)
    line = format_context_config_source_line()
    assert "来源=yaml+env" in line
    assert "压缩缓冲=11000" in line


def test_format_context_config_source_line_env_default(butler_home):
    reload_butler_settings()
    line = format_context_config_source_line()
    assert "来源=env/默认" in line


def test_save_butler_config_preserves_context(butler_home):
    cfg_path = butler_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"context": {"budget": {"compact_reserve": 12_000}}}),
        encoding="utf-8",
    )
    reload_butler_settings()
    from butler.config import save_butler_config

    save_butler_config()
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["context"]["budget"]["compact_reserve"] == 12_000
