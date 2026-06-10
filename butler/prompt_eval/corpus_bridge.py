"""Bridge prompt-eval gate to corpus mock rubric (subset)."""

from __future__ import annotations

from butler.env_parse import int_env
from pathlib import Path

import yaml

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_OVERLAY = _REPO / "tests" / "fixtures" / "prompt_eval" / "corpus_cases.yaml"


def load_corpus_overlay(path: Path | None = None) -> list[dict[str, str]]:
    p = path or _DEFAULT_OVERLAY
    if not p.is_file():
        return []
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rows = data.get("cases") or []
    out: list[dict[str, str]] = []
    for row in rows:
        if isinstance(row, dict) and row.get("suite_id") and row.get("case_id"):
            out.append(
                {
                    "suite_id": str(row["suite_id"]),
                    "case_id": str(row["case_id"]),
                    "note": str(row.get("note") or ""),
                }
            )
    return out


def run_corpus_prompt_subset(
    *,
    overlay_path: Path | None = None,
    system_prompt_path: str = "butler/prompts/butler_system.md",
) -> tuple[bool, list[str]]:
    """Run mock AgentLoop cases with production system prompt excerpt (no live API)."""
    from butler.core.agent_loop import AgentLoop, LoopConfig
    from butler.tools.registry import dispatch_tool, get_tool_definitions
    from tests.corpus.harness import (
        assert_keywords,
        build_canonical_answer,
        canonical_response,
    )
    from tests.corpus.harness.registry import get_suite, load_suite_corpus

    overlay = load_corpus_overlay(overlay_path)
    if not overlay:
        return True, ["no corpus overlay cases"]

    sp_path = _REPO / system_prompt_path
    system = sp_path.read_text(encoding="utf-8")[:12000] if sp_path.is_file() else "你是 Butler。"

    errors: list[str] = []
    try:
        from unittest.mock import MagicMock

        client = MagicMock()
        client.provider_name = "mock"
        client.model = "mock"
        loop = AgentLoop(
            client=client,
            system_prompt=system,
            tools=get_tool_definitions(),
            tool_dispatcher=dispatch_tool,
            config=LoopConfig(stream=False, max_iterations=2),
        )
        for row in overlay:
            sid = row["suite_id"]
            cid = row["case_id"]
            try:
                corpus, _ = load_suite_corpus(get_suite(sid))
                case = next(c for c in corpus["cases"] if c["id"] == cid)
            except Exception as exc:
                errors.append(f"{sid}/{cid}: load failed: {exc}")
                continue
            answer = build_canonical_answer(case)
            client.complete.return_value = canonical_response(answer)
            client.stream.return_value = client.complete.return_value
            loop.reset()
            result = loop.run(case["user"])
            if result.status.value != "completed":
                errors.append(f"{sid}/{cid}: status={result.status.value}")
                continue
            try:
                assert_keywords(result.final_response or "", case)
            except AssertionError as exc:
                errors.append(f"{sid}/{cid}: {exc}")
    except Exception as exc:
        errors.append(f"corpus bridge setup failed: {exc}")

    return len(errors) == 0, errors


def corpus_live_enabled() -> bool:
    import os

    return os.getenv("BUTLER_RUN_REAL_API_SMOKE") == "1"


def iter_registry_live_smoke_cases() -> list[tuple[str, str]]:
    """All (suite_id, case_id) from registry suites with ``live_smoke_from_corpus: true``."""
    from tests.corpus.harness.registry import get_suite, iter_suites, load_suite_corpus

    out: list[tuple[str, str]] = []
    for entry in iter_suites(runner="agent_loop_rubric"):
        if not entry.get("live_smoke_from_corpus"):
            continue
        sid = str(entry["suite_id"])
        corpus, _ = load_suite_corpus(get_suite(sid))
        for cid in corpus.get("live_smoke_ids") or []:
            out.append((sid, str(cid)))
    return out


