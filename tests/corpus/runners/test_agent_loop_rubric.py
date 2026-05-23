"""Generic AgentLoop + keyword-rubric runner for all dev_assistant.* suites.

Registry: tests/corpus/registry.yaml
Run:
  PYTHONPATH=. pytest tests/corpus/runners/test_agent_loop_rubric.py -m corpus_mock -q
  BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. pytest tests/corpus/runners/test_agent_loop_rubric.py -m corpus_live -v
"""

from __future__ import annotations

from typing import Any

import pytest

from butler.core.agent_loop import AgentLoop, LoopConfig
from tests.corpus.harness import (
    DEFAULT_LIVE_PROMPT,
    append_run_record,
    assert_keywords,
    build_canonical_answer,
    canonical_response,
    classify_fail,
    live_minimax_model,
    make_live_loop,
    multi_turn_case_ids,
    single_turn_case_ids,
    validate_corpus_schema,
)
from tests.corpus.harness.registry import (
    agent_loop_suite_ids,
    get_suite,
    load_suite_corpus,
)

_SUITE_IDS = agent_loop_suite_ids()

# (suite_id, case_id) for parametrized single-turn mock/live
_SINGLE_TURN_PARAMS: list[tuple[str, str]] = []
_MULTI_TURN_PARAMS: list[tuple[str, str]] = []
_LIVE_SMOKE_PARAMS: list[tuple[str, str]] = []

for _sid in _SUITE_IDS:
    _entry = get_suite(_sid)
    _corpus, _ = load_suite_corpus(_entry)
    for _cid in single_turn_case_ids(_corpus):
        _SINGLE_TURN_PARAMS.append((_sid, _cid))
    for _cid in sorted(multi_turn_case_ids(_corpus)):
        _MULTI_TURN_PARAMS.append((_sid, _cid))
    for _cid in _corpus.get("live_smoke_ids") or []:
        _LIVE_SMOKE_PARAMS.append((_sid, _cid))


def _case_for(corpus: dict[str, Any], case_id: str) -> dict[str, Any]:
    return next(c for c in corpus["cases"] if c["id"] == case_id)


@pytest.fixture
def suite_corpus(request):
    """Parametrized by suite_id when test uses indirect or dual param."""
    suite_id = request.param if hasattr(request, "param") and isinstance(request.param, str) else request.getfixturevalue("suite_id")
    entry = get_suite(suite_id)
    corpus, path = load_suite_corpus(entry)
    return corpus, entry, path


@pytest.fixture
def agent_loop_rubric(mock_llm_client) -> AgentLoop:
    from butler.tools.registry import dispatch_tool, get_tool_definitions

    return AgentLoop(
        client=mock_llm_client,
        system_prompt="你是专业开发助手。",
        tools=get_tool_definitions(),
        tool_dispatcher=dispatch_tool,
        config=LoopConfig(stream=False, max_iterations=3),
    )


@pytest.mark.corpus
@pytest.mark.corpus_mock
@pytest.mark.module_test
class TestAgentLoopRubricRegistry:
    @pytest.mark.parametrize("suite_id", _SUITE_IDS)
    def test_schema_valid(self, suite_id: str):
        entry = get_suite(suite_id)
        corpus, _ = load_suite_corpus(entry)
        errors = validate_corpus_schema(corpus, channel=entry.get("channel", "agent_loop"))
        assert not errors, f"{suite_id}: {errors}"

    @pytest.mark.parametrize("suite_id", _SUITE_IDS)
    def test_meta_live_model(self, suite_id: str):
        corpus, _ = load_suite_corpus(get_suite(suite_id))
        assert (corpus.get("meta") or {}).get("live_model") == "MiniMax-M2.7"


@pytest.mark.corpus
@pytest.mark.corpus_mock
@pytest.mark.module_test
class TestAgentLoopRubricMock:
    @pytest.mark.parametrize(("suite_id", "case_id"), _SINGLE_TURN_PARAMS)
    def test_single_turn(
        self,
        agent_loop_rubric: AgentLoop,
        mock_llm_client,
        suite_id: str,
        case_id: str,
    ):
        corpus, _ = load_suite_corpus(get_suite(suite_id))
        case = _case_for(corpus, case_id)
        answer = build_canonical_answer(case)
        mock_llm_client.complete.return_value = canonical_response(answer)
        mock_llm_client.stream.return_value = mock_llm_client.complete.return_value
        agent_loop_rubric.reset()
        result = agent_loop_rubric.run(case["user"])
        assert result.status.value == "completed", f"{suite_id}/{case_id}"
        assert_keywords(result.final_response or "", case)

    @pytest.mark.parametrize(("suite_id", "mt_id"), _MULTI_TURN_PARAMS)
    def test_multi_turn(
        self,
        agent_loop_rubric: AgentLoop,
        mock_llm_client,
        suite_id: str,
        mt_id: str,
    ):
        corpus, _ = load_suite_corpus(get_suite(suite_id))
        case = _case_for(corpus, mt_id)
        agent_loop_rubric.reset()
        for turn in case.get("turns") or []:
            answer = build_canonical_answer({"title": mt_id, **turn})
            mock_llm_client.complete.return_value = canonical_response(answer)
            mock_llm_client.stream.return_value = mock_llm_client.complete.return_value
            result = agent_loop_rubric.run(turn["user"])
            assert_keywords(result.final_response or "", turn)


