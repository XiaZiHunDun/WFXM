"""Tests for AgentLoop retry policy extraction."""

from butler.core.agent_loop import LoopConfig
from butler.core.retry_policy import retry_delay_for_config


def test_retry_delay_for_config_uses_loop_config_values():
    config = LoopConfig(
        retry_delay=0.5,
        retry_max_delay=10,
        retry_jitter_ratio=0,
    )

    assert retry_delay_for_config(config, 0) == 0.5
    assert retry_delay_for_config(config, 1) == 1.0


def test_retry_delay_for_config_respects_cap():
    config = LoopConfig(
        retry_delay=1,
        retry_max_delay=3,
        retry_jitter_ratio=0,
    )

    assert retry_delay_for_config(config, 10) == 3