def _run_live_cases(
    cases: list[tuple[str, str]],
    *,
    system_prompt_path: str = "butler/prompts/butler_system.md",
) -> tuple[bool, list[str]]:
    from tests.corpus.harness import DEFAULT_LIVE_PROMPT, assert_keywords, make_live_loop
    from tests.corpus.harness.registry import get_suite, load_suite_corpus

    sp_path = _REPO / system_prompt_path
    system = sp_path.read_text(encoding="utf-8")[:12000] if sp_path.is_file() else DEFAULT_LIVE_PROMPT
    errors: list[str] = []
    for sid, cid in cases:
        try:
            corpus, _ = load_suite_corpus(get_suite(sid))
            case = next(c for c in corpus["cases"] if c["id"] == cid)
        except Exception as exc:
            errors.append(f"{sid}/{cid}: load failed: {exc}")
            continue
        if case.get("turns"):
            errors.append(f"{sid}/{cid}: multi-turn not supported in prompt-eval live")
            continue
        try:
            loop = make_live_loop(system_prompt=system)
            loop.reset()
            result = loop.run(case["user"])
            if result.status.value != "completed":
                errors.append(f"{sid}/{cid}: status={result.status.value}")
                continue
            assert_keywords(result.final_response or "", case)
        except AssertionError as exc:
            errors.append(f"{sid}/{cid}: {exc}")
        except Exception as exc:
            errors.append(f"{sid}/{cid}: {exc}")
    return len(errors) == 0, errors


def run_corpus_prompt_live_subset(
    *,
    overlay_path: Path | None = None,
    system_prompt_path: str = "butler/prompts/butler_system.md",
) -> tuple[bool, list[str]]:
    """Run overlay cases against a real LLM (requires ``BUTLER_RUN_REAL_API_SMOKE=1``)."""
    if not corpus_live_enabled():
        return False, ["corpus live skipped: set BUTLER_RUN_REAL_API_SMOKE=1 and API keys"]

    overlay = load_corpus_overlay(overlay_path)
    if not overlay:
        return True, ["no corpus overlay cases"]
    cases = [(row["suite_id"], row["case_id"]) for row in overlay]
    return _run_live_cases(cases, system_prompt_path=system_prompt_path)


def _prompt_eval_live_max_cases() -> int:
    import os

    try:
        return int_env("BUTLER_PROMPT_EVAL_LIVE_MAX", 12, min=0)
    except ValueError:
        return 12


def iter_registry_live_single_turn_cases() -> list[tuple[str, str]]:
    """Single-turn cases from ``live_smoke_from_corpus`` suites (capped by env)."""
    from tests.corpus.harness.agent_loop import single_turn_case_ids
    from tests.corpus.harness.registry import get_suite, iter_suites, load_suite_corpus

    cap = _prompt_eval_live_max_cases()
    out: list[tuple[str, str]] = []
    for entry in iter_suites(runner="agent_loop_rubric"):
        if not entry.get("live_smoke_from_corpus"):
            continue
        sid = str(entry["suite_id"])
        corpus, _ = load_suite_corpus(get_suite(sid))
        for cid in single_turn_case_ids(corpus):
            out.append((sid, cid))
            if cap and len(out) >= cap:
                return out
    return out


def run_corpus_prompt_live_smoke_registry(
    *,
    system_prompt_path: str = "butler/prompts/butler_system.md",
) -> tuple[bool, list[str]]:
    """Run registry ``live_smoke_ids`` for v2–v5 agent_loop suites (full smoke, not overlay-only)."""
    if not corpus_live_enabled():
        return False, ["corpus live smoke skipped: set BUTLER_RUN_REAL_API_SMOKE=1 and API keys"]
    cases = iter_registry_live_smoke_cases()
    if not cases:
        return True, ["no registry live_smoke cases"]
    return _run_live_cases(cases, system_prompt_path=system_prompt_path)


def run_corpus_prompt_live_full(
    *,
    system_prompt_path: str = "butler/prompts/butler_system.md",
) -> tuple[bool, list[str]]:
    """Run capped single-turn live cases from v2–v5 corpora."""
    if not corpus_live_enabled():
        return False, ["corpus live full skipped: set BUTLER_RUN_REAL_API_SMOKE=1 and API keys"]
    cases = iter_registry_live_single_turn_cases()
    if not cases:
        return True, ["no registry single-turn live cases"]
    return _run_live_cases(cases, system_prompt_path=system_prompt_path)


__all__ = [
    "corpus_live_enabled",
    "iter_registry_live_smoke_cases",
    "iter_registry_live_single_turn_cases",
    "load_corpus_overlay",
    "run_corpus_prompt_live_full",
    "run_corpus_prompt_live_smoke_registry",
    "run_corpus_prompt_live_subset",
    "run_corpus_prompt_subset",
]
