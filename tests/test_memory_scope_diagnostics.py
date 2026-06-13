"""Memory scope diagnostics CLI and /诊断 integration."""

from __future__ import annotations

import json
from pathlib import Path

from butler.memory.scope_diagnostics import (
    collect_memory_scope_stats,
    format_memory_scope_diagnostic_lines,
    run_memory_scope_diagnose,
)


def test_collect_scope_stats_l4_only(tmp_path):
    l4 = tmp_path / "coding_experiences.json"
    l4.write_text(
        json.dumps(
            [
                {
                    "id": "B9_EX_global",
                    "title": "g",
                    "domain": ["b9"],
                    "theorem_basis": ["T01"],
                    "context": "c",
                    "pattern": "p",
                    "scope": {"visibility": "global", "source": "b9"},
                },
                {
                    "id": "B9_EX_prod_lingwen_demo_add",
                    "title": "lw",
                    "domain": ["b9"],
                    "theorem_basis": ["T01"],
                    "context": "c",
                    "pattern": "p",
                    "scope": {
                        "visibility": "private",
                        "project_id": "灵文1号",
                        "source": "b9",
                    },
                },
            ]
        ),
        encoding="utf-8",
    )
    stats = collect_memory_scope_stats(butler_home=tmp_path, project_name="")
    assert stats["l4_tenant"]["total"] == 2
    assert stats["l4_tenant"]["by_visibility"]["private"] == 1


def test_collect_scope_stats_infers_legacy_lingwen_private(tmp_path):
    """Legacy rows without scope field still count as private via infer_default_scope."""
    l4 = tmp_path / "coding_experiences.json"
    l4.write_text(
        json.dumps(
            [
                {
                    "id": "B9_EX_prod_lingwen_demo_add",
                    "title": "lw",
                    "domain": ["b9"],
                    "theorem_basis": ["T01"],
                    "context": "c",
                    "pattern": "p",
                }
            ]
        ),
        encoding="utf-8",
    )
    stats = collect_memory_scope_stats(butler_home=tmp_path, project_name="")
    assert stats["l4_tenant"]["by_visibility"]["private"] == 1


def test_backfill_tenant_scopes_dry_run(tmp_path):
    l4 = tmp_path / "coding_experiences.json"
    l4.write_text(
        json.dumps(
            [
                {
                    "id": "B9_EX_prod_lingwen_demo_add",
                    "title": "lw",
                    "domain": ["b9"],
                    "theorem_basis": ["T01"],
                    "context": "c",
                    "pattern": "p",
                }
            ]
        ),
        encoding="utf-8",
    )
    from butler.memory.scope_diagnostics import backfill_tenant_coding_scopes

    result = backfill_tenant_coding_scopes(butler_home=tmp_path, dry_run=True)
    assert result["updated"] == 1
    raw = json.loads(l4.read_text(encoding="utf-8"))
    assert "scope" not in raw[0]

    result2 = backfill_tenant_coding_scopes(butler_home=tmp_path, dry_run=False)
    assert result2["updated"] == 1
    raw2 = json.loads(l4.read_text(encoding="utf-8"))
    assert raw2[0]["scope"]["visibility"] == "private"
    assert raw2[0]["scope"]["project_id"] == "灵文1号"


def test_collect_scope_stats_project_filter(tmp_path, monkeypatch):
    from types import SimpleNamespace

    l4 = tmp_path / "coding_experiences.json"
    l4.write_text(
        json.dumps(
            [
                {
                    "id": "B9_EX_global",
                    "title": "g",
                    "domain": ["b9"],
                    "theorem_basis": ["T01", "T03", "T04", "T10"],
                    "context": "global ctx keywords",
                    "pattern": "p",
                    "benchmarks": {"retrieval_keywords": "global"},
                    "scope": {"visibility": "global", "source": "b9"},
                },
                {
                    "id": "B9_EX_prod_lingwen_demo_add",
                    "title": "lw",
                    "domain": ["b9"],
                    "theorem_basis": ["T01", "T03", "T04", "T10"],
                    "context": "lingwen demo",
                    "pattern": "p",
                    "benchmarks": {"retrieval_keywords": "lingwen,demo"},
                    "scope": {
                        "visibility": "private",
                        "project_id": "灵文1号",
                        "source": "b9",
                    },
                },
            ]
        ),
        encoding="utf-8",
    )
    ws = tmp_path / "lingwen"
    ws.mkdir()
    l3 = ws / ".butler" / "memory" / "coding_experiences.json"
    l3.parent.mkdir(parents=True)
    l3.write_text(
        json.dumps(
            [
                {
                    "id": "PROD_FAIL_abc",
                    "title": "pf",
                    "domain": ["prod"],
                    "theorem_basis": ["T01"],
                    "context": "c",
                    "pattern": "p",
                    "scope": {
                        "level": "project",
                        "visibility": "private",
                        "project_id": "灵文1号",
                        "source": "prod_failure",
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    class _PM:
        def get_project(self, name: str):
            if name == "灵文1号":
                return SimpleNamespace(
                    name="灵文1号",
                    workspace=ws,
                    pack="novel-factory",
                    type="content",
                )
            return None

        def list_projects(self):
            return [
                SimpleNamespace(name="灵文1号", workspace=ws),
            ]

    monkeypatch.setattr("butler.project.manager.get_project_manager", lambda: _PM())

    stats = collect_memory_scope_stats(butler_home=tmp_path, project_name="灵文1号")
    assert stats["l3_project"]["total"] == 1
    l4v = stats["l4_visible_to_project"]
    assert l4v["total"] == 2  # 1 global + 1 private(灵文1号)
    assert l4v["by_visibility"]["global"] == 1
    assert l4v["by_visibility"]["private"] == 1
    lines = format_memory_scope_diagnostic_lines(stats)
    text = "\n".join(lines)
    assert "L3 项目库" in text
    assert "灵文1号" in text


def test_format_memory_diagnostic_includes_scope(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    (tmp_path / "coding_experiences.json").write_text("[]", encoding="utf-8")

    from butler.memory.diagnostics import format_memory_diagnostic_lines

    stats = {
        "profile_entries": 0,
        "profile_chars": 0,
        "experience_long_term": 0,
        "conversation_rows": 0,
        "project_name": "灵文1号",
        "project_bullets": 0,
        "project_pending": 0,
        "semantic_enabled": False,
        "memory_scope": collect_memory_scope_stats(
            butler_home=tmp_path,
            project_name="灵文1号",
        ),
    }
    lines = format_memory_diagnostic_lines(stats)
    assert any("编码经验作用域" in ln for ln in lines)


def test_cli_diagnose_json(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    (tmp_path / "coding_experiences.json").write_text("[]", encoding="utf-8")
    payload = run_memory_scope_diagnose(
        butler_home=tmp_path,
        project="",
        json_out=True,
    )
    assert payload["ok"] is True
    assert "stats" in payload
