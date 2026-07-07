"""L7 approval storage lines for ``butler doctor``."""

from __future__ import annotations

from pathlib import Path

from butler.contracts.approval_registry import get_approval_store
from butler.contracts.workflow_gate_registry import get_workflow_gate


def count_legacy_exec_approval_files(butler_home: Path) -> int:
    root = butler_home / "exec_approvals"
    if not root.is_dir():
        return 0
    return sum(1 for path in root.glob("*.json") if path.is_file())


def format_approval_storage_doctor_lines(butler_home: Path) -> list[str]:
    lines: list[str] = []
    store = get_approval_store()
    gate = get_workflow_gate()
    lines.append(
        f"  ApprovalStore: {'✓' if store is not None else '✗ 未注册'}"
    )
    lines.append(
        f"  WorkflowGateStore: {'✓' if gate is not None else '✗ 未注册'}"
    )
    lines.append("  Terminal 批准存储: sessions/<sk>/approvals.json")
    legacy = count_legacy_exec_approval_files(butler_home)
    if legacy:
        lines.append(
            f"  ⚠ 遗留 exec_approvals/*.json: {legacy} 个（首次 check 时自动迁移）"
        )
    else:
        lines.append("  遗留 exec_approvals/*.json: ✓ 无")
    return lines


__all__ = [
    "count_legacy_exec_approval_files",
    "format_approval_storage_doctor_lines",
]
