"""Owner-facing delegate acceptance card (PROD-P4-02)."""

from __future__ import annotations

from typing import Any

from butler.report.report_types import AgentReport, Change
from butler.delegate.task_kind import infer_delegate_task_kind


def attach_delegate_acceptance_meta(
    report: AgentReport,
    *,
    role: str = "",
    project: Any = None,
    dev_engine: dict[str, Any] | None = None,
    task: str = "",
    task_preview: str = "",
    category_meta: dict[str, Any] | None = None,
) -> AgentReport:
    """Stamp ``structured_output['acceptance']`` for WeChat acceptance card."""
    norm = str(role or "").replace("_agent", "").strip().lower()
    dev_cfg: dict[str, Any] = {}
    if project is not None:
        dev_cfg = dict(getattr(project, "dev", None) or {})

    meta: dict[str, Any] = {
        "role": norm,
        "test_configured": bool(str(dev_cfg.get("test_command") or "").strip()),
        "change_count": len(report.changes or []),
    }
    task_kind = infer_delegate_task_kind(
        role=role,
        task=task,
        task_preview=task_preview or report.task_preview or "",
        changes=report.changes,
        category_meta=category_meta,
    )
    if task_kind:
        meta["task_kind"] = task_kind
    de = dev_engine if isinstance(dev_engine, dict) else {}
    if norm == "dev":
        meta["edits"] = int(de.get("edits") or meta["change_count"] or 0)
        if de.get("verify_passed") is True:
            meta["verify_passed"] = True
        elif de.get("verify_passed") is False:
            meta["verify_passed"] = False
        elif any("DEV_VERIFY_GATE" in str(i) for i in report.issues):
            meta["verify_passed"] = False
        else:
            meta["verify_passed"] = None
    else:
        meta["verify_applicable"] = False

    report.structured_output = dict(report.structured_output or {})
    report.structured_output["acceptance"] = meta
    return report


def _test_line(meta: dict[str, Any], report: AgentReport) -> str:
    if meta.get("task_kind") == "ingest":
        return "测试：—（ingest 写盘）"
    if meta.get("verify_applicable") is False:
        return "测试：—（非开发委派）"
    if not meta.get("test_configured"):
        return "测试：⚪ 未配置（project.yaml dev.test_command）"
    edits = int(meta.get("edits") or meta.get("change_count") or 0)
    if edits <= 0 and not report.changes:
        return "测试：—（无代码变更）"
    vp = meta.get("verify_passed")
    if vp is True:
        return "测试：✅ 通过"
    if vp is False or any("DEV_VERIFY_GATE" in str(i) for i in report.issues):
        return "测试：❌ 未通过"
    if report.success:
        return "测试：✅ 通过"
    return "测试：⚪ 未执行"


def _lint_line(meta: dict[str, Any], report: AgentReport) -> str:
    if meta.get("verify_applicable") is False:
        return "lint：—"
    if not meta.get("test_configured") and meta.get("verify_passed") is None:
        return "lint：—"
    for issue in report.issues:
        blob = str(issue).lower()
        if "lint" in blob or "ruff" in blob or "flake8" in blob:
            return "lint：❌ 有问题"
    vp = meta.get("verify_passed")
    if vp is True:
        return "lint：✅（随验证）"
    if vp is False:
        return "lint：—"
    return "lint：—"


def _change_line(report: AgentReport) -> str:
    n = len(report.changes or [])
    if n == 0:
        return "变更：0 个文件"
    actions: dict[str, int] = {}
    for c in report.changes:
        if isinstance(c, Change):
            actions[c.action] = actions.get(c.action, 0) + 1
        elif isinstance(c, dict):
            actions[str(c.get("action") or "")] = actions.get(str(c.get("action") or ""), 0) + 1
    bits: list[str] = []
    if actions.get("created"):
        bits.append(f"新建 {actions['created']}")
    if actions.get("modified"):
        bits.append(f"修改 {actions['modified']}")
    if actions.get("deleted"):
        bits.append(f"删除 {actions['deleted']}")
    tail = "，".join(bits) if bits else f"{n} 处"
    return f"变更：{tail}"


def format_delegate_acceptance_card(report: AgentReport) -> str:
    """Fixed four-line Owner footer for delegate completion."""
    meta = dict((report.structured_output or {}).get("acceptance") or {})
    lines = [
        "── 验收卡 ──",
        _test_line(meta, report),
        _lint_line(meta, report),
        _change_line(report),
        "详情：发 /详细 或回复「详细」",
    ]
    return "\n".join(lines)


__all__ = [
    "attach_delegate_acceptance_meta",
    "format_delegate_acceptance_card",
]
