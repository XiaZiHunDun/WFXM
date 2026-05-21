"""CLI /new single finalize + memory-reindex."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.memory import ButlerMemory
from butler.memory.reindex import reindex_semantic_memory


@pytest.mark.module_test
class TestCliNewSingleFinalize:
    def test_rebuild_branch_does_not_call_trigger_before_rebuild_loop(self):
        """Regression: /new → rebuild only finalizes inside _rebuild_loop once."""
        src = Path(__file__).resolve().parents[1] / "butler" / "main.py"
        text = src.read_text(encoding="utf-8")
        start = text.index('if handled == "rebuild":')
        end = text.index("elif handled ==", start)
        branch = text[start:end]
        assert branch.count("_trigger_session_end") == 0
        assert "_rebuild_loop()" in branch


@pytest.mark.module_test
class TestMemoryReindex:
    def test_reindex_experience_and_project_bullets(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        home = tmp_path / "butler_home"
        proj_dir = tmp_path / "projects" / "Demo"
        proj_dir.mkdir(parents=True)
        (proj_dir / "project.yaml").write_text(
            f"name: Demo\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path / "projects"))

        bm = ButlerMemory(home, tenant_id="default")
        rid = bm.experience.add("Demo", "experience", "采用 pytest 做守门")
        assert rid > 0
        from butler.memory.project_memory import ProjectMemory

        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Notes", "试点 reindex 条目", classification="fact")

        result = reindex_semantic_memory(
            home,
            projects_dir=tmp_path / "projects",
            clear_vectors=True,
        )
        assert result["ok"] is True
        assert result["indexed_experience"] >= 1
        assert result["indexed_project_bullets"] >= 1
        assert result["vector_rows"] >= 2
        hits = bm.semantic.search("pytest 守门", limit=5)
        assert any("pytest" in (h.get("content") or "") for h in hits)

    def test_reindex_disabled_without_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("BUTLER_SEMANTIC_MEMORY", raising=False)
        result = reindex_semantic_memory(tmp_path / "home")
        assert result["ok"] is False
