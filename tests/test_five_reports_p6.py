"""Five-reports P6: prompt eval, layered post-session, presets."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_prompt_eval_runner():
    from butler.prompt_eval.runner import run_prompt_eval

    ok, results = run_prompt_eval(repo_root=ROOT)
    assert ok
    assert len(results) >= 6


@pytest.mark.unit
def test_provider_presets_builtin():
    from butler.provider_presets import format_preset_uri, load_presets, resolve_preset

    presets = load_presets()
    assert presets
    p = resolve_preset("minimax-default")
    assert p is not None
    assert format_preset_uri(p).startswith("butler://")


@pytest.mark.unit
def test_post_session_layered_disabled_by_default():
    from butler.session.post_session_layered import post_session_layered_enabled

    assert not post_session_layered_enabled()


@pytest.mark.unit
def test_injection_llm_disabled_by_default():
    from butler.memory.injection_llm_score import injection_llm_score_enabled

    assert not injection_llm_score_enabled()
