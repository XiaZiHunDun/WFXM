"""L2 module tests for butler.post_session."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from butler.post_session import (
    PostSessionProcessor,
    _format_messages,
    _normalize_project_section,
    _parse_json_from_response,
)


@pytest.mark.module_test
class TestFormatMessages:
    def test_normal_conversation_formatting(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ]
        text = _format_messages(messages)
        assert "[USER]: Hello" in text
        assert "[ASSISTANT]: Hi there" in text

    def test_tool_content_truncated_at_500_chars(self):
        long_content = "x" * 600
        messages = [{"role": "tool", "content": long_content}]
        text = _format_messages(messages)
        assert "..." in text
        assert "[600 chars]" in text
        assert len(text) < 600

    def test_list_type_content_joined(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"text": "part one"},
                    {"text": "part two"},
                ],
            }
        ]
        text = _format_messages(messages)
        assert "part one" in text
        assert "part two" in text

    def test_empty_content_skipped(self):
        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "visible"},
        ]
        text = _format_messages(messages)
        assert "[USER]" not in text
        assert "[ASSISTANT]: visible" in text

    def test_max_chars_truncation(self):
        messages = [
            {"role": "user", "content": "a" * 500},
            {"role": "assistant", "content": "b" * 500},
            {"role": "user", "content": "c" * 500},
        ]
        text = _format_messages(messages, max_chars=900)
        assert len(text) < 2500


@pytest.mark.module_test
class TestParseJsonResponse:
    def test_valid_json_parsed(self):
        data = _parse_json_from_response('{"updates": [{"target": "butler"}]}')
        assert data is not None
        assert data["updates"][0]["target"] == "butler"

    def test_json_wrapped_in_code_fence_parsed(self):
        raw = 'Here is the result:\n```json\n{"skills": [{"name": "test-skill"}]}\n```'
        data = _parse_json_from_response(raw)
        assert data is not None
        assert data["skills"][0]["name"] == "test-skill"

    def test_non_json_returns_none(self):
        assert _parse_json_from_response("just plain text") is None

    def test_empty_string_returns_none(self):
        assert _parse_json_from_response("") is None


@pytest.mark.module_test
class TestNormalizeProjectSection:
    def test_chinese_section_maps_to_canonical_section(self):
        assert _normalize_project_section("关键决策") == "Decisions"

    def test_canonical_section_is_preserved(self):
        assert _normalize_project_section("Architecture") == "Architecture"

    def test_unknown_section_falls_back_to_visible_notes(self):
        assert _normalize_project_section("技术栈") == "Notes"


@pytest.mark.module_test
class TestExtractMemories:
    def _long_messages(self):
        filler = "x" * 80
        return [
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
        ]

    def test_butler_target_calls_profile_add(self):
        async def llm_call(prompt):
            return '{"updates": [{"target": "butler", "content": "prefers dark mode"}]}'

        butler_memory = MagicMock()
        butler_memory.profile.add.return_value = {"success": True}
        proc = PostSessionProcessor(llm_call=llm_call)

        count = asyncio.run(
            proc._extract_memories(self._long_messages(), butler_memory, None, "proj")
        )
        assert count == 1
        butler_memory.profile.add.assert_called_once_with("prefers dark mode")

    def test_project_target_calls_markdown_append(self):
        async def llm_call(prompt):
            return (
                '{"updates": [{"target": "project", "section": "架构与设计", '
                '"content": "uses FastAPI"}]}'
            )

        project_memory = MagicMock()
        proc = PostSessionProcessor(llm_call=llm_call)

        count = asyncio.run(
            proc._extract_memories(self._long_messages(), None, project_memory, "proj")
        )
        assert count == 1
        project_memory.markdown.append.assert_called_once_with("Architecture", "uses FastAPI")

    def test_experience_target_calls_experience_add(self):
        async def llm_call(prompt):
            return '{"updates": [{"target": "experience", "content": "always test auth"}]}'

        butler_memory = MagicMock()
        proc = PostSessionProcessor(llm_call=llm_call)

        count = asyncio.run(
            proc._extract_memories(self._long_messages(), butler_memory, None, "MyProj")
        )
        assert count == 1
        butler_memory.experience.add.assert_called_once_with(
            project="MyProj",
            category="experience",
            content="always test auth",
        )

    def test_invalid_target_skipped(self):
        async def llm_call(prompt):
            return '{"updates": [{"target": "unknown", "content": "ignored"}]}'

        butler_memory = MagicMock()
        proc = PostSessionProcessor(llm_call=llm_call)

        count = asyncio.run(
            proc._extract_memories(self._long_messages(), butler_memory, None, "")
        )
        assert count == 0
        butler_memory.profile.add.assert_not_called()


@pytest.mark.module_test
class TestExtractSkills:
    def _skill_messages(self):
        filler = "y" * 100
        return [
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
        ]

    def test_normal_skill_extraction_calls_create(self):
        async def llm_call(prompt):
            return json_skill_response()

        skill_manager = MagicMock()
        skill_manager.list_skills.return_value = []
        proc = PostSessionProcessor(llm_call=llm_call)

        count = asyncio.run(
            proc._extract_skills(self._skill_messages(), skill_manager, "proj")
        )
        assert count == 1
        skill_manager.create.assert_called_once()
        kwargs = skill_manager.create.call_args.kwargs
        assert kwargs["name"] == "deploy-checklist"
        assert kwargs["description"] == "Deploy steps"
        assert "Step 1" in kwargs["content"]

    def test_no_skills_found_returns_zero(self):
        async def llm_call(prompt):
            return '{"skills": []}'

        skill_manager = MagicMock()
        skill_manager.list_skills.return_value = []
        proc = PostSessionProcessor(llm_call=llm_call)

        count = asyncio.run(
            proc._extract_skills(self._skill_messages(), skill_manager, "proj")
        )
        assert count == 0
        skill_manager.create.assert_not_called()


def json_skill_response():
    return json_dumps_skills()


def json_dumps_skills():
    import json

    return json.dumps(
        {
            "skills": [
                {
                    "name": "deploy-checklist",
                    "description": "Deploy steps",
                    "triggers": ["deploy"],
                    "body": "Step 1: build\nStep 2: ship",
                }
            ]
        }
    )


@pytest.mark.module_test
class TestProcess:
    def test_short_conversation_skipped(self):
        proc = PostSessionProcessor(llm_call=lambda p: asyncio.sleep(0))
        result = asyncio.run(proc.process([{"role": "user", "content": "hi"}] * 3))
        assert result == {"memory_updates": 0, "skills_extracted": 0, "errors": []}

    def test_no_llm_call_returns_zero(self):
        proc = PostSessionProcessor()
        messages = [{"role": "user", "content": "a"}] * 5
        result = asyncio.run(proc.process(messages))
        assert result["memory_updates"] == 0
        assert result["skills_extracted"] == 0

    def test_normal_flow_with_mock_llm(self):
        calls = {"n": 0}

        async def llm_call(prompt):
            calls["n"] += 1
            if "skills" in prompt.lower() or "skill" in prompt:
                return '{"skills": []}'
            return '{"updates": []}'

        filler = "z" * 120
        messages = [
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
        ]
        proc = PostSessionProcessor(llm_call=llm_call)
        result = asyncio.run(proc.process(messages))
        assert result["memory_updates"] == 0
        assert result["skills_extracted"] == 0
        assert calls["n"] >= 1
