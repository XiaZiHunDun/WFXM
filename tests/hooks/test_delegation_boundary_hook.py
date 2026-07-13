"""P1 #4 — delegation boundary hook 单测。

不动真实 YAML、不写真实 audit log；monkeypatch 注入 env 和 stdin。
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_hook(monkeypatch: pytest.MonkeyPatch, payload: dict, env_role: str | None) -> int:
    """调用 hook 的 _run_for_test 入口（Task 3 实现）。"""
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    if env_role is None:
        monkeypatch.delenv("BUTLER_AGENT_ROLE", raising=False)
    else:
        monkeypatch.setenv("BUTLER_AGENT_ROLE", env_role)
    monkeypatch.setenv("BUTLER_ACTIVE_PROJECT", "LingWen1")
    from butler.hooks.delegation_boundary_hook import _run_for_test
    return _run_for_test()


def test_content_can_write_docs(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "projects/灵文1号/docs/notes.md"}}, "content") == 0


def test_content_denied_src(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "src/butler/foo.py"}}, "content") == 2


def test_content_denied_butler_core(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "butler/hooks/x.py"}}, "content") == 2


def test_dev_can_write_src(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "src/butler/x.py"}}, "dev") == 0


def test_dev_can_write_tests(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "tests/hooks/test_x.py"}}, "dev") == 0


def test_dev_denied_docs(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Edit", "tool_input": {"file_path": "projects/灵文1号/docs/x.md"}}, "dev") == 2


def test_dev_denied_archive_docs(monkeypatch):
    assert _run_hook(monkeypatch, {"tool_name": "Edit", "tool_input": {"file_path": "projects/灵文1号/docs/archive/x.md"}}, "dev") == 2


def test_no_role_passthrough(monkeypatch):
    """Lead 本体：role 缺失 → 静默放行（兼容主公）。"""
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "projects/灵文1号/docs/x.md"}}, None) == 0


def test_unknown_role_passthrough(monkeypatch):
    """role 既不是 content 也不是 dev（如 'qa'）→ 静默放行。"""
    assert _run_hook(monkeypatch, {"tool_name": "Write", "tool_input": {"file_path": "src/x.py"}}, "qa") == 0


def test_no_delegation_section_fails_open(monkeypatch, tmp_path, capsys):
    """新项目无 delegation: 段 → fail-open + stderr warn。"""
    from butler.hooks import delegation_boundary_hook as h

    fake_repo = tmp_path
    (fake_repo / "projects" / "新项目" / "config").mkdir(parents=True)
    (fake_repo / "projects" / "新项目" / "config" / "permissions.yaml").write_text(
        "# 无 delegation 段\nrules: []\n", encoding="utf-8"
    )

    monkeypatch.setattr(h, "REPO_ROOT", fake_repo)
    monkeypatch.setenv("BUTLER_AGENT_ROLE", "content")
    monkeypatch.setenv("BUTLER_ACTIVE_PROJECT", "新项目")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Write", "tool_input": {"file_path": "src/x.py"}})))
    from butler.hooks.delegation_boundary_hook import _run_for_test

    rc = _run_for_test()
    captured = capsys.readouterr()
    assert rc == 0
    assert "WARN" in captured.err
    assert "无 delegation 段" in captured.err