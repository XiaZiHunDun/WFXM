"""Sprint 11 TST-11-1 误报防护: butler/runtime/approval.py 实际不是死代码

Sprint 11 审计误报：subagent 报 `butler/runtime/approval.py` 0 importer/0 test，
建议删。实际：service.py:12 `from butler.runtime import approval, ...` 是
namespace import，subagent grep pattern `^from butler\\.runtime\\.approval import\\|^import butler\\.runtime\\.approval\\b`
漏检这种形式。

修复：测试用更精确 pattern 覆盖两种 import 形式，**确保 approval 保留不删**。
原 Sprint 10 REL-NEW-07（consume_approval RMW 无锁）仍独立成立。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


APPROVAL_FILE = "butler/runtime/approval.py"


@pytest.mark.unit
def test_approval_module_still_exists():
    """approval.py 应保留 — Sprint 11 误报撤回。"""
    repo_root = Path("/home/ailearn/projects/WFXM")
    assert (repo_root / APPROVAL_FILE).exists(), (
        f"approval.py 应保留（service.py 真引用）：{APPROVAL_FILE}"
    )


@pytest.mark.unit
def test_approval_module_can_be_imported():
    """approval 模块应能被 import。"""
    from butler.runtime import approval

    assert approval is not None


@pytest.mark.unit
def test_approval_namespace_import_in_service():
    """service.py:12 显式 import approval（namespace 形式）— 这是 Sprint 11 漏检的真引用。"""
    repo_root = Path("/home/ailearn/projects/WFXM")
    service_path = repo_root / "butler" / "runtime" / "service.py"
    text = service_path.read_text(encoding="utf-8")
    # 匹配 "from butler.runtime import" 后接 approval
    assert re.search(
        r"from\s+butler\.runtime\s+import\s+[^#\n]*\bapproval\b", text
    ), (
        f"service.py 应 'from butler.runtime import ... approval ...'\n"
        f"实际：\n{text[:200]}"
    )


@pytest.mark.unit
def test_approval_used_by_service_functions():
    """service.py 多个函数调 approval.* — approval 是 active API。"""
    repo_root = Path("/home/ailearn/projects/WFXM")
    service_path = repo_root / "butler" / "runtime" / "service.py"
    text = service_path.read_text(encoding="utf-8")
    # 至少 3 处 approval.* 调用
    approval_call_count = len(re.findall(r"\bapproval\.\w+\(", text))
    assert approval_call_count >= 3, (
        f"service.py 应至少 3 处 approval.*() 调用，实际 {approval_call_count}"
    )


@pytest.mark.unit
def test_approval_imports_comprehensive_check():
    """回归保护：两种 import 形式都应被检测到（修复 Sprint 11 subagent 漏检）。"""
    repo_root = Path("/home/ailearn/projects/WFXM")
    py_files = list((repo_root / "butler").rglob("*.py")) + list((repo_root / "tests").rglob("*.py"))
    hits = []
    for p in py_files:
        if p.name == "approval.py":
            continue
        if p.name == "test_sprint11_tst1_approval_alive.py":
            continue  # 本测试自身合法
        text = p.read_text(encoding="utf-8")
        # 形式 1: from butler.runtime.approval import X
        if re.search(r"from\s+butler\.runtime\.approval\s+import", text):
            hits.append((str(p.relative_to(repo_root)), "form1"))
        # 形式 2: import butler.runtime.approval
        if re.search(r"^import\s+butler\.runtime\.approval\b", text, re.M):
            hits.append((str(p.relative_to(repo_root)), "form2"))
        # 形式 3: from butler.runtime import X, approval, Y  ← Sprint 11 漏检的
        if re.search(
            r"from\s+butler\.runtime\s+import\s+[^#\n]*\bapproval\b", text
        ):
            hits.append((str(p.relative_to(repo_root)), "form3-namespace"))
    # 应至少 service.py form3 命中
    form3_hits = [h for h in hits if h[1] == "form3-namespace"]
    assert any("service.py" in h[0] for h in form3_hits), (
        f"service.py 应 form3-namespace import approval，实际 hits: {form3_hits}"
    )
