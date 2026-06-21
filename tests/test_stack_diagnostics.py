"""stack.yaml diagnostics for /诊断."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.ops.stack_diagnostics import collect_stack_health, format_stack_diagnostic_lines


def test_collect_stack_health_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "novel-factory" / "references").mkdir(parents=True)
    (ws / "docs" / "research").mkdir(parents=True)
    (ws / "stack.yaml").write_text(
        """
version: 1
project: test
python_extras:
  includes: [mcp]
process_env:
  HTTP_PROXY: "http://127.0.0.1:9"
  HTTPS_PROXY: "http://127.0.0.1:9"
env_recommended:
  BUTLER_MCP_ENABLED: "1"
ingest_pilot_dirs:
  - novel-factory/references
  - docs/research
skills:
  skills_expected:
    - demo-skill
""".strip(),
        encoding="utf-8",
    )
    (ws / ".butler" / "skills").mkdir(parents=True)
    (ws / ".butler" / "skills" / "demo-skill.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")

    stats = collect_stack_health(ws)
    assert stats["found"] is True
    assert stats["ok"] is True
    assert "extra:mcp=ok" in stats["checks"]
    assert "BUTLER_MCP_ENABLED=ok" in stats["checks"]
    assert "HTTP_PROXY=ok" in stats["checks"]
    assert "skill:demo-skill=ok" in stats["checks"]
    assert "ingest_dirs=ok" in stats["checks"]
    lines = format_stack_diagnostic_lines(ws)
    assert any("项目 stack" in ln for ln in lines)


def test_format_stack_missing_file(tmp_path: Path):
    assert format_stack_diagnostic_lines(tmp_path) == []


def test_collect_stack_directory_skill_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    ws = tmp_path / "proj"
    skills = ws / ".butler" / "skills"
    skills.mkdir(parents=True)
    (skills / "webnovel-write.md").write_text("---\nname: webnovel-write\n---\n\nflat\n", encoding="utf-8")
    (ws / "stack.yaml").write_text(
        """
version: 2
project: test
skills:
  skills_expected: [webnovel-write]
  directory_skills: [webnovel-write]
plugin_adoption:
  claude_plugin: webnovel-writer
  mcp_suggested:
    - id: firecrawl
""".strip(),
        encoding="utf-8",
    )
    stats = collect_stack_health(ws)
    assert stats["found"] is True
    assert any("flat" in w or "单文件" in w for w in stats["warnings"])
    assert any("firecrawl" in w for w in stats["warnings"])