@pytest.mark.corpus
@pytest.mark.corpus_live
@pytest.mark.live_llm
class TestAgentLoopRubricLive:
    @pytest.fixture(autouse=True)
    def _require_live(self):
        from tests.test_real_api_smoke import _require_smoke_enabled

        _require_smoke_enabled()

    @pytest.fixture
    def live_loop_factory(self):
        def _factory(corpus: dict[str, Any]) -> AgentLoop:
            loop = make_live_loop(system_prompt=DEFAULT_LIVE_PROMPT)
            assert loop.client.model == live_minimax_model(corpus)
            return loop

        return _factory

    def _record(
        self,
        *,
        suite_id: str,
        case: dict[str, Any],
        loop_status: str,
        passed: bool,
        keyword_error: str | None,
        response: str,
        model: str,
    ) -> None:
        append_run_record(
            suite_id=suite_id,
            case_id=case["id"],
            dimension=case.get("dimension", ""),
            status="passed" if passed else "failed",
            fail_type=classify_fail(
                loop_status=loop_status, passed=passed, keyword_error=keyword_error
            ),
            loop_status=loop_status,
            model=model,
            response_excerpt=response,
        )

    @pytest.mark.parametrize(("suite_id", "case_id"), _SINGLE_TURN_PARAMS)
    def test_single_turn_full(
        self,
        live_loop_factory,
        suite_id: str,
        case_id: str,
    ):
        entry = get_suite(suite_id)
        corpus, _ = load_suite_corpus(entry)
        case = _case_for(corpus, case_id)
        loop = live_loop_factory(corpus)
        loop.reset()
        result = loop.run(case["user"])
        model = live_minimax_model(corpus)
        status = result.status.value
        response = result.final_response or ""
        kw_err: str | None = None
        try:
            assert status == "completed", case_id
            assert response, case_id
            assert_keywords(response, case)
            self._record(
                suite_id=suite_id,
                case=case,
                loop_status=status,
                passed=True,
                keyword_error=None,
                response=response,
                model=model,
            )
        except AssertionError as exc:
            kw_err = str(exc) if "missing required" in str(exc) or "none matched" in str(exc) else None
            self._record(
                suite_id=suite_id,
                case=case,
                loop_status=status,
                passed=False,
                keyword_error=kw_err or str(exc),
                response=response,
                model=model,
            )
            raise

    @pytest.mark.corpus_smoke
    @pytest.mark.parametrize(("suite_id", "case_id"), _LIVE_SMOKE_PARAMS)
    def test_smoke_subset(self, live_loop_factory, suite_id: str, case_id: str):
        entry = get_suite(suite_id)
        corpus, _ = load_suite_corpus(entry)
        case = _case_for(corpus, case_id)
        loop = live_loop_factory(corpus)
        loop.reset()
        result = loop.run(case["user"])
        response = result.final_response or ""
        model = live_minimax_model(corpus)
        status = result.status.value
        try:
            assert response
            assert_keywords(response, case)
            self._record(
                suite_id=suite_id,
                case=case,
                loop_status=status,
                passed=True,
                keyword_error=None,
                response=response,
                model=model,
            )
        except AssertionError as exc:
            kw_err = str(exc) if "missing required" in str(exc) or "none matched" in str(exc) else None
            fail_type = classify_fail(
                loop_status=status, passed=False, keyword_error=kw_err
            )
            if case.get("dimension") == "safety_bounds" and fail_type == "keyword_miss":
                fail_type = "unsafe_ok"
            append_run_record(
                suite_id=suite_id,
                case_id=case["id"],
                dimension=case.get("dimension", ""),
                status="failed",
                fail_type=fail_type,
                loop_status=status,
                model=model,
                response_excerpt=response,
            )
            raise

    @pytest.mark.parametrize(("suite_id", "mt_id"), _MULTI_TURN_PARAMS)
    def test_multi_turn(self, live_loop_factory, suite_id: str, mt_id: str):
        entry = get_suite(suite_id)
        corpus, _ = load_suite_corpus(entry)
        case = _case_for(corpus, mt_id)
        loop = live_loop_factory(corpus)
        loop.reset()
        for turn in case["turns"]:
            result = loop.run(turn["user"])
            assert result.final_response
            assert_keywords(result.final_response, turn)
