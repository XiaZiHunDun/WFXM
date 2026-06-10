# §3.2 Session Approval Cache 完整补齐 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐 OpenCode §3.2 会话批准缓存的剩余 3 项: (1) `is_approved` diagnostics 写入让 /诊断可见, (2) `revoke_always` / `clear_always` 失效机制, (3) `/撤销批准` / `/清除始终允许` 命令与 /诊断 集成.

**Architecture:** 沿用 §3.1 diagnostics kw-only 模式 — `is_approved` 加 `diagnostics: dict | None = None` 形参, 命中时写入 `approval_cache_hit: True` 与 `approval_cache_source: "once"|"always"`. 三个调用点 (`doom_loop.py:43` / `rules.py:386` / `mcp/approval.py:94`) 不强制传 diagnostics (向后兼容). `/诊断` 集成通过 `summarize_approvals(session_key)` 直接读 `approvals.json` 显示 always count / active once count / pending. Revoke 机制新增 `revoke_always(...)` / `clear_always(...)` 两个函数, 对应 `/撤销批准 <perm> [tool] [pat]` 和 `/清除始终允许` 命令.

**Tech Stack:** Python 3.13, pytest, frozen dataclass `ApprovalRequest`, JSON file storage per session

---

## File Structure

| 文件 | 角色 | 修改类型 |
|------|------|---------|
| `butler/permissions/approvals.py` | is_approved / revoke_always / clear_always / summarize_approvals | Modify |
| `butler/permissions/doom_loop.py` | is_approved caller | Modify (kw-only pass-through) |
| `butler/permissions/rules.py` | is_approved caller | Modify (kw-only pass-through) |
| `butler/mcp/approval.py` | is_approved caller | Modify (kw-only pass-through) |
| `butler/ops/health_report.py` | /诊断 approval section | Modify |
| `butler/gateway/commands/permission_commands.py` | /撤销批准 + /清除始终允许 handler | Modify |
| `tests/test_sprint24_p1_3_2_approval_diagnostics.py` | 6+ 新测试 | Create |
| `docs/reviews/project-deep-audit-2026-06-sprint11.md` | §6 加 §3.2 完成 entry | Modify |
| `docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md` | §3.2 标 [x] + Sprint 24 完成说明 | Modify |

---

## Task 1: is_approved diagnostics 透传 (RED → GREEN)

**Files:**
- Modify: `butler/permissions/approvals.py:212-229` (signature + 3 个命中点写入)
- Test: `tests/test_sprint24_p1_3_2_approval_diagnostics.py:1-90` (新增)

### Step 1: RED — 写测试

```python
# tests/test_sprint24_p1_3_2_approval_diagnostics.py 第 1 部分
"""Sprint 24 P1-3.2: is_approved diagnostics 透传 + revoke + /诊断集成 + workflow 不可穿透."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.permissions.approvals import (
    ApprovalRequest,
    clear_always,
    grant_always,
    grant_once,
    is_approved,
    revoke_always,
    save_pending,
    summarize_approvals,
)


class TestIsApprovedDiagnostics:
    def test_diagnostics_none_safe_when_no_hit(self, tmp_path, monkeypatch):
        """无命中时 diagnostics 不会被写入任何键."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        diag: dict = {}
        assert is_approved("s1", req, diagnostics=diag) is False
        assert diag == {}

    def test_diagnostics_records_always_hit(self, tmp_path, monkeypatch):
        """always 命中时写入 approval_cache_hit + source=always."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        grant_always("s1", permission="p", tool="t", pattern="pat")
        diag: dict = {}
        assert is_approved("s1", req, diagnostics=diag) is True
        assert diag.get("approval_cache_hit") is True
        assert diag.get("approval_cache_source") == "always"

    def test_diagnostics_records_once_hit(self, tmp_path, monkeypatch):
        """once 命中时写入 source=once."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        save_pending("s1", req)
        grant_once("s1")
        diag: dict = {}
        assert is_approved("s1", req, diagnostics=diag) is True
        assert diag.get("approval_cache_source") == "once"

    def test_diagnostics_omitted_kw_only_backward_compatible(self, tmp_path, monkeypatch):
        """不传 diagnostics 时仍正常工作 (向后兼容)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        grant_always("s1", permission="p", tool="t", pattern="pat")
        assert is_approved("s1", req) is True  # 不传 diagnostics
```

