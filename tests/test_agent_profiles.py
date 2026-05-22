"""L1 unit tests for butler.agent_profiles."""

import pytest

from butler.agent_profiles import (
    CONTENT_AGENT,
    DEV_AGENT,
    REVIEW_AGENT,
    get_model_aware_prompt_extra,
    get_profile,
)


@pytest.mark.unit
class TestGetProfile:
    def test_dev_profile(self):
        profile = get_profile("dev")
        assert profile is DEV_AGENT
        assert "patch" in profile.system_prompt or "read_file" in profile.system_prompt

    def test_content_profile(self):
        profile = get_profile("content")
        assert profile is CONTENT_AGENT
        assert profile.system_prompt

    def test_review_profile(self):
        profile = get_profile("review")
        assert profile is REVIEW_AGENT
        assert profile.system_prompt

    def test_unknown_returns_none(self):
        assert get_profile("unknown") is None

    def test_writer_alias_maps_to_content(self):
        assert get_profile("writer") is CONTENT_AGENT

    def test_reviewer_alias_maps_to_review(self):
        assert get_profile("reviewer") is REVIEW_AGENT


@pytest.mark.unit
class TestGetModelAwarePromptExtra:
    def test_domestic_provider_returns_non_empty(self):
        extra = get_model_aware_prompt_extra("deepseek")
        assert extra
        assert "function calling" in extra or "工具" in extra

    def test_non_domestic_returns_empty(self):
        assert get_model_aware_prompt_extra("openai") == ""

    def test_empty_provider_returns_empty(self):
        assert get_model_aware_prompt_extra("") == ""
