"""Tests for B9 delegate pytest gate and workspace pre-read."""

from __future__ import annotations

from types import SimpleNamespace

from butler.core.read_state import get_read_state, reset_read_state
from butler.dev_engine.b9_delegate_gate import (
    apply_b9_pytest_success_gate,
    apply_coding_strict_pilot_gate,
    apply_dev_auto_verify_success_gate,
    build_b9_workspace_preamble,
    format_oracle_replay_block,
    is_b9_benchmark_category,
    prepare_b9_subagent_workspace,
    seed_b9_workspace_read_state,
)
from butler.dev_engine.b9_live_tuning import B9_LIVE_CATEGORY
from butler.tools.delegate_impl import finalize_delegate_success


class _FakeStatus:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeResult:
    def __init__(self, status: str = "completed") -> None:
        self.status = _FakeStatus(status)


def test_is_b9_benchmark_category():
    assert is_b9_benchmark_category(B9_LIVE_CATEGORY)
    assert not is_b9_benchmark_category("deep")


def test_pytest_gate_blocks_when_red(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    (tmp_path / "broken.py").write_text("def f():\n    return 0\n", encoding="utf-8")
    (tmp_path / "test_b9.py").write_text(
        "from broken import f\n\ndef test_f():\n    assert f() == 1\n",
        encoding="utf-8",
    )
    project = SimpleNamespace(workspace=tmp_path)
    ok, issues = apply_b9_pytest_success_gate(
        category=B9_LIVE_CATEGORY,
        project=project,
        base_success=True,
        issues=[],
    )
    assert ok is False
    assert any("BENCHMARK_PYTEST_GATE" in i for i in issues)


def test_pytest_gate_passes_when_green(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    (tmp_path / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_b9.py").write_text(
        "from ok import ok\n\ndef test_ok():\n    assert ok() == 1\n",
        encoding="utf-8",
    )
    project = SimpleNamespace(workspace=tmp_path)
    ok, issues = apply_b9_pytest_success_gate(
        category=B9_LIVE_CATEGORY,
        project=project,
        base_success=True,
        issues=[],
    )
    assert ok is True
    assert issues == []


def test_finalize_delegate_success_applies_b9_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    (tmp_path / "test_b9.py").write_text(
        "def test_fail():\n    assert False\n",
        encoding="utf-8",
    )
    project = SimpleNamespace(workspace=tmp_path)
    success, issues = finalize_delegate_success(
        _FakeResult(),
        changes=[SimpleNamespace()],
        issues=[],
        category=B9_LIVE_CATEGORY,
        project=project,
    )
    assert success is False
    assert issues


    assert any("BENCHMARK_PYTEST_GATE" in i for i in issues)


def test_dev_verify_gate_blocks_edits_without_green():
    ok, issues = apply_dev_auto_verify_success_gate(
        role="dev",
        base_success=True,
        issues=[],
        dev_engine={"edits": 2, "verify_passed": False},
    )
    assert ok is False
    assert any("DEV_VERIFY_GATE" in i for i in issues)


def test_dev_verify_gate_allows_read_only():
    ok, issues = apply_dev_auto_verify_success_gate(
        role="dev",
        base_success=True,
        issues=[],
        dev_engine={"edits": 0, "verify_passed": False},
    )
    assert ok is True
    assert issues == []


def test_finalize_dev_verify_gate(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_DEV_VERIFY_SUCCESS_GATE", "1")
    monkeypatch.setenv("BUTLER_DEV_AUTO_VERIFY", "1")
    success, issues = finalize_delegate_success(
        _FakeResult(),
        changes=[SimpleNamespace()],
        issues=[],
        category="deep",
        role="dev",
        dev_engine={"edits": 1, "verify_passed": False},
    )
    assert success is False
    assert any("DEV_VERIFY_GATE" in i for i in issues)


def test_coding_strict_pilot_blocks_violations(monkeypatch):
    monkeypatch.setenv("BUTLER_CODING_STRICT", "1")
    ok, issues = apply_coding_strict_pilot_gate(
        role="dev",
        category="deep",
        base_success=True,
        issues=[],
        dev_engine={
            "coding_knowledge": {"violated": ["T04"]},
            "verify_passed": True,
            "edits": 1,
        },
    )
    assert ok is False
    assert any("CODING_STRICT_GATE" in i for i in issues)


def test_coding_strict_pilot_skips_non_pilot_category(monkeypatch):
    monkeypatch.setenv("BUTLER_CODING_STRICT", "1")
    ok, issues = apply_coding_strict_pilot_gate(
        role="dev",
        category="b9-benchmark",
        base_success=True,
        issues=[],
        dev_engine={"coding_knowledge": {"violated": ["T04"]}},
    )
    assert ok is True
    assert issues == []


def test_seed_b9_workspace_read_state(tmp_path):
    reset_read_state("_gate_test")
    (tmp_path / "test_b9.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("# empty\n", encoding="utf-8")
    n = seed_b9_workspace_read_state(tmp_path, session_key="_gate_test")
    assert n == 2
    assert get_read_state(tmp_path / "service.py", session_key="_gate_test") is not None


def test_workspace_preamble_includes_files(tmp_path):
    (tmp_path / "test_b9.py").write_text("assert True\n", encoding="utf-8")
    (tmp_path / "service.py").write_text("x = 1\n", encoding="utf-8")
    block = build_b9_workspace_preamble(tmp_path)
    assert "benchmark-workspace-files" in block
    assert "test_b9.py" in block
    assert "service.py" in block


def test_prepare_b9_subagent_workspace(tmp_path):
    reset_read_state("_prep")
    (tmp_path / "test_b9.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    preamble = prepare_b9_subagent_workspace(tmp_path, session_key="_prep")
    assert "benchmark-workspace-files" in preamble
    assert get_read_state(tmp_path / "test_b9.py", session_key="_prep") is not None


def test_oracle_replay_test_driven_add():
    block = format_oracle_replay_block("B9L_test_driven_add")
    assert "ORACLE REPLAY" in block
    assert "service.py" in block
    assert "ping" in block


def test_swe_verify_hook_gate(tmp_path, monkeypatch):
    from butler.dev_engine.b9_delegate_gate import (
        SWE_LIVE_CATEGORY,
        benchmark_verify_context,
    )

    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))

    def _verify(ws: Path) -> tuple[bool, str]:
        return False, "swe tests failed"

    with benchmark_verify_context(_verify):
        ok, issues = apply_b9_pytest_success_gate(
            category=SWE_LIVE_CATEGORY,
            project=__import__("types").SimpleNamespace(workspace=tmp_path),
            base_success=True,
            issues=[],
        )
    assert ok is False
    assert any("BENCHMARK_PYTEST_GATE" in i for i in issues)
