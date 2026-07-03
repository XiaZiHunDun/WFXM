"""WeChat gateway corpus → LangFuse scores (phase 4 non-dev regression)."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CORPUS_NAME = "wechat_gateway"
_PASSED_RE = re.compile(r"(?P<passed>\d+)\s+passed")
_FAILED_RE = re.compile(r"(?P<failed>\d+)\s+failed")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _audit_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "wechat_corpus_eval.jsonl"


def catalog_delegate_stats() -> dict[str, Any]:
    """Static stats from utterance catalogs (no pytest run)."""
    from butler.ops.wechat_corpus_eval_ops import catalog_delegate_stats_safe

    return catalog_delegate_stats_safe()


def _parse_pytest_output(output: str) -> dict[str, int]:
    passed = 0
    failed = 0
    for line in output.splitlines():
        pm = _PASSED_RE.search(line)
        fm = _FAILED_RE.search(line)
        if pm or fm:
            if pm:
                passed = int(pm.group("passed"))
            if fm:
                failed = int(fm.group("failed"))
    return {"passed": passed, "failed": failed, "total": passed + failed}


def run_wechat_gateway_corpus(
    *,
    extra_args: list[str] | None = None,
) -> dict[str, Any]:
    """Run mock gateway utterance catalog tests and return pass/fail summary."""
    root = _repo_root()
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/corpus/runners/test_gateway_utterance_catalog.py",
        "-m",
        "corpus_mock",
        "-q",
        "--tb=no",
    ]
    if extra_args:
        cmd.extend(extra_args)

    proc = subprocess.run(
        cmd,
        cwd=str(root),
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": str(root)},
    )
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    counts = _parse_pytest_output(combined)
    if counts["total"] == 0:
        from butler.ops.wechat_corpus_eval_ops import parametrized_catalog_count_safe

        fallback_total = parametrized_catalog_count_safe()
        if fallback_total:
            counts["total"] = fallback_total
            counts["passed"] = fallback_total if proc.returncode == 0 else 0
            counts["failed"] = counts["total"] - counts["passed"]

    pass_rate = counts["passed"] / max(1, counts["total"])
    return {
        "corpus": _CORPUS_NAME,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "total": counts["total"],
        "pass_rate": round(pass_rate, 4),
        "exit_code": proc.returncode,
        "catalog": catalog_delegate_stats(),
    }


def _append_audit(record: dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def push_wechat_corpus_scores(summary: dict[str, Any]) -> dict[str, Any]:
    from butler.ops.eval_bridge import corpus_run_to_scores, push_scores

    total = int(summary.get("total") or 0)
    passed = int(summary.get("passed") or 0)
    catalog = summary.get("catalog") or {}
    delegate_ratio = float(catalog.get("delegate_ratio") or 0.0)

    scores = corpus_run_to_scores(
        _CORPUS_NAME,
        total=total,
        passed=passed,
        tool_accuracy=delegate_ratio if delegate_ratio else 0.0,
    )
    # Alias for assistant_health cross-dimension view
    if scores:
        scores[0].name = f"corpus.{_CORPUS_NAME}.pass_rate"
    push_report = push_scores(scores)
    return {
        "scores_pushed": push_report.scores_pushed,
        "pass_rate": summary.get("pass_rate"),
        "total": total,
    }


def run_and_push_wechat_corpus_eval(
    *,
    push_langfuse: bool = True,
) -> dict[str, Any]:
    """Run gateway corpus gate and optionally push LangFuse scores."""
    summary = run_wechat_gateway_corpus()
    _append_audit(summary)
    if push_langfuse:
        from butler.ops.wechat_corpus_eval_ops import push_wechat_corpus_scores_safe

        langfuse = push_wechat_corpus_scores_safe(summary)
        if langfuse:
            summary["langfuse"] = langfuse
        else:
            summary["langfuse_error"] = "langfuse push failed"
    return summary


__all__ = [
    "catalog_delegate_stats",
    "push_wechat_corpus_scores",
    "run_and_push_wechat_corpus_eval",
    "run_wechat_gateway_corpus",
]
