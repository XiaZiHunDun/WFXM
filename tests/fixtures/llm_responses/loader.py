"""Load JSON LLM turn scripts into NormalizedResponse sequences and mock clients."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from butler.transport.types import NormalizedResponse, Usage, build_tool_call

_FIXTURES_DIR = Path(__file__).resolve().parent


def _usage(data: dict[str, Any] | None) -> Usage:
    raw = data or {}
    prompt = int(raw.get("prompt_tokens", 10))
    completion = int(raw.get("completion_tokens", 5))
    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=int(raw.get("total_tokens", prompt + completion)),
        cached_tokens=int(raw.get("cached_tokens", 0)),
    )


def _turn_to_response(turn: dict[str, Any]) -> NormalizedResponse:
    tool_calls = None
    raw_tools = turn.get("tool_calls") or []
    if raw_tools:
        tool_calls = [
            build_tool_call(
                tc.get("id"),
                str(tc.get("name") or ""),
                tc.get("arguments") or {},
            )
            for tc in raw_tools
        ]
    finish = str(turn.get("finish_reason") or ("tool_calls" if tool_calls else "stop"))
    return NormalizedResponse(
        content=turn.get("content"),
        tool_calls=tool_calls,
        finish_reason=finish,
        reasoning=turn.get("reasoning"),
        usage=_usage(turn.get("usage")),
    )


def load_llm_script(name: str) -> dict[str, Any]:
    """Load a fixture JSON by basename (e.g. ``text_only.json``)."""
    path = _FIXTURES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"LLM script not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def responses_from_script(script: dict[str, Any]) -> list[NormalizedResponse]:
    turns = script.get("turns") or []
    if not turns:
        raise ValueError("LLM script must contain a non-empty 'turns' list")
    return [_turn_to_response(turn) for turn in turns]


def mock_client_from_script(
    script: dict[str, Any],
    *,
    provider: str = "minimax",
    model: str = "fixture-model",
):
    """Return an LLMClient whose complete/stream play through scripted turns."""
    from butler.transport.llm_client import LLMClient

    from tests.conftest import link_llm_stream_mock

    responses = responses_from_script(script)
    client = LLMClient(provider=provider, model=model)
    client.complete = MagicMock(side_effect=list(responses))  # noqa: magicmock-no-spec
    client.stream = MagicMock()  # noqa: magicmock-no-spec
    link_llm_stream_mock(client.complete, client.stream)
    return client
