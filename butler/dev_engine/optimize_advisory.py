"""Read-only optimization hints derived from static review signals."""

from __future__ import annotations

from pathlib import Path

from butler.contracts.review_ports import DevReviewView
from butler.dev_engine.review_static import review_max_function_lines, run_static_review


def build_optimize_hints(
    workspace: Path,
    *,
    changed_files: list[str] | None = None,
    edit_paths: list[str] | None = None,
    review_view: DevReviewView | None = None,
) -> list[str]:
    """Return advisory suggestions (non-blocking) from review findings."""
    view = review_view
    if view is None:
        view = run_static_review(
            workspace,
            changed_files=changed_files,
            edit_paths=edit_paths,
        )
    hints: list[str] = []
    size_count = sum(1 for f in view.findings if f.rule_id == "RK-SIZE")
    err_count = sum(1 for f in view.findings if f.rule_id == "RK-ERROR")
    boundary_count = sum(1 for f in view.findings if f.rule_id == "RK-BOUNDARY")
    test_info = sum(1 for f in view.findings if f.rule_id == "RK-TEST")
    max_fn = review_max_function_lines()
    if size_count:
        hints.append(
            f"考虑拆分 {size_count} 处超长函数/文件，保持单函数 ≤{max_fn} 行。"
        )
    if err_count:
        hints.append("宽 except 处补充 logger 或显式 re-raise，避免静默吞错。")
    if boundary_count:
        hints.append("跨层 import 改走 contracts/adapter 防腐层。")
    if test_info:
        hints.append("为改动模块补充 tests/ 覆盖（启发式未命中现有测试引用）。")
    if not hints and view.findings:
        hints.append("审查有 warning/info 项；可用 dev_review 查看结构化 findings。")
    return hints[:8]


def enrich_review_with_suggestions(
    workspace: Path,
    view: DevReviewView,
    *,
    changed_files: list[str] | None = None,
    edit_paths: list[str] | None = None,
) -> DevReviewView:
    suggestions = build_optimize_hints(
        workspace,
        changed_files=changed_files,
        edit_paths=edit_paths,
        review_view=view,
    )
    return view.model_copy(update={"suggestions": suggestions})
