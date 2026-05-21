"""Memory phase-2 quality: post_session dedup, prefetch caps, diagnostics."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from butler.memory import ButlerMemory, ProjectMemory
from butler.memory.diagnostics import collect_memory_layer_stats, format_memory_diagnostic_lines
from butler.post_session import PostSessionProcessor, memory_update_is_duplicate
from butler.project import Project
from butler.session_lifecycle import inject_turn_memory, prefetch_limits, prefetch_turn_memory


@pytest.mark.module_test
class TestPostSessionDedup:
    def test_memory_update_is_duplicate_detects_substring(self):
        corpus = "- [2026-05-21] 试点验收日期：2026-05-21"
        assert memory_update_is_duplicate("试点验收日期：2026-05-21", corpus)

    def test_extract_skips_duplicate_updates(self, tmp_path):
        import json

        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Notes", "试点验收日期：2026-05-21", classification="fact")

        existing_note = "试点验收日期：2026-05-21"
        llm_json = json.dumps(
            {
                "updates": [
                    {"target": "project", "section": "Notes", "content": existing_note}
                ]
            }
        )

        proc = PostSessionProcessor()

        async def _fake_llm(_prompt: str) -> str:
            return llm_json

        proc.set_llm_call(_fake_llm)
        chunk = "请记住试点验收日期。" * 8
        messages = [
            {"role": "user", "content": chunk},
            {"role": "assistant", "content": "好的"},
        ] * 3
        result = asyncio.run(
            proc.process(
                messages,
                butler_memory=bm,
                project_memory=pm,
                skill_manager=None,
            )
        )
        assert result["memory_updates"] == 0


@pytest.mark.module_test
class TestPrefetchLimits:
    def test_prefetch_truncates_total_chars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_PREFETCH_TOTAL_MAX_CHARS", "80")
        monkeypatch.setenv("BUTLER_PREFETCH_PROJECT_MAX_CHARS", "40")

        orch = MagicMock()
        orch.project_manager.resolve_active_project_name.return_value = "p"
        orch.butler_memory.get_system_context.return_value = "G" * 200
        orch.butler_memory.experience.search.return_value = []
        orch._project_memory.get_context_for_agent.return_value = "P" * 200

        out = prefetch_turn_memory(orch, "query")
        assert len(out) <= 80 + 20
        assert "截断" in out or len(out) <= 100

    def test_inject_respects_max_chars_env(self, monkeypatch):
        monkeypatch.setenv("BUTLER_PREFETCH_MAX_CHARS", "50")
        monkeypatch.setenv("BUTLER_PREFETCH_TOTAL_MAX_CHARS", "200")

        orch = MagicMock()
        orch.project_manager.resolve_active_project_name.return_value = ""
        orch.butler_memory.get_system_context.return_value = "x" * 300
        orch.butler_memory.experience.search.return_value = []
        orch._project_memory = None

        out = inject_turn_memory(orch, "hello")
        assert "## 相关记忆" in out
        assert len(out) < 400


@pytest.mark.module_test
class TestMemoryDiagnostics:
    def test_collect_and_format_layer_stats(self, tmp_path):
        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: demo\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        bm.profile.add("称呼主公")
        bm.experience.add("demo", "experience", "长期经验一条")
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Notes", "试点记录", classification="fact")

        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = pm
        orch.project_manager.current_project = "demo"

        stats = collect_memory_layer_stats(orch)
        assert stats["profile_entries"] >= 1
        assert stats["experience_long_term"] >= 1
        assert stats["project_bullets"] >= 1

        lines = format_memory_diagnostic_lines(stats)
        text = "\n".join(lines)
        assert "记忆分层" in text
        assert "Owner 画像" in text
        assert "Pending" in text
