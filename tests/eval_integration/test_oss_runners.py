"""OSS eval runner and sync policy tests."""

from __future__ import annotations

import json
from unittest.mock import patch

from butler.eval_integration.oss.deepeval_runner import run_deterministic
from butler.eval_integration.oss.ragas_runner import heuristic_faithfulness, run_heuristic
from butler.eval_integration.sync_policy import evaluate_sync


def test_heuristic_faithfulness_overlap():
    ctx = "项目根目录为 /home/ailearn/projects/WFXM"
    ans = "根目录是 /home/ailearn/projects/WFXM"
    score = heuristic_faithfulness(ctx, ans)
    assert score > 0.3


def test_run_heuristic_passes_fixtures():
    ok, metrics = run_heuristic()
    assert ok
    assert metrics["mode"] in ("heuristic", "audit")
    assert metrics["cases_passed"] == metrics["cases_total"]


def test_load_prefetch_audit_cases_from_transcript(tmp_path, monkeypatch):
    from butler.eval_integration.oss.prefetch_audit_loader import load_prefetch_audit_cases

    sessions = tmp_path / "sessions" / "sess1"
    sessions.mkdir(parents=True)
    rows = [
        {"type": "user", "content_preview": "项目 Loop 在哪？"},
        {
            "type": "knowledge_inject",
            "source": "memory_prefetch",
            "chars": 120,
            "terms": ["butler/core/agent_loop.py"],
        },
        {"type": "assistant", "content_preview": "Loop 在 butler/core/agent_loop.py"},
    ]
    (sessions / "transcript.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "butler.eval_integration.oss.prefetch_audit_loader.get_butler_home",
        lambda: tmp_path,
    )
    cases = load_prefetch_audit_cases(limit_sessions=5)
    assert len(cases) == 1
    assert cases[0]["source"] == "transcript_audit"
    assert "agent_loop" in cases[0]["context"]


@patch("butler.eval_integration.oss.deepeval_runner.deepeval_available", return_value=True)
def test_deepeval_deterministic_passes(_mock_avail):
    ok, metrics = run_deterministic()
    assert ok
    assert metrics["mode"] == "deterministic"
    assert metrics["pass_rate"] == 1.0


def test_sync_check_missing_audit():
    out = evaluate_sync(
        "tcr",
        {"audit": None, "junit": {"ok": True}, "langfuse": None},
    )
    assert out["ok"] is False
    assert any("audit" in w for w in out["warnings"])


def test_sync_check_ok_mismatch():
    out = evaluate_sync(
        "tcr",
        {
            "audit": {"ok": True, "ts": 1.0},
            "junit": {"ok": False},
        },
    )
    assert out["ok"] is False
    assert any("mismatch" in w for w in out["warnings"])


def test_sync_check_all_present():
    out = evaluate_sync(
        "tcr",
        {
            "audit": {"ok": True, "ts": 1.0},
            "junit": {"ok": True},
        },
    )
    assert out["ok"] is True
    assert out["warnings"] == []
