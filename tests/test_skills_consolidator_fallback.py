"""Tests for R2-1: SkillConsolidator fallback_used flag and exception class.

Audit R2-1: LLM consolidator 任意异常都走 fallback(把原 2 个 skills 加 -merged 后缀拼
回去)。用户看到 "merged" skill 以为是去重后的,实际是原始两份。

Fix:
- Introduce ConsolidatorLLMUnavailable exception class for LLM-down errors.
- Narrow the except clause to that class only; let other exceptions propagate.
- Add fallback_used flag on every multi-skill return path so callers can
  detect silent fallbacks and decide what to do.
"""

from __future__ import annotations

import pytest

from butler.skills.consolidator import (
    ConsolidatorLLMUnavailable,
    SkillConsolidator,
)


# ---------------------------------------------------------------------------
# Test fixtures: small multi-skill input
# ---------------------------------------------------------------------------


def _two_skills() -> list[dict]:
    return [
        {"name": "alpha", "description": "Alpha skill", "triggers": ["a", "b"], "content": "Body A"},
        {"name": "beta", "description": "Beta skill", "triggers": ["b", "c"], "content": "Body B"},
    ]


def _single_skill() -> list[dict]:
    return [{"name": "solo", "description": "Solo skill", "triggers": ["x"], "content": "Body X"}]


# ---------------------------------------------------------------------------
# 1. fallback_used=False on LLM success
# ---------------------------------------------------------------------------


def test_fallback_used_false_on_llm_success():
    """When LLM returns valid JSON, fallback_used must be False."""

    def llm_fn(prompt: str) -> str:
        return (
            '{"name": "merged-skill", "description": "Merged", '
            '"triggers": ["a", "b"], "content": "# Merged workflow"}'
        )

    cons = SkillConsolidator(llm_fn=llm_fn)
    result = cons.consolidate(_two_skills())

    assert "fallback_used" in result
    assert result["fallback_used"] is False
    assert result["name"] == "merged-skill"
    assert result["content"] == "# Merged workflow"


# ---------------------------------------------------------------------------
# 2. fallback_used=True on garbled JSON from LLM
# ---------------------------------------------------------------------------


def test_fallback_used_true_on_garbled_json():
    """When LLM returns non-JSON, fallback path is used and flag is True."""

    def llm_fn(prompt: str) -> str:
        return "Sorry, I cannot help with that."  # no JSON object

    cons = SkillConsolidator(llm_fn=llm_fn)
    result = cons.consolidate(_two_skills())

    assert result["fallback_used"] is True
    # Fallback produces a -merged name and concatenates bodies.
    assert result["name"].endswith("-merged")
    assert "Body A" in result["content"]
    assert "Body B" in result["content"]


# ---------------------------------------------------------------------------
# 3. fallback_used=True on LLM unavailable (NEW exception class)
# ---------------------------------------------------------------------------


def test_fallback_used_true_on_llm_unavailable():
    """When _llm_fn raises ConsolidatorLLMUnavailable, fallback + flag=True."""

    def llm_fn(prompt: str) -> str:
        raise ConsolidatorLLMUnavailable("provider timeout")

    cons = SkillConsolidator(llm_fn=llm_fn)
    result = cons.consolidate(_two_skills())

    assert result["fallback_used"] is True
    assert result["name"].endswith("-merged")
    assert "Body A" in result["content"]
    assert "Body B" in result["content"]


def test_llm_unavailable_is_runtime_error_subclass():
    """ConsolidatorLLMUnavailable should subclass RuntimeError for compatibility."""
    assert issubclass(ConsolidatorLLMUnavailable, RuntimeError)


# ---------------------------------------------------------------------------
# 4. Re-raise on non-LLM exception
# ---------------------------------------------------------------------------


def test_reraises_on_non_llm_runtime_error():
    """A generic RuntimeError from _llm_fn must propagate, not be swallowed."""

    def llm_fn(prompt: str) -> str:
        raise RuntimeError("data access failure")

    cons = SkillConsolidator(llm_fn=llm_fn)
    with pytest.raises(RuntimeError, match="data access failure"):
        cons.consolidate(_two_skills())


def test_reraises_on_value_error():
    """A ValueError (programming error) from _llm_fn must propagate."""

    def llm_fn(prompt: str) -> str:
        raise ValueError("bad prompt template")

    cons = SkillConsolidator(llm_fn=llm_fn)
    with pytest.raises(ValueError, match="bad prompt template"):
        cons.consolidate(_two_skills())


# ---------------------------------------------------------------------------
# 5. Caller can detect fallback via the flag
# ---------------------------------------------------------------------------


def test_caller_can_detect_fallback_via_flag():
    """A caller that checks fallback_used can refuse a silent-fallback result."""

    def llm_fn(prompt: str) -> str:
        raise ConsolidatorLLMUnavailable("network down")

    cons = SkillConsolidator(llm_fn=llm_fn)
    result = cons.consolidate(_two_skills())

    # Simulate a caller that wants to fail loudly on silent fallback.
    with pytest.raises(RuntimeError, match="caller policy"):
        if result.get("fallback_used"):
            raise RuntimeError("caller policy: refuse silent-fallback merge")
        pytest.fail("expected caller to raise on fallback_used=True")


# ---------------------------------------------------------------------------
# 6. Single-skill path: passthrough (no merge needed)
# ---------------------------------------------------------------------------


def test_single_skill_passthrough_returns_skill_unchanged():
    """Single-skill input is a passthrough: caller passed 1 skill, no merge."""
    cons = SkillConsolidator()
    result = cons.consolidate(_single_skill())

    # Passthrough preserves the skill dict.
    assert result["name"] == "solo"
    assert result["content"] == "Body X"
    assert result["description"] == "Solo skill"


# ---------------------------------------------------------------------------
# 7. Empty-skills path: raise ValueError (programming error)
# ---------------------------------------------------------------------------


def test_empty_skills_raises_value_error():
    """Empty input is a programming error and must raise, not silently fallback."""
    cons = SkillConsolidator()
    with pytest.raises(ValueError, match="at least one skill"):
        cons.consolidate([])


# ---------------------------------------------------------------------------
# 8. Backwards-compat: merge dict is valid for downstream use
# ---------------------------------------------------------------------------


def test_backwards_compat_merge_dict_has_required_keys():
    """Legacy callers that destructure the merge dict must still work.

    The merge result must contain the canonical keys (name, description,
    triggers, content) regardless of fallback_used being present.
    """
    # Garbled-JSON path: fallback
    cons_garbled = SkillConsolidator(llm_fn=lambda p: "not json")
    r1 = cons_garbled.consolidate(_two_skills())
    for k in ("name", "description", "triggers", "content"):
        assert k in r1, f"missing key {k!r} in fallback result"

    # LLM success path: real merge
    cons_ok = SkillConsolidator(
        llm_fn=lambda p: '{"name": "m", "description": "d", "triggers": [], "content": "c"}'
    )
    r2 = cons_ok.consolidate(_two_skills())
    for k in ("name", "description", "triggers", "content"):
        assert k in r2, f"missing key {k!r} in success result"

    # LLM-unavailable path: fallback
    cons_down = SkillConsolidator(llm_fn=lambda p: (_ for _ in ()).throw(ConsolidatorLLMUnavailable("down")))
    r3 = cons_down.consolidate(_two_skills())
    for k in ("name", "description", "triggers", "content"):
        assert k in r3, f"missing key {k!r} in unavailable result"
