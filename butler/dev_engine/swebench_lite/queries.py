from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from .bug_fix_instances import _bug_fix_instances
from .complex_instances import _complex_instances
from .feature_instances import _feature_instances
from .models import SWEInstance
from .refactor_instances import _refactor_instances
from .test_fix_instances import _test_fix_instances


def _instances() -> list[SWEInstance]:
    return (
        _bug_fix_instances()
        + _feature_instances()
        + _refactor_instances()
        + _test_fix_instances()
        + _complex_instances()
    )


def get_all_instances() -> list[SWEInstance]:
    return _instances()


def get_instance(instance_id: str) -> SWEInstance | None:
    for inst in _instances():
        if inst.instance_id == instance_id:
            return inst
    return None


def get_instances_by_category(category: str) -> list[SWEInstance]:
    return [i for i in _instances() if i.category == category]


def run_oracle_verification(workspace: Path) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for inst in _instances():
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            inst.setup_workspace(ws)
            inst.apply_oracle(ws)
            from butler.dev_engine.swebench_lite_ops import verify_swebench_instance_safe

            passed, error = verify_swebench_instance_safe(inst, ws)
            if error:
                results.append({
                    "id": inst.instance_id,
                    "passed": False,
                    "error": error,
                })
                continue
            results.append({
                "id": inst.instance_id,
                "category": inst.category,
                "passed": passed,
            })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / max(1, total),
        "results": results,
    }
