"""Tests for EXT-3 document ingest."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from butler.memory.document_ingest import (
    ingest_enabled,
    ingest_workspace,
    pilot_dirs_from_stack,
)


@pytest.mark.unit
def test_pilot_dirs_from_stack(tmp_path: Path):
    ws = tmp_path / "proj"
    (ws / "docs" / "research").mkdir(parents=True)
    (ws / "stack.yaml").write_text(
        "ingest_pilot_dirs:\n  - docs/research\n",
        encoding="utf-8",
    )
    dirs = pilot_dirs_from_stack(ws)
    assert len(dirs) == 1
    assert dirs[0].name == "research"


@pytest.mark.unit
def test_ingest_workspace_writes_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BUTLER_INGEST_ENABLED", "1")
    assert ingest_enabled() is True
    ws = tmp_path / "proj"
    pilot = ws / "docs" / "research"
    pilot.mkdir(parents=True)
    (pilot / "note.pdf").write_bytes(b"%PDF-1.4 fake")
    (ws / "stack.yaml").write_text("ingest_pilot_dirs:\n  - docs/research\n", encoding="utf-8")

    with patch(
        "butler.memory.document_ingest._convert_to_markdown",
        return_value="# Converted\n\nBody from pdf.",
    ):
        result = ingest_workspace(ws)
    assert result["ok"] is True
    assert result["written"] == 1
    out = ws / ".butler" / "ingest" / "note.md"
    assert out.is_file()
    assert "Body from pdf" in out.read_text(encoding="utf-8")


@pytest.mark.unit
def test_ingest_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("BUTLER_INGEST_ENABLED", raising=False)
    ws = tmp_path / "proj"
    (ws / "docs").mkdir(parents=True)
    (ws / "stack.yaml").write_text("ingest_pilot_dirs:\n  - docs\n", encoding="utf-8")
    result = ingest_workspace(ws)
    assert result["ok"] is False
    assert "BUTLER_INGEST_ENABLED" in str(result.get("error", ""))
