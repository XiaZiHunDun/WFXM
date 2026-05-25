"""Remaining roadmap items: tool_modes, crash guard, corpus design, simplicity."""

from __future__ import annotations

from pathlib import Path

from butler.core.research_simplicity import format_simplicity_anchor
from butler.experiments.crash_guard import consecutive_crash_count, should_block_experiment_run
from butler.experiments.ledger import append_record
from butler.memory.corpus_router import route_corpus_query
from butler.project import Project
from butler.tools.project_tools import allowed_tool_names_for_project


def test_tool_modes_review_subset(tmp_path: Path):
    cfg = tmp_path / "project.yaml"
    cfg.write_text(
        "name: r\ntools: [read_file, patch, terminal]\n"
        "tool_modes:\n  review: [read_file, search_files]\n",
        encoding="utf-8",
    )
    proj = Project.from_yaml(cfg)
    allowed = allowed_tool_names_for_project(proj, role="review")
    assert allowed is not None
    assert "read_file" in allowed
    assert "patch" not in allowed


def test_route_design_keywords():
    route = route_corpus_query("DESIGN.md 里 primary 色是什么")
    assert route.scope == "project"
    assert route.reason == "design_keywords"


def test_crash_streak_blocks(tmp_path: Path):
    for _ in range(3):
        append_record(
            tmp_path,
            metric_name="score",
            metric_value=0.0,
            status="crash",
            hypothesis="hyp-a",
        )
    assert consecutive_crash_count(tmp_path, hypothesis="hyp-a") == 3
    blocked, reason = should_block_experiment_run(tmp_path, hypothesis="hyp-a")
    assert blocked and "crash" in reason


def test_simplicity_anchor_nonempty():
    text = format_simplicity_anchor()
    assert "简洁性" in text
    assert "METRIC" in text
