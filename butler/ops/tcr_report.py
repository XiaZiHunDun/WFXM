"""Trajectory Compliance Rate (TCR) report writer (AP-2)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / ".butler" / "reports" / "tcr-latest.json"
DEFAULT_THRESHOLD = 0.98

_TCR_PYTEST_TARGETS = [
    "tests/test_tool_boundary_validators.py",
    "tests/gateway/test_rag_failure_degradation.py",
    "tests/corpus/runners/test_trajectory_compliance_catalog.py",
]


def _parse_junit(path: Path) -> tuple[int, int, list[str]]:
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag == "testsuite":
        suites = [root]
    else:
        suites = list(root.findall("testsuite"))
    total = passed = 0
    failed_ids: list[str] = []
    for suite in suites:
        for case in suite.findall("testcase"):
            total += 1
            name = case.get("name") or ""
            cls = case.get("classname") or ""
            failed = case.find("failure") is not None or case.find("error") is not None
            if failed:
                failed_ids.append(f"{cls}::{name}")
            else:
                passed += 1
    return total, passed, failed_ids


def run_tcr_pytest(*, junit_path: Path) -> int:
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *_TCR_PYTEST_TARGETS,
        "-q",
        "--tb=line",
        f"--junit-xml={junit_path}",
    ]
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env)
    return int(proc.returncode)


def build_report(
    *,
    total: int,
    passed: int,
    failed_ids: list[str],
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    rate = (passed / total) if total else 1.0
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trajectory_compliance_rate": round(rate, 6),
        "threshold": threshold,
        "passed": passed,
        "total": total,
        "failed_count": len(failed_ids),
        "failed": failed_ids[:200],
        "targets": _TCR_PYTEST_TARGETS,
        "ok": rate >= threshold and not failed_ids,
    }


def write_report(report: dict[str, Any], path: Path = DEFAULT_REPORT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run TCR gate and write JSON report")
    parser.add_argument(
        "--threshold",
        type=float,
        default=float(__import__("os").environ.get("BUTLER_TCR_THRESHOLD", DEFAULT_THRESHOLD)),
    )
    parser.add_argument("--junit", type=Path, default=ROOT / ".butler" / "reports" / "tcr-junit.xml")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--warn-only", action="store_true", help="Exit 0 even when below threshold")
    args = parser.parse_args(argv)

    exit_code = run_tcr_pytest(junit_path=args.junit)
    if not args.junit.is_file():
        report = build_report(total=0, passed=0, failed_ids=["junit missing"], threshold=args.threshold)
        write_report(report, args.report)
        print("TCR gate: junit missing", file=sys.stderr)
        return 1

    total, passed, failed_ids = _parse_junit(args.junit)
    report = build_report(
        total=total,
        passed=passed,
        failed_ids=failed_ids,
        threshold=args.threshold,
    )
    write_report(report, args.report)

    rate_pct = report["trajectory_compliance_rate"] * 100
    print(
        f"TCR: {passed}/{total} ({rate_pct:.2f}%) threshold={args.threshold * 100:.1f}% "
        f"-> {args.report}"
    )
    if failed_ids:
        print(f"TCR failures ({len(failed_ids)}):", file=sys.stderr)
        for fid in failed_ids[:10]:
            print(f"  - {fid}", file=sys.stderr)

    if report["ok"]:
        return 0
    if args.warn_only:
        print("TCR below threshold (warn-only mode)", file=sys.stderr)
        return 0
    return exit_code or 1


if __name__ == "__main__":
    raise SystemExit(main())
