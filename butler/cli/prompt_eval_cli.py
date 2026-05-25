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
    p_eval.set_defaults(func=_cmd_prompt_eval)


def _cmd_prompt_eval(ns: argparse.Namespace) -> int:
    from butler.prompt_eval.runner import format_prompt_eval_report, run_prompt_eval

    cases_path = None
    raw = str(getattr(ns, "cases", "") or "").strip()
    if raw:
        cases_path = Path(raw).expanduser()
    ok, results = run_prompt_eval(cases_path=cases_path)
    print(format_prompt_eval_report(results))
    return 0 if ok else 1
