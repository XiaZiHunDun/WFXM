"""Turn token budget parsing."""

from __future__ import annotations

from butler.core.loop_types import LoopConfig
from butler.core.turn_token_budget import (
    parse_token_budget_text,
    resolve_turn_budget,
    strip_budget_markers,
    wants_extended_turn,
)


def test_parse_shorthand():
    assert parse_token_budget_text("请做完 +500k") == 500_000


def test_parse_budget_command():
    assert parse_token_budget_text("/budget 2m") == 2_000_000


def test_wants_extended_turn():
    assert wants_extended_turn("本轮尽量做完，把测试跑完")


def test_resolve_increases_iterations():
    cfg = LoopConfig(max_iterations=30)
    new_cfg, budget, cleaned = resolve_turn_budget("长任务 +500k", cfg)
    assert budget == 500_000
    assert new_cfg.max_iterations > 30
    assert "+500k" not in cleaned


def test_strip_markers():
    assert strip_budget_markers("hello +500k") == "hello"
