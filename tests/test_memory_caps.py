"""Tests for MEMORY.md size caps."""

from butler.memory.memory_caps import truncate_memory_text


def test_truncate_memory_text_lines_before_bytes(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_MAX_LINES", "3")
    monkeypatch.setenv("BUTLER_MEMORY_MAX_BYTES", "100000")
    text = "\n".join(f"line {i}" for i in range(10))
    out, truncated = truncate_memory_text(text)
    assert truncated
    assert out.startswith("line 0")
    assert "WARNING" in out
    assert "line 9" not in out


def test_truncate_memory_text_bytes_at_newline(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_MAX_LINES", "0")
    monkeypatch.setenv("BUTLER_MEMORY_MAX_BYTES", "50")
    text = "short\n" + ("x" * 200)
    out, truncated = truncate_memory_text(text)
    assert truncated
    assert "WARNING" in out
