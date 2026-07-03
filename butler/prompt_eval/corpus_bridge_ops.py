"""Prompt eval corpus bridge best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any


def load_corpus_case_safe(suite_id: str, case_id: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        from tests.corpus.harness.registry import get_suite, load_suite_corpus

        corpus, _ = load_suite_corpus(get_suite(suite_id))
        case = next(c for c in corpus["cases"] if c["id"] == case_id)
        return case, None
    except Exception as exc:
        return None, f"{suite_id}/{case_id}: load failed: {exc}"


def run_corpus_setup_safe(fn: Any) -> str | None:
    try:
        fn()
        return None
    except Exception as exc:
        return f"corpus bridge setup failed: {exc}"


def run_live_case_safe(
    fn: Any,
    *,
    suite_id: str,
    case_id: str,
) -> str | None:
    try:
        fn()
        return None
    except AssertionError as exc:
        return f"{suite_id}/{case_id}: {exc}"
    except Exception as exc:
        return f"{suite_id}/{case_id}: {exc}"
