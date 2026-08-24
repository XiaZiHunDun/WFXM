"""v5 Claude Code Stop: state.md soft reminder script tests."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "claude_session_end_v5.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("claude_session_end_v5", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load claude_session_end_v5.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def tmp_bb(tmp_path, monkeypatch):
    bb = tmp_path / ".blackboard"
    bb.mkdir()
    monkeypatch.setenv("BLACKBOARD_ROOT", str(bb))
    return bb


def _write_valid_state(bb: Path) -> None:
    (bb / "state.md").write_text(
        "# WFXM BlackBoard State\n\n"
        "_last_synced: 2026-08-24 12:00_\n"
        "_handoff: docs/plans/decisions/v5-engineering-handoff-2026-08.md_\n"
        "_commit: abc_\n\n"
        "## 主线\n\nx\n\n"
        "## 下一步\n\nx\n\n"
        "## 不要做\n\nx\n\n"
        "## 上一班\n\nx\n",
        encoding="utf-8",
    )


def test_check_state_snapshot_ok(tmp_bb):
    mod = _load_script_module()
    _write_valid_state(tmp_bb)
    assert mod.check_state_snapshot(root=tmp_bb) is None


def test_check_state_snapshot_missing_section(tmp_bb):
    mod = _load_script_module()
    (tmp_bb / "state.md").write_text(
        "# WFXM\n\n_last_synced: 2026-08-24 12:00_\n\n## 主线\n\nx\n",
        encoding="utf-8",
    )
    msg = mod.check_state_snapshot(root=tmp_bb)
    assert msg is not None
    assert "## 下一步" in msg


def test_main_soft_warns_but_exits_zero(tmp_bb):
    (tmp_bb / "state.md").write_text("# WFXM\n\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env={**os.environ, "BLACKBOARD_ROOT": str(tmp_bb), "BLACKBOARD_STRICT": "0"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "⚠" in proc.stderr


def test_main_valid_state_ok(tmp_bb):
    _write_valid_state(tmp_bb)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        env={**os.environ, "BLACKBOARD_ROOT": str(tmp_bb), "BLACKBOARD_STRICT": "0"},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "state.md 快照就绪" in proc.stderr
