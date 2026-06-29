"""Tests for butler.core.model_context.resolve_max_output_tokens."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.config import ModelConfig
from butler.core.model_context import resolve_max_output_tokens
from butler.model_resolve import EffectiveModel


def test_resolve_max_output_tokens_from_role_config():
    orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    orch.project_manager.get_current.return_value = None
    with patch("butler.model_resolve.resolve_effective_model") as rem:
        rem.return_value = EffectiveModel(
            config=ModelConfig(max_tokens=8192),
            sources=("system",),
        )
        with patch(
            "butler.project.lead.gateway_loop_role",
            return_value="butler",
        ):
            assert (
                resolve_max_output_tokens(orch, session_key="wechat:x:p", role="butler")
                == 8192
            )


def test_resolve_max_output_tokens_none_when_unset():
    orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    with patch("butler.model_resolve.resolve_effective_model") as rem:
        rem.return_value = EffectiveModel(config=ModelConfig(), sources=("system",))
        with patch(
            "butler.project.lead.gateway_loop_role",
            return_value="butler",
        ):
            assert resolve_max_output_tokens(orch) is None
