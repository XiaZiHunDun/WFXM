"""Tests for explicit input stage helpers."""

from __future__ import annotations

import pytest

from butler.core.input_stage import begin_input_stage, normalize_inbound_text


@pytest.mark.unit
def test_normalize_inbound_text_strips_zero_width():
    raw = "hello\u200bworld"
    assert normalize_inbound_text(raw) == "helloworld"


@pytest.mark.unit
def test_begin_input_stage_sets_flag(monkeypatch):
    monkeypatch.setenv("BUTLER_INPUT_STAGE", "1")
    diag: dict = {}
    begin_input_stage(diag)
    assert diag.get("input_stage") == "prefetch"
