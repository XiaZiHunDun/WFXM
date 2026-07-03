"""Boundary observability best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.ops.boundary_observability import BoundaryObservation


def observe_g1_02_cost_baseline() -> "BoundaryObservation":
    from butler.ops.boundary_observability import BoundaryObservation

    try:
        from butler.ops.cost_calibration import load_baseline

        baseline = load_baseline()
        if baseline:
            note = str(baseline.get("period_note") or "")[:40]
            return BoundaryObservation(
                "G1-02",
                "ok",
                f"成本基线已设 ({note or '有 actual_usd'})",
                "butler cost report 可看偏差",
            )
        return BoundaryObservation(
            "G1-02",
            "warn",
            "成本基线未设",
            "butler cost set-baseline",
        )
    except Exception as exc:
        return BoundaryObservation("G1-02", "info", f"成本基线: 不可用 ({exc})")


def observe_g2_01_pii_rule() -> "BoundaryObservation":
    from butler.ops.boundary_observability import BoundaryObservation

    try:
        from butler.core.compaction_prompt import PII_EXCLUSION_RULE

        active = "PRIVACY" in PII_EXCLUSION_RULE
        return BoundaryObservation(
            "G2-01",
            "ok" if active else "warn",
            "压缩 PII_EXCLUSION_RULE 已注入" if active else "PII 规则缺失",
            "边界已接受；pii_clearable 已接",
        )
    except Exception as exc:
        return BoundaryObservation("G2-01", "info", f"PII 缓解: ({exc})")


def observe_g2_02_push_queue() -> "BoundaryObservation":
    from butler.ops.boundary_observability import BoundaryObservation

    try:
        from butler.runtime import push_queue
        from butler.runtime.notify import rate_limit_drain_wait_seconds

        pending = push_queue.count_pending_pushes()
        wait_s = rate_limit_drain_wait_seconds()
        if pending and wait_s > 0:
            return BoundaryObservation(
                "G2-02",
                "deferred",
                f"推送队列 {pending} 条 · 限流冷却 ~{wait_s:.0f}s",
                "冷却后 drain-push",
            )
        if pending:
            return BoundaryObservation(
                "G2-02",
                "info",
                f"推送队列 {pending} 条待送达",
                "drain-push 或 push-drain.timer（缓解已验 2026-06-10）",
            )
        return BoundaryObservation("G2-02", "ok", "推送队列空")
    except Exception as exc:
        return BoundaryObservation("G2-02", "info", f"推送队列: ({exc})")


def observe_g2_04_pim_truncation() -> "BoundaryObservation":
    from butler.ops.boundary_observability import BoundaryObservation

    try:
        from butler.tools import pim_schema as ps

        return BoundaryObservation(
            "G2-04",
            "ok",
            "PIM 字段截断",
            f"边界已接受 memo≤{ps.MAX_MEMO_CONTENT_LEN} reminder≤{ps.MAX_REMINDER_MESSAGE_LEN}",
        )
    except Exception as exc:
        return BoundaryObservation("G2-04", "info", f"PIM 截断: ({exc})")


def observe_g2_09_mem_benchmark() -> "BoundaryObservation":
    from butler.ops.boundary_observability import BoundaryObservation

    try:
        from butler.ops.eval_diagnostics import collect_eval_quality_snapshot

        snap = collect_eval_quality_snapshot()
        mem_rate = None
        if snap.regression:
            mem_rate = float(snap.regression.get("mem_pass_rate") or 0.0)
        if mem_rate is not None:
            ok = mem_rate >= 0.7
            return BoundaryObservation(
                "G2-09",
                "ok" if ok else "warn",
                f"Mem 基准 {mem_rate:.0%}",
                "边界已接受；写后索引 MB1 见 memory_benchmark",
            )
        return BoundaryObservation(
            "G2-09",
            "info",
            "Mem 基准未记录",
            "butler-eval-regression.sh",
        )
    except Exception as exc:
        return BoundaryObservation("G2-09", "info", f"Mem 基准: ({exc})")
