"""PR-F2: PEG P0 prompt contracts present in system prompts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_butler_system_has_task_discipline():
    text = (ROOT / "butler/prompts/butler_system.md").read_text(encoding="utf-8")
    assert "禁止静默跳步" in text
    assert "IN-PROGRESS" in text or "进行中" in text


def test_butler_system_has_rag_factuality():
    text = (ROOT / "butler/prompts/butler_system.md").read_text(encoding="utf-8")
    assert "未在记忆" in text or "未找到依据" in text


def test_butler_system_has_tool_error_format_hint():
    text = (ROOT / "butler/prompts/butler_system.md").read_text(encoding="utf-8")
    assert "错误类型" in text
    assert "建议下一步" in text
