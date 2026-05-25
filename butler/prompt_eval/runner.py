"""Run pattern-based prompt eval cases from ``tests/fixtures/prompt_eval/``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

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


def _eval_one(case: PromptEvalCase, *, repo_root: Path) -> PromptEvalResult:
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
    return PromptEvalResult(case.id, not errors, errors)


def run_prompt_eval(
    *,
    cases_path: Path | None = None,
    repo_root: Path | None = None,
) -> tuple[bool, list[PromptEvalResult]]:
    root = (repo_root or _REPO_ROOT).resolve()
    cases = _load_cases(cases_path)
    results = [_eval_one(c, repo_root=root) for c in cases]
    ok = all(r.ok for r in results)
    return ok, results


def format_prompt_eval_report(results: list[PromptEvalResult]) -> str:
    lines = [f"Prompt eval: {sum(1 for r in results if r.ok)}/{len(results)} passed"]
    for r in results:
        mark = "OK" if r.ok else "FAIL"
        lines.append(f"  [{mark}] {r.case_id}")
        for err in r.errors:
            lines.append(f"       - {err}")
    return "\n".join(lines)


__all__ = [
    "PromptEvalCase",
    "PromptEvalResult",
    "format_prompt_eval_report",
    "run_prompt_eval",
]
