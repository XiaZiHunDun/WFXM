"""Corpus test harness — stable import surface for runners and legacy tests."""

from tests.corpus.harness.agent_loop import (
    DEFAULT_LIVE_PROMPT,
    bind_llm_script,
    live_minimax_model,
    make_live_loop,
    multi_turn_case_ids,
    single_turn_case_ids,
)
from tests.corpus.harness.archive import append_run_record, archive_enabled, classify_fail
from tests.corpus.harness.keywords import (
    assert_keywords,
    build_canonical_answer,
    canonical_response,
    keyword_groups,
)
from tests.corpus.harness.loader import (
    load_corpus,
    resolve_corpus_path,
    validate_corpus_schema,
    validate_gateway_corpus,
)
from tests.corpus.harness.registry import (
    agent_loop_suite_ids,
    gateway_runner_modules,
    get_suite,
    iter_suites,
    load_registry,
    load_suite_corpus,
    resolve_runner_module_path,
)

__all__ = [
    "agent_loop_suite_ids",
    "DEFAULT_LIVE_PROMPT",
    "append_run_record",
    "archive_enabled",
    "assert_keywords",
    "bind_llm_script",
    "build_canonical_answer",
    "canonical_response",
    "classify_fail",
    "keyword_groups",
    "live_minimax_model",
    "load_corpus",
    "make_live_loop",
    "multi_turn_case_ids",
    "resolve_corpus_path",
    "single_turn_case_ids",
    "validate_corpus_schema",
    "validate_gateway_corpus",
    "iter_suites",
    "load_registry",
    "load_suite_corpus",
    "get_suite",
    "gateway_runner_modules",
    "resolve_runner_module_path",
]
