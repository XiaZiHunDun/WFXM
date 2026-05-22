"""Regression harness for developer-assistant evaluation corpus.

The corpus describes ideal assistant answers for 12 dev scenarios. CI uses mock LLM
to inject canonical responses and asserts keyword coverage (routing/format guard).
Real answer quality requires optional ``live_llm`` runs.

Corpus: tests/scenarios/dev_assistant_corpus.yaml
Analysis: docs/plans/dev-assistant-corpus-analysis-2026-05.md

Run:
  PYTHONPATH=. pytest tests/test_dev_assistant_corpus.py -q
  BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest -m live_llm tests/test_dev_assistant_corpus.py -v
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from butler.core.agent_loop import AgentLoop, LoopConfig
from butler.transport.types import NormalizedResponse, Usage

_CORPUS_PATH = Path(__file__).resolve().parent / "scenarios" / "dev_assistant_corpus.yaml"


def _load_corpus() -> dict[str, Any]:
    with _CORPUS_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _canonical_response(text: str) -> NormalizedResponse:
    return NormalizedResponse(
        content=text,
        usage=Usage(prompt_tokens=10, completion_tokens=80, total_tokens=90),
    )


def _build_canonical_answer(case: dict[str, Any]) -> str:
    """Synthesize a response that satisfies all must_contain rules for mock runs."""
    parts: list[str] = []
    for key in ("must_contain", "must_contain_any"):
        for item in case.get(key) or []:
            parts.append(str(item))
    for turn in case.get("turns") or []:
        for key in ("must_contain", "must_contain_any"):
            for item in turn.get(key) or []:
                parts.append(str(item))
    # Minimal prose wrapper so assertions are meaningful
    title = case.get("title") or case.get("id", "")
    body = "\n".join(parts)
    return f"【{title}】\n{body}"


def _assert_keywords(text: str, rules: dict[str, Any]) -> None:
    lower = (text or "").lower()
    for kw in rules.get("must_contain") or []:
        assert kw.lower() in lower or kw in (text or ""), f"missing required: {kw!r}"
    any_list = rules.get("must_contain_any") or []
    if any_list:
        assert any(
            k.lower() in lower or k in (text or "") for k in any_list
        ), f"none of must_contain_any matched: {any_list!r}"
    for bad in rules.get("must_not_contain") or []:
        assert bad.lower() not in lower, f"forbidden phrase present: {bad!r}"


@pytest.fixture
def corpus() -> dict[str, Any]:
    return _load_corpus()


@pytest.fixture
def single_turn_cases(corpus) -> list[dict[str, Any]]:
    return [c for c in corpus.get("cases") or [] if "turns" not in c]


@pytest.mark.module_test
class TestDevAssistantCorpusSchema:
    def test_yaml_loads_twelve_cases(self, corpus):
        cases = corpus.get("cases") or []
        assert len(cases) == 12
        ids = {c["id"] for c in cases}
        assert ids == {f"DA-{i:02d}" for i in range(1, 13)}

    @pytest.mark.parametrize("case_id", [f"DA-{i:02d}" for i in range(1, 13)])
    def test_each_case_has_user_or_turns(self, corpus, case_id):
        case = next(c for c in corpus["cases"] if c["id"] == case_id)
        if case.get("turns"):
            assert len(case["turns"]) >= 2
        else:
            assert (case.get("user") or "").strip()


@pytest.mark.module_test
class TestDevAssistantCorpusMockPipeline:
    """Mock LLM returns canonical text → AgentLoop → keyword assertions."""

    @pytest.fixture
    def agent_loop(self, mock_llm_client):
        from butler.tools.registry import dispatch_tool, get_tool_definitions

        return AgentLoop(
            client=mock_llm_client,
            system_prompt="你是开发助手，直接回答技术问题。",
            tools=get_tool_definitions(),
            tool_dispatcher=dispatch_tool,
            config=LoopConfig(stream=False, max_iterations=3),
        )

    @pytest.mark.parametrize(
        "case_id",
        [f"DA-{i:02d}" for i in range(1, 11)] + ["DA-12"],
    )
    def test_single_turn_mock_satisfies_keywords(
        self, agent_loop, mock_llm_client, corpus, case_id
    ):
        case = next(c for c in corpus["cases"] if c["id"] == case_id)
        answer = _build_canonical_answer(case)
        mock_llm_client.complete.return_value = _canonical_response(answer)
        mock_llm_client.stream.return_value = mock_llm_client.complete.return_value

        result = agent_loop.run(case["user"])
        assert result.status.value == "completed"
        _assert_keywords(result.final_response or "", case)

    def test_da11_multi_turn_pytest_followup(self, agent_loop, mock_llm_client, corpus):
        case = next(c for c in corpus["cases"] if c["id"] == "DA-11")
        t1, t2 = case["turns"]
        r1 = _build_canonical_answer({"title": "round1", **t1})
        r2 = _build_canonical_answer({"title": "round2", **t2})
        mock_llm_client.complete.side_effect = [
            _canonical_response(r1),
            _canonical_response(r2),
        ]
        mock_llm_client.stream.side_effect = (
            lambda *a, **k: mock_llm_client.complete.side_effect[
                min(mock_llm_client.complete.call_count - 1, 1)
            ]
        )

        agent_loop.reset()
        out1 = agent_loop.run(t1["user"])
        _assert_keywords(out1.final_response or "", t1)

        out2 = agent_loop.run(t2["user"])
        _assert_keywords(out2.final_response or "", t2)
        assert "unittest" in (out2.final_response or "").lower() or "pytest" in (
            out2.final_response or ""
        )


@pytest.mark.module_test
class TestDevAssistantCorpusButlerLead:
    """灵文 Lead 场景：代码生成类应收口为 delegate，而非厂长直接长篇作答。"""

    def test_da01_lead_should_delegate_not_write(self, lingwen_handler, patch_llm):
        from butler.tools.registry import dispatch_tool
        from tests.test_gateway_dev_conversations import _bind_llm_script
        from tests.test_gateway_acceptance import _tool_response, _text_response

        handler, _proj = lingwen_handler
        corpus = _load_corpus()
        case = next(c for c in corpus["cases"] if c["id"] == "DA-01")
        mock_complete, mock_stream = patch_llm
        _bind_llm_script(
            mock_complete,
            mock_stream,
            [
                _tool_response(
                    "delegate_task",
                    {"role": "dev", "task": "编写读取 sales.csv 计算 amount 列总和的 Python 函数"},
                ),
                _text_response("已创建 sales 读取函数"),
                _text_response("已委派开发代理完成代码任务"),
            ],
        )

        with patch(
            "butler.gateway.message_handler.dispatch_tool",
            wraps=dispatch_tool,
        ) as spy:
            handler.handle_message(
                case["user"].strip(),
                session_key="wechat:u1",
                platform="wechat",
            )
            names = [c[0][0] for c in spy.call_args_list if c[0]]

        assert "delegate_task" in names
        assert "write_file" not in names


# Reuse lingwen fixture from dev conversation tests
@pytest.fixture
def lingwen_handler(tmp_path, monkeypatch, tmp_butler_home):
    from butler.gateway.message_handler import ButlerMessageHandler
    from butler.report import clear_report_cache
    from tests.test_gateway_dev_conversations import _setup_lingwen_gateway_project
    from tests.test_gateway_handler import _reset_singletons

    clear_report_cache()
    _setup_lingwen_gateway_project(tmp_path, monkeypatch)
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    _reset_singletons()
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project_for_chat(
        platform="wechat", chat_id="u1", name="灵文1号",
    )
    return handler, None


@pytest.fixture
def patch_llm(mock_llm_response):
    from tests.test_gateway_acceptance import LLM_PATCH
    from unittest.mock import patch

    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        default = mock_llm_response()
        mock_complete.return_value = default
        mock_stream.return_value = default
        yield mock_complete, mock_stream


@pytest.mark.live_llm
class TestDevAssistantCorpusLive:
    """Real MiniMax answers checked against keyword rubric (full 12-case round)."""

    @pytest.fixture(autouse=True)
    def _require_live(self):
        from tests.test_real_api_smoke import _require_smoke_enabled

        _require_smoke_enabled()

    @pytest.fixture
    def live_loop(self):
        from butler.transport.llm_client import LLMClient
        from butler.tools.registry import dispatch_tool, get_tool_definitions

        client = LLMClient(provider="minimax")
        return AgentLoop(
            client=client,
            system_prompt=(
                "你是专业开发助手，回答准确、简洁。"
                "涉及 Git/Docker/安全时给出可执行命令或明确风险提醒。"
                "用户要代码时给出完整可运行示例。"
            ),
            tools=get_tool_definitions(),
            tool_dispatcher=dispatch_tool,
            config=LoopConfig(stream=False, max_iterations=8),
        )

    @pytest.mark.parametrize(
        "case_id",
        [f"DA-{i:02d}" for i in range(1, 11)] + ["DA-12"],
    )
    def test_live_single_turn_keywords(self, live_loop, corpus, case_id):
        case = next(c for c in corpus["cases"] if c["id"] == case_id)
        live_loop.reset()
        result = live_loop.run(case["user"])
        assert result.status.value == "completed", (
            f"{case_id} loop status={result.status.value}"
        )
        assert result.final_response, f"{case_id} empty response"
        _assert_keywords(result.final_response, case)

    def test_live_da11_multi_turn(self, live_loop, corpus):
        case = next(c for c in corpus["cases"] if c["id"] == "DA-11")
        t1, t2 = case["turns"]
        live_loop.reset()
        r1 = live_loop.run(t1["user"])
        assert r1.final_response
        _assert_keywords(r1.final_response, t1)
        r2 = live_loop.run(t2["user"])
        assert r2.final_response
        _assert_keywords(r2.final_response, t2)
