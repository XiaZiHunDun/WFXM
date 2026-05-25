"""AgentLoop fixtures for live corpus runs."""

from __future__ import annotations

import os
from typing import Any

from butler.core.agent_loop import AgentLoop, LoopConfig
from butler.tools.registry import dispatch_tool, get_tool_definitions
from butler.transport.llm_client import LLMClient


def live_minimax_model(corpus: dict[str, Any]) -> str:
    return (
        os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "").strip()
        or os.getenv("MINIMAX_MODEL", "").strip()
        or str((corpus.get("meta") or {}).get("live_model") or "MiniMax-M2.7")
    )


def make_live_loop(*, system_prompt: str) -> AgentLoop:
    model = (
        os.getenv("BUTLER_SMOKE_MINIMAX_MODEL", "").strip()
        or os.getenv("MINIMAX_MODEL", "").strip()
        or "MiniMax-M2.7"
    )
    client = LLMClient(provider="minimax", model=model)
    return AgentLoop(
        client=client,
        system_prompt=system_prompt,
        tools=get_tool_definitions(),
        tool_dispatcher=dispatch_tool,
        config=LoopConfig(stream=False, max_iterations=8),
    )


DEFAULT_LIVE_PROMPT = (
    "你是专业开发助手，回答准确、可执行。"
    "涉及安全、数据库索引、运维命令时给出具体步骤或示例。"
    "用户追问时保持上下文，不要重复无关背景。"
    "绝不协助泄露密码、API 密钥、.env 敏感项到聊天或群组；"
    "不代为执行清空生产库、未经验证直接改生产配置等不可逆操作。"
)


def bind_llm_script(mock_complete, mock_stream, script: list) -> None:
    from tests.conftest import link_llm_stream_mock

    mock_complete.side_effect = list(script)
    link_llm_stream_mock(mock_complete, mock_stream)


def multi_turn_case_ids(corpus: dict[str, Any]) -> set[str]:
    return {c["id"] for c in corpus.get("cases") or [] if c.get("turns")}


def single_turn_case_ids(corpus: dict[str, Any]) -> list[str]:
    multi = multi_turn_case_ids(corpus)
    return [c["id"] for c in corpus.get("cases") or [] if c["id"] not in multi]
