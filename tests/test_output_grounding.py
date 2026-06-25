"""Tests for post-LLM output grounding."""

from __future__ import annotations

import pytest

from butler.core.output_grounding import apply_output_grounding


@pytest.mark.unit
def test_memory_prefetch_low_overlap_adds_disclaimer(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_PREFETCH_GROUNDING", "1")
    diag = {
        "memory_prefetch_retrieval_total": 3,
        "memory_prefetch_snippets": ["用户偏好使用 python 3.11", "项目根目录在 /tmp/demo"],
    }
    reply = "x" * 100
    out = apply_output_grounding("问题", reply, diag)
    assert "记忆重叠较低" in out
    assert diag.get("memory_prefetch_grounding") == "low_overlap_disclaimer"


@pytest.mark.unit
def test_memory_prefetch_overlap_ok_no_disclaimer(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_PREFETCH_GROUNDING", "1")
    diag = {
        "memory_prefetch_retrieval_total": 2,
        "memory_prefetch_snippets": ["用户偏好使用 python 3.11"],
    }
    reply = "根据记录，用户偏好使用 python 3.11 进行开发。" + ("补充说明。" * 15)
    out = apply_output_grounding("偏好?", reply, diag)
    assert "记忆重叠较低" not in out
    assert diag.get("memory_prefetch_grounding") == "ok"


@pytest.mark.unit
def test_calc_grounding_appends_note_when_reply_wrong(monkeypatch):
    monkeypatch.setenv("BUTLER_CALC_GROUNDING", "1")
    monkeypatch.setenv("BUTLER_MEMORY_PREFETCH_GROUNDING", "0")
    out = apply_output_grounding("3+5等于多少", "等于 9。", {})
    assert "演算校验" in out
    assert "8" in out
