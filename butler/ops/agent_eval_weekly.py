"""Weekly agent eval KPI aggregator (AP-8 / AP-9)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / ".butler" / "reports" / "agent-eval-weekly.json"
FLAKY_PATH = ROOT / ".butler" / "ci" / "flaky-corpus-allowlist.yaml"
PASS_K = 3


def _load_tcr() -> dict[str, Any]:
    path = ROOT / ".butler" / "reports" / "tcr-latest.json"
    if not path.is_file():
        return {}
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _run_pass_at_k() -> dict[str, Any]:
    allow: set[str] = set()
    if FLAKY_PATH.is_file():
        data = yaml.safe_load(FLAKY_PATH.read_text(encoding="utf-8")) or {}
        allow = set(data.get("allowlist") or [])

    target = "tests/corpus/runners/test_trajectory_compliance_catalog.py"
    passes = 0
    for _ in range(PASS_K):
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", target, "-q", "--tb=no"],
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
        )
        if proc.returncode == 0:
            passes += 1
    return {
        "pass_at_k": PASS_K,
        "passes": passes,
        "rate": round(passes / PASS_K, 4),
        "flaky_allowlist_size": len(allow),
    }


def build_weekly_report() -> dict[str, Any]:
    tcr = _load_tcr()
    pass_k = _run_pass_at_k()
    cup = float(tcr.get("trajectory_compliance_rate") or 0.0)
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dimensions": {
            "reliability": {
                "tcr": tcr.get("trajectory_compliance_rate"),
                "pass_at_3": pass_k.get("rate"),
            },
            "safety": {
                "cup_strict": cup,
            },
            "efficiency": {
                "cna_note": "mock-only until G1-02 cost baseline",
            },
        },
        "tcr_detail": tcr,
        "pass_at_3_detail": pass_k,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent eval weekly KPI report")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    report = build_weekly_report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["dimensions"], ensure_ascii=False, indent=2))
    print(f"-> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
