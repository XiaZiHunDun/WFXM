"""Execution surface diagnostics and preflight skill sync checks."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from butler.ops.execution_surface_diagnostics import (
    check_legacy_global_skills,
    collect_execution_surface_stats,
    format_execution_surface_diagnostic_lines,
    project_skills_sync_issues,
)


def test_project_skills_sync_detects_missing_runtime_copy(tmp_path: Path):
    git_skills = tmp_path / "skills"
    git_skills.mkdir()
    (git_skills / "lead.md").write_text("---\nname: lead\n---\n", encoding="utf-8")
    issues = project_skills_sync_issues(tmp_path)
    assert any("缺同步" in i for i in issues)


def test_project_skills_sync_detects_stale_mtime(tmp_path: Path):
    git_skills = tmp_path / "skills"
    runtime = tmp_path / ".butler" / "skills"
    git_skills.mkdir()
    runtime.mkdir(parents=True, exist_ok=True)
    dest = runtime / "lead.md"
    src = git_skills / "lead.md"
    dest.write_text("old", encoding="utf-8")
    src.write_text("new", encoding="utf-8")
    import os
    import time

    old = time.time() - 3600
    os.utime(dest, (old, old))
    issues = project_skills_sync_issues(tmp_path)
    assert any("过期" in i for i in issues)


def test_legacy_global_skills_warns_when_files_present(tmp_path: Path):
    legacy = tmp_path / "skills"
    legacy.mkdir()
    (legacy / "old.md").write_text("x", encoding="utf-8")
    tenant = tmp_path / "tenants" / "default" / "skills"
    tenant.mkdir(parents=True)
    (tenant / "new.md").write_text("y", encoding="utf-8")
    warns = check_legacy_global_skills(tmp_path)
    assert warns
    assert "遗留" in warns[0]


def test_format_execution_surface_lines():
    stats = {
        "skill_injection_mode": "fallback",
        "skill_injection_reason": "experience_hit_skip_unverified_skill",
        "tool_selector_output": 12,
        "tool_selector_input": 74,
        "tool_selector_dropped": 62,
        "mcp_enabled": True,
        "mcp_deferred": True,
        "mcp_promoted_tools": [],
    }
    lines = format_execution_surface_diagnostic_lines(stats)
    text = "\n".join(lines)
    assert "执行面" in text
    assert "fallback" in text
    assert "工具预选" in text


def test_collect_stats_from_health_dict():
    orch = MagicMock()  # noqa: magicmock-no-spec
    orch._skill_manager.list_skills.return_value = [{"name": "a"}]
    orch.project_manager.get_current.return_value = None
    health = {
        "loop": {
            "skill_injection_reason": "router_fallback_no_experience",
            "tool_selector_output": 10,
            "tool_selector_dropped": 5,
        }
    }
    stats = collect_execution_surface_stats(orch, health=health, session_key="s1")
    assert stats.get("skill_injection_reason") == "router_fallback_no_experience"
    assert stats.get("skill_catalog_count") == 1
