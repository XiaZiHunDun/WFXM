"""Run pattern-based prompt eval cases from ``tests/fixtures/prompt_eval/``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CASES = _REPO_ROOT / "tests" / "fixtures" / "prompt_eval" / "cases.yaml"


@dataclass
class PromptEvalCase:
    id: str
    file: str
    must_contain: list[str] = field(default_factory=list)
    must_not_contain: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class PromptEvalResult:
    case_id: str
    ok: bool
    errors: list[str] = field(default_factory=list)
    llm_score: int | None = None
    llm_note: str = ""


def _load_cases(path: Path | None = None) -> list[PromptEvalCase]:
    p = path or _DEFAULT_CASES
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raw = data.get("cases") or []
    out: list[PromptEvalCase] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        cid = str(row.get("id") or "").strip()
        rel = str(row.get("file") or "").strip()
        if not cid or not rel:
            continue
        out.append(
            PromptEvalCase(
                id=cid,
                file=rel,
                must_contain=[str(x) for x in (row.get("must_contain") or []) if str(x).strip()],
                must_not_contain=[
                    str(x) for x in (row.get("must_not_contain") or []) if str(x).strip()
                ],
                description=str(row.get("description") or ""),
            )
        )
    return out


def _eval_one(case: PromptEvalCase, *, repo_root: Path, use_llm: bool = False) -> PromptEvalResult:
    path = repo_root / case.file
    errors: list[str] = []
    if not path.is_file():
        return PromptEvalResult(case.id, False, [f"missing file: {case.file}"])
    text = path.read_text(encoding="utf-8")
    for needle in case.must_contain:
        if needle not in text:
            errors.append(f"missing required phrase: {needle!r}")
    for needle in case.must_not_contain:
        if needle in text:
            errors.append(f"forbidden phrase present: {needle!r}")
    llm_score: int | None = None
    llm_note = ""
    if use_llm and not errors:
        from butler.prompt_eval.llm_rubric import (
            llm_rubric_passes,
            prompt_eval_llm_enabled,
            score_prompt_eval_llm,
        )

        if prompt_eval_llm_enabled():
            llm_score, llm_note = score_prompt_eval_llm(case, text)
            if llm_score is not None and not llm_rubric_passes(llm_score):
                errors.append(f"LLM rubric score {llm_score} < min ({llm_note})")
    return PromptEvalResult(case.id, not errors, errors, llm_score=llm_score, llm_note=llm_note)


def run_prompt_eval(
    *,
    cases_path: Path | None = None,
    repo_root: Path | None = None,
    use_llm: bool = False,
) -> tuple[bool, list[PromptEvalResult]]:
    root = (repo_root or _REPO_ROOT).resolve()
    cases = _load_cases(cases_path)
    results = [_eval_one(c, repo_root=root, use_llm=use_llm) for c in cases]
    ok = all(r.ok for r in results)
    return ok, results


def format_prompt_eval_report(results: list[PromptEvalResult]) -> str:
    lines = [f"Prompt eval: {sum(1 for r in results if r.ok)}/{len(results)} passed"]
    for r in results:
        mark = "OK" if r.ok else "FAIL"
        extra = ""
        if r.llm_score is not None:
            extra = f" llm={r.llm_score}"
            if r.llm_note:
                extra += f" ({r.llm_note[:60]})"
        lines.append(f"  [{mark}] {r.case_id}{extra}")
        for err in r.errors:
            lines.append(f"       - {err}")
    return "\n".join(lines)


__all__ = [
    "PromptEvalCase",
    "PromptEvalResult",
    "format_prompt_eval_report",
    "run_prompt_eval",
]
