"""Env-gated smoke tests for real domestic LLM APIs.

Default pytest runs skip this file through pyproject's ``not live_llm`` marker.

Run explicitly with:
    BUTLER_RUN_REAL_API_SMOKE=1 DEEPSEEK_API_KEY=... pytest -m live_llm tests/test_real_api_smoke.py
    BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=... pytest -m live_llm tests/test_real_api_smoke.py
"""

from __future__ import annotations

import os

import pytest

from butler.transport.llm_client import LLMClient


pytestmark = pytest.mark.live_llm


def _require_live(provider: str, key_var: str) -> str:
    if os.getenv("BUTLER_RUN_REAL_API_SMOKE") != "1":
        pytest.skip("set BUTLER_RUN_REAL_API_SMOKE=1 to run real API smoke tests")
    key = os.getenv(key_var, "").strip()
    if not key:
        pytest.skip(f"set {key_var} to run {provider} smoke tests")
    return key


def _assert_non_empty_text(text: str | None) -> None:
    assert text is not None
    assert text.strip()


def test_deepseek_chat_completion_smoke():
    api_key = _require_live("deepseek", "DEEPSEEK_API_KEY")
    client = LLMClient(
        provider="deepseek",
        api_key=api_key,
        model=os.getenv("BUTLER_SMOKE_DEEPSEEK_MODEL", "deepseek-chat"),
        max_tokens=64,
        temperature=0,
        timeout=60,
    )

    response = client.complete(
        messages=[{"role": "user", "content": "Reply with exactly: butler-smoke-ok"}],
    )

    _assert_non_empty_text(response.content)


def test_deepseek_streaming_reasoning_smoke():
    api_key = _require_live("deepseek", "DEEPSEEK_API_KEY")
    client = LLMClient(
        provider="deepseek",
        api_key=api_key,
        model=os.getenv("BUTLER_SMOKE_DEEPSEEK_REASONER_MODEL", "deepseek-reasoner"),
        max_tokens=128,
        temperature=0,
        timeout=90,
    )
    deltas: list[str] = []

    response = client.stream(
        messages=[{"role": "user", "content": "Reply with exactly: butler-smoke-ok"}],
        on_delta=deltas.append,
    )

    _assert_non_empty_text(response.content)
    assert all("<think>" not in d.lower() for d in deltas)


def test_minimax_chat_completion_smoke():
    api_key = _require_live("minimax", "MINIMAX_API_KEY")
    client = LLMClient(
        provider="minimax",
        api_key=api_key,
        model=os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "MiniMax-M2.7"),
        max_tokens=64,
        temperature=0,
        timeout=60,
    )

    response = client.complete(
        messages=[{"role": "user", "content": "Reply with exactly: butler-smoke-ok"}],
    )

    _assert_non_empty_text(response.content)


def test_minimax_streaming_think_scrubber_smoke():
    api_key = _require_live("minimax", "MINIMAX_API_KEY")
    client = LLMClient(
        provider="minimax",
        api_key=api_key,
        model=os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "MiniMax-M2.7"),
        max_tokens=128,
        temperature=0,
        timeout=90,
    )
    deltas: list[str] = []

    response = client.stream(
        messages=[{"role": "user", "content": "Reply with one short sentence."}],
        on_delta=deltas.append,
    )

    _assert_non_empty_text(response.content)
    assert all("<think>" not in d.lower() for d in deltas)
