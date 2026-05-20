"""Env-gated smoke tests for real domestic LLM APIs.

Default pytest runs skip this file through pyproject's ``not live_llm`` marker.

Run explicitly with:
    BUTLER_RUN_REAL_API_SMOKE=1 DEEPSEEK_API_KEY=... pytest -m live_llm tests/test_real_api_smoke.py
    BUTLER_RUN_REAL_API_SMOKE=1 MINIMAX_API_KEY=... pytest -m live_llm tests/test_real_api_smoke.py
    BUTLER_RUN_REAL_API_SMOKE=1 DASHSCOPE_API_KEY=... pytest -m live_llm tests/test_real_api_smoke.py -k qwen

Optional model overrides:
    BUTLER_SMOKE_DEEPSEEK_MODEL, BUTLER_SMOKE_DEEPSEEK_REASONER_MODEL
    BUTLER_SMOKE_MINIMAX_MODEL, BUTLER_SMOKE_QWEN_MODEL
"""

from __future__ import annotations

import json
import os

import pytest

from butler.core.agent_loop import AgentLoop, LoopConfig, LoopStatus
from butler.transport.llm_client import LLMClient
from butler.transport.providers import get_provider


pytestmark = pytest.mark.live_llm

_SMOKE_MODEL_ENV: dict[str, str] = {
    "deepseek": "BUTLER_SMOKE_DEEPSEEK_MODEL",
    "minimax": "BUTLER_SMOKE_MINIMAX_MODEL",
    "qwen": "BUTLER_SMOKE_QWEN_MODEL",
}


def _require_smoke_enabled() -> None:
    if os.getenv("BUTLER_RUN_REAL_API_SMOKE") != "1":
        pytest.skip("set BUTLER_RUN_REAL_API_SMOKE=1 to run real API smoke tests")


def _require_provider(provider: str) -> tuple[str, str]:
    _require_smoke_enabled()
    profile = get_provider(provider)
    if profile is None:
        pytest.skip(f"unknown smoke provider: {provider}")
    api_key = profile.resolve_api_key()
    if not api_key:
        pytest.skip(f"set one of {profile.env_vars} to run {provider} smoke tests")
    model_env = _SMOKE_MODEL_ENV.get(provider, f"BUTLER_SMOKE_{provider.upper()}_MODEL")
    model = os.getenv(model_env, profile.default_model).strip()
    if not model:
        pytest.skip(f"set {model_env} or provider default_model for {provider}")
    return api_key, model


def _smoke_client(
    provider: str,
    *,
    model: str | None = None,
    max_tokens: int = 64,
    timeout: int = 60,
) -> LLMClient:
    api_key, default_model = _require_provider(provider)
    return LLMClient(
        provider=provider,
        api_key=api_key,
        model=model or default_model,
        max_tokens=max_tokens,
        temperature=0,
        timeout=timeout,
    )


def _assert_non_empty_text(text: str | None) -> None:
    assert text is not None
    assert text.strip()


def test_deepseek_chat_completion_smoke():
    client = _smoke_client("deepseek")

    response = client.complete(
        messages=[{"role": "user", "content": "Reply with exactly: butler-smoke-ok"}],
    )

    _assert_non_empty_text(response.content)
    assert response.usage is not None
    assert response.usage.total_tokens > 0


def test_deepseek_streaming_reasoning_smoke():
    client = _smoke_client(
        "deepseek",
        model=os.getenv("BUTLER_SMOKE_DEEPSEEK_REASONER_MODEL", "deepseek-reasoner"),
        max_tokens=128,
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
    client = _smoke_client("minimax")

    response = client.complete(
        messages=[{"role": "user", "content": "Reply with exactly: butler-smoke-ok"}],
    )

    _assert_non_empty_text(response.content)


def test_minimax_streaming_think_scrubber_smoke():
    client = _smoke_client("minimax", max_tokens=128, timeout=90)
    deltas: list[str] = []

    response = client.stream(
        messages=[{"role": "user", "content": "Reply with one short sentence."}],
        on_delta=deltas.append,
    )

    _assert_non_empty_text(response.content)
    assert all("<think>" not in d.lower() for d in deltas)


def test_qwen_chat_completion_smoke():
    client = _smoke_client("qwen")

    response = client.complete(
        messages=[{"role": "user", "content": "Reply with exactly: butler-smoke-ok"}],
    )

    _assert_non_empty_text(response.content)
    assert response.usage is not None
    assert response.usage.total_tokens > 0


def test_agent_loop_deepseek_completion_smoke():
    client = _smoke_client("deepseek")
    loop = AgentLoop(
        client,
        config=LoopConfig(stream=False, max_iterations=3),
    )

    result = loop.run("Say hello in one short English sentence.")

    assert result.status == LoopStatus.COMPLETED
    assert result.iterations >= 1
    _assert_non_empty_text(result.final_response)


def test_agent_loop_minimax_completion_smoke():
    client = _smoke_client("minimax")
    loop = AgentLoop(
        client,
        config=LoopConfig(stream=False, max_iterations=3),
    )

    result = loop.run("Say hello in one short English sentence.")

    assert result.status == LoopStatus.COMPLETED
    assert result.iterations >= 1
    _assert_non_empty_text(result.final_response)


def test_agent_loop_deepseek_tool_round_trip_smoke():
    client = _smoke_client("deepseek", max_tokens=256, timeout=90)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "echo_smoke",
                "description": "Echo the input text back to the caller.",
                "parameters": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            },
        }
    ]

    def _dispatcher(name: str, args: dict) -> str:
        if name != "echo_smoke":
            return json.dumps({"error": f"unknown tool {name}"})
        return json.dumps({"echo": str(args.get("text") or "")})

    loop = AgentLoop(
        client,
        tools=tools,
        tool_dispatcher=_dispatcher,
        config=LoopConfig(stream=False, max_iterations=5, enable_parallel_tools=False),
    )

    result = loop.run(
        "You must call echo_smoke exactly once with text 'hello-smoke', "
        "then reply with the word done."
    )

    assert result.status == LoopStatus.COMPLETED
    assert result.tool_calls_made >= 1
    tool_msgs = [msg for msg in loop.messages if msg.get("role") == "tool"]
    assert tool_msgs
    assert "hello-smoke" in tool_msgs[0]["content"]
