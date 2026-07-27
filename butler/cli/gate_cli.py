"""Butler Gate CLI — unified access to all engineering gates."""

from __future__ import annotations

import argparse
import subprocess
import sys
from enum import StrEnum, auto
from typing import List


class Gate(StrEnum):
    FAST = auto()
    MYPY = auto()
    CONTRACTS = auto()
    FILE_SIZE = auto()
    LAZY_IMPORT = auto()
    ENV_HYGIENE = auto()
    LAYER_IMPORT = auto()
    CC_HARNESS = auto()
    SCHEMA_DRIFT = auto()
    EXCEPTION = auto()
    DEGRADATION = auto()
    TRAJECTORY = auto()
    FIVE_REPORTS = auto()
    DOMAIN = auto()


GATE_DESCRIPTIONS = {
    Gate.FAST: "快速门禁（smoke + wechat + CC + contracts + mypy）",
    Gate.MYPY: "Mypy strict 门禁",
    Gate.CONTRACTS: "契约测试（Port + Shim __all__）",
    Gate.FILE_SIZE: "文件大小守卫（>800 警告 / >1200 阻止）",
    Gate.LAZY_IMPORT: "Lazy import 预算检查",
    Gate.ENV_HYGIENE: "环境变量卫生检查（reference ↔ .env.example）",
    Gate.LAYER_IMPORT: "层依赖矩阵检查（ENG-15）",
    Gate.CC_HARNESS: "CC 线束测试",
    Gate.SCHEMA_DRIFT: "Schema drift 检查",
    Gate.EXCEPTION: "异常门禁（P0A）",
    Gate.DEGRADATION: "降级门禁（P0B）",
    Gate.TRAJECTORY: "轨迹合规检查",
    Gate.FIVE_REPORTS: "五报告门禁",
    Gate.DOMAIN: "领域测试门禁",
}


def _run_script(name: str, args: List[str] = None) -> int:
    """Run a shell script and return exit code."""
    cmd = ["bash", f"scripts/{name}.sh"] + (args or [])
    result = subprocess.run(cmd)
    return result.returncode


def _run_pytest(path: str, extra_args: List[str] = None) -> int:
    """Run pytest on a path."""
    cmd = ["python", "-m", "pytest", path, "-q"] + (extra_args or [])
    result = subprocess.run(cmd)
    return result.returncode


def _run_python_script(name: str, args: List[str] = None) -> int:
    """Run a Python script."""
    cmd = ["python", f"scripts/{name}.py"] + (args or [])
    result = subprocess.run(cmd)
    return result.returncode


def run_gate(gate: Gate, verbose: bool = False) -> int:
    """Run a specific gate."""
    print(f"== Running gate: {gate.value} ==")

    match gate:
        case Gate.FAST:
            return run_fast_gate(verbose=verbose)
        case Gate.MYPY:
            return _run_script("butler-mypy-strict-gate")
        case Gate.CONTRACTS:
            return _run_pytest("tests/contracts/", ["--tb=line"])
        case Gate.FILE_SIZE:
            return _run_python_script("ai_guard/file_size_check", ["--ci"])
        case Gate.LAZY_IMPORT:
            return _run_script("p3i-lazy-import-report")
        case Gate.ENV_HYGIENE:
            return _run_script("p3j-env-hygiene-gate")
        case Gate.LAYER_IMPORT:
            return _run_script("butler-layer-import-gate")
        case Gate.CC_HARNESS:
            return _run_script("butler-cc-harness-gate")
        case Gate.SCHEMA_DRIFT:
            return _run_script("check-schema-drift")
        case Gate.EXCEPTION:
            return _run_script("butler-p0a-exception-gate")
        case Gate.DEGRADATION:
            return _run_script("butler-p0b-degradation-gate")
        case Gate.TRAJECTORY:
            return _run_script("butler-trajectory-compliance-gate", ["--strict"])
        case Gate.FIVE_REPORTS:
            return _run_script("butler-five-reports-gate")
        case Gate.DOMAIN:
            return _run_script("butler-eng-domain-gate")

    return 1


def run_fast_gate(verbose: bool = False) -> int:
    """Run the fast gate (all critical checks)."""
    gates = [
        ("smoke", lambda: _run_script("butler-smoke", ["--tier=quick"])),
        ("wechat-attach-smoke", lambda: _run_script("butler-wechat-attach-smoke")),
        ("wechat-attach-probe", lambda: _run_script("butler-wechat-attach-probe")),
        ("cc-harness", lambda: _run_script("butler-cc-harness-gate")),
        ("exception", lambda: _run_script("butler-p0a-exception-gate")),
        ("degradation", lambda: _run_script("butler-p0b-degradation-gate")),
        ("p1c", lambda: _run_script("butler-p1c-gate")),
        ("schema-drift", lambda: _run_script("check-schema-drift")),
        ("env-hygiene", lambda: _run_script("p3j-env-hygiene-gate")),
        ("lazy-import", lambda: _run_script("p3i-lazy-import-report")),
        ("contracts", lambda: _run_pytest("tests/contracts/", ["--tb=line"])),
        ("file-size", lambda: _run_python_script("ai_guard/file_size_check", ["--ci"])),
        ("mypy", lambda: _run_script("butler-mypy-strict-gate")),
        ("trajectory", lambda: _run_script("butler-trajectory-compliance-gate", ["--strict"])),
    ]

    failed = []
    for name, runner in gates:
        if verbose:
            print(f"-> {name}")
        try:
            code = runner()
            if code != 0:
                failed.append(name)
                if verbose:
                    print(f"   FAIL (exit {code})")
        except Exception as e:
            failed.append(name)
            if verbose:
                print(f"   ERROR: {e}")

    if failed:
        print(f"\nFast gate: FAILED ({', '.join(failed)})")
        return 1
    print("\nFast gate: ALL PASSED")
    return 0


def register_gate_parser(sub) -> None:
    """Register the gate subcommand parser."""
    gate_parser = sub.add_parser(
        "gate",
        help="工程门禁（统一访问所有质量检查）",
        description="运行 Butler 项目的工程门禁，包含类型检查、契约测试、文件大小守卫等。",
    )

    gate_sub = gate_parser.add_subparsers(dest="gate", required=True)

    for gate in Gate:
        desc = GATE_DESCRIPTIONS.get(gate, "")
        gate_sub.add_parser(
            gate.value,
            help=desc,
            description=desc,
        )

    gate_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="显示详细输出",
    )

    gate_parser.set_defaults(func=_cmd_gate)


def _cmd_gate(args) -> int:
    """Run the gate command."""
    try:
        gate = Gate(args.gate)
    except ValueError:
        print(f"未知门禁: {args.gate}", file=sys.stderr)
        return 1

    verbose = getattr(args, "verbose", False)
    return run_gate(gate, verbose=verbose)


__all__ = ["Gate", "run_gate", "run_fast_gate", "register_gate_parser"]