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
    monkeypatch.setenv("BUTLER_ACTIVE_PROJECT", "灵文1号")
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