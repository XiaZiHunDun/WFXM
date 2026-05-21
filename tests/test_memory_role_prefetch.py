"""Role-scoped project memory prefetch and /new user messaging."""

from __future__ import annotations

from butler.memory.project_memory import (
    filter_memory_hits_by_role,
    project_prefetch_max_chars,
    sections_for_agent_role,
)
from butler.session_lifecycle import format_new_session_user_message


def test_sections_for_lead_vs_content():
    lead = sections_for_agent_role("lead")
    content = sections_for_agent_role("content")
    assert "Decisions" in lead
    assert "API" not in lead
    assert "Notes" in content
    assert "API" not in content


def test_filter_hits_by_role_drops_api_for_lead():
    hits = [
        {"content": "use FastAPI", "section": "API"},
        {"content": "试点验收日", "section": "Notes"},
    ]
    out = filter_memory_hits_by_role(hits, "lead")
    assert len(out) == 1
    assert out[0]["section"] == "Notes"


def test_project_prefetch_max_chars_role():
    assert project_prefetch_max_chars("lead", default=1200) == 800
    assert project_prefetch_max_chars("dev_agent", default=1200) == 1200


def test_format_new_session_message_includes_long_term_hint():
    text = format_new_session_user_message(
        extract_result={"memory_updates": 2},
        purge_result={"removed": 3},
    )
    assert "已清空本轮对话上下文" in text
    assert "长期记忆" in text
    assert "长期记忆 +2" in text
    assert "3 条会话回声" in text
