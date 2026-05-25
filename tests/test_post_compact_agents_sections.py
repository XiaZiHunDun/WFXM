"""AGENTS.md section extraction for post-compact anchors."""

from __future__ import annotations

from pathlib import Path

from butler.core.agents_md_sections import extract_agents_md_sections


def test_extract_session_startup_and_red_lines(tmp_path: Path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text(
        "# Root\n\n"
        "## Session Startup\n"
        "Check MEMORY.\n\n"
        "## Red Lines\n"
        "Never delete prod.\n\n"
        "## Other\n"
        "ignored.\n",
        encoding="utf-8",
    )
    block = extract_agents_md_sections(
        tmp_path,
        section_names=("Session Startup", "Red Lines"),
    )
    assert "Session Startup" in block
    assert "Red Lines" in block
    assert "Never delete" in block
    assert "ignored" not in block or "Other" not in block.split("Red Lines")[0]


def test_missing_agents_returns_empty(tmp_path: Path):
    assert extract_agents_md_sections(tmp_path) == ""
