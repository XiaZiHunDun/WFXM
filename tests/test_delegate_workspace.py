"""Tests for delegate workspace seeding (ENG-2)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from butler.dev_engine.delegate_workspace import (
    prepare_b9_benchmark_workspace,
    prepare_isolated_workspace_read_state,
)
from butler.tools.delegate_phases import DelegateRunState


def test_prepare_b9_skips_non_benchmark_category():
    state = DelegateRunState(
        category="general",
        category_meta={"category": "general"},
        task="fix",
        context="ctx",
    )
    with patch(
        "butler.dev_engine.b9_delegate_gate.is_benchmark_category",
        return_value=False,
    ) as mock_is:
        prepare_b9_benchmark_workspace(state)
    mock_is.assert_called_once()
    assert state.context == "ctx"


def test_prepare_isolated_read_state_skips_non_drill(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    state = DelegateRunState(
        category="general",
        category_meta={"category": "general"},
        project=SimpleNamespace(workspace=ws),
    )
    with patch(
        "butler.dev_engine.b9_delegate_gate.seed_b9_workspace_read_state",
    ) as mock_seed:
        prepare_isolated_workspace_read_state(state)
    mock_seed.assert_not_called()


def test_prepare_isolated_read_state_drill(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    state = DelegateRunState(
        category="head-to-head",
        category_meta={"category": "head-to-head"},
        child_session_key="sk1",
        project=SimpleNamespace(workspace=Path(ws)),
    )
    with patch(
        "butler.dev_engine.b9_delegate_gate.seed_b9_workspace_read_state",
    ) as mock_seed:
        prepare_isolated_workspace_read_state(state)
    mock_seed.assert_called_once()