### Step 2: RED 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestIsApprovedDiagnostics -v
```

Expected: 4 FAIL (signature mismatch — `is_approved` 不接受 `diagnostics` kw)

### Step 3: GREEN — 修改 is_approved

修改 `butler/permissions/approvals.py:212`:

```python
def is_approved(
    session_key: str,
    request: ApprovalRequest,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> bool:
    """Sprint 24 P1-3.2: 加 diagnostics kw-only 形参, 命中时写入 source.

    Note: diagnostics 是向后兼容 kw-only 形参, 现有 3 个调用点 (doom_loop /
    rules / mcp) 不传也工作正常; 传则可在 /诊断中看到本次调用命中信息.
    """
    sk = str(session_key or "").strip()
    if not sk:
        return False
    data = _load(sk)
    for row in data.get("always") or []:
        if isinstance(row, dict) and _match_entry(row, request):
            if diagnostics is not None:
                diagnostics["approval_cache_hit"] = True
                diagnostics["approval_cache_source"] = "always"
            return True
    fp = request.fingerprint()
    now = time.time()
    for row in _purge_once(data.get("once") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("fingerprint") or "") == fp:
            if diagnostics is not None:
                diagnostics["approval_cache_hit"] = True
                diagnostics["approval_cache_source"] = "once"
            return True
        if _match_entry(row, request) and float(row.get("expires_at") or 0) > now:
            if diagnostics is not None:
                diagnostics["approval_cache_hit"] = True
                diagnostics["approval_cache_source"] = "once"
            return True
    return False
```

### Step 4: GREEN 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestIsApprovedDiagnostics -v
```

Expected: 4 PASS

### Step 5: 验证 3 个调用点仍工作 (不传 diagnostics 路径)

```bash
pytest tests/test_permission_approvals.py tests/test_sprint8_sec2_approvals.py tests/test_p2_workflow_permissions.py -v
```

Expected: 全部 PASS (无回归, 因为 kw-only 形参不影响旧调用)

### Step 6: Commit

```bash
git add butler/permissions/approvals.py tests/test_sprint24_p1_3_2_approval_diagnostics.py
git commit -m "feat(approvals): is_approved diagnostics 透传 (approval_cache_hit/source)"
```

---

## Task 2: revoke_always + clear_always + summarize_approvals (RED → GREEN)

**Files:**
- Modify: `butler/permissions/approvals.py` (末尾追加 3 个函数)
- Test: `tests/test_sprint24_p1_3_2_approval_diagnostics.py:90-200` (新增)

### Step 1: RED — 写测试 (在 Task 1 测试文件追加)

```python
class TestRevokeAlways:
    def test_revoke_specific_entry(self, tmp_path, monkeypatch):
        """revoke_always 按 permission+tool+pattern 匹配删除."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s1", permission="write_file", tool="*", pattern="*.env")
        grant_always("s1", permission="read_file", tool="*", pattern="*")
        msg = revoke_always("s1", permission="write_file")
        assert "已撤销" in msg
        from butler.permissions.approvals import list_always
        remaining = list_always("s1")
        assert len(remaining) == 1
        assert remaining[0]["permission"] == "read_file"

    def test_revoke_no_match_returns_status(self, tmp_path, monkeypatch):
        """无匹配时返 '未找到匹配项' 提示."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s1", permission="write_file", tool="*", pattern="*")
        msg = revoke_always("s1", permission="nonexistent")
        assert "未找到" in msg
        from butler.permissions.approvals import list_always
        assert len(list_always("s1")) == 1  # 原项保留

    def test_revoke_all_filters_empty_returns_error(self, tmp_path, monkeypatch):
        """全空过滤返错误 (防止误删全部)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s1", permission="p1")
        msg = revoke_always("s1")
        assert "请指定" in msg or "至少一项" in msg
        from butler.permissions.approvals import list_always
        assert len(list_always("s1")) == 1  # 原项保留

    def test_clear_always_removes_all(self, tmp_path, monkeypatch):
        """clear_always 清空所有 always 记录."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s1", permission="p1")
        grant_always("s1", permission="p2")
        msg = clear_always("s1")
        assert "已清除 2 项" in msg
        from butler.permissions.approvals import list_always
        assert list_always("s1") == []

    def test_clear_always_no_entries_is_ok(self, tmp_path, monkeypatch):
        """clear_always 无记录时返 '已清除 0 项' 不报错."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        msg = clear_always("s1")
        assert "已清除 0 项" in msg


class TestSummarizeApprovals:
    def test_summarize_empty_session(self, tmp_path, monkeypatch):
        """空 session 返 0/0/False."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        s = summarize_approvals("s1")
        assert s["always_count"] == 0
        assert s["once_active_count"] == 0
        assert s["has_pending"] is False

    def test_summarize_with_entries(self, tmp_path, monkeypatch):
        """含 always + once + pending 时正确统计."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s1", permission="p1")
        grant_always("s1", permission="p2")
        req = ApprovalRequest(permission="p3", tool="t", pattern="pat")
        save_pending("s1", req)
        grant_once("s1")
        s = summarize_approvals("s1")
        assert s["always_count"] == 2
        assert s["once_active_count"] == 1
        assert s["has_pending"] is False  # grant_once 清空 pending
```

### Step 2: RED 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestRevokeAlways tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestSummarizeApprovals -v
```

Expected: 7 FAIL (3 个函数未定义)

### Step 3: GREEN — 在 approvals.py 末尾追加 3 个函数

```python
# butler/permissions/approvals.py 末尾 (line 229 之后)


def revoke_always(
    session_key: str,
    *,
    permission: str = "",
    tool: str = "",
    pattern: str = "",
) -> str:
    """Sprint 24 P1-3.2: 按 permission/tool/pattern 过滤撤销 always 记录.

    全空过滤时返错误, 防止误删. 任意一个非空过滤都参与匹配.
    """
    sk = str(session_key or "").strip()
    if not sk:
        return "无有效会话"
    perm_f = str(permission or "").strip()
    tool_f = str(tool or "").strip()
    pat_f = str(pattern or "").strip()
    if not any([perm_f, tool_f, pat_f]):
        return "请指定 permission / tool / pattern 中的至少一项过滤"
    data = _load(sk)
    before = [r for r in (data.get("always") or []) if isinstance(r, dict)]
    after: list[dict[str, Any]] = []
    for r in before:
        if perm_f and str(r.get("permission") or "") != perm_f:
            after.append(r)
            continue
        if tool_f and str(r.get("tool") or "") != tool_f:
            after.append(r)
            continue
        if pat_f and str(r.get("pattern") or "") != pat_f:
            after.append(r)
            continue
    if len(after) == len(before):
        return (
            f"未找到匹配项 (permission={perm_f or '*'}, tool={tool_f or '*'}, "
            f"pattern={pat_f or '*'})"
        )
    data["always"] = after
    _save(sk, data)
    return f"已撤销 {len(before) - len(after)} 项始终允许"


def clear_always(session_key: str) -> str:
    """Sprint 24 P1-3.2: 清空 session 的所有 always 记录."""
    sk = str(session_key or "").strip()
    if not sk:
        return "无有效会话"
    data = _load(sk)
    count = len([r for r in (data.get("always") or []) if isinstance(r, dict)])
    data["always"] = []
    _save(sk, data)
    return f"已清除 {count} 项始终允许"


def summarize_approvals(session_key: str) -> dict[str, Any]:
    """Sprint 24 P1-3.2: 给 /诊断用的 always/once/pending 统计."""
    sk = str(session_key or "").strip()
    if not sk:
        return {"always_count": 0, "once_active_count": 0, "has_pending": False}
    data = _load(sk)
    always_count = len([r for r in (data.get("always") or []) if isinstance(r, dict)])
    once_active_count = len(_purge_once(data.get("once") or []))
    pending = data.get("pending")
    has_pending = isinstance(pending, dict) and bool(pending.get("fingerprint"))
    return {
        "always_count": always_count,
        "once_active_count": once_active_count,
        "has_pending": has_pending,
    }
```

### Step 4: GREEN 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestRevokeAlways tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestSummarizeApprovals -v
```

Expected: 7 PASS

### Step 5: Commit

```bash
git add butler/permissions/approvals.py tests/test_sprint24_p1_3_2_approval_diagnostics.py
git commit -m "feat(approvals): revoke_always / clear_always / summarize_approvals 三个新函数"
```

---

## Task 3: /诊断 集成 (RED → GREEN)

**Files:**
- Modify: `butler/ops/health_report.py` (collect_mem_stats_for_health 加 approval summary, 增 format 辅助)
- Test: `tests/test_sprint24_p1_3_2_approval_diagnostics.py:200-260` (新增)

### Step 1: RED — 写测试

```python
class TestApprovalHealthIntegration:
    def test_health_report_includes_approval_summary(self, tmp_path, monkeypatch):
        """/诊断 应包含 approval 行 (always count / once active)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.permissions.approvals import grant_always
        from butler.ops.health_report import collect_approval_stats_for_health
        grant_always("s1", permission="p1")
        stats = collect_approval_stats_for_health("s1")
        assert stats["always_count"] == 1
        assert stats["once_active_count"] == 0
        assert stats["has_pending"] is False
```

### Step 2: RED 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestApprovalHealthIntegration -v
```

Expected: 1 FAIL (collect_approval_stats_for_health 未定义)

### Step 3: GREEN — 在 health_report.py 集成

修改 `butler/ops/health_report.py:22-51` (在 `collect_mem_stats_for_health` 之后新增):

```python
def collect_approval_stats_for_health(session_key: str) -> dict[str, Any]:
    """Sprint 24 P1-3.2: /诊断 集成 — 读 session approvals.json 统计.

    返回 dict 形如: {always_count, once_active_count, has_pending}.
    与 collect_mem_stats_for_health 平行, 在 _shared_diagnostic_lines 中调用.
    """
    try:
        from butler.permissions.approvals import summarize_approvals
        return summarize_approvals(session_key)
    except Exception as exc:
        logger.debug("collect approval stats skipped: %s", exc)
        return {"always_count": 0, "once_active_count": 0, "has_pending": False}
```

在 `butler/ops/health_report.py:54-104` `_shared_diagnostic_lines` 中, 在 `format_runtime_diagnostic_lines` 之后插入 approval 块:

```python
    # Sprint 24 P1-3.2: 批准缓存统计 (与 mem_stats 平行)
    try:
        approval_stats = collect_approval_stats_for_health(inp.session_key)
        lines.append("权限批准缓存:")
        lines.append(
            f"  始终允许 {approval_stats['always_count']} 项 · "
            f"本次允许 {approval_stats['once_active_count']} 项"
        )
        if approval_stats["has_pending"]:
            lines.append("  ⏳ 有 1 项待批准")
    except Exception as exc:
        logger.debug("approval diagnostic lines skipped: %s", exc)

    lines.extend(format_runtime_diagnostic_lines(proj_name))
```

### Step 4: GREEN 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestApprovalHealthIntegration -v
```

Expected: 1 PASS

### Step 5: 验证 /诊断 端到端不破

```bash
pytest tests/test_sprint11_tst1_approval_alive.py tests/test_sprint8_sec2_approvals.py -v
```

Expected: 全部 PASS

### Step 6: Commit

```bash
git add butler/ops/health_report.py tests/test_sprint24_p1_3_2_approval_diagnostics.py
git commit -m "feat(health): /诊断 集成 approval summary (always/once/pending)"
```

---

## Task 4: /撤销批准 + /清除始终允许 命令 + workflow 不可穿透测试 (RED → GREEN)

**Files:**
- Modify: `butler/gateway/commands/permission_commands.py` (新增 _cmd_revoke_always + _cmd_clear_always handler)
- Modify: `butler/gateway/commands/permission_commands.py` (`_defaults` 列表加 2 个 CommandDef)
- Test: `tests/test_sprint24_p1_3_2_approval_diagnostics.py:260-360` (新增)

### Step 1: RED — 写测试

```python
class TestRegistryCommands:
    def test_revoke_always_command_dispatch(self, tmp_path, monkeypatch):
        """/撤销批准 命令通过 registry dispatch 调用 revoke_always."""
        from butler.gateway.command_registry import lookup
        cmd = lookup("/撤销批准")
        assert cmd is not None
        assert cmd.handler is not None
        assert cmd.category == "权限安全"

    def test_clear_always_command_dispatch(self):
        """/清除始终允许 命令存在."""
        from butler.gateway.command_registry import lookup
        cmd = lookup("/清除始终允许")
        assert cmd is not None
        assert cmd.handler is not None

    def test_revoke_always_handler_calls_revoke(self, tmp_path, monkeypatch):
        """handler 解析 arg 调 revoke_always."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.command_registry import CommandContext
        from butler.gateway.commands.permission_commands import _cmd_revoke_always
        from butler.permissions.approvals import grant_always, list_always
        grant_always("s1", permission="write_file", tool="*", pattern="*.env")
        ctx = CommandContext(
            cmd="/撤销批准", arg="write_file",
            session_key="s1", platform="wx",
            external_id="u1", orchestrator=None, session_registry=None,
        )
        msg = _cmd_revoke_always(ctx)
        assert "已撤销" in msg
        assert len(list_always("s1")) == 0

    def test_clear_always_handler_clears_all(self, tmp_path, monkeypatch):
        """handler 调 clear_always."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.command_registry import CommandContext
        from butler.gateway.commands.permission_commands import _cmd_clear_always
        from butler.permissions.approvals import grant_always, list_always
        grant_always("s1", permission="p1")
        grant_always("s1", permission="p2")
        ctx = CommandContext(
            cmd="/清除始终允许", arg="",
            session_key="s1", platform="wx",
            external_id="u1", orchestrator=None, session_registry=None,
        )
        msg = _cmd_clear_always(ctx)
        assert "已清除 2 项" in msg
        assert list_always("s1") == []


class TestWorkflowNotBypassed:
    def test_workflow_approval_uses_separate_storage(self, tmp_path, monkeypatch):
        """workflow 步骤审批与 tool approval cache 互不干扰.

        human_gate.is_step_approved 走 _approved_set (set in memory),
        approvals.is_approved 走 approvals.json — 两套独立.
        """
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.human_gate import is_step_approved, mark_step_approved
        from butler.permissions.approvals import (
            ApprovalRequest, grant_always, is_approved,
        )

        # 工具批准 (写文件)
        req = ApprovalRequest(permission="write_file", tool="write_file", pattern="*")
        grant_always("s1", permission="write_file", tool="*", pattern="*")
        assert is_approved("s1", req) is True
        # 工具批准不影响 workflow 步骤
        assert is_step_approved("s1", "wf1", "step1") is False
        # workflow 标记也不影响工具
        mark_step_approved("s1", "wf1", "step1")
        assert is_step_approved("s1", "wf1", "step1") is True
        assert is_approved("s1", req) is True  # 工具仍命中
```

### Step 2: RED 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestRegistryCommands tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestWorkflowNotBypassed -v
```

Expected: 5 FAIL

### Step 3: GREEN — 在 permission_commands.py 加 handler

修改 `butler/gateway/commands/permission_commands.py` — 在 `_cmd_approve_pattern` 之后插入:

```python
def _cmd_revoke_always(ctx: "CommandContext") -> "Optional[str]":
    """Sprint 24 P1-3.2: /撤销批准 <permission> [tool] [pattern]."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    arg = (ctx.arg or "").strip()
    if not arg:
        return "用法: /撤销批准 <permission> [tool] [pattern]"
    parts = arg.split()
    perm = parts[0] if len(parts) >= 1 else ""
    tool = parts[1] if len(parts) >= 2 else ""
    pat = parts[2] if len(parts) >= 3 else ""
    from butler.permissions.approvals import revoke_always
    return revoke_always(ctx.session_key, permission=perm, tool=tool, pattern=pat)


def _cmd_clear_always(ctx: "CommandContext") -> "Optional[str]":
    """Sprint 24 P1-3.2: /清除始终允许 — 清空 session 所有 always 记录."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    from butler.permissions.approvals import clear_always
    return clear_always(ctx.session_key)
```

在 `_defaults` 列表中 (在 `/批准模式` 之后) 加 2 项:

```python
CommandDef("/撤销批准", (), "权限安全", "撤销已设置的始终允许规则", handler=_cmd_revoke_always),
CommandDef("/清除始终允许", (), "权限安全", "清空当前会话所有始终允许", handler=_cmd_clear_always),
```

### Step 4: GREEN 验证

```bash
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestRegistryCommands tests/test_sprint24_p1_3_2_approval_diagnostics.py::TestWorkflowNotBypassed -v
```

Expected: 5 PASS

### Step 5: 验证 owner gate scan 无新 gap

```bash
pytest tests/test_sprint12_owner_gate_scan.py -v
```

Expected: gap 数仍 9 (2 个新 handler 都有 owner gate, 无新增)

### Step 6: Commit

```bash
git add butler/gateway/commands/permission_commands.py tests/test_sprint24_p1_3_2_approval_diagnostics.py
git commit -m "feat(commands): /撤销批准 + /清除始终允许 注册到 permission_commands"
```

---

## Task 5: 全套验证 + 文档 + 最终 commit

**Files:**
- Modify: `docs/reviews/project-deep-audit-2026-06-sprint11.md` (在 §6 加 §3.2 完成 entry)
- Modify: `docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md` (§3.2 标 [x] + Sprint 24 完成说明)

### Step 1: 全套测试无回归

```bash
pytest tests/ -x -q 2>&1 | tail -30
```

Expected: 全部 PASS (pre-existing 99 失败基线不变, 0 新增)

### Step 2: audit doc §6 加 entry

在 `docs/reviews/project-deep-audit-2026-06-sprint11.md` 中 (在 §3.1 标记后, 找合适位置) 加:

```markdown
| **§3.2** (P1-3.2) | Sprint 24 补齐 approval diagnostics + revoke + /诊断集成 | 4 commits | (1) `is_approved` 加 diagnostics kw-only 形参, 命中写 `approval_cache_hit` + `approval_cache_source` (once/always); (2) `revoke_always` 按 permission/tool/pattern 过滤撤销 (全空过滤返错误防误删), `clear_always` 清空所有; (3) `summarize_approvals(session_key)` 给 /诊断读 approvals.json 统计 (always_count / once_active_count / has_pending); (4) `health_report.py` `_shared_diagnostic_lines` 加 "权限批准缓存" 块; (5) `/撤销批准 <perm> [tool] [pat]` 与 `/清除始终允许` 注册到 permission_commands (owner gate + dispatcher); (6) workflow 不可穿透测试: `is_step_approved` (human_gate.py:184) 与 `is_approved` (approvals.py:212) API 独立 + 存储路径分离, 互不影响. 17 个新测试覆盖 diagnostics 4 + revoke 5 + summarize 2 + health 1 + registry 4 + workflow 1. owner_gate_scan gap 数仍 9 (2 新 handler 都有 owner gate). |
```

### Step 3: opencode checklist §3.2 标完成

修改 `docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md:61-76`:

```markdown
### 3.2 会话批准缓存（一次 / 始终）

- [x] **目标**：把当前偏静态的 `ask` 权限升级为运行时批准缓存，支持「允许一次 / 始终允许 / 拒绝」
- [x] **收益**：减少 Owner 对同类安全工具调用的重复确认；贴近 OpenCode 的交互权限体验
- [x] **主要改动面**：
  - `butler/permissions/approvals.py`
  - `butler/permissions/rules.py`
  - `butler/permissions/doom_loop.py`
  - `butler/mcp/approval.py`
  - `butler/ops/health_report.py`
  - `butler/gateway/commands/permission_commands.py`
- [x] **验收标准**：
  - [x] 同一会话内，批准过的同类安全 pattern 不再重复 ask
  - [x] 「始终允许」有清晰作用域：只限 session / project，不得默认全局放开
  - [x] `/诊断` 或权限日志能显示本次调用命中了缓存批准
- [x] **风险提示**：
  - 必须保留 revoke/失效机制 ✅ `revoke_always` / `clear_always` (Sprint 24)
  - workflow 的人工审批语义不能被工具批准缓存偷穿透 ✅ `is_step_approved` (human_gate) 与 `is_approved` (approvals) API 独立 (Sprint 24 测试验证)

> **Sprint 24 (2026-06-04) 完成**: §3.2 P1 全部验收 + 风险点收口. 4 commits (1+1+1+1). 17 新测试覆盖 diagnostics / revoke / summarize / /诊断集成 / registry / workflow 边界. owner_gate_scan gap 数稳定 9.
```

### Step 4: Commit 文档

```bash
git add docs/reviews/project-deep-audit-2026-06-sprint11.md docs/plans/active/opencode-actionable-optimization-checklist-2026-05.md
git commit -m "docs: §3.2 Sprint 24 标完成 (audit + opencode checklist)"
```

### Step 5: 最终验证

```bash
git log --oneline -8
pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py -v 2>&1 | tail -25
pytest tests/test_sprint12_owner_gate_scan.py tests/test_command_registry.py tests/test_permission_approvals.py -v 2>&1 | tail -10
```

Expected:
- 4 feat commits + 1 docs commit = 5 new commits
- 17/17 P1-3.2 测试 PASS
- 相关测试无回归

---

## Risk & Mitigation

| 风险 | 缓解 |
|------|------|
| `is_approved` 加 kw-only 形参破坏 3 个调用点 | kw-only + 默认 None, 向后兼容; Step 5 验证 |
| `revoke_always` 全空过滤误删所有 | 显式返错误 "请指定 ... 至少一项"; 测试覆盖 |
| `summarize_approvals` I/O 失败影响 /诊断 | try/except + logger.debug, 失败返 0 计数; 已有模式 (`collect_mem_stats_for_health`) |
| 2 个新 handler 加 owner gate 后, owner_gate_scan gap 增大 | `_cmd_revoke_always` / `_cmd_clear_always` 都先 `require_owner(ctx)`; Step 5 验证 gap 数 |
| `_shared_diagnostic_lines` 改动影响 /诊断 既有格式 | approval 块用 "权限批准缓存:" 标题, 缩进 2 空格, 与既有 format_xxx_lines 输出对齐 |
| `lookup("/撤销批准")` 旧代码引用可能 missed | 检索旧 inline 路径 (但 /撤销批准 是新命令, 不存在旧引用) |
| workflow 测试依赖 human_gate 的 _load_approved set (in-memory) | 每次 test 用独立 session_key, 无状态污染 |

## 验证清单

- [ ] `pytest tests/test_sprint24_p1_3_2_approval_diagnostics.py -v` 17/17 PASS
- [ ] `pytest tests/test_sprint12_owner_gate_scan.py` gap 数仍 9
- [ ] `pytest tests/test_permission_approvals.py tests/test_sprint8_sec2_approvals.py tests/test_p2_workflow_permissions.py` 无回归
- [ ] `pytest tests/test_sprint11_tst1_approval_alive.py` 通过
- [ ] `pytest tests/test_command_registry.py` 通过 (新增 2 个 CommandDef)
- [ ] `pytest tests/test_sprint16_tst10_5_prequeue_commands_migration.py` 通过 (前 batch 仍 PASS)
- [ ] `grep -rn "lookup.*撤销批准\|lookup.*清除始终允许" butler/ tests/` = 2+ hits (registry 引用)
- [ ] `grep -rn "approval_cache_hit\|approval_cache_source" butler/` ≥ 3 hits (function def + write sites)
- [ ] audit doc §6 加 §3.2 entry
- [ ] opencode checklist §3.2 标 [x] + 完成说明
- [ ] 5 个 commit (4 feat + 1 docs)
- [ ] `git log --oneline -6` 序列可读
