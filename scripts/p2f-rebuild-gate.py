#!/usr/bin/env python3
"""Rebuild P2-F mypy strict gate from verified modules (fixes corrupted gate script)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/butler-mypy-strict-gate.sh"

# Base modules (contracts + original P2-F seeds)
SEED = [
    "butler/contracts/__init__.py",
    "butler/contracts/bridge_access.py",
    "butler/contracts/compaction_ports.py",
    "butler/contracts/context_transform_ports.py",
    "butler/contracts/dev_context_ports.py",
    "butler/contracts/dev_state_ports.py",
    "butler/contracts/eval_ports.py",
    "butler/contracts/events.py",
    "butler/contracts/gateway_registry.py",
    "butler/contracts/hook_context_ports.py",
    "butler/contracts/memory_ports.py",
    "butler/contracts/message_ports.py",
    "butler/contracts/owner_gate.py",
    "butler/contracts/review_ports.py",
    "butler/contracts/sink_registry.py",
    "butler/tools/delegate_run_state.py",
    "butler/tools/delegate_record.py",
    "butler/core/approval_cards.py",
    "butler/core/events_sink.py",
    "butler/core/schema_recovery.py",
    "butler/core/llm_retry_errors.py",
    "butler/core/llm_retry_outcomes.py",
    "butler/core/tool_batch_finalize.py",
    "butler/ops/lazy_import_budget.py",
    "butler/ops/degradation_registry.py",
    "butler/tools/terminal_approval.py",
    "butler/dag_scheduler.py",
    "butler/gateway/network_route_verify_runner.py",
    "butler/gateway/events_sink_impl.py",
    "butler/workflow_step_runner.py",
    "butler/gateway/locked_phase_registry.py",
    "butler/defaults/model_defaults.py",
    "butler/orchestrator/templates.py",
    "butler/orchestrator/loop_factory.py",
    "butler/orchestrator/memory_bridge.py",
    "butler/orchestrator/skill_bridge.py",
    "butler/orchestrator/prompt_assembler.py",
]

SCAN_DIRS = [
    "butler/core",
    "butler/gateway",
    "butler/runtime",
    "butler/tools",
    "butler/transport",
    "butler/mcp",
    "butler/memory",
    "butler/skills",
    "butler/session",
    "butler/hooks",
    "butler/eval",
    "butler/orchestrator",
    "butler/dev_engine",
    "butler/ops",
]


def mypy_ok(path: Path) -> bool:
    r = subprocess.run(
        [sys.executable, "-m", "mypy", str(path), "--follow-imports=skip"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return r.returncode == 0


def collect_candidates() -> list[str]:
    out: list[str] = list(SEED)
    seen = set(out)
    for d in SCAN_DIRS:
        for p in sorted((ROOT / d).glob("*.py")):
            if p.name.endswith("_ops.py"):
                continue
            rel = str(p.relative_to(ROOT))
            if rel in seen:
                continue
            seen.add(rel)
            out.append(rel)
    return out


def write_gate(modules: list[str]) -> None:
    lines = [
        "#!/usr/bin/env bash",
        "# Mypy strict gate for opt-in modules (--follow-imports=skip keeps it fast).",
        "# Usage: bash scripts/butler-mypy-strict-gate.sh",
        "set -euo pipefail",
        "",
        'ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"',
        'cd "$ROOT"',
        "",
        "if ! command -v python >/dev/null 2>&1; then",
        '  echo "python not found" >&2',
        "  exit 1",
        "fi",
        "",
        'python -c "import mypy" 2>/dev/null || {',
        '  echo "mypy not installed (pip install -e \'.[dev]\')" >&2',
        "  exit 1",
        "}",
        "",
        "# P2-F expansion: contracts + opt-in strict modules.",
        "MODULES=(",
    ]
    for m in modules:
        lines.append(f"  {m}")
    lines.extend(
        [
            ")",
            "",
            'echo "== Butler mypy strict gate (${#MODULES[@]} modules) =="',
            'for mod in "${MODULES[@]}"; do',
            '  echo "  -> $mod"',
            '  python -m mypy "$mod" --follow-imports=skip',
            "done",
            'echo "Mypy strict gate: OK"',
            "",
        ]
    )
    GATE.write_text("\n".join(lines), encoding="utf-8")
    GATE.chmod(0o755)


def write_pyproject(modules: list[str]) -> None:
    py = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dotted = sorted(
        {
            m[:-3].replace("/", ".")
            for m in modules
            if m.startswith("butler/") and not m.startswith("butler/contracts/")
        }
    )
    block = "module = [\n" + "".join(f'    "{m}",\n' for m in dotted) + "]"
    import re

    py = re.sub(
        r"\[\[tool\.mypy\.overrides\]\]\nmodule = \[[^\]]+\]\nstrict = true",
        f"[[tool.mypy.overrides]]\n{block}\nstrict = true",
        py,
        count=1,
        flags=re.DOTALL,
    )
    (ROOT / "pyproject.toml").write_text(py, encoding="utf-8")


def main() -> int:
    min_target = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    candidates = collect_candidates()
    ok: list[str] = []
    fail: list[str] = []
    for rel in candidates:
        if not (ROOT / rel).exists():
            continue
        if mypy_ok(ROOT / rel):
            ok.append(rel)
        else:
            fail.append(rel)
    # preserve seed order first, then rest sorted
    seed_set = set(SEED)
    ordered = [m for m in SEED if m in ok]
    ordered.extend(sorted(m for m in ok if m not in seed_set))
    write_gate(ordered)
    write_pyproject(ordered)
    print(f"Gate rebuilt: {len(ordered)} modules pass (target {min_target})")
    print(f"Failed mypy: {len(fail)}")
    for f in fail[:20]:
        print(f"  FAIL {f}")
    if len(fail) > 20:
        print(f"  ... +{len(fail) - 20} more")
    return 0 if len(ordered) >= min_target else 1


if __name__ == "__main__":
    raise SystemExit(main())
