"""TCR strict flip readiness (calendar + rate) — AP-2 ops helper."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from butler.ops.tcr_report import DEFAULT_REPORT as TCR_LATEST

ROOT = Path(__file__).resolve().parents[2]
READINESS_REPORT = ROOT / ".butler" / "reports" / "tcr-strict-readiness.json"
DEFAULT_STRICT_AFTER = "2026-07-27"
FLIP_COMMAND = "bash scripts/butler-tcr-strict-apply.sh"


def _parse_ymd(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def days_until_flip(*, today: str, strict_after: str) -> int:
    """Days remaining before calendar allows flip (0 on or after flip day)."""
    delta = (_parse_ymd(strict_after) - _parse_ymd(today)).days
    return max(0, delta)


def assess_readiness(
    *,
    tcr_report: dict[str, Any],
    today: str,
    strict_after: str,
) -> dict[str, Any]:
    rate = float(tcr_report.get("trajectory_compliance_rate") or 0.0)
    passed = int(tcr_report.get("passed") or 0)
    total = int(tcr_report.get("total") or 0)
    threshold = float(tcr_report.get("threshold") or 0.98)
    tcr_ok = bool(tcr_report.get("ok")) and total > 0
    calendar_ready = _parse_ymd(today) >= _parse_ymd(strict_after)
    days_left = days_until_flip(today=today, strict_after=strict_after)

    if not tcr_ok:
        status = "fail"
    elif not calendar_ready:
        status = "wait"
    else:
        status = "ready"

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "today": today,
        "strict_after": strict_after,
        "days_until_flip": days_left,
        "calendar_ready": calendar_ready,
        "status": status,
        "tcr": {
            "trajectory_compliance_rate": rate,
            "passed": passed,
            "total": total,
            "threshold": threshold,
            "ok": tcr_ok,
            "report_path": str(TCR_LATEST),
        },
        "flip_command": FLIP_COMMAND,
        "fast_gate_path": str(ROOT / "scripts" / "butler-pytest-fast-gate.sh"),
    }


def write_readiness(report: dict[str, Any], path: Path = READINESS_REPORT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_summary(report: dict[str, Any]) -> str:
    tcr = report["tcr"]
    rate_pct = float(tcr["trajectory_compliance_rate"]) * 100
    lines = [
        f"TCR rate: {rate_pct:.2f}%  passed={tcr['passed']}/{tcr['total']}",
        f"status={report['status']}  days_until_flip={report['days_until_flip']}",
    ]
    if report["status"] == "fail":
        lines.append("TCR strict: FAIL — rate below threshold; do not flip fast-gate")
    elif report["status"] == "wait":
        lines.append(
            f"Calendar: WAIT — stable weekly through {report['strict_after']}, then:"
        )
        lines.append(f"  {FLIP_COMMAND}")
    else:
        lines.append("READY: apply strict TCR in fast-gate:")
        lines.append(f"  {FLIP_COMMAND}")
        lines.append("  bash scripts/butler-pytest-fast-gate.sh  # verify after flip")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess TCR strict flip readiness")
    parser.add_argument("--today", default=date.today().isoformat())
    parser.add_argument(
        "--strict-after",
        default=os.environ.get("BUTLER_TCR_STRICT_AFTER", DEFAULT_STRICT_AFTER),
    )
    parser.add_argument("--tcr-report", type=Path, default=TCR_LATEST)
    parser.add_argument("--out", type=Path, default=READINESS_REPORT)
    args = parser.parse_args(argv)

    if not args.tcr_report.is_file():
        print(f"TCR strict: missing {args.tcr_report}", file=sys.stderr)
        return 1

    tcr_report = json.loads(args.tcr_report.read_text(encoding="utf-8"))
    readiness = assess_readiness(
        tcr_report=tcr_report,
        today=args.today,
        strict_after=args.strict_after,
    )
    write_readiness(readiness, args.out)
    print(format_summary(readiness))
    return 1 if readiness["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
