"""CLI: ``butler prompt eval``."""

from __future__ import annotations

import argparse
from pathlib import Path


def register_prompt_eval_parser(sub: argparse._SubParsersAction) -> None:
    prompt = sub.add_parser("prompt", help="Prompt 契约与 eval")
    sp = prompt.add_subparsers(dest="prompt_cmd", required=True)
    p_eval = sp.add_parser("eval", help="跑 pattern rubric（无 LLM）")
    p_eval.add_argument(
        "--cases",
        default="",
        help="cases.yaml 路径（默认 tests/fixtures/prompt_eval/cases.yaml）",
    )
    p_eval.add_argument(
        "--corpus",
        action="store_true",
        help="追加 corpus mock 子集（tests/fixtures/prompt_eval/corpus_cases.yaml）",
    )
    p_eval.add_argument(
        "--corpus-overlay",
        default="",
        help="corpus overlay yaml 路径",
    )
    p_eval.add_argument(
        "--corpus-live",
        action="store_true",
        help="追加 corpus live 子集（需 BUTLER_RUN_REAL_API_SMOKE=1 + API Key）",
    )
    p_eval.add_argument(
        "--corpus-live-smoke",
        action="store_true",
        help="追加 registry live_smoke_ids（v2–v5 全量 smoke，需 API Key）",
    )
    p_eval.add_argument(
        "--corpus-live-full",
        action="store_true",
        help="追加 registry 单轮 live 子集（BUTLER_PROMPT_EVAL_LIVE_MAX 条上限）",
    )
    p_eval.add_argument(
        "--llm",
        action="store_true",
        help="pattern 通过后追加辅助模型 rubric（BUTLER_PROMPT_EVAL_LLM=1）",
    )
    p_eval.set_defaults(func=_cmd_prompt_eval)


def _cmd_prompt_eval(ns: argparse.Namespace) -> int:
    from butler.prompt_eval.runner import format_prompt_eval_report, run_prompt_eval

    cases_path = None
    raw = str(getattr(ns, "cases", "") or "").strip()
    if raw:
        cases_path = Path(raw).expanduser()
    use_llm = bool(getattr(ns, "llm", False))
    if use_llm:
        import os

        os.environ["BUTLER_PROMPT_EVAL_LLM"] = "1"
    ok, results = run_prompt_eval(cases_path=cases_path, use_llm=use_llm)
    print(format_prompt_eval_report(results))
    exit_code = 0 if ok else 1

    if getattr(ns, "corpus", False):
        from butler.prompt_eval.corpus_bridge import run_corpus_prompt_subset

        overlay = None
        overlay_raw = str(getattr(ns, "corpus_overlay", "") or "").strip()
        if overlay_raw:
            overlay = Path(overlay_raw).expanduser()
        corpus_ok, errors = run_corpus_prompt_subset(overlay_path=overlay)
        print("\n--- corpus mock ---")
        if corpus_ok:
            print("corpus: PASS")
        else:
            for err in errors:
                print(f"corpus FAIL: {err}")
            exit_code = 1

    if getattr(ns, "corpus_live", False):
        from butler.prompt_eval.corpus_bridge import run_corpus_prompt_live_subset

        overlay = None
        overlay_raw = str(getattr(ns, "corpus_overlay", "") or "").strip()
        if overlay_raw:
            overlay = Path(overlay_raw).expanduser()
        live_ok, live_errors = run_corpus_prompt_live_subset(overlay_path=overlay)
        print("\n--- corpus live ---")
        if live_ok:
            print("corpus live: PASS")
        else:
            for err in live_errors:
                print(f"corpus live: {err}")
            exit_code = 1

    if getattr(ns, "corpus_live_smoke", False):
        from butler.prompt_eval.corpus_bridge import run_corpus_prompt_live_smoke_registry

        smoke_ok, smoke_errors = run_corpus_prompt_live_smoke_registry()
        print("\n--- corpus live smoke (registry) ---")
        if smoke_ok:
            print("corpus live smoke: PASS")
        else:
            for err in smoke_errors:
                print(f"corpus live smoke: {err}")
            exit_code = 1

    if getattr(ns, "corpus_live_full", False):
        from butler.prompt_eval.corpus_bridge import run_corpus_prompt_live_full

        full_ok, full_errors = run_corpus_prompt_live_full()
        print("\n--- corpus live full (registry single-turn) ---")
        if full_ok:
            print("corpus live full: PASS")
        else:
            for err in full_errors:
                print(f"corpus live full: {err}")
            exit_code = 1
    return exit_code
