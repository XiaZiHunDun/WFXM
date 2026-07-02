"""Hermes 对标能力 pytest 门禁（P0/P1 回归子集）。"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


HERMES_GATE_TESTS: tuple[str, ...] = (
    "tests/test_tool_result_classification.py",
    "tests/test_memory_write_approval.py",
    "tests/test_delegate_summary_budget.py",
    "tests/test_transcript_search.py",
    "tests/test_hermes_improvements.py",
    "tests/test_skill_load_policy.py",
    "tests/test_skill_learn.py",
    "tests/gateway/test_skill_commands.py",
    "tests/test_memory_pending_cli.py",
    "tests/test_coding_recall.py",
    "tests/test_transcript_recall.py",
    "tests/test_unified_recall.py",
)


@dataclass
class HermesGateReport:
    passed: bool
    failures: list[str] = field(default_factory=list)
    stdout_tail: str = ""


def run_hermes_gate(*, repo_root: Path | None = None) -> HermesGateReport:
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(root))
    cmd = [sys.executable, "-m", "pytest", *HERMES_GATE_TESTS, "-q"]
    proc = subprocess.run(
        cmd,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    tail = (proc.stdout or "") + (proc.stderr or "")
    tail = tail.strip()[-4000:]
    if proc.returncode == 0:
        return HermesGateReport(passed=True, stdout_tail=tail)
    failures = [line for line in tail.splitlines() if "FAILED" in line or "ERROR" in line]
    if not failures:
        failures = [f"pytest exit {proc.returncode}"]
    return HermesGateReport(passed=False, failures=failures, stdout_tail=tail)


__all__ = ["HERMES_GATE_TESTS", "HermesGateReport", "run_hermes_gate"]
