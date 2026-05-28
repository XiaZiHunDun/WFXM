"""post_session project MEMORY writes must sync semantic vectors (P2 follow-up)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from butler.session.post_session import PostSessionProcessor


@pytest.mark.module_test
class TestPostSessionProjectVectors:
    def _long_messages(self):
        filler = "x" * 80
        return [
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
        ]

    def test_project_fact_append_syncs_vector(self):
        async def llm_call(prompt):
            return (
                '{"updates": [{"target": "project", "section": "Notes", '
                '"content": "试点统一测试日 2026-05-22"}]}'
            )

        butler_memory = MagicMock()
        butler_memory.semantic = MagicMock()
        project_memory = MagicMock()
        project_memory.markdown.append.return_value = "fact"

        proc = PostSessionProcessor(llm_call=llm_call)

        with patch(
            "butler.memory.semantic_project.sync_project_append_vectors"
        ) as sync_mock:
            count = asyncio.run(
                proc._extract_memories(
                    self._long_messages(),
                    butler_memory,
                    project_memory,
                    "灵文1号",
                )
            )

        assert count == 1
        project_memory.markdown.append.assert_called_once_with(
            "Notes", "试点统一测试日 2026-05-22"
        )
        sync_mock.assert_called_once_with(
            butler_memory.semantic,
            "灵文1号",
            "Notes",
            "试点统一测试日 2026-05-22",
            "fact",
        )

    def test_project_pending_append_syncs_pending_vector(self):
        async def llm_call(prompt):
            return (
                '{"updates": [{"target": "project", "section": "关键决策", '
                '"content": "我们决定采用 redis 做试点缓存"}]}'
            )

        butler_memory = MagicMock()
        butler_memory.semantic = MagicMock()
        project_memory = MagicMock()
        project_memory.markdown.append.return_value = "pending"

        proc = PostSessionProcessor(llm_call=llm_call)

        with patch(
            "butler.memory.semantic_project.sync_project_append_vectors"
        ) as sync_mock:
            with patch(
                "butler.memory.semantic_project.resolve_project_display_name",
                return_value="灵文1号",
            ):
                count = asyncio.run(
                    proc._extract_memories(
                        self._long_messages(),
                        butler_memory,
                        project_memory,
                        "",
                    )
                )

        assert count == 1
        sync_mock.assert_called_once()
        args = sync_mock.call_args[0]
        assert args[2] == "Decisions"
        assert args[4] == "pending"
